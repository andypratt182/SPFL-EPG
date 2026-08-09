"""
sources/fixture_download.py

Fixture Download source adapter.

Fetches football fixtures from Fixture Download's JSON endpoints
and stores them in data/fixtures.json.

The rest of the EPG does not need to know where the fixtures came
from.

Current supported competition:
    Scottish Premiership 2026/27
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"


# ---------------------------------------------------------------------
# Fixture Download configuration
# ---------------------------------------------------------------------

BASE_URL = "https://fixturedownload.com/view/json"

COMPETITIONS = {
    "Scottish Premiership": {
        "slug": "scottish-premiership-2026",
    },
}


# ---------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0.0.0 "
            "Safari/537.36"
        ),
        "Accept": (
            "application/json,"
            "text/plain,"
            "*/*"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": "https://fixturedownload.com/",
    }
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def team_slug(team_name: str) -> str:
    """
    Convert a team name into Fixture Download's URL slug.
    """

    replacements = {
        "St. ": "st-",
        " ": "-",
    }

    value = team_name.strip().lower()

    for old, new in replacements.items():
        value = value.replace(old.lower(), new)

    return value


def fetch_json(url: str):
    """
    Fetch JSON with a small retry mechanism.
    """

    for attempt in range(1, 4):

        print(
            f"    Request attempt {attempt}/3"
        )

        try:

            response = SESSION.get(
                url,
                timeout=30,
            )

            print(
                f"    HTTP status: "
                f"{response.status_code}"
            )

            if response.status_code != 200:

                print(
                    "    Response preview:"
                )

                print(
                    response.text[:500]
                )

            else:

                try:

                    return response.json()

                except ValueError:

                    print(
                        "    Response was not valid JSON."
                    )

                    print(
                        "    Content-Type:",
                        response.headers.get(
                            "Content-Type"
                        ),
                    )

                    print(
                        "    Response preview:"
                    )

                    print(
                        response.text[:500]
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


def parse_fixture(item: dict, competition: str):
    """
    Convert Fixture Download JSON into the internal data format.
    """

    home = item.get("HomeTeam")
    away = item.get("AwayTeam")
    date_utc = item.get("DateUtc")

    if not home or not away or not date_utc:
        return None

    try:

        kickoff = datetime.fromisoformat(
            date_utc.replace(
                "Z",
                "+00:00",
            )
        )

        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(
                tzinfo=timezone.utc,
            )

        kickoff = kickoff.astimezone(
            timezone.utc
        )

    except ValueError:

        print(
            f"    Could not parse date: "
            f"{date_utc}"
        )

        return None

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff.isoformat(),
        "competition": competition,
    }


def save_fixtures(fixtures: list[dict]):
    """
    Save the normalised fixture data.

    Existing data is replaced only after the complete source
    collection succeeds.
    """

    DATA_DIR.mkdir(
        exist_ok=True
    )

    output = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "fixtures": fixtures,
    }

    temporary_file = FIXTURES_FILE.with_suffix(
        ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    temporary_file.replace(
        FIXTURES_FILE
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

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
        f"Teams configured: {len(TEAMS)}"
    )

    all_fixtures = []

    for competition, config in COMPETITIONS.items():

        competition_slug = config["slug"]

        print(
            "\n--------------------------------"
        )

        print(
            f"Competition: {competition}"
        )

        print(
            f"Competition slug: "
            f"{competition_slug}"
        )

        print(
            "--------------------------------"
        )

        for team in TEAMS:

            slug = team_slug(team)

            url = (
                f"{BASE_URL}/"
                f"{competition_slug}/"
                f"{slug}"
            )

            print(
                f"\n{team}"
            )

            print(
                f"URL: {url}"
            )

            data = fetch_json(
                url
            )

            if data is None:

                print(
                    "    REQUEST FAILED"
                )

                continue

            if not isinstance(
                data,
                list,
            ):

                print(
                    "    Unexpected JSON structure:"
                )

                print(
                    str(data)[:500]
                )

                continue

            print(
                f"    JSON fixtures returned: "
                f"{len(data)}"
            )

            for item in data:

                fixture = parse_fixture(
                    item,
                    competition,
                )

                if fixture is None:
                    continue

                all_fixtures.append(
                    fixture
                )

                print(
                    f"    {fixture['kickoff']} "
                    f"- "
                    f"{fixture['home']} "
                    f"vs "
                    f"{fixture['away']}"
                )

    # -------------------------------------------------------------
    # Remove duplicates
    # -------------------------------------------------------------

    unique = {}

    for fixture in all_fixtures:

        key = (
            fixture["kickoff"],
            fixture["home"],
            fixture["away"],
            fixture["competition"],
        )

        unique[key] = fixture

    all_fixtures = list(
        unique.values()
    )

    all_fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    print(
        "\n=============================="
    )

    print(
        f"TOTAL UNIQUE FIXTURES: "
        f"{len(all_fixtures)}"
    )

    print(
        "=============================="
    )

    # -------------------------------------------------------------
    # Safety check
    # -------------------------------------------------------------
    #
    # Do NOT destroy an existing fixture file if the source has
    # suddenly returned zero fixtures.
    #

    if not all_fixtures:

        print(
            "\nERROR:"
        )

        print(
            "Fixture Download returned "
            "zero usable fixtures."
        )

        print(
            "Existing data/fixtures.json "
            "has NOT been replaced."
        )

        sys.exit(1)

    # -------------------------------------------------------------
    # Save
    # -------------------------------------------------------------

    save_fixtures(
        all_fixtures
    )

    print(
        f"\nSaved fixture data to:"
    )

    print(
        FIXTURES_FILE
    )

    print(
        "\nFixture Download adapter "
        "completed successfully."
    )


if __name__ == "__main__":
    main()
