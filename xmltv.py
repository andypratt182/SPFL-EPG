from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from teams import SPFL_TEAMS


UK_TZ = ZoneInfo("Europe/London")

MATCH_DURATION = timedelta(hours=2)

LOGO_BASE_URL = (
    "https://andypratt182.github.io/"
    "SPFL-EPG/logos/"
)

LOGO_FOLDER = Path("logos")


def add_programme(
    tv,
    channel_id,
    start,
    stop,
    title,
    description
):
    """
    Add a programme entry to the XMLTV document.
    """

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


def parse_kickoff(timestamp):
    """
    Convert fixture kickoff data into a UTC datetime.

    Supports both:

        datetime objects

    and existing XMLTV-style strings:

        20260809150000 +0000
    """

    if isinstance(timestamp, datetime):

        if timestamp.tzinfo is None:
            return timestamp.replace(
                tzinfo=UK_TZ
            )

        return timestamp.astimezone(
            timezone.utc
        )

    if not timestamp:
        return None

    return datetime.strptime(
        timestamp,
        "%Y%m%d%H%M%S +0000",
    ).replace(
        tzinfo=timezone.utc
    )


def format_kickoff(timestamp):
    """
    Format kickoff for human-readable EPG descriptions.
    """

    utc_time = parse_kickoff(timestamp)

    if utc_time is None:
        return "Kick-off time TBC"

    return utc_time.astimezone(
        UK_TZ
    ).strftime(
        "%A %d %B %Y at %H:%M"
    )


def xml_time(dt):
    """
    Convert datetime to XMLTV UTC timestamp.
    """

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    dt = dt.astimezone(
        timezone.utc
    )

    return dt.strftime(
        "%Y%m%d%H%M%S"
    ) + " +0000"


def get_next_match(
    fixtures,
    channel_id,
    after_time
):
    """
    Find the next fixture for a particular channel.
    """

    for match in fixtures:

        if match.get("channel_id") != channel_id:
            continue

        kickoff = parse_kickoff(
            match["kickoff"]
        )

        if kickoff is None:
            continue

        if kickoff > after_time:
            return match

    return None


def create_next_game_programme(
    tv,
    channel_id,
    start,
    stop,
    fixtures
):
    """
    Create the Next Game programme.

    The title format is deliberately kept unchanged.
    """

    next_match = get_next_match(
        fixtures,
        channel_id,
        start
    )

    if next_match:

        kickoff = parse_kickoff(
            next_match["kickoff"]
        ).astimezone(
            UK_TZ
        )

        # -------------------------------------------------
        # Create ordinal suffix
        #
        # 1st, 2nd, 3rd, 4th...
        # 11th, 12th and 13th are exceptions.
        # -------------------------------------------------

        day = kickoff.day

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

        date_text = (
            f"{kickoff.strftime('%A')} "
            f"{day}{suffix}"
        )

        # -------------------------------------------------
        # Venue
        #
        # Fixture Download supplies the stadium/venue.
        # Fall back to Venue TBC if unavailable.
        # -------------------------------------------------

        venue = (
            next_match.get("stadium")
            or next_match.get("venue")
            or "Venue TBC"
        )

        # -------------------------------------------------
        # Next Game description
        # -------------------------------------------------

        channel_name = (
            SPFL_TEAMS
            .get(channel_id, {})
            .get("name", "this channel")
        )

        description = (
            f"{next_match['home']} vs "
            f"{next_match['away']}\n\n"
            f"Competition: "
            f"{next_match['competition']}\n"
            f"Venue: "
            f"{venue}\n"
            f"Kick-off: "
            f"{format_kickoff(next_match['kickoff'])}\n\n"
            f"The next scheduled fixture for "
            f"{channel_name}."
        )

        # -------------------------------------------------
        # Next Game title
        #
        # IMPORTANT:
        # Keep this exactly as it was.
        #
        # Example:
        #
        # Next Game: Rangers vs Hibernian | Sunday 9th
        # -------------------------------------------------

        title = (
            f"Next Game: "
            f"{next_match['home']} vs "
            f"{next_match['away']} "
            f"| {date_text}"
        )

    else:

        description = (
            "There are currently no upcoming "
            "fixtures scheduled."
        )

        title = "Next Game"

    add_programme(
        tv,
        channel_id,
        xml_time(start),
        xml_time(stop),
        title,
        description
    )


def create_channel_entries(tv):
    """
    Create XMLTV channel definitions.
    """

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

        # -------------------------------------------------
        # Automatic channel logo
        # -------------------------------------------------

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


def create_xmltv(
    fixtures,
    filename
):
    """
    Create the complete XMLTV EPG.

    Generates a 240-hour rolling EPG window.
    """

    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "SPFL IPTV EPG"
        }
    )

    # -----------------------------------------------------
    # Channels
    # -----------------------------------------------------

    create_channel_entries(tv)

    # -----------------------------------------------------
    # Sort fixtures by kickoff
    # -----------------------------------------------------

    fixtures = sorted(
        fixtures,
        key=lambda x: parse_kickoff(
            x["kickoff"]
        )
    )

    # -----------------------------------------------------
    # Current UTC time
    # -----------------------------------------------------

    now = datetime.now(
        timezone.utc
    )

    epg_start = now.replace(
        minute=0,
        second=0,
        microsecond=0
    )

    # -----------------------------------------------------
    # Generate 240 hours of EPG data
    # -----------------------------------------------------

    epg_end = (
        epg_start +
        timedelta(hours=240)
    )

    # -----------------------------------------------------
    # Create timeline separately for each club
    # -----------------------------------------------------

    for channel_id in SPFL_TEAMS:

        channel_matches = [
            fixture
            for fixture in fixtures
            if fixture.get("channel_id")
            == channel_id
        ]

        current = epg_start

        for match in channel_matches:

            kickoff = parse_kickoff(
                match["kickoff"]
            )

            if kickoff is None:
                continue

            match_end = (
                kickoff +
                MATCH_DURATION
            )

            # -------------------------------------------------
            # Ignore matches that have already finished
            # -------------------------------------------------

            if match_end <= epg_start:
                continue

            # -------------------------------------------------
            # Stop once outside the EPG window
            # -------------------------------------------------

            if kickoff >= epg_end:
                break

            # -------------------------------------------------
            # Next Game programme before the match
            # -------------------------------------------------

            if current < kickoff:

                create_next_game_programme(
                    tv,
                    channel_id,
                    current,
                    kickoff,
                    fixtures
                )

            # -------------------------------------------------
            # Live match programme
            # -------------------------------------------------

            live_start = max(
                kickoff,
                epg_start
            )

            live_end = min(
                match_end,
                epg_end
            )

            venue = (
                match.get("stadium")
                or match.get("venue")
                or "Venue TBC"
            )

            add_programme(
                tv,
                channel_id,
                xml_time(live_start),
                xml_time(live_end),
                (
                    f"⚽ "
                    f"{match['home']} vs "
                    f"{match['away']} "
                    f"ˡⁱᵛᵉ 🔴"
                ),
                (
                    f"{match['competition']}\n"
                    f"Venue: "
                    f"{venue}\n"
                    f"Kick-off: "
                    f"{format_kickoff(match['kickoff'])}"
                )
            )

            current = max(
                current,
                match_end
            )

        # -----------------------------------------------------
        # Fill remaining EPG time with Next Game
        # -----------------------------------------------------

        if current < epg_end:

            create_next_game_programme(
                tv,
                channel_id,
                current,
                epg_end,
                fixtures
            )

    # ---------------------------------------------------------
    # Save XMLTV file
    # ---------------------------------------------------------

    output_path = Path(filename)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    ET.ElementTree(tv).write(
        output_path,
        encoding="utf-8",
        xml_declaration=True
        )
