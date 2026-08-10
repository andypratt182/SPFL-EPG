from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from teams import SPFL_TEAMS


UK_TZ = ZoneInfo("Europe/London")

MATCH_DURATION = timedelta(hours=2)

EPG_DURATION = timedelta(hours=240)

LOGO_BASE_URL = (
    "https://andypratt182.github.io/"
    "SPFL-EPG/logos/"
)

LOGO_FOLDER = Path("logos")


# ============================================================
# TIME HANDLING
# ============================================================

def parse_kickoff(value):
    """
    Convert fixture kickoff data into a timezone-aware UTC datetime.

    Supports both:
        - datetime objects
        - XMLTV-style strings
        - ISO 8601 strings
    """

    if isinstance(value, datetime):

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    if not value:
        return None

    if not isinstance(value, str):
        return None

    value = value.strip()

    # XMLTV format:
    # 20260809150000 +0000
    try:

        return datetime.strptime(
            value,
            "%Y%m%d%H%M%S %z"
        ).astimezone(
            timezone.utc
        )

    except ValueError:
        pass

    # ISO format:
    # 2026-08-09T15:00:00+00:00
    try:

        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00"
            )
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    except ValueError:
        return None


def format_kickoff(value):
    """
    Format a fixture kickoff in UK local time.
    """

    kickoff = parse_kickoff(value)

    if kickoff is None:
        return "Kick-off time TBC"

    return kickoff.astimezone(
        UK_TZ
    ).strftime(
        "%A %d %B %Y at %H:%M"
    )


def xml_time(dt):
    """
    Convert datetime to XMLTV UTC format.
    """

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    dt = dt.astimezone(
        timezone.utc
    )

    return (
        dt.strftime(
            "%Y%m%d%H%M%S"
        )
        + " +0000"
    )


# ============================================================
# XMLTV PROGRAMME
# ============================================================

def add_programme(
    tv,
    channel_id,
    start,
    stop,
    title,
    description
):

    if stop <= start:
        return

    programme = ET.SubElement(
        tv,
        "programme",
        {
            "start": start,
            "stop": stop,
            "channel": channel_id,
        },
    )

    ET.SubElement(
        programme,
        "title"
    ).text = title

    ET.SubElement(
        programme,
        "desc"
    ).text = description


# ============================================================
# ORDINAL DATE
# ============================================================

def ordinal_day(day):

    if 11 <= day <= 13:
        suffix = "th"

    else:
        suffix = {
            1: "st",
            2: "nd",
            3: "rd"
        }.get(
            day % 10,
            "th"
        )

    return f"{day}{suffix}"


# ============================================================
# NEXT MATCH
# ============================================================

def get_next_match(
    fixtures,
    channel_id,
    after_time
):
    """
    Find the next fixture for this specific channel.

    Important:
    This works from the complete fixture list rather than
    assuming fixtures are already grouped or ordered.
    """

    candidates = []

    for match in fixtures:

        if match.get(
            "channel_id"
        ) != channel_id:
            continue

        kickoff = parse_kickoff(
            match.get("kickoff")
        )

        if kickoff is None:
            continue

        if kickoff <= after_time:
            continue

        candidates.append(
            (
                kickoff,
                match
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0]
    )

    return candidates[0][1]


# ============================================================
# NEXT GAME PROGRAMME
# ============================================================

def create_next_game_programme(
    tv,
    channel_id,
    start,
    stop,
    fixtures
):
    next_match = get_next_match(
        fixtures,
        channel_id,
        start
    )

    if next_match:

        kickoff = parse_kickoff(
            next_match.get("kickoff")
        )

        if kickoff is None:
            return

        local_kickoff = kickoff.astimezone(
            UK_TZ
        )

        day_text = (
            f"{local_kickoff.strftime('%A')} "
            f"{ordinal_day(local_kickoff.day)}"
        )

        # ----------------------------------------------------
        # KEEP EXISTING TITLE
        # ----------------------------------------------------

        title = (
            f"Next Game: "
            f"{next_match['home']} vs "
            f"{next_match['away']} "
            f"| {day_text}"
        )

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        home = next_match["home"]
        away = next_match["away"]

        competition = next_match.get(
            "competition",
            "Competition TBC"
        )

        # Fixtur.es venue
        venue = next_match.get(
            "venue"
        )

        # Fallbacks for compatibility
        if not venue:
            venue = next_match.get(
                "stadium"
            )

        if not venue:
            venue = next_match.get(
                "location"
            )

        if not venue:
            venue = "Venue TBC"

        kickoff_time = local_kickoff.strftime(
            "%-I:%M %p"
        )

        description = (
            f"{home} take on {away} "
            f"in the {competition} "
            f"at {venue}. "
            f"Kick-off is scheduled for "
            f"{kickoff_time}."
        )

        # ----------------------------------------------------
        # Use "face" for Hearts
        # ----------------------------------------------------

        if home == "Hearts":

            description = (
                f"{home} face {away} "
                f"in the {competition} "
                f"at {venue}. "
                f"Kick-off is scheduled for "
                f"{kickoff_time}."
            )

    else:

        title = "Next Game"

        description = (
            "No upcoming fixture currently scheduled."
        )

    add_programme(
        tv,
        channel_id,
        xml_time(start),
        xml_time(stop),
        title,
        description
    )

# ============================================================
# CHANNELS
# ============================================================

def create_channel_entries(tv):

    for channel_id, team in SPFL_TEAMS.items():

        channel = ET.SubElement(
            tv,
            "channel",
            {
                "id": channel_id
            }
        )

        ET.SubElement(
            channel,
            "display-name"
        ).text = team["name"]

        logo_file = (
            LOGO_FOLDER /
            f"{channel_id}.png"
        )

        if logo_file.exists():

            ET.SubElement(
                channel,
                "icon",
                {
                    "src":
                        f"{LOGO_BASE_URL}"
                        f"{channel_id}.png"
                }
            )

            print(
                f"Logo found: "
                f"{team['name']} -> "
                f"{logo_file}"
            )

        else:

            print(
                f"WARNING: Logo missing for "
                f"{team['name']} "
                f"({logo_file})"
            )


# ============================================================
# LIVE MATCH PROGRAMME
# ============================================================

def create_live_programme(
    tv,
    channel_id,
    match,
    start,
    stop
):

    competition = match.get(
        "competition",
        "Competition TBC"
    )

    venue = match.get("venue")

    if not venue:
        venue = match.get("stadium")

    if not venue:
        venue = match.get("location")

    if not venue:
        venue = "Venue TBC"

    kickoff = parse_kickoff(
        match.get("kickoff")
    )

    if kickoff is not None:

        local_kickoff = kickoff.astimezone(
            UK_TZ
        )

        kickoff_time = local_kickoff.strftime(
            "%-I:%M %p"
        )

    else:

        kickoff_time = "TBC"

    description = (
        f"Live coverage of "
        f"{match['home']} taking on "
        f"{match['away']} "
        f"in the {competition} "
        f"at {venue}. "
        f"Kick-off is at "
        f"{kickoff_time}."
    )

    title = (
        f"⚽ "
        f"{match['home']} vs "
        f"{match['away']} "
        f"ˡⁱᵛᵉ 🔴"
    )

    add_programme(
        tv,
        channel_id,
        xml_time(start),
        xml_time(stop),
        title,
        description
    )


# ============================================================
# CREATE XMLTV
# ============================================================

def create_xmltv(
    fixtures,
    filename
):

    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "SPFL IPTV EPG"
        }
    )

    create_channel_entries(tv)

    # --------------------------------------------------------
    # Normalise fixture kickoff values
    # --------------------------------------------------------

    normalised_fixtures = []

    for fixture in fixtures:

        kickoff = parse_kickoff(
            fixture.get("kickoff")
        )

        if kickoff is None:
            print(
                "WARNING: Ignoring fixture with "
                f"invalid kickoff: {fixture}"
            )
            continue

        fixture = dict(fixture)

        fixture["_kickoff_dt"] = kickoff

        normalised_fixtures.append(
            fixture
        )

    # --------------------------------------------------------
    # Current UTC time
    # --------------------------------------------------------

    now = datetime.now(
        timezone.utc
    )

    epg_start = now.replace(
        minute=0,
        second=0,
        microsecond=0
    )

    epg_end = (
        epg_start +
        EPG_DURATION
    )

    # --------------------------------------------------------
    # Build each channel independently
    # --------------------------------------------------------

    for channel_id in SPFL_TEAMS:

        print(
            f"Generating EPG for "
            f"{channel_id}"
        )

        # ----------------------------------------------------
        # ONLY fixtures belonging to this channel
        # ----------------------------------------------------

        channel_matches = []

        for fixture in normalised_fixtures:

            if fixture.get(
                "channel_id"
            ) != channel_id:
                continue

            kickoff = fixture[
                "_kickoff_dt"
            ]

            if kickoff >= epg_end:
                continue

            match_end = (
                kickoff +
                MATCH_DURATION
            )

            if match_end <= epg_start:
                continue

            channel_matches.append(
                fixture
            )

        # ----------------------------------------------------
        # Sort THIS channel's fixtures
        # ----------------------------------------------------

        channel_matches.sort(
            key=lambda fixture:
                fixture["_kickoff_dt"]
        )

        print(
            f"  Fixtures in EPG: "
            f"{len(channel_matches)}"
        )

        # ----------------------------------------------------
        # Timeline starts at EPG beginning
        # ----------------------------------------------------

        current = epg_start

        # ----------------------------------------------------
        # Process every fixture independently
        # ----------------------------------------------------

        for match in channel_matches:

            kickoff = match[
                "_kickoff_dt"
            ]

            match_end = (
                kickoff +
                MATCH_DURATION
            )

            # ------------------------------------------------
            # Fill gap before match
            # ------------------------------------------------

            if current < kickoff:

                next_game_start = current

                next_game_stop = min(
                    kickoff,
                    epg_end
                )

                if next_game_start < next_game_stop:

                    create_next_game_programme(
                        tv,
                        channel_id,
                        next_game_start,
                        next_game_stop,
                        normalised_fixtures
                    )

            # ------------------------------------------------
            # Live match
            # ------------------------------------------------

            live_start = max(
                kickoff,
                epg_start
            )

            live_end = min(
                match_end,
                epg_end
            )

            if live_start < live_end:

                create_live_programme(
                    tv,
                    channel_id,
                    match,
                    live_start,
                    live_end
                )

            # ------------------------------------------------
            # Move timeline forward
            # ------------------------------------------------

            if match_end > current:

                current = match_end

            if current >= epg_end:
                break

        # ----------------------------------------------------
        # Fill remaining EPG window
        # ----------------------------------------------------

        if current < epg_end:

            create_next_game_programme(
                tv,
                channel_id,
                current,
                epg_end,
                normalised_fixtures
            )

    # ========================================================
    # WRITE FILE
    # ========================================================

    Path(filename).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    ET.ElementTree(tv).write(
        filename,
        encoding="utf-8",
        xml_declaration=True
    )

    print(
        f"XMLTV written to {filename}"
            )
