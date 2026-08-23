"""
venues.py

Stadium lookup by team name, backed by data/venues.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from normalisation import normalise_team_name

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "venues.json"

UNKNOWN_VENUE = "Venue TBC"


def _load_venues() -> dict:
    """Load venue data from data/venues.json.

    Kept in a JSON file under data/ so venue information can be
    expanded without touching this module.
    """

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Venue data file not found: {DATA_FILE}")

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid venue JSON: {DATA_FILE}") from error

    if not isinstance(data, dict):
        raise RuntimeError(f"Venue data must be a JSON object: {DATA_FILE}")

    return data


VENUES = _load_venues()

# Pre-normalise the lookup table once at import time rather than
# re-normalising every key on every call to get_venue().
_NORMALISED_VENUES = {normalise_team_name(name): venue for name, venue in VENUES.items()}

# Known cases where the team name as it appears in fixture data
# (Fixtur.es SUMMARY parsing) doesn't match the venues.json key --
# usually an extra club-type prefix ("FK ", "SK ") or city qualifier
# ("Linz") that normalise_team_name() doesn't strip generically.
# Generic prefix/suffix stripping isn't safe here: venues.json has
# 800+ entries including short, common words as keys ("Rangers",
# "United"), so a loose substring match risks matching the wrong
# club entirely (e.g. "Rangers" matching inside "Queens Park
# Rangers"). Confirmed mismatches are added here explicitly instead.
_FIXTURE_NAME_ALIASES = {
    "FK Jablonec 97": "Jablonec",
    "LASK Linz": "LASK",
    "SK Rapid Wien": "Rapid Wien",
}


def _stadium_from(venue) -> str | None:
    if isinstance(venue, str) and venue.strip():
        return venue.strip()

    if isinstance(venue, dict):
        stadium = venue.get("stadium")
        if stadium:
            return str(stadium).strip()

    return None


def get_venue(team_name: str | None) -> str:
    """Return the stadium for a team, or "Venue TBC" if unknown."""

    if not team_name:
        return UNKNOWN_VENUE

    if team_name in VENUES:
        stadium = _stadium_from(VENUES[team_name])
        if stadium:
            return stadium

    venue = _NORMALISED_VENUES.get(normalise_team_name(team_name))

    if venue is None:
        alias = _FIXTURE_NAME_ALIASES.get(team_name)
        if alias:
            venue = VENUES.get(alias)

    stadium = _stadium_from(venue)

    if stadium:
        return stadium

    # Data-completeness gap rather than a code bug: this team just
    # isn't in venues.json under any name we tried. Logged so new
    # mismatches (an opponent's name spelled differently to how
    # venues.json has it) are visible in run logs instead of
    # silently producing "Venue TBC" forever.
    logger.warning("No venue found for %r", team_name)

    return UNKNOWN_VENUE


def has_venue(team_name: str | None) -> bool:
    """Return True if a known venue exists for the team."""

    return get_venue(team_name) != UNKNOWN_VENUE


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    test_teams = [
        "Rangers",
        "Celtic",
        "Aberdeen",
        "Dundee",
        "Dundee United",
        "Hearts",
        "Hibernian",
        "Kilmarnock",
        "Motherwell",
        "Falkirk",
        "St Johnstone",
        "St Mirren",
        "Jagiellonia Białystok",
        "LASK Linz",
        "Benfica",
        "FK Shkendija 79",
        "HJK Helsinki",
    ]

    print("=" * 60)
    print("VENUE DATABASE TEST")
    print("=" * 60)

    for team in test_teams:
        print(f"{team:30} -> {get_venue(team)}")
