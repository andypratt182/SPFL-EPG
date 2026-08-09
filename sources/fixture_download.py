"""
sources/fixture_download.py

Primary fixture source adapter for SPFL-EPG.

Source:
    Fixture Download

Raw JSON endpoint:
    https://fixturedownload.com/feed/json/{season}/{team}

The adapter:
    1. Downloads Fixture Download JSON
    2. Normalises the fixture data
    3. Includes the venue/stadium
    4. Removes duplicate fixtures
    5. Saves the complete fixture set through data_layer.py

This file can be run directly from GitHub Actions:

    python sources/fixture_download.py
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# ============================================================
# Make the repository root importable
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from data_layer import save_fixtures
from teams import SPFL_TEAMS


# ============================================================
# Configuration
# ============================================================

BASE_URL = "https://fixturedownload.com/feed/json"

COMPETITIONS = {
    "Scottish Premiership": "scottish-premiership-2026",
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

RETRY_DELAY_SECONDS = 2


# ============================================================
# Team slug handling
# ============================================================

TEAM_SLUGS = {
    "Aberdeen": "aberdeen",
    "Celtic": "celtic",
    "Dundee": "dundee",
    "Dundee United": "dundee-united",
    "Falkirk": "falkirk",
    "Heart of Midlothian": "heart-of-midlothian",
    "Hibernian": "hibernian",
    "Kilmarnock": "kilmarnock",
    "Motherwell": "motherwell",
    "Rangers": "rangers",
    "St. Johnstone": "st-johnstone",
    "St. Mirren": "st-mirren",
}


# ============================================================
# HTTP session
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(compatible; SPFL-EPG/1.0)"
        )
    }
)


# ============================================================
# Helpers
# ============================================================

def get_team_slug(team_name):
    """
    Convert the configured team name into the Fixture Download slug.
    """

    if team_name.endswith(" TV"):
        team_name = team_name[:-3].strip()

    slug = TEAM_SLUGS.get(team_name)

    if slug:
        return slug

    raise ValueError(
        f"No Fixture Download slug configured for: {team_name}"
    )


def parse_date_utc(value):
    """
    Convert Fixture Download DateUtc into a standard ISO timestamp.

    Example input:
        2026-08-09 15:00:00Z

    Example output:
        2026-08-09T15:00:00+00:00
    """

    if not value:
        return None

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%SZ",
        )

        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

        return parsed.isoformat()

    except ValueError:
        return None


def request_json(url):
    """
    Download JSON with retry handling.
    """

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        print(
            f"    Request attempt "
            f"{attempt}/{MAX_RETRIES}"
        )

        try:

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )

            print(
                f"    HTTP status: "
                f"{response.status_code}"
            )

            response.raise_for_status()

            try:

                data = response.json()

            except ValueError:

                print(
                    "    ERROR: Response was "
                    "not valid JSON."
                )

                print(
                    "    Content-Type: "
                    f"{response.headers.get('Content-Type')}"
                )

                print(
                    "    Response preview:"
                )

                print(
                    response.text[:1000]
                )

                data = None

            if data is not None:

                return data

        except requests.RequestException as error:

            print(
                f"    Request failed: {error}"
            )

        if attempt < MAX_RETRIES:

            delay = (
                RETRY_DELAY_SECONDS
                * attempt
            )

            print(
                f"    Retrying in {delay}s..."
            )

            time.sleep(delay)

    return None


def normalise_fixture(
    fixture,
    competition,
):
    """
    Convert a Fixture Download fixture into the common
    SPFL-EPG fixture format.
    """

    home = str(
        fixture.get(
            "HomeTeam",
            ""
        )
    ).strip()

    away = str(
        fixture.get(
            "AwayTeam",
            ""
        )
    ).strip()

    kickoff = parse_date_utc(
        fixture.get("DateUtc")
    )

    stadium = str(
        fixture.get(
            "Location",
            ""
        )
    ).strip()

    if not home:
        return None

    if not away:
        return None

    if not kickoff:
        return None

    if not stadium:
        stadium = "Venue TBC"

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "competition": competition,
        "stadium": stadium,
    }


def fixture_key(fixture):
    """
    Generate a unique key for a fixture.

    This prevents the same match being stored multiple times
    when both clubs are downloaded.
    """

    return (
        fixture["home"].lower().strip(),
        fixture["away"].lower().strip(),
        fixture["kickoff"],
        fixture["competition"].lower().strip(),
    )


# ============================================================
# Download fixtures for one team
# ============================================================

def fetch_team_fixtures(
    team_name,
    competition,
    season,
):
    """
    Download all fixtures for one team and competition.
    """

    slug = get_team_slug(
        team_name
    )

    url = (
        f"{BASE_URL}/"
        f"{season}/"
        f"{slug}"
    )

    print(team_name)

    print(
        f"URL: {url}"
    )

    data = request_json(
        url
    )

    if data is None:

        print(
            "    No JSON data returned."
        )

        return []

    if not isinstance(
        data,
        list,
    ):

        print(
            "    ERROR: JSON response "
            "was not a fixture list."
        )

        return []

    print(
        f"    JSON fixtures returned: "
        f"{len(data)}"
    )

    fixtures = []

    for item in data:

        fixture = normalise_fixture(
            item,
            competition,
        )

        if fixture is None:
            continue

        fixtures.append(
            fixture
        )

    return fixtures


# ============================================================
# Main adapter
# ============================================================

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

    print(
        f"Teams configured: "
        f"{len(SPFL_TEAMS)}"
    )

    all_fixtures = []

    # --------------------------------------------------------
    # Download each configured competition
    # --------------------------------------------------------

    for competition, season in COMPETITIONS.items():

        print(
            "--------------------------------"
        )

        print(
            f"Competition: {competition}"
        )

        print(
            f"Season: {season}"
        )

        print(
            "--------------------------------"
        )

        for channel_id, team in SPFL_TEAMS.items():

            team_name = team["name"]

            if team_name.endswith(" TV"):

                team_name = (
                    team_name[:-3]
                    .strip()
                )

            try:

                fixtures = fetch_team_fixtures(
                    team_name,
                    competition,
                    season,
                )

                for fixture in fixtures:

                    fixture["channel_id"] = (
                        channel_id
                    )

                    all_fixtures.append(
                        fixture
                    )

            except Exception as error:

                print(
                    f"    ERROR loading "
                    f"{
