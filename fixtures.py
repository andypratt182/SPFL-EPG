"""
fixtures.py

Public fixture interface used by generator.py. Fixtur.es is the live
fixture source (see sources/fixtur_es.py); this module windows and
filters its output per-team.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from normalisation import normalise_team_name
from sources.fixtur_es import get_all_fixtures
from teams import SPFL_TEAMS

logger = logging.getLogger(__name__)

UK_TZ = ZoneInfo("Europe/London")

# How far ahead of "now" to include fixtures in the generated EPG.
# Must stay >= xmltv.py's EPG_DURATION -- if this is narrower, it
# silently clips fixtures before they ever reach the EPG window, no
# matter how wide EPG_DURATION is set.
FIXTURE_DAYS = 60

_ALL_FIXTURES: list[dict] | None = None


def _load_fixtures() -> list[dict]:
    """Download the Fixtur.es calendars once per generator run.

    generator.py calls get_fixtures() once per channel (12 times), so
    caching here avoids downloading the same feeds 12 times over.
    """

    global _ALL_FIXTURES

    if _ALL_FIXTURES is None:
        _ALL_FIXTURES = get_all_fixtures()

    return _ALL_FIXTURES


def _parse_kickoff(value) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        kickoff = value
    else:
        try:
            normalised = str(value).strip()
            if normalised.endswith("Z"):
                normalised = normalised[:-1] + "+00:00"
            kickoff = datetime.fromisoformat(normalised)
        except ValueError:
            return None

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=UK_TZ)

    return kickoff.astimezone(UK_TZ)


def _stadium_for(home: str) -> str:
    """Look up the known stadium for a home team via teams.py.

    Falling back to SPFL_TEAMS here (rather than duplicating stadium
    data in the Fixtur.es importer) means there's one place that
    knows each club's home ground.
    """

    target = normalise_team_name(home)

    for team in SPFL_TEAMS.values():
        if normalise_team_name(team.get("name", "")) == target:
            return team.get("stadium", "Venue TBC")

    return "Venue TBC"


def get_fixtures(team: dict) -> list[dict]:
    """Return upcoming fixtures for one team, within FIXTURE_DAYS."""

    target = normalise_team_name(team.get("name", ""))

    now = datetime.now(UK_TZ)
    window_end = now + timedelta(days=FIXTURE_DAYS)

    fixtures = []

    for fixture in _load_fixtures():
        home = fixture.get("home", "")
        away = fixture.get("away", "")

        if not home or not away:
            continue

        if normalise_team_name(home) != target and normalise_team_name(away) != target:
            continue

        kickoff = _parse_kickoff(fixture.get("kickoff"))

        if kickoff is None or kickoff < now or kickoff > window_end:
            continue

        fixtures.append(
            {
                "home": home,
                "away": away,
                "kickoff": kickoff,
                "competition": fixture.get("competition", "Unknown"),
                "competition_type": fixture.get("competition_type", "UNKNOWN"),
                "classification_status": fixture.get("classification_status", "UNKNOWN"),
                "venue": fixture.get("venue", "Venue TBC"),
            }
        )

    fixtures.sort(key=lambda fixture: fixture["kickoff"])

    return fixtures


# How many days back to look for a completed result before treating
# it as too stale to reference (off-season, international break,
# long injury-enforced gap, etc).
RECENT_RESULT_WITHIN_DAYS = 14


def get_last_result(team_name: str, *, within_days: int = RECENT_RESULT_WITHIN_DAYS) -> dict | None:
    """
    Return the team's most recent COMPLETED fixture -- kickoff
    already passed, both scores present -- within the last
    `within_days` days, or None if there isn't one.

    The Fixtur.es feeds contain a full season's fixtures including
    past results with scores embedded in the SUMMARY field (already
    parsed into home_score/away_score by sources/fixtur_es.py), but
    get_fixtures() above only ever returns UPCOMING fixtures -- this
    is a separate lookup over the same underlying (cached) data for
    the opposite direction.
    """

    target = normalise_team_name(team_name)

    now = datetime.now(UK_TZ)
    cutoff = now - timedelta(days=within_days)

    candidates = []

    for fixture in _load_fixtures():
        home = fixture.get("home", "")
        away = fixture.get("away", "")

        if normalise_team_name(home) != target and normalise_team_name(away) != target:
            continue

        if fixture.get("home_score") is None or fixture.get("away_score") is None:
            continue

        kickoff = _parse_kickoff(fixture.get("kickoff"))

        if kickoff is None or kickoff >= now or kickoff < cutoff:
            continue

        candidates.append((kickoff, fixture))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    kickoff, fixture = candidates[0]

    home = fixture["home"]
    away = fixture["away"]
    home_score = fixture["home_score"]
    away_score = fixture["away_score"]

    is_home = normalise_team_name(home) == target
    our_score = home_score if is_home else away_score
    their_score = away_score if is_home else home_score
    opponent = away if is_home else home

    if our_score > their_score:
        outcome = "win"
    elif our_score < their_score:
        outcome = "loss"
    else:
        outcome = "draw"

    return {
        "opponent": opponent,
        "our_score": our_score,
        "their_score": their_score,
        "outcome": outcome,
        "kickoff": kickoff,
    }
