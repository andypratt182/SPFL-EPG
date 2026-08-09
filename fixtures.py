"""
fixtures.py

Source-independent fixture interface.

The EPG generator uses:

    get_fixtures(team)

Fixture data is read from:

    data/fixtures.json

The external fixture source is handled separately by
sources/fixture_download.py.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


UK_TZ = ZoneInfo("Europe/London")

BASE_DIR = Path(__file__).resolve().parent
FIXTURES_FILE = BASE_DIR / "data" / "fixtures.json"

# Number of days ahead to include in the EPG.
FIXTURE_DAYS = 24


def normalise_team_name(name: str) -> str:
    """
    Normalise team names so small naming differences do not prevent
    fixtures from being matched.
    """

    if not name:
        return ""

    name = str(name).lower().strip()

    name = re.sub(r"[^\w\s]", " ", name)

    for suffix in (
        " football club",
        " fc",
    ):
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()

    return " ".join(name.split())


def _load_fixture_data() -> list[dict]:
    """
    Load normalised fixture data from data/fixtures.json.
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
        ) as file:
            data = json.load(file)

    except (OSError, json.JSONDecodeError) as error:
        print(
            f"WARNING: unable to read fixture data: "
            f"{error}"
        )
        return []

    if not isinstance(data, dict):
        print(
            "WARNING: fixture data file does not contain "
            "a JSON object."
        )
        return []

    fixtures = data.get("fixtures", [])

    if not isinstance(fixtures, list):
        print(
            "WARNING: fixture data does not contain "
            "a valid fixtures list."
        )
        return []

    return fixtures


def _parse_kickoff(value):
    """
    Convert a stored ISO timestamp into a timezone-aware
    datetime in UK time.

    Supports values such as:

        2026-08-22T14:00:00+00:00
        2026-08-22T15:00:00+01:00
        2026-08-22 14:00:00Z
    """

    if not value:
        return None

    if isinstance(value, datetime):
        kickoff = value

    elif isinstance(value, str):
        try:
            normalised = value.strip()

            if normalised.endswith("Z"):
                normalised = (
                    normalised[:-1] + "+00:00"
                )

            kickoff = datetime.fromisoformat(
                normalised
            )

        except ValueError:
            return None

    else:
        return None

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(
            tzinfo=UK_TZ
        )

    return kickoff.astimezone(UK_TZ)


def get_fixtures(team: dict) -> list[dict]:
    """
    Public fixture interface used by generator.py.

    Returns fixtures for one team in the format expected
    by the EPG system:

        {
            "home": str,
            "away": str,
            "kickoff": datetime,
            "competition": str,
            "stadium": str,
        }
    """

    team_name = team.get("name", "")

    # Channel names such as "Rangers TV" are matched against
    # the actual football club name "Rangers".
    if team_name.endswith(" TV"):
        team_name = team_name[:-3]

    target = normalise_team_name(
        team_name
    )

    now = datetime.now(UK_TZ)

    window_end = (
        now
        + timedelta(days=FIXTURE_DAYS)
    )

    fixtures = []

    for fixture in _load_fixture_data():

        if not isinstance(fixture, dict):
            continue

        home = fixture.get(
            "home",
            ""
        )

        away = fixture.get(
            "away",
            ""
        )

        # Ignore malformed fixture records.
        if not home or not away:
            continue

        home_normalised = normalise_team_name(
            home
        )

        away_normalised = normalise_team_name(
            away
        )

        if (
            home_normalised != target
            and
            away_normalised != target
        ):
            continue

        kickoff = _parse_kickoff(
            fixture.get("kickoff")
        )

        if kickoff is None:
            continue

        # Only return fixtures inside the EPG's
        # upcoming fixture window.
        if kickoff < now:
            continue

        if kickoff > window_end:
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

    # Sort chronologically.
    fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    return fixtures
