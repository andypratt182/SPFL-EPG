"""
sources/espn.py

ESPN fixture source adapter.

IMPORTANT:

This module is the only part of the project that should know
about ESPN's API.

If ESPN is replaced later, this file can be replaced without
changing fixtures.py, generator.py, or xmltv.py.
"""

from datetime import datetime
from typing import Optional

import requests

from data_layer import save_fixtures


ESPN_BASE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer"
)


COMPETITIONS = {
    "sco.1": "Scottish Premiership",
    "sco.cup": "Scottish Cup",
    "sco.league_cup": "Scottish League Cup",
}


# ESPN team IDs for SPFL clubs.
# These can be expanded later.
ESPN_TEAMS = {
    "Aberdeen": 263,
    "Celtic": 256,
    "Dundee": 265,
    "Dundee United": 267,
    "Falkirk": 277,
    "Hearts": 264,
    "Hibernian": 266,
    "Kilmarnock": 269,
    "Livingston": 270,
    "Motherwell": 271,
    "Rangers": 257,
    "St Mirren": 268,
}


def create_session() -> requests.Session:
    """
    Create a browser-style HTTP session.

    This does not bypass network restrictions. It simply makes
    the request resemble a normal browser request.
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
                "https://www.espn.com/"
            ),
            "Origin": (
                "https://www.espn.com"
            ),
            "Connection": "keep-alive",
        }
    )

    return session


def parse_fixture(
    event: dict,
    competition: str,
) -> Optional[dict]:
    """
    Convert one ESPN event into our normalised fixture format.
    """

    competitions = event.get(
        "competitions",
        [],
    )

    if not competitions:
        return None

    competition_data = competitions[0]

    competitors = competition_data.get(
        "competitors",
        [],
    )

    if len(competitors) < 2:
        return None

    home = None
    away = None

    for competitor in competitors:

        team = competitor.get(
            "team",
            {}
        )

        name = team.get("displayName")

        if not name:
            continue

        if competitor.get(
            "homeAway"
        ) == "home":

            home = name

        elif competitor.get(
            "homeAway"
        ) == "away":

            away = name

    if not home or not away:
        return None

    kickoff = event.get(
        "date"
    )

    if not kickoff:
        return None

    try:

        datetime.fromisoformat(
            kickoff.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:

        return None

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "competition": competition,
    }


def fetch_team_competition(
    session: requests.Session,
    team_id: int,
    competition_code: str,
) -> list[dict]:
    """
    Fetch one team's fixtures from one ESPN competition.
    """

    url = (
        f"{ESPN_BASE_URL}/"
        f"{competition_code}/"
        f"teams/{team_id}/"
        f"schedule"
    )

    print(
        f"Fetching {url}"
    )

    try:

        response = session.get(
            url,
            timeout=30,
        )

    except requests.RequestException as e:

        print(
            f"ERROR requesting ESPN: {e}"
        )

        return []

    print(
        f"HTTP {response.status_code}"
    )

    if response.status_code != 200:

        print(
            "ESPN request failed."
        )

        return []

    try:

        data = response.json()

    except ValueError:

        print(
            "ESPN returned invalid JSON."
        )

        return []

    fixtures = []

    for event in data.get(
        "events",
        []
    ):

        fixture = parse_fixture(
            event,
            COMPETITIONS[
                competition_code
            ],
        )

        if fixture:
            fixtures.append(
                fixture
            )

    return fixtures


def fetch_all_fixtures() -> list[dict]:
    """
    Fetch fixtures for all configured SPFL teams.
    """

    session = create_session()

    all_fixtures = []

    for team_name, team_id in ESPN_TEAMS.items():

        print(
            f"\nFetching fixtures for "
            f"{team_name}"
        )

        for competition_code in COMPETITIONS:

            fixtures = (
                fetch_team_competition(
                    session,
                    team_id,
                    competition_code,
                )
            )

            all_fixtures.extend(
                fixtures
            )

    # Remove duplicates.
    unique = {}

    for fixture in all_fixtures:

        key = (
            fixture["home"],
            fixture["away"],
            fixture["kickoff"],
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


def update_fixture_database() -> None:
    """
    Fetch ESPN data and update the normalised fixture store.
    """

    print(
        "=============================="
    )
    print(
        "UPDATING FIXTURE DATA FROM ESPN"
    )
    print(
        "=============================="
    )

    fixtures = fetch_all_fixtures()

    print(
        f"\nTotal fixtures received: "
        f"{len(fixtures)}"
    )

    if not fixtures:

        print(
            "\nWARNING:"
        )

        print(
            "ESPN returned no fixtures."
        )

        print(
            "The existing fixture data "
            "will NOT be overwritten."
        )

        return

    save_fixtures(
        fixtures
    )


if __name__ == "__main__":

    update_fixture_database()
