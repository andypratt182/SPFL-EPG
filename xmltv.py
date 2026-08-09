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
    Convert fixture kickoff data into a timezone-aware UTC datetime.

    The new data layer stores kickoff as a datetime object.

    The older EPG code stored kickoff as a string in the format:

        YYYYMMDDHHMMSS +0000

    This function deliberately supports both formats so the
    XMLTV layer remains compatible with existing data.
    """

    # ---------------------------------------------------------
    # New data-layer format
    # ---------------------------------------------------------

    if isinstance(timestamp, datetime):

        if timestamp.tzinfo is None:

            timestamp = timestamp.replace(
                tzinfo=UK_TZ
            )

        return timestamp.astimezone(
            timezone.utc
        )

    # ---------------------------------------------------------
    # Existing string format
    # ---------------------------------------------------------

    if isinstance(timestamp, str):

        return datetime.strptime(
            timestamp,
            "%Y%m%d%H%M%S +0000",
        ).replace(
            tzinfo=timezone.utc
        )

    raise TypeError(
        "Unsupported kickoff type: "
        f"{type(timestamp).__name__}"
    )


def format_kickoff(timestamp):

    utc_time = parse_kickoff(
        timestamp
    )

    return utc_time.astimezone(
        UK_TZ
    ).strftime(
        "%A %d %B %Y at %H:%M"
    )


def xml_time(dt):

    # ---------------------------------------------------------
    # XMLTV timestamps are written in UTC.
    # ---------------------------------------------------------

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

    for match in fixtures:

        if match.get("channel_id") != channel_id:
            continue

        kickoff = parse_kickoff(
            match["kickoff"]
        )

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
        # Create the correct ordinal suffix
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
        # Next Game description
        # -------------------------------------------------

        description = (
            f"{next_match['home']} vs "
            f"{next_match['away']}\n"
            f"Competition: "
            f"{next_match['competition']}\n"
            f"Venue: "
            f"{next_match.get('stadium', 'Venue TBC')}\n"
            f"Kick-off: "
            f"{format_kickoff(next_match['kickoff'])}"
        )

        # -------------------------------------------------
        # Next Game title
        # -------------------------------------------------

        title = (
            f"Next Game: "
            f"{next_match['home']} vs "
            f"{next_match['away']} "
            f"| {date_text}"
        )

    else:

        description = (
            "No upcoming fixture"
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

    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "SPFL IPTV EPG"
        }
    )

    create_channel_entries(tv)

    # -----------------------------------------------------
    # Sort all fixtures by kick-off time.
    #
    # parse_kickoff() allows this to work with both the
    # old string format and the new datetime format.
    # -----------------------------------------------------

    fixtures = sorted(
        fixtures,
        key=lambda x:
            parse_kickoff(
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
            f
            for f in fixtures
            if f.get("channel_id") == channel_id
        ]

        current = epg_start

        for match in channel_matches:

            kickoff = parse_kickoff(
                match["kickoff"]
            )

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
            # Stop processing once we are beyond the EPG
            # window.
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
                    f"{match.get('stadium', 'Venue TBC')}\n"
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

    Path(filename).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    ET.ElementTree(tv).write(
        filename,
        encoding="utf-8",
        xml_declaration=True
    )
