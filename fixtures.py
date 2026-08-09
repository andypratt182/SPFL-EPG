"""
fixtures.py

Source-independent fixture interface.

The EPG generator uses:

    get_fixtures(team)

This module deliberately knows nothing about ESPN, BBC,
Fixture Download, or any other external source.

All fixture data comes from:

    data/fixtures.json

This means the fixture source can be replaced later without
changing generator.py or xmltv.py.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from zoneinfo import ZoneInfo


UK_TZ = ZoneInfo("Europe/London")

BASE_DIR = Path(__file__).resolve().parent

FIXTURES_FILE = (
    BASE_DIR /
    "data" /
    "fixtures.json"
)

# Number of days ahead to include.
FIXTURE_DAYS = 24


def normalise_team_name(name: str) -> str:
    """
    Normalise team names so differences between sources do not
    prevent fixtures from being matched.

    Examples:

        Hearts
        Heart of Midlothian

    are treated as the same team.

    Likewise:

        Rangers FC
        Rangers Football Club

    are treated as the same team.
    """

    if not name:
        return ""

    name = name.lower().strip()

    # ---------------------------------------------------------
    # Remove punctuation.
    #
    # St. Mirren -> St Mirren
    # ---------------------------------------------------------

    name = re.sub(
        r"[^\w\s]",
        " ",
        name,
    )

    # ---------------------------------------------------------
    # Remove common club suffixes.
    # ---------------------------------------------------------

    for suffix in (
        " football club",
        " fc",
    ):

        if name.endswith(suffix):

            name = name[
                : -len(suffix)
            ].strip()

    # ---------------------------------------------------------
    # Collapse multiple spaces.
    # ---------------------------------------------------------

    name = " ".join(
        name.split()
    )

    # ---------------------------------------------------------
    # Known team aliases.
    #
    # The value is the canonical name used for matching.
    # ---------------------------------------------------------

    aliases = {

        # Rangers
        "rangers":
            "rangers",

        # Celtic
        "celtic":
            "celtic",

        # Aberdeen
        "aberdeen":
            "aberdeen",

        # Dundee
        "dundee":
            "dundee",

        # Dundee United
        "dundee united":
            "dundee united",

        # Hearts
        "hearts":
            "heart of midlothian",

        "heart of midlothian":
            "heart of midlothian",

        # Hibernian
        "hibs":
            "hibernian",

        "hibernian":
            "hibernian",

        # Kilmarnock
        "kilmarnock":
            "kilmarnock",

        # Motherwell
        "motherwell":
            "motherwell",

        # Falkirk
        "falkirk":
            "falkirk",

        # St Johnstone
        "st johnstone":
            "st johnstone",

        "st johnstones":
            "st johnstone",

        # St Mirren
        "st mirren":
            "st mirren",
    }

    return aliases.get(
        name,
        name
    )


def _load_fixture_data() -> list[dict]:
    """
    Load fixtures from the normalised data file.
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
            "WARNING: fixture data is not a JSON object"
        )

        return []

    fixtures = data.get(
        "fixtures",
        []
    )

    if not isinstance(
        fixtures,
        list
    ):

        print(
            "WARNING: fixture data does not contain "
            "a valid fixtures list"
        )

        return []

    return fixtures


def _parse_kickoff(value):
    """
    Convert stored ISO timestamp into a timezone-aware
    datetime.

    Supports:

        2026-08-09T15:00:00+00:00

        2026-08-09T15:00:00Z

        2026-08-09 15:00:00Z

    and timezone-naive values.
    """

    if not value:
        return None

    # ---------------------------------------------------------
    # The data layer normally stores strings.
    #
    # This additional check makes the function safe if a
    # datetime object is passed in directly.
    # ---------------------------------------------------------

    if isinstance(
        value,
        datetime
    ):

        if value.tzinfo is None:

            value = value.replace(
                tzinfo=UK_TZ
            )

        return value.astimezone(
            UK_TZ
        )

    try:

        value = value.strip()

        # -----------------------------------------------------
        # Convert trailing Z to an ISO timezone.
        # -----------------------------------------------------

        value = value.replace(
            "Z",
            "+00:00"
        )

        kickoff = datetime.fromisoformat(
            value
        )

        # -----------------------------------------------------
        # If no timezone was supplied, assume UK time.
        # -----------------------------------------------------

        if kickoff.tzinfo is None:

            kickoff = kickoff.replace(
                tzinfo=UK_TZ
            )

        return kickoff.astimezone(
            UK_TZ
        )

    except (
        ValueError,
        TypeError,
        AttributeError,
    ):

        return None


def get_fixtures(team: dict) -> list[dict]:
    """
    Public interface used by generator.py.

    Returns fixtures for one team in the format expected by
    the existing EPG system:

        {
            "home": str,
            "away": str,
            "kickoff": datetime,
            "competition": str,
