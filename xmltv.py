"""
xmltv.py

Builds the XMLTV output consumed by TiviMate: channel entries (with
logos), live-match programmes, and "Next Game" filler programmes for
the gaps between matches.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from teams import SPFL_TEAMS

logger = logging.getLogger(__name__)

UK_TZ = ZoneInfo("Europe/London")

MATCH_DURATION = timedelta(hours=2)
# The actual visible EPG window. Must stay <= fixtures.py's
# FIXTURE_DAYS -- widening this alone does nothing if fixtures.py is
# still discarding fixtures beyond a narrower window first.
EPG_DURATION = timedelta(days=60)

LOGO_BASE_URL = "https://andypratt182.github.io/SPFL-EPG/logos/"
LOGO_FOLDER = Path("logos")


# ============================================================
# TIME HANDLING
# ============================================================

def parse_kickoff(value) -> datetime | None:
    """
    Convert fixture kickoff data into a timezone-aware UTC datetime.

    Supports datetime objects, XMLTV-style strings
    ("20260809150000 +0000"), and ISO 8601 strings.
    """

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if not value or not isinstance(value, str):
        return None

    value = value.strip()

    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S %z").astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def xml_time(dt: datetime) -> str:
    """Convert a datetime to XMLTV UTC format."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S") + " +0000"


def ordinal_day(day: int) -> str:
    if 11 <= day <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    return f"{day}{suffix}"


# ============================================================
# XMLTV PROGRAMME
# ============================================================

def add_programme(tv, channel_id: str, start: str, stop: str, title: str, description: str) -> None:
    if stop <= start:
        return

    programme = ET.SubElement(tv, "programme", {"start": start, "stop": stop, "channel": channel_id})
    ET.SubElement(programme, "title").text = title
    ET.SubElement(programme, "desc").text = description


def _venue_for(match: dict) -> str:
    """Fixtur.es uses "venue"; older/alternate sources have used
    "stadium" or "location". Fall back through all three."""

    return match.get("venue") or match.get("stadium") or match.get("location") or "Venue TBC"


# ============================================================
# NEXT MATCH
# ============================================================

def get_next_match(fixtures: list[dict], channel_id: str, after_time: datetime) -> dict | None:
    """Find the next fixture for this channel from the full fixture list
    (rather than assuming fixtures are pre-grouped or pre-sorted)."""

    candidates = []

    for match in fixtures:
        if match.get("channel_id") != channel_id:
            continue

        kickoff = parse_kickoff(match.get("kickoff"))

        if kickoff is None or kickoff <= after_time:
            continue

        candidates.append((kickoff, match))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])

    return candidates[0][1]


def create_next_game_programme(tv, channel_id: str, start: datetime, stop: datetime, fixtures: list[dict]) -> None:
    next_match = get_next_match(fixtures, channel_id, start)

    if next_match:
        kickoff = parse_kickoff(next_match.get("kickoff"))

        if kickoff is None:
            return

        local_kickoff = kickoff.astimezone(UK_TZ)
        day_text = f"{local_kickoff.strftime('%A')} {ordinal_day(local_kickoff.day)}"

        home = next_match["home"]
        away = next_match["away"]
        competition = next_match.get("competition", "Competition TBC")
        venue = _venue_for(next_match)
        kickoff_time = local_kickoff.strftime("%-I:%M %p")

        title = f"Next Game: {home} vs {away} | {day_text}"

        description = (
            f"{home} take on {away} in the {competition} "
            f"at {venue}. Kick-off is scheduled for {kickoff_time}."
        )

    else:
        title = "Next Game"
        description = "No upcoming fixture currently scheduled."

    add_programme(tv, channel_id, xml_time(start), xml_time(stop), title, description)


# ============================================================
# CHANNELS
# ============================================================

def create_channel_entries(tv) -> None:
    for channel_id, team in SPFL_TEAMS.items():
        channel = ET.SubElement(tv, "channel", {"id": channel_id})
        ET.SubElement(channel, "display-name").text = team["name"]

        logo_file = LOGO_FOLDER / f"{channel_id}.png"

        if logo_file.exists():
            ET.SubElement(channel, "icon", {"src": f"{LOGO_BASE_URL}{channel_id}.png"})
            logger.debug("Logo found for %s: %s", team["name"], logo_file)
        else:
            logger.warning("Logo missing for %s (%s)", team["name"], logo_file)


# ============================================================
# LIVE MATCH PROGRAMME
# ============================================================

def create_live_programme(tv, channel_id: str, match: dict, start: datetime, stop: datetime) -> None:
    competition = match.get("competition", "Competition TBC")
    venue = _venue_for(match)

    kickoff = parse_kickoff(match.get("kickoff"))
    kickoff_time = kickoff.astimezone(UK_TZ).strftime("%-I:%M %p") if kickoff else "TBC"

    title = f"⚽ {match['home']} vs {match['away']} ˡⁱᵛᵉ 🔴"

    description = (
        f"Live coverage of {match['home']} taking on {match['away']} "
        f"in the {competition} at {venue}. Kick-off is at {kickoff_time}."
    )

    add_programme(tv, channel_id, xml_time(start), xml_time(stop), title, description)


# ============================================================
# CREATE XMLTV
# ============================================================

def create_xmltv(fixtures: list[dict], filename: str) -> None:
    tv = ET.Element("tv", {"generator-info-name": "SPFL IPTV EPG"})

    create_channel_entries(tv)

    normalised_fixtures = []

    for fixture in fixtures:
        kickoff = parse_kickoff(fixture.get("kickoff"))

        if kickoff is None:
            logger.warning("Ignoring fixture with invalid kickoff: %s", fixture)
            continue

        fixture = dict(fixture)
        fixture["_kickoff_dt"] = kickoff
        normalised_fixtures.append(fixture)

    now = datetime.now(timezone.utc)
    epg_start = now.replace(minute=0, second=0, microsecond=0)
    epg_end = epg_start + EPG_DURATION

    for channel_id in SPFL_TEAMS:
        logger.info("Generating EPG for %s", channel_id)

        channel_matches = sorted(
            (
                fixture
                for fixture in normalised_fixtures
                if fixture.get("channel_id") == channel_id
                and fixture["_kickoff_dt"] < epg_end
                and fixture["_kickoff_dt"] + MATCH_DURATION > epg_start
            ),
            key=lambda fixture: fixture["_kickoff_dt"],
        )

        logger.info("  Fixtures in EPG: %d", len(channel_matches))

        current = epg_start

        for match in channel_matches:
            kickoff = match["_kickoff_dt"]
            match_end = kickoff + MATCH_DURATION

            if current < kickoff:
                next_game_start = current
                next_game_stop = min(kickoff, epg_end)

                if next_game_start < next_game_stop:
                    create_next_game_programme(
                        tv, channel_id, next_game_start, next_game_stop, normalised_fixtures
                    )

            live_start = max(kickoff, epg_start)
            live_end = min(match_end, epg_end)

            if live_start < live_end:
                create_live_programme(tv, channel_id, match, live_start, live_end)

            if match_end > current:
                current = match_end

            if current >= epg_end:
                break

        if current < epg_end:
            create_next_game_programme(tv, channel_id, current, epg_end, normalised_fixtures)

    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(tv).write(filename, encoding="utf-8", xml_declaration=True)

    logger.info("XMLTV written to %s", filename)
