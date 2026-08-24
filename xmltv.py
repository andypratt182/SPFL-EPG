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

from fixtures import get_head_to_head_result, get_last_result
from normalisation import normalise_team_name
from teams import SPFL_TEAMS, get_derby_label
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


def _competition_clause(competition: str | None, round_label: str | None = None) -> str:
    """
    A natural-language clause describing the competition, including
    its own leading space -- e.g. " in the Scottish Premiership",
    " in a friendly match", or "" if there's nothing sensible to say
    (competition unknown). Designed to be embedded directly after
    "{home} take on {away}" / "{home} taking on {away}".

    round_label, if present, is appended -- e.g. " in the Scottish
    Cup Quarter Final". Comes from the fixture feed's own SUMMARY
    text (see ics.py's parse_match_summary), so it's shown exactly
    as the feed wrote it rather than reformatted.
    """

    if competition in _UNKNOWN_COMPETITION_VALUES:
        return ""

    if competition == "Friendly":
        base = " in a friendly match"
    else:
        base = f" in the {competition}"

    if round_label:
        base += f" {round_label}"

    return base


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
    genuinely new information -- see _narrative_sentence), a demonym
    for the opponent (home fixtures only -- see below), a derby
    label if this pairing is a known rivalry (either home or away),
    their most recent result if recent enough to be worth mentioning,
    and the result of their last meeting THIS season against this
    specific opponent if they've already played (takes priority over
    the generic last result -- see _narrative_sentence).
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
        "derby": get_derby_label(our_team, opponent),
        "last_result": get_last_result(our_team),
        "head_to_head": get_head_to_head_result(our_team, opponent),
        "is_european": match.get("competition_type") == "EUROPEAN",
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


def _last_result_clause(last_result: dict | None) -> str:
    """
    Trailing clause referencing the team's most recent result, e.g.
    ", after their 2-1 win over Hearts" -- including its own leading
    comma and space. Deliberately placed at the very END of the full
    sentence by the caller (after the competition clause), not
    inserted in the middle: "...at Ibrox Stadium, after their 2-1
    win over Hearts, in the Scottish Premiership" reads as if the
    competition belongs to the Hearts result, not the fixture being
    described. Empty string if there's no result recent enough to
    reference (see fixtures.get_last_result).
    """

    if last_result is None:
        return ""

    opponent = last_result["opponent"]
    our_score = last_result["our_score"]
    their_score = last_result["their_score"]
    outcome = last_result["outcome"]

    if outcome == "win":
        return f", after their {our_score}-{their_score} win over {opponent}"

    if outcome == "loss":
        return f", after their {our_score}-{their_score} defeat to {opponent}"

    return f", after their {our_score}-{their_score} draw with {opponent}"


def _head_to_head_clause(head_to_head: dict | None, is_european: bool) -> str:
    """
    Trailing clause for a repeat meeting against the SAME opponent
    this season -- more specific and more useful than generic recent
    form, so this takes priority over _last_result_clause when both
    are available (see _form_clause). Two phrasings:

      - European fixtures ("{team} in {country}, taking on..." or
        "{team} travel to {country}..." elsewhere in the sentence --
        i.e. this pairing already involves a non-Scottish opponent):
        "...after winning the first leg 1-0". UEFA qualifying rounds
        are two-legged, so a repeat meeting against the same
        European opponent within the same season is overwhelmingly
        likely to be the second leg of the same tie -- there's no
        structural way to be 100% certain (no explicit "leg" data
        from the feed), but this is a safe, well-founded assumption.
      - Domestic fixtures: "...after winning 2-1 the last time these
        sides met" -- deliberately doesn't restate the opponent's
        name, since it's the same opponent as the current fixture.

    Empty string if these two teams haven't met yet this season (see
    fixtures.get_head_to_head_result).
    """

    if head_to_head is None:
        return ""

    our_score = head_to_head["our_score"]
    their_score = head_to_head["their_score"]
    outcome = head_to_head["outcome"]

    if is_european:
        if outcome == "win":
            return f", after winning the first leg {our_score}-{their_score}"
        if outcome == "loss":
            return f", after losing the first leg {our_score}-{their_score}"
        return f", after a {our_score}-{their_score} draw in the first leg"

    if outcome == "win":
        return f", after winning {our_score}-{their_score} the last time these sides met"
    if outcome == "loss":
        return f", after losing {our_score}-{their_score} the last time these sides met"
    return f", after a {our_score}-{their_score} draw the last time these sides met"


def _form_clause(parts: dict) -> str:
    """
    The trailing "recent form" clause -- head-to-head against this
    specific opponent if they've already met this season, otherwise
    generic recent form, otherwise nothing. Showing both would be
    redundant/cluttered, so only one ever appears.
    """

    return _head_to_head_clause(parts["head_to_head"], parts["is_european"]) or _last_result_clause(
        parts["last_result"]
    )


def _opponent_label(parts: dict) -> str:
    """
    The opponent's name, prefixed with whichever is relevant: a
    derby label ("Old Firm rivals Celtic") or a non-Scottish demonym
    ("Czech opposition FK Jablonec 97"). Derby takes priority, though
    in practice the two never overlap -- a derby only fires between
    two Scottish clubs, a demonym only fires for a non-Scottish
    opponent.
    """

    opponent = parts["opponent"]

    if parts["derby"]:
        return f"{parts['derby']} {opponent}"

    if parts["demonym"]:
        return f"{parts['demonym']} opposition {opponent}"

    return opponent


def _narrative_sentence(
    parts: dict, venue: str, competition: str, *, gerund: bool, round_label: str | None = None
) -> str:
    """
    The core "Team host/travel..." sentence (no "Live coverage of"
    prefix or trailing "Kick-off is..." -- callers add those).
    Reframed around the channel's own club rather than generic
    home/away, since that's who the channel exists for:

      - Home, no derby/demonym: "{team} host(ing) {opponent} at
        {venue}{competition}."
      - Home, known derby: "{team} host(ing) {derby label} {opponent}
        at {venue}{competition}." -- e.g. "Rangers hosting Old Firm
        rivals Celtic...".
      - Home, non-Scottish opponent (no derby possible): "{team}
        host(ing) {demonym} opposition {opponent} at {venue}
        {competition}." -- e.g. "Rangers hosting Czech opposition FK
        Jablonec 97...".
      - Away, in Scotland, no derby: "{team} travel(ling) to {venue}
        to take on {opponent}{competition}." -- naming the country
        here would be redundant/odd for a routine domestic away trip.
      - Away, known derby: "...to take on {derby label} {opponent}
        {competition}." -- derby applies to away fixtures too, e.g.
        "Rangers travel to Celtic Park to take on Old Firm rivals
        Celtic...".
      - Away, abroad, "Next Game" form (gerund=False): "{team}
        travel to {country} to take on {opponent} at {venue}
        {competition}." -- describes something still upcoming, so
        "travel to" is accurate.
      - Away, abroad, live form (gerund=True): "{team} in {country},
        taking on {opponent} at {venue}{competition}." -- "travelling
        to Germany" reads oddly for something already live; "in
        Germany" reads naturally for coverage that's happening now.

    Derby and demonym never actually collide: a derby only fires
    between two Scottish clubs, a demonym only fires for a
    non-Scottish opponent -- but derby takes priority in
    _opponent_label() regardless, since it's the more specific fact.

    In both away-abroad cases, {country} is run through
    _country_phrase() first, so a handful of country names get a
    leading "the" where English grammar requires it ("the Czech
    Republic") without affecting the rest ("Germany").

    Whichever of the above applies, a form clause (see _form_clause
    -- head-to-head against this opponent if they've met already
    this season, otherwise generic recent form) is always appended
    last, after the competition -- so it never gets grammatically
    confused with the competition of the CURRENT fixture.
    """

    clause = _competition_clause(competition, round_label)
    our_team = parts["our_team"]
    opponent = _opponent_label(parts)

    if parts["is_home"]:
        verb = "hosting" if gerund else "host"
        sentence = f"{our_team} {verb} {opponent} at {venue}{clause}"

    elif parts["country"]:
        country = _country_phrase(parts["country"])
        if gerund:
            sentence = f"{our_team} in {country}, taking on {opponent} at {venue}{clause}"
        else:
            sentence = f"{our_team} travel to {country} to take on {opponent} at {venue}{clause}"

    else:
        verb = "travelling" if gerund else "travel"
        sentence = f"{our_team} {verb} to {venue} to take on {opponent}{clause}"

    return sentence + _form_clause(parts)


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


def _derby_title_suffix(parts: dict) -> str:
    """
    A short, title-friendly derby marker with its own leading space,
    e.g. " (Old Firm)", " (Tayside derby)" -- or "" if this fixture
    isn't a known rivalry. Derived from the same derby label used in
    the description ("Old Firm rivals" -> "Old Firm") rather than a
    separately maintained short form, so the two can't drift apart.
    """

    derby = parts.get("derby")

    if not derby:
        return ""

    short = derby.removesuffix(" rivals").strip()

    return f" ({short})"


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
        round_label = next_match.get("round")
        venue = _venue_for(next_match)
        kickoff_time = local_kickoff.strftime("%-I:%M %p")

        parts = _match_parts(channel_id, next_match)

        title = f"Next Game: {home} vs {away}{_derby_title_suffix(parts)} | {day_text}"

        sentence = _narrative_sentence(parts, venue, competition, gerund=False, round_label=round_label)

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
    round_label = match.get("round")
    venue = _venue_for(match)

    kickoff = parse_kickoff(match.get("kickoff"))
    kickoff_time = kickoff.astimezone(UK_TZ).strftime("%-I:%M %p") if kickoff else "TBC"

    parts = _match_parts(channel_id, match)

    title = f"⚽ {match['home']} vs {match['away']}{_derby_title_suffix(parts)} ˡⁱᵛᵉ 🔴"

    sentence = _narrative_sentence(parts, venue, competition, gerund=True, round_label=round_label)

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
