"""
Fixture Download source adapter.

This module retrieves football fixtures from Fixture Download's
raw JSON feed and converts them into the source-independent format
used by the SPFL-EPG data layer.

The rest of the EPG should never need to know that Fixture Download
is being used.

Raw source:
    https://fixturedownload.com/feed/json/

Normalised destination:
    data/fixtures.json
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# -------------------------------------------------------------------
# Make imports from the repository root work when this file is run as:
#
#     python sources/fixture_download.py
#
# -------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from data_layer import save_fixtures


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

BASE_URL = "https://fixturedownload.com/feed/json"

SEASON = "scottish-premiership-2026"

REQUEST_TIMEOUT = 30

MAX_ATTEMPTS = 3

RETRY_DELAYS = [2, 4, 8]


# -------------------------------------------------------------------
# Teams
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# HTTP session
# -------------------------------------------------------------------

def create_session():
    """
    Create a browser-style HTTP session.

    Fixture Download currently responds successfully to the raw
    feed endpoint from GitHub Actions, so we keep the request simple
    and avoid unnecessary scraping behaviour.
    """

    session = requests.Session()

    session.headers.update(
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

    return session


# -------------------------------------------------------------------
# Fetch one team's feed
# -------------------------------------------------------------------

def fetch_team_fixtures(
    session,
    team_name,
    team_slug,
):
    """
    Fetch the raw JSON feed for one team.

    Returns:
        list[dict]
    """

    url = (
        f"{BASE_URL}/"
        f"{SEASON}/"
        f"{team_slug}"
    )

    print(f"\n{team_name}")
    print(f"URL: {url}")

    for attempt in range(1, MAX_ATTEMPTS + 1):

        try:

            print(
                f"    Request attempt "
                f"{attempt}/{MAX_ATTEMPTS}"
            )

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
                    "    Response was not valid JSON."
                )

                print(
                    "    Content-Type:",
                    response.headers.get(
                        "Content-Type",
                        "",
                    ),
                )

                print(
                    "    Response preview:",
                    response.text[:500],
                )

                data = None

            if isinstance(data, list):

                print(
                    f"    JSON fixtures returned: "
                    f"{len(data)}"
                )

                return data

            if isinstance(data, dict):

                # Some feeds may theoretically return an
                # object containing the fixture list.

                for key in (
                    "fixtures",
                    "matches",
                    "data",
                ):

                    if isinstance(
                        data.get(key),
                        list,
                    ):

                        fixtures = data[key]

                        print(
                            f"    JSON fixtures returned: "
                            f"{len(fixtures)}"
                        )

                        return fixtures

                print(
                    "    JSON response did not "
                    "contain a fixture list."
                )

                return []

            print(
                "    Unexpected JSON structure."
            )

            return []

        except requests.RequestException as e:

            print(
                f"    Request failed: {e}"
            )

            if attempt < MAX_ATTEMPTS:

                delay = RETRY_DELAYS[
                    attempt - 1
                ]

                print(
                    f"    Retrying in "
                    f"{delay}s..."
                )

                time.sleep(delay)

            else:

                print(
                    "    REQUEST FAILED"
                )

    return []


# -------------------------------------------------------------------
# Convert Fixture Download fixture
# -------------------------------------------------------------------

def normalise_fixture(
    fixture,
    competition,
):
    """
    Convert one Fixture Download record into the format consumed
    by data_layer.py / fixtures.py.
    """

    home = str(
        fixture.get(
            "HomeTeam",
            "",
        )
    ).strip()

    away = str(
        fixture.get(
            "AwayTeam",
            "",
        )
    ).strip()

    date_value = fixture.get(
        "DateUtc"
    )

    if not home or not away:
        return None

    if not date_value:
        return None

    try:

        kickoff = datetime.strptime(
            date_value,
            "%Y-%m-%d %H:%M:%SZ",
        ).replace(
            tzinfo=timezone.utc
        )

    except ValueError:

        print(
            f"    Invalid DateUtc: "
            f"{date_value}"
        )

        return None

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff.isoformat(),
        "competition": competition,
    }


# -------------------------------------------------------------------
# Main adapter
# -------------------------------------------------------------------

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
        f"{len(TEAM_SLUGS)}"
    )

    print(
        f"Competition: "
        f"Scottish Premiership"
    )

    print(
        f"Season: "
        f"{SEASON}"
    )

    session = create_session()

    all_fixtures = {}

    for team_name, team_slug in TEAM_SLUGS.items():

        raw_fixtures = fetch_team_fixtures(
            session,
            team_name,
            team_slug,
        )

        if not raw_fixtures:

            print(
                "    No fixtures returned."
            )

            continue

        for raw_fixture in raw_fixtures:

            fixture = normalise_fixture(
                raw_fixture,
                "Scottish Premiership",
            )

            if fixture is None:
                continue

            # Use the combination of teams and kickoff as a
            # stable unique key. This prevents the same match
            # being stored twice when both teams are queried.

            key = (
                fixture["kickoff"],
                fixture["home"],
                fixture["away"],
            )

            all_fixtures[key] = fixture

    fixtures = list(
        all_fixtures.values()
    )

    fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    print()
    print(
        "=============================="
    )

    print(
        f"TOTAL UNIQUE FIXTURES: "
        f"{len(fixtures)}"
    )

    print(
        "=============================="
    )

    if not fixtures:

        print()
        print(
            "ERROR:"
        )

        print(
            "Fixture Download returned "
            "zero usable fixtures."
        )

        print(
            "Existing data/fixtures.json "
            "has NOT been replaced."
        )

        return 1

    print()

    for fixture in fixtures:

        print(
            f"{fixture['kickoff']} | "
            f"{fixture['home']} vs "
            f"{fixture['away']} | "
            f"{fixture['competition']}"
        )

    print()

    # The data layer is responsible for safely writing the
    # normalised data to data/fixtures.json.

    save_fixtures(fixtures)

    print(
        "Fixture data saved successfully."
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
