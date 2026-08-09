"""
sources/fixture_download.py

Fixture Download source adapter.

Downloads Scottish Premiership fixtures from the
Fixture Download raw JSON feed and converts them into
the source-independent format used by the SPFL EPG.

Output:

    data/fixtures.json

The rest of the EPG system does not need to know where
the fixture data came from.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ---------------------------------------------------------
# Make the repository root importable when this file is
# executed directly with:
#
#     python sources/fixture_download.py
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from data_layer import save_fixtures
from teams import SPFL_TEAMS


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

COMPETITION = "Scottish Premiership"

SEASON = "scottish-premiership-2026"

BASE_URL = (
    "https://fixturedownload.com/feed/json/"
    f"{SEASON}"
)

REQUEST_TIMEOUT = 30

MAX_RETRIES = 3


# ---------------------------------------------------------
# Team slug conversion
#
# The EPG uses the names we want displayed to users.
# Fixture Download has its own URL naming convention.
#
# For example:
#
#     Hearts
#         ↓
#     heart-of-midlothian
#
# ---------------------------------------------------------

TEAM_SLUGS = {
    "Aberdeen": "aberdeen",
    "Celtic": "celtic",
    "Dundee": "dundee",
    "Dundee United": "dundee-united",
    "Falkirk": "falkirk",

    # Hearts is displayed as "Hearts" in the EPG,
    # but Fixture Download uses "heart-of-midlothian".
    "Hearts": "heart-of-midlothian",

    "Hibernian": "hibernian",
    "Kilmarnock": "kilmarnock",
    "Motherwell": "motherwell",
    "Rangers": "rangers",
    "St Johnstone": "st-johnstone",
    "St. Johnstone": "st-johnstone",
    "St Mirren": "st-mirren",
    "St. Mirren": "st-mirren",
}


# ---------------------------------------------------------
# HTTP request
# ---------------------------------------------------------

def download_json(url: str):

    headers = {
        "User-Agent": "SPFL-EPG/1.0",
        "Accept": "application/json",
    }

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"    Request attempt "
            f"{attempt}/{MAX_RETRIES}"
        )

        request = Request(
            url,
            headers=headers
        )

        try:

            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT
            ) as response:

                status = response.status

                print(
                    f"    HTTP status: {status}"
                )

                body = response.read().decode(
                    "utf-8"
                )

            data = json.loads(body)

            if not isinstance(data, list):

                print(
                    "    Response JSON was not a list."
                )

                return []

            print(
                f"    JSON fixtures returned: "
                f"{len(data)}"
            )

            return data

        except HTTPError as error:

            print(
                f"    HTTP error: "
                f"{error.code}"
            )

        except URLError as error:

            print(
                f"    URL error: "
                f"{error.reason}"
            )

        except TimeoutError:

            print(
                "    Request timed out."
            )

        except json.JSONDecodeError:

            print(
                "    Response was not valid JSON."
            )

        except Exception as error:

            print(
                f"    Unexpected error: {error}"
            )

        if attempt < MAX_RETRIES:

            delay = 2 ** attempt

            print(
                f"    Retrying in {delay}s..."
            )

            time.sleep(delay)

    return []


# ---------------------------------------------------------
# Kick-off conversion
# ---------------------------------------------------------

def convert_kickoff(
    date_value: str
) -> str | None:
    """
    Convert Fixture Download's:

        2026-08-09 15:00:00Z

    into ISO 8601:

        2026-08-09T15:00:00+00:00
    """

    if not date_value:
        return None

    try:

        dt = datetime.strptime(
            date_value,
            "%Y-%m-%d %H:%M:%SZ"
        )

        dt = dt.replace(
            tzinfo=timezone.utc
        )

        return dt.isoformat()

    except ValueError:

        return None


# ---------------------------------------------------------
# Team name
# ---------------------------------------------------------

def get_team_name(team: dict) -> str:

    name = team.get(
        "name",
        ""
    )

    if name.endswith(" TV"):

        name = name[:-3]

    return name.strip()


# ---------------------------------------------------------
# Normalise one fixture
# ---------------------------------------------------------

def normalise_fixture(
    fixture: dict
) -> dict | None:

    home = fixture.get(
        "HomeTeam"
    )

    away = fixture.get(
        "AwayTeam"
    )

    date_utc = fixture.get(
        "DateUtc"
    )

    location = fixture.get(
        "Location"
    )

    if not home or not away:
        return None

    kickoff = convert_kickoff(
        date_utc
    )

    if kickoff is None:
        return None

    # -----------------------------------------------------
    # Keep the official EPG naming convention.
    #
    # Fixture Download may return:
    #
    #     Heart of Midlothian
    #
    # but the EPG should display:
    #
    #     Hearts
    #
    # -----------------------------------------------------

    if home.strip() == "Heart of Midlothian":
        home = "Hearts"

    if away.strip() == "Heart of Midlothian":
        away = "Hearts"

    # -----------------------------------------------------
    # Fixture Download calls the venue "Location".
    #
    # Store it as "stadium" because that is the field
    # consumed by fixtures.py and the XMLTV generator.
    # -----------------------------------------------------

    stadium = (
        location.strip()
        if isinstance(location, str)
        and location.strip()
        else "Venue TBC"
    )

    return {
        "home": home.strip(),

        "away": away.strip(),

        "kickoff": kickoff,

        "competition": COMPETITION,

        "stadium": stadium,
    }


# ---------------------------------------------------------
# Main download process
# ---------------------------------------------------------

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

    print(
        f"Competition: "
        f"{COMPETITION}"
    )

    print(
        f"Season: "
        f"{SEASON}"
    )

    print(
        "=============================="
    )

    all_fixtures = {}

    # -----------------------------------------------------
    # Download each team's fixture feed.
    # -----------------------------------------------------

    for channel_id, team in SPFL_TEAMS.items():

        team_name = get_team_name(team)

        slug = TEAM_SLUGS.get(team_name)

        print()
        print(
            "--------------------------------"
        )

        print(team_name)

        print(
            "--------------------------------"
        )

        if not slug:

            print(
                f"WARNING: No Fixture Download "
                f"slug configured for {team_name}"
            )

            continue

        url = (
            f"{BASE_URL}/{slug}"
        )

        print(
            f"URL: {url}"
        )

        raw_fixtures = download_json(url)

        if not raw_fixtures:

            print(
                "    No fixtures returned."
            )

            continue

        for raw_fixture in raw_fixtures:

            fixture = normalise_fixture(
                raw_fixture
            )

            if fixture is None:
                continue

            # -------------------------------------------------
            # Deduplicate fixtures.
            #
            # The same match appears in both teams' feeds.
            # -------------------------------------------------

            key = (
                fixture["kickoff"],
                fixture["home"],
                fixture["away"],
            )

            if key not in all_fixtures:

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

    # -----------------------------------------------------
    # Safety check.
    #
    # Never replace the existing fixture file with an empty
    # result.
    # -----------------------------------------------------

    if not fixtures:

        print()
        print("ERROR:")

        print(
            "Fixture Download returned zero "
            "usable fixtures."
        )

        print(
            "Existing data/fixtures.json "
            "has NOT been replaced."
        )

        return 1

    # -----------------------------------------------------
    # Display downloaded fixtures.
    # -----------------------------------------------------

    print()

    for fixture in fixtures:

        print(
            f"{fixture['kickoff']} | "
            f"{fixture['home']} vs "
            f"{fixture['away']} | "
            f"{fixture['competition']} | "
            f"{fixture['stadium']}"
        )

    # -----------------------------------------------------
    # Save data.
    # -----------------------------------------------------

    save_fixtures(fixtures)

    print()

    print(
        "Fixture data saved successfully"
    )

    print(
        f"Saved to: "
        f"{BASE_DIR / 'data' / 'fixtures.json'}"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
