"""
Fixture Download source adapter.

Fetches Scottish Premiership fixtures from Fixture Download,
normalises them into the common fixture format, and stores them
through the data layer.

The rest of the EPG does not need to know where the fixture data
came from.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from data_layer import save_fixtures
from teams import SPFL_TEAMS


BASE_URL = "https://fixturedownload.com/feed/json"

COMPETITIONS = {
    "Scottish Premiership": "scottish-premiership-2026",
}

REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 3


def team_slug(name):
    """
    Convert a team name into the Fixture Download URL slug.
    """

    replacements = {
        "St. ": "st-",
        "St ": "st-",
        "Heart of Midlothian": "heart-of-midlothian",
        "Dundee United": "dundee-united",
    }

    if name in replacements:
        return replacements[name]

    return (
        name.lower()
        .replace("&", "and")
        .replace(".", "")
        .replace(" ", "-")
    )


def create_session():
    """
    Create a browser-style HTTP session.
    """

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
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
            "Connection": "keep-alive",
        }
    )

    return session


def fetch_json(
    session,
    url,
):
    """
    Fetch JSON from Fixture Download with retries.
    """

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1
    ):

        print(
            f"    Request attempt "
            f"{attempt}/{MAX_ATTEMPTS}"
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

            if response.status_code != 200:

                print(
                    "    Request failed."
                )

            else:

                try:

                    data = response.json()

                    if isinstance(
                        data,
                        list
                    ):

                        print(
                            f"    JSON fixtures "
                            f"returned: {len(data)}"
                        )

                        return data

                    print(
                        "    JSON response was "
                        "not a fixture list."
                    )

                except ValueError:

                    print(
                        "    Response was not "
                        "valid JSON."
                    )

                    print(
                        "    Content-Type: "
                        f"{response.headers.get('Content-Type')}"
                    )

        except requests.RequestException as e:

            print(
                f"    Request error: {e}"
            )

        if attempt < MAX_ATTEMPTS:

            delay = 2 ** attempt

            print(
                f"    Retrying in {delay}s..."
            )

            time.sleep(delay)

    return []


def parse_datetime(value):
    """
    Convert Fixture Download DateUtc into a UTC datetime.
    """

    if not value:
        return None

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%SZ",
        ).replace(
            tzinfo=timezone.utc
        )

    except ValueError:

        return None


def normalise_fixture(
    fixture,
    competition,
):
    """
    Convert Fixture Download's fixture format into the common
    format used by the EPG data layer.
    """

    home = fixture.get(
        "HomeTeam"
    )

    away = fixture.get(
        "AwayTeam"
    )

    kickoff = parse_datetime(
        fixture.get("DateUtc")
    )

    if not home or not away or not kickoff:
        return None

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff.isoformat(),
        "competition": competition,

        # Fixture Download calls the venue "Location".
        # Store it as "stadium" because that is the field
        # already used by the XMLTV layer.
        "stadium": (
            fixture.get("Location")
            or "Venue TBC"
        ),
    }


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

    session = create_session()

    all_fixtures = []

    for (
        competition,
        season_slug
    ) in COMPETITIONS.items():

        print(
            f"Competition: "
            f"{competition}"
        )

        print(
            f"Season: "
            f"{season_slug}"
        )

        print(
            "--------------------------------"
        )

        for (
            channel_id,
            team
        ) in SPFL_TEAMS.items():

            team_name = team["name"]

            # Remove the IPTV channel suffix.
            if team_name.endswith(" TV"):

                team_name = (
                    team_name[:-3]
                )

            slug = team_slug(
                team_name
            )

            url = (
                f"{BASE_URL}/"
                f"{quote(season_slug)}/"
                f"{quote(slug)}"
            )

            print()
            print(team_name)

            print(
                f"URL: {url}"
            )

            fixtures = fetch_json(
                session,
                url,
            )

            if not fixtures:

                print(
                    "    No fixture data returned."
                )

                continue

            for fixture in fixtures:

                normalised = (
                    normalise_fixture(
                        fixture,
                        competition,
                    )
                )

                if normalised is None:
                    continue

                all_fixtures.append(
                    normalised
                )

    # ---------------------------------------------------------
    # Remove duplicate fixtures.
    # ---------------------------------------------------------

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

    print()
    print(
        "=============================="
    )
    print(
        f"TOTAL UNIQUE FIXTURES: "
        f"{len(all_fixtures)}"
    )
    print(
        "=============================="
    )

    if not all_fixtures:

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

        raise SystemExit(1)

    # ---------------------------------------------------------
    # Display fixtures and venue information.
    # ---------------------------------------------------------

    print()

    for fixture in all_fixtures:

        print(
            f"{fixture['kickoff']} | "
            f"{fixture['home']} vs "
            f"{fixture['away']} | "
            f"{fixture['competition']} | "
            f"{fixture['stadium']}"
        )

    # ---------------------------------------------------------
    # Save through the source-independent data layer.
    # ---------------------------------------------------------

    save_fixtures(
        all_fixtures
    )

    print()
    print(
        "Fixture data saved successfully"
    )


if __name__ == "__main__":

    main()
