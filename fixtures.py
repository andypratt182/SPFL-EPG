"""
fixtures.py

Drop-in replacement for the old SportMonks-based fixtures.py.
Same public interface (get_fixtures(team) -> list[dict]) so
generator.py and xmltv.py do not need to change.

Data flow:
    scraper.py  -> raw fixtures scraped from BBC Sport
    overrides.json -> manual additions / corrections you maintain
    fixtures.py -> merges both, matches against SPFL_TEAMS,
                   returns fixtures in the shape generator.py expects:
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
from datetime import date, datetime

from zoneinfo import ZoneInfo

from teams import SPFL_TEAMS
import scraper

UK_TZ = ZoneInfo("Europe/London")

# How many days ahead to pull fixtures for.
FIXTURE_DAYS = 24

OVERRIDES_PATH = Path(__file__).parent / "overrides.json"

# Module-level cache so we only scrape once per run, no matter how
# many times get_fixtures() is called (once per team in generator.py).
_all_fixtures_cache = None


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
    postponed/rearranged matches before BBC updates their page.
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


def _get_all_fixtures() -> list[dict]:
    """
    Scrapes BBC Sport for the configured date window, merges in
    overrides.json, and caches the result for the rest of this run.
    """
    global _all_fixtures_cache
    if _all_fixtures_cache is not None:
        return _all_fixtures_cache

    print()
    print("==============================")
    print("FETCHING FIXTURES FROM BBC SPORT")
    print("==============================")

    scraped = scraper.fetch_range(date.today(), FIXTURE_DAYS)

    fixtures = []
    for fx in scraped:
        if fx.get("kickoff") is None:
            # No confirmed kickoff time yet (e.g. "TBC") - skip for now,
            # add a manual override once BBC confirms the time.
            continue
        fixtures.append(
            {
                "home": fx["home"],
                "away": fx["away"],
                "kickoff": fx["kickoff"],
                "competition": fx["competition"],
            }
        )

    overrides = _load_overrides()
    if overrides:
        print(f"Applying {len(overrides)} override(s) from overrides.json")
        fixtures.extend(overrides)

    print()
    print(f"Total scraped/override fixtures: {len(fixtures)}")
    print("==============================")

    _all_fixtures_cache = fixtures
    return fixtures


def get_fixtures(team: dict) -> list[dict]:
    """
    Same interface as the old SportMonks version:
    returns upcoming fixtures for a single team (as defined in
    SPFL_TEAMS), in the format generator.py expects.
    """
    team_name = team["name"]
    if team_name.endswith(" TV"):
        team_name = team_name[:-3]
    target = normalise_team_name(team_name)

    all_fixtures = _get_all_fixtures()

    matches = []
    for fx in all_fixtures:
        if normalise_team_name(fx["home"]) == target or normalise_team_name(fx["away"]) == target:
            matches.append(
                {
                    "home": fx["home"],
                    "away": fx["away"],
                    "kickoff": fx["kickoff"],
                    "competition": fx["competition"],
                }
            )

    matches.sort(key=lambda m: m["kickoff"])
    return matches
