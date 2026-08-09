"""
scraper.py

Fixture source adapter for ESPN.

GitHub Actions cannot reliably access ESPN's API, so this module is
designed to be used by a local/manual data collection process rather
than by the EPG generator itself.

The important part is the normalised fixture format returned by the
source:

{
    "home": "Rangers",
    "away": "Dundee United",
    "kickoff": "2026-07-31T19:00:00Z",
    "competition": "Scottish Premiership",
    "source_id": "401878416"
}

fixtures.py consumes the normalised data and does not need to know
where it came from.
"""

import json
from datetime import datetime
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
}


ESPN_BASE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer"
)


COMPETITIONS = {
    "Scottish Premiership": "sco.1",
    "Scottish Cup": "sco.cup",
    "Scottish League Cup": "sco.league_cup",
}


REQUEST_TIMEOUT = 20


def fetch_team_competition_fixtures(
    team_name: str,
    espn_id: int,
    competition: str,
) -> list[dict]:
    """
    Fetch fixtures for one team and one competition from ESPN.

    Returns normalised fixture dictionaries.
    """

    if competition not in COMPETITIONS:
        raise ValueError(
            f"Unknown competition: {competition}"
        )

    league = COMPETITIONS[competition]

    url = (
        f"{ESPN_BASE_URL}/"
        f"{league}/teams/{espn_id}/schedule"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    return parse_espn_events(
        data.get("events", []),
        competition,
    )


def parse_espn_events(
    events: list[dict],
    competition: str,
) -> list[dict]:
    """
    Convert ESPN events into our source-independent format.
    """

    fixtures = []

    for event in events:
        try:
            event_id = str(event["id"])
            kickoff = event.get("date")

            competitors = (
                event
                .get("competitions", [{}])[0]
                .get("competitors", [])
            )

            home = None
            away = None

            for competitor in competitors:
                team = competitor.get("team", {})
                name = (
                    team.get("displayName")
                    or team.get("name")
                )

                if not name:
                    continue

                if competitor.get("homeAway") == "home":
                    home = name

                elif competitor.get("homeAway") == "away":
                    away = name

            if not home or not away:
                continue

            fixtures.append(
                {
                    "home": home,
                    "away": away,
                    "kickoff": kickoff,
                    "competition": competition,
                    "source_id": event_id,
                }
            )

        except (KeyError, IndexError, TypeError):
            continue

    return fixtures


def save_fixtures(fixtures: list[dict]) -> None:
    """
    Save normalised fixtures to data/fixtures.json.
    """

    DATA_DIR.mkdir(exist_ok=True)

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "fixtures": fixtures,
    }

    with open(
        FIXTURES_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Saved {len(fixtures)} fixtures to "
        f"{FIXTURES_FILE}"
    )


def load_fixtures() -> list[dict]:
    """
    Load normalised fixtures from data/fixtures.json.
    """

    if not FIXTURES_FILE.exists():
        return []

    with open(
        FIXTURES_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    return data.get("fixtures", [])


if __name__ == "__main__":
    print("Fixture source adapter")
    print()
    print("This module provides the ESPN source adapter.")
    print(
        "GitHub Actions should consume data/fixtures.json "
        "rather than call ESPN directly."
    )
