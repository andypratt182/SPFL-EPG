"""
fixtures.py

Drop-in replacement for the old SportMonks-based fixtures.py.
Same public interface (get_fixtures(team) -> list[dict]) so
generator.py and xmltv.py do not need to change.

Data flow:
    scraper.py + espn_team_ids.py -> one ESPN fixtures page fetched
        per team, already filtered to that team's own matches
    overrides.json -> manual additions / corrections you maintain
    fixtures.py -> merges both, returns fixtures in the shape
        generator.py expects:
            {
                "home": str,
                "away": str,
                "kickoff": datetime,
                "competition": str,
            }
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta, date

from zoneinfo import ZoneInfo

import scraper
from espn_team_ids import ESPN_TEAM_IDS

UK_TZ = ZoneInfo("Europe/London")

# How many days ahead of today to include fixtures for.
FIXTURE_DAYS = 24

OVERRIDES_PATH = Path(__file__).parent / "overrides.json"

# Module-level cache: scrape every team once per run, no matter how
# many times get_fixtures() is called.
_all_team_fixtures_cache = None


def normalise_team_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", " ", name)
    for suffix in (" football club", " fc"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return " ".join(name.split())


def _load_overrides() -> list[dict]:
    """
    overrides.json format - a flat list of fixture objects you maintain
    by hand, e.g.:

    [
      {
        "home": "Celtic",
        "away": "Rangers",
        "kickoff": "2026-09-05T15:00:00",
        "competition": "Scottish Premiership"
      }
    ]

    Use this for fixtures the scraper missed, got wrong, or for
    postponed/rearranged matches before ESPN updates their page.
    """
    if not OVERRIDES_PATH.exists():
        return []

    with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
        raw_overrides = json.load(f)

    parsed = []
    for entry in raw_overrides:
        try:
            kickoff = datetime.fromisoformat(entry["kickoff"])
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=UK_TZ)
            parsed.append(
                {
                    "home": entry["home"],
                    "away": entry["away"],
                    "kickoff": kickoff,
                    "competition": entry["competition"],
                }
            )
        except (KeyError, ValueError) as e:
            print(f"WARNING: skipping malformed override entry {entry}: {e}")

    return parsed


def _get_all_team_fixtures() -> dict:
    """
    Scrapes ESPN for every team in ESPN_TEAM_IDS and caches the
    result for the rest of this run.
    """
    global _all_team_fixtures_cache
    if _all_team_fixtures_cache is not None:
        return _all_team_fixtures_cache

    print()
    print("==============================")
    print("FETCHING FIXTURES FROM ESPN")
    print("==============================")

    _all_team_fixtures_cache = scraper.fetch_all_teams(ESPN_TEAM_IDS, debug_first=False)
    return _all_team_fixtures_cache


def get_fixtures(team: dict) -> list[dict]:
    """
    Same interface as the old SportMonks version:
    returns upcoming fixtures (within FIXTURE_DAYS) for a single team
    (as defined in SPFL_TEAMS), in the format generator.py expects.
    """
    team_name = team["name"]
    if team_name.endswith(" TV"):
        team_name = team_name[:-3]

    all_team_fixtures = _get_all_team_fixtures()

    # ESPN_TEAM_IDS keys should match SPFL_TEAMS names (minus " TV").
    # Fall back to a normalised match in case of minor spelling
    # differences between the two files.
    raw_fixtures = all_team_fixtures.get(team_name)
    if raw_fixtures is None:
        target = normalise_team_name(team_name)
        for key, fixtures in all_team_fixtures.items():
            if normalise_team_name(key) == target:
                raw_fixtures = fixtures
                break
    raw_fixtures = raw_fixtures or []

    now = datetime.now(UK_TZ)
    window_end = now + timedelta(days=FIXTURE_DAYS)

    matches = []
    for fx in raw_fixtures:
        if fx.get("kickoff") is None:
            continue  # no confirmed time yet - add via overrides.json once known
        if not (now <= fx["kickoff"] <= window_end):
            continue
        matches.append(
            {
                "home": fx["home"],
                "away": fx["away"],
                "kickoff": fx["kickoff"],
                "competition": fx["competition"],
            }
        )

    # Apply overrides: add any override fixture involving this team.
    for ov in _load_overrides():
        if normalise_team_name(ov["home"]) == normalise_team_name(team_name) or \
           normalise_team_name(ov["away"]) == normalise_team_name(team_name):
            matches.append(ov)

    matches.sort(key=lambda m: m["kickoff"])
    return matches
