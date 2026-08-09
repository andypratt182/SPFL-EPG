"""
sources/fixture_download.py

Fixture Download source adapter.

This module retrieves football fixtures from Fixture Download
and converts them into the source-independent format expected
by data_layer.py.

Pipeline:

    Fixture Download
          ↓
    fixture_download.py
          ↓
    data_layer.py
          ↓
    data/fixtures.json
          ↓
    fixtures.py
          ↓
    generator.py
          ↓
    XMLTV EPG
"""

import sys
import time
from pathlib import Path

import requests


# ----------------------------------------------------------------------
# Make the repository root available to Python
# ----------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data_layer import save_fixtures
from teams import SPFL_TEAMS


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

BASE_URL = "https://fixturedownload.com"

REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


# ----------------------------------------------------------------------
# Fixture Download competition mappings
# ----------------------------------------------------------------------

# Fixture Download uses competition names in its URLs.
#
# These are kept here rather than in fixtures.py so the rest of the
# EPG remains completely independent of the external source.

COMPETITIONS = {
    "Scottish Premiership": [
        "scottish-premiership",
    ],
    "Scottish Cup": [
        "scottish-cup",
    ],
    "Scottish League Cup": [
        "scottish-league-cup",
    ],
}


# ----------------------------------------------------------------------
# HTTP session
# ----------------------------------------------------------------------

session = requests.Session()
session.headers.update(HEADERS)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def normalise_team_name(name):
    """
    Normalise a team name for comparison.
    """

    if not name:
        return ""

    name = str(name).lower().strip()

    replacements = {
        "football club": "",
        " fc": "",
        "f.c.": "",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    return " ".join(name.split())


def get_team_name(team):
    """
    Return the team name from the SPFL_TEAMS structure.

    Supports the current dictionary structure while keeping the
    adapter tolerant of small future changes.
    """

    if isinstance(team, dict):
        return team.get("name", "")

    return str(team)


def fetch_url(url):
    """
    Fetch a Fixture Download URL.

    Returns the response object or None on failure.
    """

    for attempt in range(1, 4):

        try:

            print(
                f"    Request attempt "
                f"{attempt}/3"
            )

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )

            print(
                f"    HTTP status: "
                f"{response.status_code}"
            )

            if response.ok:
                return response

            print(
                f"    Request failed: "
                f"HTTP {response.status_code}"
            )

        except requests.RequestException as exc:

            print(
                f"    Request error: {exc}"
            )

        if attempt < 3:

            delay = attempt * 2

            print(
                f"    Retrying in {delay}s..."
            )

            time.sleep(delay)

    return None


def extract_json_from_response(response):
    """
    Attempt to extract JSON from a Fixture Download response.

    Fixture Download may return JSON directly. If the response is
    not JSON, this function reports that clearly rather than
    allowing the adapter to silently produce bad fixture data.
    """

    try:
        return response.json()

    except ValueError:

        print(
            "    Response was not valid JSON."
        )

        preview = response.text[:500].replace(
            "\n",
            " ",
        )

        print(
            f"    Response preview: {preview}"
        )

        return None


def parse_fixture(item, competition):
    """
    Convert one Fixture Download record into the common fixture
    structure used by the data layer.

    Returns None if the record cannot be converted.
    """

    if not isinstance(item, dict):
        return None

    # Fixture Download has used several field naming conventions
    # over time. Try the common possibilities.

    home = (
        item.get("HomeTeam")
        or item.get("homeTeam")
        or item.get("home")
        or item.get("Home")
    )

    away = (
        item.get("AwayTeam")
        or item.get("awayTeam")
        or item.get("away")
        or item.get("Away")
    )

    kickoff = (
        item.get("DateUtc")
        or item.get("dateUtc")
        or item.get("Kickoff")
        or item.get("kickoff")
        or item.get("Date")
        or item.get("date")
    )

    if not home or not away or not kickoff:
        return None

    return {
        "home": str(home).strip(),
        "away": str(away).strip(),
        "kickoff": str(kickoff).strip(),
        "competition": competition,
    }


def extract_fixture_list(data):
    """
    Extract the fixture list from the returned JSON.

    Supports either:

        [...]
    
    or common wrapper structures such as:

        {"fixtures": [...]}

        {"data": [...]}
    """

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "fixtures",
        "Fixtures",
        "data",
        "Data",
        "matches",
        "Matches",
    ):

        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


# ----------------------------------------------------------------------
# Main adapter
# ----------------------------------------------------------------------

def main():

    print(
        "=============================="
    )

    print(
        "FIXTURE DOWNLOAD SOURCE ADAPTER"
    )

    print(
        "=============================="
    )

    fixtures = []

    seen = set()

    # --------------------------------------------------------------
    # Determine which teams we need
    # --------------------------------------------------------------

    teams = []

    for channel_id, team in SPFL_TEAMS.items():

        team_name = get_team_name(team)

        if not team_name:
            continue

        teams.append(
            (
                channel_id,
                team_name,
            )
        )

    print(
        f"Teams configured: {len(teams)}"
    )

    print()

    # --------------------------------------------------------------
    # Download competitions
    # --------------------------------------------------------------

    for competition_name, competition_slugs in COMPETITIONS.items():

        for slug in competition_slugs:

            url = (
                f"{BASE_URL}/"
                f"sport/football"
            )

            print(
                "--------------------------------"
            )

            print(
                f"Competition: "
                f"{competition_name}"
            )

            print(
                f"URL: {url}"
            )

            print(
                "--------------------------------"
            )

            response = fetch_url(url)

            if response is None:

                print(
                    "    Unable to access "
                    "Fixture Download."
                )

                continue

            # ------------------------------------------------------
            # At this point Fixture Download may return a page rather
            # than an API response. We inspect the response rather
            # than guessing at its structure.
            # ------------------------------------------------------

            data = extract_json_from_response(
                response
            )

            if data is None:

                print(
                    "    No JSON data extracted."
                )

                continue

            records = extract_fixture_list(
                data
            )

            print(
                f"    Records returned: "
                f"{len(records)}"
            )

            # ------------------------------------------------------
            # Convert records
            # ------------------------------------------------------

            for item in records:

                fixture = parse_fixture(
                    item,
                    competition_name,
                )

                if fixture is None:
                    continue

                key = (
                    normalise_team_name(
                        fixture["home"]
                    ),
                    normalise_team_name(
                        fixture["away"]
                    ),
                    fixture["kickoff"],
                    fixture["competition"],
                )

                if key in seen:
                    continue

                seen.add(key)

                fixtures.append(
                    fixture
                )

    # --------------------------------------------------------------
    # Final results
    # --------------------------------------------------------------

    fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    print()
    print(
        "=============================="
    )

    print(
        f"TOTAL FIXTURES: {len(fixtures)}"
    )

    print(
        "=============================="
    )

    for fixture in fixtures:

        print(
            f"{fixture['kickoff']} | "
            f"{fixture['home']} vs "
            f"{fixture['away']} | "
            f"{fixture['competition']}"
        )

    # --------------------------------------------------------------
    # Save normalised data
    # --------------------------------------------------------------

    print()
    print(
        "Saving fixture data..."
    )

    save_fixtures(
        fixtures
    )

    print(
        "Saved to:"
    )

    print(
        "data/fixtures.json"
    )

    print()
    print(
        "Fixture Download adapter "
        "completed."
    )


if __name__ == "__main__":
    main()
