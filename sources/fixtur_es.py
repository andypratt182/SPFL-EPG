"""
sources/fixtur_es.py

Fixtur.es fixture source adapter.

Downloads per-team and per-competition .ics calendars from
ics.fixtur.es, cross-references them to classify each fixture by
competition, and returns a merged, deduplicated fixture list.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ics import (
    download_ics,
    localise,
    parse_ics_datetime,
    parse_match_summary,
    property_value,
    split_events,
)
from normalisation import SPFL_TEAMS, is_spfl_team, normalise_team_name
from venues import get_venue

logger = logging.getLogger(__name__)

UK_TZ = ZoneInfo("Europe/London")


# ============================================================
# FIXTUR.ES SOURCE CONFIGURATION
# ============================================================

TEAM_CALENDARS = {
    "Rangers": "https://ics.fixtur.es/v2/rangers.ics",
    "Celtic": "https://ics.fixtur.es/v2/celtic.ics",
    "Aberdeen": "https://ics.fixtur.es/v2/aberdeen.ics",
    "Dundee": "https://ics.fixtur.es/v2/dundee-fc.ics",
    "Dundee United": "https://ics.fixtur.es/v2/dundee-united.ics",
    "Hearts": "https://ics.fixtur.es/v2/heart-of-midlothian.ics",
    "Hibernian": "https://ics.fixtur.es/v2/hibernian.ics",
    "Kilmarnock": "https://ics.fixtur.es/v2/kilmarnock.ics",
    "Motherwell": "https://ics.fixtur.es/v2/motherwell.ics",
    "Falkirk": "https://ics.fixtur.es/v2/falkirk.ics",
    "St Johnstone": "https://ics.fixtur.es/v2/st-johnstone.ics",
    "St Mirren": "https://ics.fixtur.es/v2/st-mirren.ics",
}

COMPETITION_CALENDARS = {
    "Scottish Premiership": "https://ics.fixtur.es/v2/league/scottish-premier-league.ics",
    "Scottish Championship": "https://ics.fixtur.es/v2/league/scottish-championship.ics",
    "Scottish League One": "https://ics.fixtur.es/v2/league/scottish-league-one.ics",
    "Scottish League Two": "https://ics.fixtur.es/v2/league/scottish-league-two.ics",
    "Scottish Cup": "https://ics.fixtur.es/v2/league/scottish-cup.ics",
    "Scottish League Cup": "https://ics.fixtur.es/v2/league/scottish-league-cup.ics",
    "UEFA Champions League": "https://ics.fixtur.es/v2/league/champions-league.ics",
    "UEFA Europa League": "https://ics.fixtur.es/v2/league/europa-league.ics",
    "UEFA Conference League": "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
}


# ============================================================
# SEASON WINDOW
# ============================================================

def current_season_bounds(reference: datetime | None = None) -> tuple[datetime, datetime]:
    """
    Return (start, end) of the Scottish football season (1 July -
    30 June) containing `reference` (defaults to now, UK time).

    This used to be a hardcoded "2026/27" literal, which meant the
    importer would silently return zero fixtures every July until
    someone remembered to bump it by hand.
    """

    now = reference or datetime.now(UK_TZ)

    start_year = now.year if now.month >= 7 else now.year - 1

    start = datetime(start_year, 7, 1, tzinfo=UK_TZ)
    end = datetime(start_year + 1, 6, 30, 23, 59, 59, tzinfo=UK_TZ)

    return start, end


# ============================================================
# TEAM NAME MATCHING
#
# normalise_team_name / is_spfl_team / SPFL_TEAMS now live in
# normalisation.py, shared with fixtures.py, venues.py, and
# tools/inspect_fixtur_es.py.
# ============================================================


# ============================================================
# PLACEHOLDER / SEASON FILTERING
# ============================================================

def is_placeholder_fixture(raw_kickoff, kickoff, home, away, competition) -> bool:
    """
    Fixtur.es sometimes emits a placeholder fixture at midnight with
    no competition assigned, before the real fixture is confirmed.
    Detect and drop those rather than showing a fake midnight kickoff.
    """

    if kickoff is None or competition or not raw_kickoff:
        return False

    raw_value = raw_kickoff.strip()

    is_midnight = raw_value.endswith("T000000") or raw_value.endswith("T0000")

    if not is_midnight:
        return False

    return is_spfl_team(home) and is_spfl_team(away)


def is_in_season(kickoff: datetime | None, season_start: datetime, season_end: datetime) -> bool:
    if kickoff is None:
        return False

    local = localise(kickoff, UK_TZ)

    return season_start <= local <= season_end


# ============================================================
# EVENT CONVERSION
# ============================================================

def parse_event(
    lines: list[str],
    source_type: str,
    source_name: str,
    season_start: datetime,
    season_end: datetime,
    competition: str | None = None,
) -> dict | None:
    """Convert one VEVENT into the internal fixture structure."""

    uid = property_value(lines, "UID")
    summary = property_value(lines, "SUMMARY")
    dtstart = property_value(lines, "DTSTART")
    dtend = property_value(lines, "DTEND")
    status = property_value(lines, "STATUS")
    sequence = property_value(lines, "SEQUENCE")
    description = property_value(lines, "DESCRIPTION")
    location = property_value(lines, "LOCATION")

    if not summary or not dtstart:
        return None

    home, away, home_score, away_score = parse_match_summary(summary)

    if not home or not away:
        return None

    raw_kickoff = dtstart.strip()
    kickoff = parse_ics_datetime(raw_kickoff)

    if kickoff is None:
        return None

    if is_placeholder_fixture(raw_kickoff, kickoff, home, away, competition):
        return None

    kickoff = localise(kickoff, UK_TZ)

    if not is_in_season(kickoff, season_start, season_end):
        return None

    end = parse_ics_datetime(dtend)
    if end is not None:
        end = localise(end, UK_TZ)

    # Prefer the feed's own LOCATION; fall back to our venue database.
    if location:
        venue = location.strip()
    else:
        context = f"vs {away}, {competition or source_name}, {kickoff.strftime('%Y-%m-%d %H:%M')}"
        venue = get_venue(home, context=context)

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "end": end,
        "competition": competition,
        "venue": venue,
        "source": "fixtur.es",
        "source_type": source_type,
        "source_name": source_name,
        "source_id": uid,
        "status": status,
        "sequence": sequence,
        "description": description,
        "home_score": home_score,
        "away_score": away_score,
    }


def parse_calendar(
    text: str,
    source_type: str,
    source_name: str,
    season_start: datetime,
    season_end: datetime,
    competition: str | None = None,
) -> tuple[list[list[str]], list[dict]]:
    events = split_events(text)

    fixtures = []

    for event in events:
        fixture = parse_event(
            event, source_type, source_name, season_start, season_end, competition
        )

        if fixture is not None:
            fixtures.append(fixture)
        elif competition:
            _log_if_unparseable_summary(event, competition)

    return events, fixtures


def _log_if_unparseable_summary(event: list[str], competition: str) -> None:
    """
    Distinguish a genuine SUMMARY-parsing failure from a fixture that
    was correctly parsed but legitimately filtered out (out of
    season, placeholder). Only the former is worth a warning -- see
    parse_calendar's docstring-equivalent comment above.
    """

    summary = property_value(event, "SUMMARY")
    home, away, _, _ = parse_match_summary(summary)

    if not home or not away:
        logger.warning(
            "%s: could not parse fixture from SUMMARY: %r", competition, summary
        )


# ============================================================
# FIXTURE IDENTITY
# ============================================================

def fixture_signature(fixture: dict) -> tuple[str, str, str]:
    """Exact signature: date + time to the minute + both team names."""

    kickoff = fixture.get("kickoff")

    if isinstance(kickoff, datetime):
        kickoff_key = localise(kickoff, UK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    else:
        kickoff_key = str(kickoff)

    home = normalise_team_name(fixture.get("home", ""))
    away = normalise_team_name(fixture.get("away", ""))

    return kickoff_key, home.lower(), away.lower()


def fixture_date_signature(fixture: dict) -> tuple | None:
    """
    Same-day signature that ignores kickoff time.

    Used as a tolerant fallback when the team calendar and a
    competition calendar agree on the date and teams but disagree on
    the exact kickoff minute (e.g. a provisional vs. confirmed
    kickoff time). Without this, a genuinely competitive fixture can
    fall through to "Friendly" purely because of a kickoff-time
    discrepancy between feeds -- which is exactly what was happening
    before this fallback was added.
    """

    kickoff = fixture.get("kickoff")

    if not isinstance(kickoff, datetime):
        return None

    local = localise(kickoff, UK_TZ)
    home = normalise_team_name(fixture.get("home", ""))
    away = normalise_team_name(fixture.get("away", ""))

    return local.date(), home.lower(), away.lower()


# ============================================================
# TEAM / COMPETITION CALENDARS
# ============================================================

def load_team_fixtures(season_start: datetime, season_end: datetime) -> list[dict]:
    all_fixtures = []

    logger.info("Loading Fixtur.es team calendars (%d feeds)", len(TEAM_CALENDARS))

    for team, url in TEAM_CALENDARS.items():
        try:
            text = download_ics(url)
            events, fixtures = parse_calendar(
                text, source_type="team", source_name=team,
                season_start=season_start, season_end=season_end,
            )
            logger.info(
                "%s: %d VEVENT records, %d usable in-season fixtures",
                team, len(events), len(fixtures),
            )
            all_fixtures.extend(fixtures)
        except Exception as error:  # noqa: BLE001 - one team failing shouldn't stop the rest
            logger.error("Error loading %s: %s", team, error)

    return all_fixtures


def load_competition_fixtures(
    calendars: dict[str, str], season_start: datetime, season_end: datetime
) -> list[dict]:
    all_fixtures = []

    logger.info("Loading competition calendars (%d feeds)", len(calendars))

    for competition, url in calendars.items():
        try:
            text = download_ics(url)
            events, fixtures = parse_calendar(
                text, source_type="competition", source_name=competition,
                competition=competition, season_start=season_start, season_end=season_end,
            )
            logger.info(
                "%s: %d VEVENT records, %d usable in-season records",
                competition, len(events), len(fixtures),
            )
            all_fixtures.extend(fixtures)
        except Exception as error:  # noqa: BLE001
            logger.error("Error loading %s: %s", competition, error)

    return all_fixtures


# ============================================================
# COMPETITION TYPE
# ============================================================

def competition_type_for(competition: str | None) -> str:
    if not competition:
        return "UNKNOWN"

    value = competition.lower()

    if value == "friendly":
        return "FRIENDLY"
    if value.startswith("uefa "):
        return "EUROPEAN"
    if value.startswith("scottish "):
        return "DOMESTIC"

    return "UNKNOWN"


# ============================================================
# CLASSIFICATION
# ============================================================

def build_competition_date_index(competition_fixtures: list[dict]) -> dict:
    index: dict = {}

    for fixture in competition_fixtures:
        signature = fixture_date_signature(fixture)
        if signature is not None:
            index.setdefault(signature, []).append(fixture)

    return index


def _apply_competition_match(fixture: dict, matches: list[dict], status: str) -> dict:
    selected = next((item for item in matches if item.get("competition")), matches[0])
    competition = selected.get("competition")

    fixture["competition"] = competition
    fixture["competition_type"] = competition_type_for(competition)
    fixture["classification_status"] = status
    fixture["competition_source_ids"] = [
        item.get("source_id") for item in matches if item.get("source_id")
    ]
    fixture["matched_competition_sources"] = [
        item.get("source_name") for item in matches if item.get("source_name")
    ]

    return fixture


def classify_fixture(
    fixture: dict,
    competition_index: dict,
    competition_date_index: dict | None = None,
) -> dict:
    """
    Classify a fixture's competition.

    1. Exact match: same date, same minute, same teams.
    2. Tolerant match: same date and teams, different kickoff time
       (see fixture_date_signature's docstring for why this matters).
    3. Both clubs SPFL, no match at all -> flagged as potentially
       missing rather than guessed.
    4. Otherwise -> Friendly (e.g. genuine pre-season friendlies
       against non-SPFL opponents with no competition evidence).
    """

    matches = competition_index.get(fixture_signature(fixture), [])

    if matches:
        return _apply_competition_match(fixture, matches, "CONFIRMED_COMPETITIVE")

    if competition_date_index:
        date_matches = competition_date_index.get(fixture_date_signature(fixture), [])
        if date_matches:
            return _apply_competition_match(
                fixture, date_matches, "CONFIRMED_COMPETITIVE_TIME_ADJUSTED"
            )

    home, away = fixture.get("home", ""), fixture.get("away", "")

    if is_spfl_team(home) and is_spfl_team(away):
        fixture["competition"] = "Unclassified"
        fixture["competition_type"] = "UNKNOWN"
        fixture["classification_status"] = "POTENTIALLY_MISSING_COMPETITION"
    else:
        fixture["competition"] = "Friendly"
        fixture["competition_type"] = "FRIENDLY"
        fixture["classification_status"] = "FRIENDLY"

    fixture["competition_source_ids"] = []
    fixture["matched_competition_sources"] = []

    return fixture


# ============================================================
# MERGE / DEDUPLICATE / SORT
# ============================================================

def merge_fixture_sources(team_fixtures: list[dict], competition_fixtures: list[dict]) -> list[dict]:
    competition_index: dict = {}
    for fixture in competition_fixtures:
        competition_index.setdefault(fixture_signature(fixture), []).append(fixture)

    competition_date_index = build_competition_date_index(competition_fixtures)

    merged: dict = {}

    for fixture in team_fixtures:
        signature = fixture_signature(fixture)

        if signature not in merged:
            entry = dict(fixture)
            entry["verified_by_team_calendar"] = True
            entry["team_sources"] = [fixture.get("source_name")]
            merged[signature] = entry
            continue

        existing = merged[signature]
        existing["verified_by_team_calendar"] = True

        source_name = fixture.get("source_name")
        existing.setdefault("team_sources", [])
        if source_name and source_name not in existing["team_sources"]:
            existing["team_sources"].append(source_name)

        if existing.get("home_score") is None and fixture.get("home_score") is not None:
            existing["home_score"] = fixture["home_score"]
            existing["away_score"] = fixture["away_score"]

    classified = [
        classify_fixture(fixture, competition_index, competition_date_index)
        for fixture in merged.values()
    ]

    classified.sort(key=lambda fixture: fixture.get("kickoff") or datetime.max.replace(tzinfo=UK_TZ))

    return classified


# ============================================================
# AUDIT LOGGING
# ============================================================

def log_source_statistics(team_fixtures: list[dict], competition_fixtures: list[dict], fixtures: list[dict]) -> None:
    counts = {"CONFIRMED_COMPETITIVE": 0, "CONFIRMED_COMPETITIVE_TIME_ADJUSTED": 0, "FRIENDLY": 0, "POTENTIALLY_MISSING_COMPETITION": 0}

    for fixture in fixtures:
        status = fixture.get("classification_status", "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1

    logger.info(
        "Fixtur.es import: %d team records, %d competition records -> %d unique fixtures",
        len(team_fixtures), len(competition_fixtures), len(fixtures),
    )
    logger.info("Classification breakdown: %s", counts)

    competition_counts: dict[str, int] = {}
    for fixture in fixtures:
        competition = fixture.get("competition") or "Unclassified"
        competition_counts[competition] = competition_counts.get(competition, 0) + 1

    logger.info("Competition breakdown: %s", dict(sorted(competition_counts.items())))

    missing = [
        f for f in fixtures if f.get("classification_status") == "POTENTIALLY_MISSING_COMPETITION"
    ]
    for fixture in missing:
        logger.warning(
            "Potentially missing competition: %s vs %s (%s)",
            fixture.get("home"), fixture.get("away"), fixture.get("kickoff"),
        )


# ============================================================
# PUBLIC API
# ============================================================

def get_all_fixtures() -> list[dict]:
    season_start, season_end = current_season_bounds()

    logger.info(
        "Fixtur.es import for season %d/%d (%s to %s)",
        season_start.year, season_end.year % 100, season_start.date(), season_end.date(),
    )

    team_fixtures = load_team_fixtures(season_start, season_end)
    competition_fixtures = load_competition_fixtures(COMPETITION_CALENDARS, season_start, season_end)

    fixtures = merge_fixture_sources(team_fixtures, competition_fixtures)

    log_source_statistics(team_fixtures, competition_fixtures, fixtures)

    logger.info("Fixtur.es import complete: %d fixtures", len(fixtures))

    return fixtures


def build_fixtures() -> list[dict]:
    """Backwards-compatible alias for get_all_fixtures()."""

    return get_all_fixtures()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    get_all_fixtures()
