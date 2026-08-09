"""
fixtures.py

Source-independent fixture interface.

The EPG generator uses:

    get_fixtures(team)

All fixture data comes from:

    data/fixtures.json

The source adapter is responsible for downloading and
normalising the data. This module only loads and filters it.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from zoneinfo import ZoneInfo


UK_TZ = ZoneInfo("Europe/London")

BASE_DIR = Path(__file__).resolve().parent
FIXTURES_FILE = BASE_DIR / "data" / "fixtures.json"

# Number of days ahead to include.
FIXTURE_DAYS = 24


def normalise_team_name(name: str) -> str:
    """
    Normalise team names so small naming differences do not
    prevent fixtures from being matched.
    """

    if not name:
        return ""

    name = name.lower().strip()

    name = re.sub(
        r"[^\w\s]",
        " ",
        name,
    )

    for suffix in (
        " football club",
        " fc",
    ):
        if name.endswith(suffix):
            name = name[
                : -len(suffix)
            ].strip()

    return " ".join(
        name.split()
    )


def _load_fixture_data() -> list[dict]:
    """
    Load fixtures from data/fixtures.json.
    """

    if not FIXTURES_FILE.exists():

        print(
            f"WARNING: fixture data file not found: "
            f"{FIXTURES_FILE}"
        )

        return []

    try:

        with open(
            FIXTURES_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

    except (
        OSError,
        json.JSONDecodeError,
    ) as e:

        print(
            f"WARNING: unable to read fixture data: {e}"
        )

        return []

    if not isinstance(data, dict):

        print(
            "WARNING: fixture data has invalid format"
        )

        return []

    fixtures = data.get(
        "fixtures",
        []
    )

    if not isinstance(fixtures, list):

        print(
            "WARNING: fixture data does not contain "
            "a valid fixtures list"
        )

        return []

    return fixtures


def _parse_kickoff(value):
    """
    Convert a stored ISO timestamp into a
    timezone-aware datetime.
    """

    if not value:
        return None

    if isinstance(value, datetime):

        kickoff = value

    elif isinstance(value, str):

        try:

            kickoff = datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00"
                )
            )

        except ValueError:

            return None

    else:

        return None

    if kickoff.tzinfo is None:

        kickoff = kickoff.replace(
            tzinfo=UK_TZ
        )

    return kickoff.astimezone(
        UK_TZ
    )


def get_fixtures(team: dict) -> list[dict]:
    """
    Public interface used by generator.py.

    Returns fixtures for one team in the format expected
    by the existing EPG system.
    """

    team_name = team["name"]

    if team_name.endswith(" TV"):

        team_name = team_name[:-3]

    target = normalise_team_name(
        team_name
    )

    now = datetime.now(
        UK_TZ
    )

    window_end = (
        now
        + timedelta(
            days=FIXTURE_DAYS
        )
    )

    fixtures = []

    for fixture in _load_fixture_data():

        home = fixture.get(
            "home",
            ""
        )

        away = fixture.get(
            "away",
            ""
        )

        if (
            normalise_team_name(home) != target
            and
            normalise_team_name(away) != target
        ):

            continue

        kickoff = _parse_kickoff(
            fixture.get("kickoff")
        )

        if kickoff is None:

            continue

        if not (
            now
            <= kickoff
            <= window_end
        ):

            continue

        fixtures.append(
            {
                "home": home,

                "away": away,

                "kickoff": kickoff,

                "competition": fixture.get(
                    "competition",
                    "Unknown",
                ),

                "stadium": fixture.get(
                    "stadium",
                    "Venue TBC",
                ),
            }
        )

    fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    return fixtures
