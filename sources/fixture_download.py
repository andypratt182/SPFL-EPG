"""
sources/fixture_download.py

Fixture Download source adapter.

Downloads Scottish Premiership fixtures from Fixture Download's
raw JSON feeds and stores them in data/fixtures.json through the
project data layer.

The adapter is deliberately source-specific. The rest of the EPG
system should only interact with the normalised fixture data.

Fixture Download raw feed format:

https://fixturedownload.com/feed/json/{season}/{team}

Example:

https://fixturedownload.com/feed/json/scottish-premiership-2026/rangers
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# When this script is executed as:
#
#     python sources/fixture_download.py
#
# Python puts "sources/" on sys.path rather than the repository root.
#
# Add the repository root explicitly so imports such as:
#
#     from data_layer import save_fixtures
#
# work correctly in GitHub Actions.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from data_layer import save_fixtures
from teams import SPFL_TEAMS


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://fixturedownload.com/feed/json"

COMPETITION = "Scottish Premiership"

SEASON = "scottish-premiership-2026"

REQUEST_TIMEOUT = 30

MAX_RETRIES = 3

RETRY_DELAY_SECONDS = 2

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; SPFL-EPG/1.0; "
    "+https://github.com/andypratt182/SPFL-EPG)"
)


# ---------------------------------------------------------------------------
# Team slug handling
# ---------------------------------------------------------------------------

TEAM_SLUG_OVERRIDES = {
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


def team_slug(team_name: str) -> str:
    """
    Convert a configured team name into the Fixture Download URL slug.
    """

    clean_name = team_name.strip()

    if clean_name.endswith(" TV"):
        clean_name = clean_name[:-3].strip()

    if clean_name in TEAM_SLUG_OVERRIDES:
        return TEAM_SLUG_OVERRIDES[clean_name]

    return (
        clean_name
        .lower()
        .replace(".", "")
        .replace("'", "")
        .replace(" ", "-")
    )


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def fetch_json(url: str):
    """
    Download JSON from Fixture Download.

    Retries temporary failures and returns None if the request cannot
    be completed successfully.
    """

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"    Request attempt "
            f"{attempt}/{MAX_RETRIES}"
        )

        request = Request(
            url,
            headers=headers,
            method="GET",
        )

        try:

            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:

                status = response.status

                body = response.read()

                print(
                    f"    HTTP status: {status}"
                )

                if status != 200:
                    print(
                        "    Unexpected HTTP status."
                    )

                else:

                    try:

                        data = json.loads(
                            body.decode("utf-8")
                        )

                    except (
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                    ):

                        print(
                            "    Response was not valid JSON."
                        )

                        preview = body[:500].decode(
                            "utf-8",
                            errors="replace",
                        )

                        print(
                            "    Response preview:"
                        )

                        print(preview)

                        data = None

                    if isinstance(data, list):

                        print(
                            f"    JSON fixtures returned: "
                            f"{len(data)}"
                        )

                        return data

                    if isinstance(data, dict):

                        print(
                            "    JSON response was an object, "
                            "not a fixture list."
                        )

                        return []

                    print(
                        "    JSON response had an "
                        "unexpected structure."
                    )

                    return []

        except HTTPError as error:

            print(
                f"    HTTP error: "
                f"{error.code} {error.reason}"
            )

        except URLError as error:

            print(
                f"    URL error: {error.reason}"
            )

        except TimeoutError:

            print(
                "    Request timed out."
            )

        except OSError as error:

            print(
                f"    Network error: {error}"
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

    print(
        "    REQUEST FAILED"
    )

    return None


# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------

def parse_fixture_date(value: str):
    """
    Convert Fixture Download's DateUtc field into an ISO-8601 UTC
    timestamp.

    Fixture Download normally supplies:

        2026-08-09 15:00:00Z

    The normalised database format becomes:

        2026-08-09T15:00:00+00:00
    """

    if not value:
        return None

    value = str(value).strip()

    formats = (
        "%Y-%m-%d %H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )

    for fmt in formats:

        try:

            parsed = datetime.strptime(
                value,
                fmt,
            )

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

            return parsed.isoformat()

        except ValueError:
            continue

    # Final fallback for ISO timestamps containing
    # an explicit timezone offset.

    try:

        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        ).isoformat()

    except ValueError:

        return None


# ---------------------------------------------------------------------------
# Fixture normalisation
# ---------------------------------------------------------------------------

def normalise_fixture(
    fixture: dict,
) -> dict | None:
    """
    Convert a Fixture Download fixture into the format used by
    data/fixtures.json.
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

    date_utc = fixture.get(
        "DateUtc"
    )

    kickoff = parse_fixture_date(
        date_utc
    )

    if not home:

        print(
            "    WARNING: fixture has no home team."
        )

        return None

    if not away:

        print(
            "    WARNING: fixture has no away team."
        )

        return None

    if not kickoff:

        print(
            f"    WARNING: invalid kickoff "
            f"for {home} vs {away}: "
            f"{date_utc}"
        )

        return None

    # Fixture Download calls the stadium/location
    # "Location".
    #
    # Store it as "stadium" because that is what
    # xmltv.py already expects.

    stadium = fixture.get(
        "Location"
    )

    if stadium is not None:

        stadium = str(
            stadium
        ).strip()

    if not stadium:

        stadium = "Venue TBC"

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "competition": COMPETITION,
        "stadium": stadium,
    }


# ---------------------------------------------------------------------------
# Download one team's fixtures
# ---------------------------------------------------------------------------

def download_team_fixtures(
    team_name: str,
) -> list[dict]:
    """
    Download and normalise all fixtures for one team.
    """

    slug = team_slug(
        team_name
    )

    url = (
        f"{BASE_URL}/"
        f"{SEASON}/"
        f"{slug}"
    )

    print(
        f"{team_name}"
    )

    print(
        f"URL: {url}"
    )

    raw_fixtures = fetch_json(
        url
    )

    if raw_fixtures is None:

        return []

    fixtures = []

    for raw_fixture in raw_fixtures:

        if not isinstance(
            raw_fixture,
            dict,
        ):

            continue

        fixture = normalise_fixture(
            raw_fixture
        )

        if fixture is None:

            continue

        fixtures.append(
            fixture
        )

    return fixtures


# ---------------------------------------------------------------------------
# De-duplication
# ---------------------------------------------------------------------------

def deduplicate_fixtures(
    fixtures: list[dict],
) -> list[dict]:
    """
    Remove duplicate fixtures.

    Each team feed contains the same match, so downloading all 12
    team feeds naturally creates duplicates.

    The combination of home, away and kickoff uniquely identifies
    a fixture for this project.
    """

    unique = {}

    for fixture in fixtures:

        key = (
            fixture["home"].strip().lower(),
            fixture["away"].strip().lower(),
            fixture["kickoff"],
        )

        if key not in unique:

            unique[key] = fixture

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda item:
        item["kickoff"]
    )

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:

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

    print()

    all_fixtures = []

    # -------------------------------------------------------
    # Download each configured SPFL team.
    # -------------------------------------------------------

    for channel_id, team in SPFL_TEAMS.items():

        team_name = team["name"]

        if team_name.endswith(" TV"):

            team_name = team_name[:-3].strip()

        print(
            "--------------------------------"
        )

        try:

            fixtures = download_team_fixtures(
                team_name
            )

            all_fixtures.extend(
                fixtures
            )

            print(
                f"    Normalised fixtures: "
                f"{len(fixtures)}"
            )

        except Exception as error:

            print(
                f"    ERROR loading "
                f"{team_name}: {error}"
            )

    # -------------------------------------------------------
    # De-duplicate.
    # -------------------------------------------------------

    unique_fixtures = deduplicate_fixtures(
        all_fixtures
    )

    print()
    print(
        "=============================="
    )

    print(
        f"TOTAL UNIQUE FIXTURES: "
        f"{len(unique_fixtures)}"
    )

    print(
        "=============================="
    )

    # -------------------------------------------------------
    # Safety check.
    #
    # NEVER replace the existing fixture database with an
    # empty result.
    # -------------------------------------------------------

    if not unique_fixtures:

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

    # -------------------------------------------------------
    # Show the fixtures that will be saved.
    # -------------------------------------------------------

    print()

    for fixture in unique_fixtures:

        print(
            f"{fixture['kickoff']} | "
            f"{fixture['home']} vs "
            f"{fixture['away']} | "
            f"{fixture['competition']} | "
            f"{fixture['stadium']}"
        )

    # -------------------------------------------------------
    # Save through the project's data layer.
    # -------------------------------------------------------

    try:

        save_fixtures(
            unique_fixtures
        )

    except TypeError:

        # Compatibility fallback in case the current data layer
        # expects a different calling convention.

        save_fixtures(
            fixtures=unique_fixtures
        )

    print()
    print(
        "Fixture data saved successfully"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
