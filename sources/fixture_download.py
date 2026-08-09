"""
sources/fixture_download.py

Fixture Download source adapter.

This module is the only part of the EPG that knows about
Fixture Download.

It converts Fixture Download data into the common fixture
format used by data_layer.py.

The rest of the EPG does not know where the data came from.
"""

import json
from datetime import datetime
from pathlib import Path

import requests

from data_layer import save_fixtures


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

BASE_URL = "https://fixturedownload.com"

REQUEST_TIMEOUT = 30


# Fixture Download competition slugs.

COMPETITIONS = {
    "Scottish Premiership": {
        "slug": "scottish-premiership-2026",
    },

    "Scottish Cup": {
        "slug": "scottish-cup-2026",
    },

    "Scottish League Cup": {
        "slug": "scottish-league-cup-2026",
    },
}


# SPFL teams used by the EPG.
#
# This can be expanded without changing the rest of the system.

TEAMS = [
    "Aberdeen",
    "Celtic",
    "Dundee",
    "Dundee United",
    "Falkirk",
    "Heart of Midlothian",
    "Hibernian",
    "Kilmarnock",
    "Motherwell",
    "Rangers",
    "St. Johnstone",
    "St. Mirren",
]


# -------------------------------------------------------------------
# HTTP
# -------------------------------------------------------------------

def create_session() -> requests.Session:
    """
    Create a browser-style HTTP session.
    """

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/139.0.0.0 "
                "Safari/537.36"
            ),
            "Accept": (
                "application/json,"
                "text/plain,"
                "*/*"
            ),
            "Accept-Language": (
                "en-GB,en;q=0.9"
            ),
            "Referer": (
                "https://fixturedownload.com/"
            ),
        }
    )

    return session


# -------------------------------------------------------------------
# URL construction
# -------------------------------------------------------------------

def build_json_url(
    competition_slug: str,
    team: str | None = None,
) -> str:
    """
    Build a Fixture Download JSON URL.

    The URL format is kept in one place so it can be changed
    easily if Fixture Download changes its routing.
    """

    if team:

        team_slug = (
            team.lower()
            .replace(".", "")
            .replace(" ", "-")
        )

        return (
            f"{BASE_URL}/"
            f"results/"
            f"{competition_slug}/"
            f"{team_slug}"
            f"?format=json"
        )

    return (
        f"{BASE_URL}/"
        f"results/"
        f"{competition_slug}"
        f"?format=json"
    )


# -------------------------------------------------------------------
# Parsing helpers
# -------------------------------------------------------------------

def parse_datetime(value):
    """
    Convert a Fixture Download date/time value into ISO format.

    Returns None if the value cannot be parsed.
    """

    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt,
            )

            return dt.isoformat()

        except ValueError:
            continue

    # Try ISO-8601 as a final option.

    try:

        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        return dt.isoformat()

    except ValueError:

        return None


def get_value(
    fixture: dict,
    *names,
):
    """
    Retrieve a value from a fixture using several possible
    field names.

    This makes the adapter tolerant of small changes in the
    JSON field naming.
    """

    for name in names:

        if name in fixture:
            return fixture[name]

    return None


def parse_fixture(
    fixture: dict,
    competition: str,
) -> dict | None:
    """
    Convert one Fixture Download fixture into our common format.
    """

    home = get_value(
        fixture,
        "Home Team",
        "homeTeam",
        "home_team",
        "home",
        "Home",
    )

    away = get_value(
        fixture,
        "Away Team",
        "awayTeam",
        "away_team",
        "away",
        "Away",
    )

    date = get_value(
        fixture,
        "Date",
        "date",
        "Kickoff",
        "kickoff",
        "datetime",
    )

    if not home or not away or not date:
        return None

    kickoff = parse_datetime(
        date
    )

    if not kickoff:
        return None

    return {
        "home": str(home).strip(),
        "away": str(away).strip(),
        "kickoff": kickoff,
        "competition": competition,
    }


# -------------------------------------------------------------------
# Fetching
# -------------------------------------------------------------------

def fetch_url(
    session: requests.Session,
    url: str,
):
    """
    Download JSON from Fixture Download.
    """

    print(
        f"URL: {url}"
    )

    try:

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
        )

    except requests.RequestException as e:

        print(
            f"REQUEST ERROR: {e}"
        )

        return None

    print(
        f"HTTP status: {response.status_code}"
    )

    if response.status_code != 200:

        preview = response.text[:300].replace(
            "\n",
            " ",
        )

        print(
            f"Response preview: {preview}"
        )

        return None

    try:

        return response.json()

    except json.JSONDecodeError:

        print(
            "ERROR: response was not valid JSON."
        )

        print(
            f"Response preview: "
            f"{response.text[:300]}"
        )

        return None


def extract_fixture_list(data):
    """
    Extract the fixture list from possible JSON structures.
    """

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "fixtures",
        "matches",
        "events",
        "data",
        "results",
    ):

        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


# -------------------------------------------------------------------
# Competition fetching
# -------------------------------------------------------------------

def fetch_competition(
    session: requests.Session,
    competition_name: str,
    competition_slug: str,
) -> list[dict]:
    """
    Fetch the full competition fixture list.

    We intentionally fetch the competition rather than making
    one request for every SPFL club.
    """

    print()
    print(
        "--------------------------------"
    )

    print(
        competition_name
    )

    print(
        "--------------------------------"
    )

    url = build_json_url(
        competition_slug
    )

    data = fetch_url(
        session,
        url,
    )

    if data is None:
        return []

    raw_fixtures = extract_fixture_list(
        data
    )

    print(
        f"Raw fixtures returned: "
        f"{len(raw_fixtures)}"
    )

    fixtures = []

    for raw_fixture in raw_fixtures:

        fixture = parse_fixture(
            raw_fixture,
            competition_name,
        )

        if fixture:
            fixtures.append(
                fixture
            )

    print(
        f"Parsed fixtures: "
        f"{len(fixtures)}"
    )

    return fixtures


# -------------------------------------------------------------------
# Main source
# -------------------------------------------------------------------

def fetch_all_fixtures() -> list[dict]:
    """
    Fetch all configured competitions.
    """

    session = create_session()

    all_fixtures = []

    for competition_name, config in COMPETITIONS.items():

        fixtures = fetch_competition(
            session,
            competition_name,
            config["slug"],
        )

        all_fixtures.extend(
            fixtures
        )

    # Remove duplicate fixtures.

    unique = {}

    for fixture in all_fixtures:

        key = (
            fixture["home"],
            fixture["away"],
            fixture["kickoff"],
            fixture["competition"],
        )

        unique[key] = fixture

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    return result


# -------------------------------------------------------------------
# Database update
# -------------------------------------------------------------------

def update_fixture_database():
    """
    Fetch Fixture Download data and update data/fixtures.json.

    IMPORTANT:

    If the source fails or returns zero fixtures, the existing
    fixture database is NOT overwritten.
    """

    print(
        "=============================="
    )

    print(
        "FIXTURE DOWNLOAD SOURCE"
    )

    print(
        "=============================="
    )

    fixtures = fetch_all_fixtures()

    print()
    print(
        f"Total parsed fixtures: "
        f"{len(fixtures)}"
    )

    if not fixtures:

        print()
        print(
            "WARNING: Fixture Download "
            "returned no usable fixtures."
        )

        print(
            "Existing fixture data will "
            "NOT be overwritten."
        )

        return False

    save_fixtures(
        fixtures
    )

    return True


# -------------------------------------------------------------------
# Command-line test
# -------------------------------------------------------------------

if __name__ == "__main__":

    success = update_fixture_database()

    if success:

        print()
        print(
            "Fixture Download update "
            "completed successfully."
        )

    else:

        print()
        print(
            "Fixture Download update "
            "FAILED."
      )
