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

from normalisation import normalise_team_name
from teams import SPFL_TEAMS
from venues import UNKNOWN_COUNTRY, get_demonym, get_venue_country

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


def day_and_month(dt: datetime) -> str:
    """
    e.g. "Thursday 1st Oct". Includes the month -- with the EPG now
    covering a 60-day window, "Thursday 1st" alone is ambiguous
    whenever two different months both have a matching weekday/date
    inside that window, which is common at this length.
    """

    return f"{dt.strftime('%A')} {ordinal_day(dt.day)} {dt.strftime('%b')}"


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


# Statuses that mean "we don't actually know the competition" -- see
# sources/fixtur_es.py's classify_fixture(). Showing these verbatim
# in a sentence ("in the Unclassified") reads as broken English, so
# they get a dedicated clause instead of the generic "in the X" one.
_UNKNOWN_COMPETITION_VALUES = {"Unclassified", "Unknown", "Competition TBC", None, ""}


def _competition_clause(competition: str | None) -> str:
    """
    A natural-language clause describing the competition, including
    its own leading space -- e.g. " in the Scottish Premiership",
    " in a friendly match", or "" if there's nothing sensible to say
    (competition unknown). Designed to be embedded directly after
    "{home} take on {away}" / "{home} taking on {away}".
    """

    if competition in _UNKNOWN_COMPETITION_VALUES:
        return ""

    if competition == "Friendly":
        return " in a friendly match"

    return f" in the {competition}"


def _channel_team_name(channel_id: str) -> str:
    """The channel's own club name, e.g. "Rangers" for "rangerstv"
    (SPFL_TEAMS stores the channel's display name including the
    " TV" suffix, which normalise_team_name() strips)."""

    team = SPFL_TEAMS.get(channel_id, {})
    return normalise_team_name(team.get("name", ""))


def _match_parts(channel_id: str, match: dict) -> dict:
    """
    Resolve a fixture from the channel's own club's point of view --
    whether they're home or away, who the opponent is, the country
    they're travelling to (away fixtures only, and only when it's
    genuinely new information -- see _narrative_sentence), and a
    demonym for the opponent (home fixtures only -- see below).
    """

    our_team = _channel_team_name(channel_id)
    home = match.get("home", "")
    away = match.get("away", "")

    is_home = normalise_team_name(home) == our_team
    opponent = away if is_home else home

    country = None
    demonym = None

    if is_home:
        # For a home fixture the country is never stated as part of
        # a "travel to X" clause (there's no travelling involved),
        # but the opponent's own country can still add a bit of
        # flavour as a demonym -- "Czech opposition FK Jablonec"
        # rather than just "FK Jablonec". Only for non-Scottish
        # opponents, for the same reason "Scotland" is never named
        # for a domestic away trip: it's true of every single
        # domestic fixture and so isn't actually new information.
        opponent_country = get_venue_country(opponent)
        if opponent_country not in (UNKNOWN_COUNTRY, "Scotland"):
            demonym = get_demonym(opponent_country)
    else:
        venue_country = get_venue_country(home)
        if venue_country not in (UNKNOWN_COUNTRY, "Scotland"):
            country = venue_country

    return {
        "our_team": our_team,
        "opponent": opponent,
        "is_home": is_home,
        "country": country,
        "demonym": demonym,
    }


# Country names that conventionally take a definite article in
# English -- "the Czech Republic", "the Netherlands", "the United
# States", "the Faroe Islands", "the Republic of Ireland". Most
# country names don't ("Germany", "Poland", "Brazil"). Checked
# against every country actually used in venues.json (75 total) --
# this is the complete, verified list, not a guessed subset.
# Deliberately excludes Ukraine: "the Ukraine" was once common but is
# now considered outdated/incorrect since independence.
_COUNTRIES_WITH_DEFINITE_ARTICLE = {
    "Czech Republic", "Faroe Islands", "Netherlands", "Republic of Ireland",
    "United States",
}


def _country_phrase(country: str) -> str:
    """Country name with a leading "the " when grammatically
    required, e.g. "the Czech Republic" -- otherwise unchanged."""

    if country in _COUNTRIES_WITH_DEFINITE_ARTICLE:
        return f"the {country}"

    return country


def _narrative_sentence(parts: dict, venue: str, competition: str, *, gerund: bool) -> str:
    """
    The core "Team host/travel..." sentence (no "Live coverage of"
    prefix or trailing "Kick-off is..." -- callers add those).
    Reframed around the channel's own club rather than generic
    home/away, since that's who the channel exists for:

      - Home, domestic opponent: "{team} host(ing) {opponent} at
        {venue}{competition}."
      - Home, non-Scottish opponent: "{team} host(ing) {demonym}
        opposition {opponent} at {venue}{competition}." -- e.g.
        "Rangers hosting Czech opposition FK Jablonec 97...". Only
        when a demonym is actually known; falls back to the plain
        form above otherwise rather than guessing one.
      - Away, in Scotland: "{team} travel(ling) to {venue} to take
        on {opponent}{competition}." -- naming the country here
        would be redundant/odd for a routine domestic away trip.
      - Away, abroad, "Next Game" form (gerund=False): "{team}
        travel to {country} to take on {opponent} at {venue}
        {competition}." -- describes something still upcoming, so
        "travel to" is accurate.
      - Away, abroad, live form (gerund=True): "{team} in {country},
        taking on {opponent} at {venue}{competition}." -- "travelling
        to Germany" reads oddly for something already live; "in
        Germany" reads naturally for coverage that's happening now.

    In both away-abroad cases, {country} is run through
    _country_phrase() first, so a handful of country names get a
    leading "the" where English grammar requires it ("the Czech
    Republic") without affecting the rest ("Germany").
    """

    clause = _competition_clause(competition)
    our_team = parts["our_team"]
    opponent = parts["opponent"]

    if parts["is_home"]:
        verb = "hosting" if gerund else "host"
        opponent_label = f"{parts['demonym']} opposition {opponent}" if parts["demonym"] else opponent
        return f"{our_team} {verb} {opponent_label} at {venue}{clause}"

    if parts["country"]:
        country = _country_phrase(parts["country"])
        if gerund:
            return f"{our_team} in {country}, taking on {opponent} at {venue}{clause}"
        return f"{our_team} travel to {country} to take on {opponent} at {venue}{clause}"

    verb = "travelling" if gerund else "travel"
    return f"{our_team} {verb} to {venue} to take on {opponent}{clause}"


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
        day_text = day_and_month(local_kickoff)

        home = next_match["home"]
        away = next_match["away"]
        competition = next_match.get("competition", "Competition TBC")
        venue = _venue_for(next_match)
        kickoff_time = local_kickoff.strftime("%-I:%M %p")

        title = f"Next Game: {home} vs {away} | {day_text}"

        parts = _match_parts(channel_id, next_match)
        sentence = _narrative_sentence(parts, venue, competition, gerund=False)

        description = f"{sentence}. Kick-off is scheduled for {kickoff_time}."

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

    parts = _match_parts(channel_id, match)
    sentence = _narrative_sentence(parts, venue, competition, gerund=True)

    description = f"Live coverage of {sentence}. Kick-off is at {kickoff_time}."

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
