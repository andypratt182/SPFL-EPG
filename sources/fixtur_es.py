from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import re
import time


# ============================================================
# FIxtur.es SOURCE CONFIGURATION
# ============================================================

TEAM_CALENDARS = {
    "Rangers":
        "https://ics.fixtur.es/v2/rangers.ics",

    "Celtic":
        "https://ics.fixtur.es/v2/celtic.ics",

    "Aberdeen":
        "https://ics.fixtur.es/v2/aberdeen.ics",

    "Dundee":
        "https://ics.fixtur.es/v2/dundee-fc.ics",

    "Dundee United":
        "https://ics.fixtur.es/v2/dundee-united.ics",

    "Hearts":
        "https://ics.fixtur.es/v2/heart-of-midlothian.ics",

    "Hibernian":
        "https://ics.fixtur.es/v2/hibernian.ics",

    "Kilmarnock":
        "https://ics.fixtur.es/v2/kilmarnock.ics",

    "Motherwell":
        "https://ics.fixtur.es/v2/motherwell.ics",

    "Falkirk":
        "https://ics.fixtur.es/v2/falkirk.ics",

    "St Johnstone":
        "https://ics.fixtur.es/v2/st-johnstone.ics",

    "St Mirren":
        "https://ics.fixtur.es/v2/st-mirren.ics",
}


COMPETITION_CALENDARS = {
    "Scottish Premiership":
        "https://ics.fixtur.es/v2/league/scottish-premier-league.ics",

    "Scottish Championship":
        "https://ics.fixtur.es/v2/league/scottish-championship.ics",

    "Scottish League One":
        "https://ics.fixtur.es/v2/league/scottish-league-one.ics",

    "Scottish League Two":
        "https://ics.fixtur.es/v2/league/scottish-league-two.ics",

    "Scottish Cup":
        "https://ics.fixtur.es/v2/league/scottish-cup.ics",

    "UEFA Champions League":
        "https://ics.fixtur.es/v2/league/champions-league.ics",

    "UEFA Europa League":
        "https://ics.fixtur.es/v2/league/europa-league.ics",

    "UEFA Conference League":
        "https://ics.fixtur.es/v2/league/europa-conference-league.ics",
}


# Kept separate so additional European competitions can be
# added later without changing the importer architecture.
EUROPEAN_COMPETITION_CALENDARS = {}


# ============================================================
# SEASON CONFIGURATION
# ============================================================

SEASON_START = datetime(
    2026,
    7,
    1,
)

SEASON_END = datetime(
    2027,
    6,
    30,
    23,
    59,
    59,
)


UK_TZ = ZoneInfo("Europe/London")


# ============================================================
# HTTP CONFIGURATION
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; SPFL-EPG/1.0; "
    "+https://github.com/andypratt182/SPFL-EPG)"
)

MAX_ATTEMPTS = 3
RETRY_DELAY = 2


# ============================================================
# SPFL TEAMS
# ============================================================

SPFL_TEAMS = {
    "Aberdeen",
    "Celtic",
    "Dundee",
    "Dundee United",
    "Falkirk",
    "Hearts",
    "Hibernian",
    "Kilmarnock",
    "Motherwell",
    "Rangers",
    "St Johnstone",
    "St Mirren",
}


# ============================================================
# COMPLETE SPFL NAME NORMALISATION
# ============================================================

TEAM_NAME_MAP = {
    # Aberdeen
    "aberdeen": "Aberdeen",
    "aberdeen fc": "Aberdeen",
    "aberdeen f.c.": "Aberdeen",

    # Celtic
    "celtic": "Celtic",
    "celtic fc": "Celtic",
    "celtic f.c.": "Celtic",

    # Dundee
    "dundee": "Dundee",
    "dundee fc": "Dundee",
    "dundee f.c.": "Dundee",

    # Dundee United
    "dundee united": "Dundee United",
    "dundee united fc": "Dundee United",
    "dundee united f.c.": "Dundee United",

    # Falkirk
    "falkirk": "Falkirk",
    "falkirk fc": "Falkirk",
    "falkirk f.c.": "Falkirk",

    # Hearts
    "hearts": "Hearts",
    "hearts fc": "Hearts",
    "hearts f.c.": "Hearts",
    "heart of midlothian": "Hearts",
    "heart of midlothian fc": "Hearts",
    "heart of midlothian f.c.": "Hearts",
    "heart of midlothian football club": "Hearts",

    # Hibernian
    "hibernian": "Hibernian",
    "hibernian fc": "Hibernian",
    "hibernian f.c.": "Hibernian",

    # Kilmarnock
    "kilmarnock": "Kilmarnock",
    "kilmarnock fc": "Kilmarnock",
    "kilmarnock f.c.": "Kilmarnock",

    # Motherwell
    "motherwell": "Motherwell",
    "motherwell fc": "Motherwell",
    "motherwell f.c.": "Motherwell",

    # Rangers
    "rangers": "Rangers",
    "rangers fc": "Rangers",
    "rangers f.c.": "Rangers",
    "rangers football club": "Rangers",

    # St Johnstone
    "st johnstone": "St Johnstone",
    "st. johnstone": "St Johnstone",
    "st johnstone fc": "St Johnstone",
    "st. johnstone fc": "St Johnstone",
    "st johnstone f.c.": "St Johnstone",
    "st. johnstone f.c.": "St Johnstone",
    "saint johnstone": "St Johnstone",
    "saint johnstone fc": "St Johnstone",

    # St Mirren
    "st mirren": "St Mirren",
    "st. mirren": "St Mirren",
    "st mirren fc": "St Mirren",
    "st. mirren fc": "St Mirren",
    "st mirren f.c.": "St Mirren",
    "st. mirren f.c.": "St Mirren",
    "saint mirren": "St Mirren",
    "saint mirren fc": "St Mirren",
}


def normalise_team_name(name):
    """
    Convert Fixtur.es team names into canonical SPFL names.

    Non-SPFL names are cleaned but otherwise preserved.
    """

    if not name:
        return ""

    name = str(name).strip()

    # Remove common suffixes.
    name = re.sub(
        r"\s+football\s+club$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+fc$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+f\.c\.$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+tv$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    # Normalise punctuation around "St."
    name = re.sub(
        r"\bst\.\s*",
        "St ",
        name,
        flags=re.IGNORECASE,
    )

    # Normalise whitespace.
    name = " ".join(name.split())

    lower = name.lower()

    if lower in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[lower]

    # Handle FC/F.C. variants after punctuation cleanup.
    without_fc = re.sub(
        r"\s+f\.?c\.?$",
        "",
        lower,
    ).strip()

    if without_fc in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[without_fc]

    return name


def is_spfl_team(name):
    return normalise_team_name(name) in SPFL_TEAMS


# ============================================================
# ICS DOWNLOADING
# ============================================================

def download_ics(url):
    last_error = None

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1,
    ):

        print(
            f"Request attempt "
            f"{attempt}/{MAX_ATTEMPTS}"
        )

        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/calendar,*/*",
            },
        )

        try:

            with urlopen(
                request,
                timeout=30,
            ) as response:

                status = response.getcode()
                data = response.read()

            text = data.decode(
                "utf-8-sig",
                errors="replace",
            )

            print(
                f"HTTP status: {status}"
            )

            print(
                f"Downloaded ICS characters: "
                f"{len(text)}"
            )

            return text

        except HTTPError as error:

            last_error = error

            print(
                f"HTTP error: {error.code}"
            )

        except URLError as error:

            last_error = error

            print(
                f"URL error: {error}"
            )

        except Exception as error:

            last_error = error

            print(
                f"Download error: {error}"
            )

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY)

    raise RuntimeError(
        "Unable to download Fixtur.es feed after "
        f"{MAX_ATTEMPTS} attempts: {last_error}"
    )


# ============================================================
# ICS PARSING
# ============================================================

def unfold_ics(text):
    """
    RFC5545 line unfolding.
    """

    text = text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    lines = text.split("\n")

    unfolded = []

    for line in lines:

        if (
            line.startswith(" ")
            or line.startswith("\t")
        ):

            if unfolded:
                unfolded[-1] += line[1:]

        else:

            unfolded.append(line)

    return unfolded


def split_events(text):
    lines = unfold_ics(text)

    events = []
    current = None

    for line in lines:

        if line.strip() == "BEGIN:VEVENT":

            current = []

            continue

        if line.strip() == "END:VEVENT":

            if current is not None:
                events.append(current)

            current = None

            continue

        if current is not None:
            current.append(line)

    return events


def property_value(
    lines,
    property_name,
):
    """
    Return the first value for an ICS property.

    Handles:
        DTSTART:
        DTSTART;TZID=Europe/London:
        DTSTART;VALUE=DATE:
    """

    prefix = property_name.upper() + ":"
    parameter_prefix = (
        property_name.upper() + ";"
    )

    for line in lines:

        upper = line.upper()

        if upper.startswith(prefix):

            return line[
                len(prefix):
            ].strip()

        if upper.startswith(
            parameter_prefix
        ):

            if ":" in line:

                return line.split(
                    ":",
                    1,
                )[1].strip()

    return None


def property_line(
    lines,
    property_name,
):
    """
    Return the complete ICS property line.
    """

    prefix = property_name.upper()

    for line in lines:

        upper = line.upper()

        if (
            upper.startswith(
                prefix + ":"
            )
            or
            upper.startswith(
                prefix + ";"
            )
        ):

            return line

    return None


# ============================================================
# DATE PARSING
# ============================================================

def parse_ics_datetime(value):
    if not value:
        return None

    value = value.strip()

    # All-day date.
    if re.fullmatch(
        r"\d{8}",
        value,
    ):

        try:

            return datetime.strptime(
                value,
                "%Y%m%d",
            )

        except ValueError:

            return None

    # UTC timestamp.
    if value.endswith("Z"):

        try:

            return datetime.strptime(
                value,
                "%Y%m%dT%H%M%SZ",
            ).replace(
                tzinfo=ZoneInfo("UTC")
            )

        except ValueError:

            return None

    # Local timestamp.
    for fmt in (
        "%Y%m%dT%H%M%S",
        "%Y%m%dT%H%M",
    ):

        try:

            return datetime.strptime(
                value,
                fmt,
            )

        except ValueError:

            pass

    # ISO fallback.
    try:

        normalised = value

        if normalised.endswith("Z"):

            normalised = (
                normalised[:-1]
                + "+00:00"
            )

        return datetime.fromisoformat(
            normalised
        )

    except ValueError:

        return None


def localise_kickoff(kickoff):
    if kickoff is None:
        return None

    if kickoff.tzinfo is None:

        kickoff = kickoff.replace(
            tzinfo=UK_TZ
        )

    return kickoff.astimezone(
        UK_TZ
    )


# ============================================================
# EXPLICIT 2026/27 SEASON FILTER
# ============================================================

def is_in_2026_27_season(kickoff):
    if kickoff is None:
        return False

    local = localise_kickoff(
        kickoff
    )

    start = SEASON_START.replace(
        tzinfo=UK_TZ
    )

    end = SEASON_END.replace(
        tzinfo=UK_TZ
    )

    return (
        start
        <= local
        <= end
    )


# ============================================================
# PLACEHOLDER FIXTURE DETECTION
# ============================================================

def is_placeholder_fixture(
    kickoff,
    home,
    away,
    competition,
):
    """
    Detect Fixtur.es placeholder fixtures.

    The known bad pattern is an otherwise unclassified
    SPFL-vs-SPFL event at exactly 00:00.

    Example:

        2026-07-01 00:00
        St Mirren vs Hearts
        Unclassified

    This is not treated as a genuine fixture.

    We deliberately do NOT discard legitimate friendlies
    or competitive fixtures simply because they occur in
    July or August.

    No UEFA competition is guessed from the date.
    """

    if kickoff is None:
        return False

    if competition:
        return False

    local = localise_kickoff(
        kickoff
    )

    if (
        local.hour != 0
        or local.minute != 0
        or local.second != 0
    ):
        return False

    if not (
        is_spfl_team(home)
        and is_spfl_team(away)
    ):
        return False

    return True


# ============================================================
# SCORE PARSING
# ============================================================

def parse_score_from_summary(summary):
    if not summary:
        return None, None

    match = re.search(
        r"\((\d+)\s*-\s*(\d+)\)\s*$",
        summary,
    )

    if not match:
        return None, None

    return (
        int(match.group(1)),
        int(match.group(2)),
    )


def remove_score_from_summary(summary):
    if not summary:
        return ""

    return re.sub(
        r"\s*\(\d+\s*-\s*\d+\)\s*$",
        "",
        summary,
    ).strip()


# ============================================================
# MATCH SUMMARY PARSING
# ============================================================

def parse_match_summary(summary):
    if not summary:
        return None, None, None, None

    home_score, away_score = (
        parse_score_from_summary(
            summary
        )
    )

    clean_summary = (
        remove_score_from_summary(
            summary
        )
    )

    if " - " not in clean_summary:

        return (
            None,
            None,
            home_score,
            away_score,
        )

    home, away = clean_summary.split(
        " - ",
        1,
    )

    home = normalise_team_name(
        home
    )

    away = normalise_team_name(
        away
    )

    return (
        home,
        away,
        home_score,
        away_score,
    )


# ============================================================
# EVENT CONVERSION
# ============================================================

def parse_event(
    lines,
    source_type,
    source_name,
    competition=None,
):
    uid = property_value(
        lines,
        "UID",
    )

    summary = property_value(
        lines,
        "SUMMARY",
    )

    dtstart = property_value(
        lines,
        "DTSTART",
    )

    dtend = property_value(
        lines,
        "DTEND",
    )

    status = property_value(
        lines,
        "STATUS",
    )

    sequence = property_value(
        lines,
        "SEQUENCE",
    )

    description = property_value(
        lines,
        "DESCRIPTION",
    )

    if not summary or not dtstart:
        return None

    (
        home,
        away,
        home_score,
        away_score,
    ) = parse_match_summary(
        summary
    )

    if not home or not away:
        return None

    kickoff = parse_ics_datetime(
        dtstart
    )

    if kickoff is None:
        return None

    kickoff = localise_kickoff(
        kickoff
    )

    # --------------------------------------------------------
    # Explicit 2026/27 filtering.
    # --------------------------------------------------------

    if not is_in_2026_27_season(
        kickoff
    ):
        return None

    # --------------------------------------------------------
    # Placeholder correction.
    # --------------------------------------------------------

    if is_placeholder_fixture(
        kickoff,
        home,
        away,
        competition,
    ):
        return None

    end = parse_ics_datetime(
        dtend
    )

    if end is not None:
        end = localise_kickoff(
            end
        )

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "end": end,
        "competition": competition,
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
    text,
    source_type,
    source_name,
    competition=None,
):
    events = split_events(text)

    fixtures = []

    for event in events:

        fixture = parse_event(
            event,
            source_type,
            source_name,
            competition,
        )

        if fixture is not None:
            fixtures.append(
                fixture
            )

    return (
        events,
        fixtures,
    )


# ============================================================
# EXACT FIXTURE MATCHING
# ============================================================

def fixture_signature(fixture):
    """
    Exact fixture identity:

        date
        time
        home
        away

    Kickoff is normalised to UK time before matching.
    """

    kickoff = fixture.get(
        "kickoff"
    )

    if isinstance(
        kickoff,
        datetime,
    ):

        kickoff = localise_kickoff(
            kickoff
        )

        kickoff_key = (
            kickoff.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

    else:

        kickoff_key = str(
            kickoff
        )

    home = normalise_team_name(
        fixture.get(
            "home",
            "",
        )
    )

    away = normalise_team_name(
        fixture.get(
            "away",
            "",
        )
    )

    return (
        kickoff_key,
        home.lower(),
        away.lower(),
    )


# ============================================================
# TEAM CALENDARS
# ============================================================

def load_team_fixtures():
    """
    Team calendars are the fixture discovery authority.

    Competition calendars never create fixtures.
    """

    all_fixtures = []

    print()
    print(
        "=" * 70
    )
    print(
        "LOADING FIxtur.es TEAM CALENDARS"
    )
    print(
        "=" * 70
    )

    for team, url in TEAM_CALENDARS.items():

        print()
        print(
            f"Loading {team}..."
        )

        try:

            text = download_ics(
                url
            )

            events, fixtures = (
                parse_calendar(
                    text,
                    source_type="team",
                    source_name=team,
                )
            )

            print(
                f"VEVENT records: "
                f"{len(events)}"
            )

            print(
                f"Usable 2026/27 fixtures: "
                f"{len(fixtures)}"
            )

            all_fixtures.extend(
                fixtures
            )

        except Exception as error:

            print(
                f"ERROR loading "
                f"{team}: {error}"
            )

    return all_fixtures


# ============================================================
# COMPETITION CALENDARS
# ============================================================

def load_competition_fixtures(
    calendars,
):
    """
    Competition calendars are classification sources only.

    A competition-calendar event does NOT create a fixture.
    It can only classify an already discovered team-calendar
    fixture when the exact fixture signature matches.
    """

    all_fixtures = []

    for competition, url in calendars.items():

        print()
        print(
            f"Loading competition: "
            f"{competition}"
        )

        print(
            f"URL: {url}"
        )

        try:

            text = download_ics(
                url
            )

            events, fixtures = (
                parse_calendar(
                    text,
                    source_type="competition",
                    source_name=competition,
                    competition=competition,
                )
            )

            print(
                f"VEVENT records: "
                f"{len(events)}"
            )

            print(
                f"Usable 2026/27 records: "
                f"{len(fixtures)}"
            )

            all_fixtures.extend(
                fixtures
            )

        except Exception as error:

            print(
                f"ERROR loading "
                f"{competition}: {error}"
            )

    return all_fixtures


# ============================================================
# COMPETITION TYPE
# ============================================================

def competition_type_for(
    competition
):
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
# FIXTURE CLASSIFICATION
# ============================================================

def classify_fixture(
    fixture,
    competition_index,
):
    """
    Classify a fixture discovered by a team calendar.

    Competition calendars can only classify an exact match.

    Matching uses:

        date
        time
        home
        away
    """

    signature = fixture_signature(
        fixture
    )

    matches = competition_index.get(
        signature,
        [],
    )

    # --------------------------------------------------------
    # Exact competition match.
    # --------------------------------------------------------

    if matches:

        # Prefer a named competition.
        selected = next(
            (
                item
                for item in matches
                if item.get(
                    "competition"
                )
            ),
            matches[0],
        )

        competition = selected.get(
            "competition"
        )

        fixture[
            "competition"
        ] = competition

        fixture[
            "competition_type"
        ] = competition_type_for(
            competition
        )

        fixture[
            "classification_status"
        ] = (
            "CONFIRMED_COMPETITIVE"
        )

        fixture[
            "competition_source_ids"
        ] = [
            item.get(
                "source_id"
            )
            for item in matches
            if item.get(
                "source_id"
            )
        ]

        return fixture

    # --------------------------------------------------------
    # No competition-calendar match.
    # --------------------------------------------------------

    home = fixture.get(
        "home",
        "",
    )

    away = fixture.get(
        "away",
        "",
    )

    home_spfl = is_spfl_team(
        home
    )

    away_spfl = is_spfl_team(
        away
    )

    # --------------------------------------------------------
    # Unmatched two-SPFL-team fixture.
    #
    # We do NOT guess Premiership, Scottish Cup,
    # League Cup, or UEFA based on date.
    # --------------------------------------------------------

    if home_spfl and away_spfl:

        fixture[
            "competition"
        ] = "Unclassified"

        fixture[
            "competition_type"
        ] = "UNKNOWN"

        fixture[
            "classification_status"
        ] = (
            "POTENTIALLY_MISSING_COMPETITION"
        )

        return fixture

    # --------------------------------------------------------
    # Unmatched fixture involving a non-SPFL team.
    #
    # Per project rules this is a FRIENDLY.
    # --------------------------------------------------------

    fixture[
        "competition"
    ] = "Friendly"

    fixture[
        "competition_type"
    ] = "FRIENDLY"

    fixture[
        "classification_status"
    ] = "FRIENDLY"

    return fixture


# ============================================================
# MERGING AND CLASSIFICATION
# ============================================================

def merge_fixture_sources(
    team_fixtures,
    competition_fixtures,
):
    """
    Team calendars establish the fixture set.

    Competition calendars only classify exact matches.
    """

    competition_index = {}

    for fixture in competition_fixtures:

        signature = fixture_signature(
            fixture
        )

        competition_index.setdefault(
            signature,
            [],
        ).append(
            fixture
        )

    merged = {}

    # --------------------------------------------------------
    # Discovery authority.
    #
    # ONLY team-calendar fixtures enter merged.
    # --------------------------------------------------------

    for fixture in team_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature not in merged:

            merged[
                signature
            ] = dict(
                fixture
            )

            merged[
                signature
            ][
                "verified_by_team_calendar"
            ] = True

            merged[
                signature
            ][
                "team_sources"
            ] = [
                fixture.get(
                    "source_name"
                )
            ]

        else:

            existing = merged[
                signature
            ]

            existing[
                "verified_by_team_calendar"
            ] = True

            source_name = fixture.get(
                "source_name"
            )

            existing.setdefault(
                "team_sources",
                [],
            )

            if (
                source_name
                and source_name
                not in existing[
                    "team_sources"
                ]
            ):

                existing[
                    "team_sources"
                ].append(
                    source_name
                )

            # Prefer a result if another team calendar
            # contains one.
            if (
                existing.get(
                    "home_score"
                ) is None
                and fixture.get(
                    "home_score"
                ) is not None
            ):

                existing[
                    "home_score"
                ] = fixture[
                    "home_score"
                ]

                existing[
                    "away_score"
                ] = fixture[
                    "away_score"
                ]

    # --------------------------------------------------------
    # Classify only the discovered fixtures.
    # --------------------------------------------------------

    classified = []

    for fixture in merged.values():

        classified_fixture = (
            classify_fixture(
                fixture,
                competition_index,
            )
        )

        classified.append(
            classified_fixture
        )

    return classified


# ============================================================
# SOURCE STATISTICS
# ============================================================

def print_source_statistics(
    team_fixtures,
    competition_fixtures,
    merged,
):
    print()
    print(
        "=" * 70
    )
    print(
        "FIXTUR.ES SOURCE / CLASSIFICATION AUDIT"
    )
    print(
        "=" * 70
    )

    print(
        f"Team-calendar records: "
        f"{len(team_fixtures)}"
    )

    print(
        f"Competition-calendar records: "
        f"{len(competition_fixtures)}"
    )

    print(
        f"Unique discovered fixtures: "
        f"{len(merged)}"
    )

    confirmed = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == "CONFIRMED_COMPETITIVE"
    )

    friendlies = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == "FRIENDLY"
    )

    potentially_missing = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == (
            "POTENTIALLY_MISSING_COMPETITION"
        )
    )

    print(
        f"Confirmed competitive: "
        f"{confirmed}"
    )

    print(
        f"Friendlies: "
        f"{friendlies}"
    )

    print(
        f"Potentially missing competition: "
        f"{potentially_missing}"
    )

    print()
    print(
        "Classification breakdown:"
    )

    counts = {}

    for fixture in merged:

        status = fixture.get(
            "classification_status",
            "UNKNOWN",
        )

        counts[
            status
        ] = (
            counts.get(
                status,
                0,
            )
            + 1
        )

    for status, count in sorted(
        counts.items()
    ):

        print(
            f"  {status}: {count}"
        )

    print()
    print(
        "Competition breakdown:"
    )

    competition_counts = {}

    for fixture in merged:

        competition = (
            fixture.get(
                "competition"
            )
            or "Unclassified"
        )

        competition_counts[
            competition
        ] = (
            competition_counts.get(
                competition,
                0,
            )
            + 1
        )

    for competition, count in sorted(
        competition_counts.items()
    ):

        print(
            f"  {competition}: "
            f"{count}"
        )


# ============================================================
# PUBLIC API
# ============================================================

def get_all_fixtures():
    """
    Main public interface.

    Architecture:

        TEAM CALENDARS
              |
              v
        FIXTURE DISCOVERY
              |
              v
        EXACT DATE/TIME/HOME/AWAY MATCH
              ^
              |
        COMPETITION CALENDARS
              |
              v
        CLASSIFICATION ONLY

    Team calendars are the discovery authority.

    Competition calendars cannot introduce fixtures.

    No database is used.
    """

    print()
    print(
        "=" * 70
    )
    print(
        "FIXTUR.ES IMPORT"
    )
    print(
        "=" * 70
    )

    print()
    print(
        "Season: 2026/27"
    )

    print(
        f"Season start: "
        f"{SEASON_START.date()}"
    )

    print(
        f"Season end: "
        f"{SEASON_END.date()}"
    )

    print()
    print(
        "Team calendars: "
        f"{len(TEAM_CALENDARS)}"
    )

    print(
        "Competition calendars: "
        f"{len(COMPETITION_CALENDARS)}"
    )

    # --------------------------------------------------------
    # STEP 1
    #
    # Team calendars discover the complete fixture set.
    # --------------------------------------------------------

    team_fixtures = (
        load_team_fixtures()
    )

    # --------------------------------------------------------
    # STEP 2
    #
    # Competition calendars classify discovered fixtures.
    # --------------------------------------------------------

    competition_fixtures = (
        load_competition_fixtures(
            COMPETITION_CALENDARS
        )
    )

    # Optional additional European calendars.
    if EUROPEAN_COMPETITION_CALENDARS:

        european_fixtures = (
            load_competition_fixtures(
                EUROPEAN_COMPETITION_CALENDARS
            )
        )

        competition_fixtures.extend(
            european_fixtures
        )

    # --------------------------------------------------------
    # STEP 3
    #
    # Merge using team calendars as the discovery authority.
    # --------------------------------------------------------

    merged = merge_fixture_sources(
        team_fixtures,
        competition_fixtures,
    )

    # --------------------------------------------------------
    # STEP 4
    #
    # Sort chronologically.
    # --------------------------------------------------------

    merged.sort(
        key=lambda fixture:
        fixture.get(
            "kickoff"
        )
        or datetime.max.replace(
            tzinfo=UK_TZ
        )
    )

    print_source_statistics(
        team_fixtures,
        competition_fixtures,
        merged,
    )

    print()
    print(
        "=" * 70
    )
    print(
        "FIXTUR.ES IMPORT COMPLETE"
    )
    print(
        "=" * 70
    )

    return merged


# ============================================================
# BACKWARDS COMPATIBILITY
# ============================================================

def build_fixtures():
    """
    Compatibility alias for older code.
    """

    return get_all_fixtures()


# ============================================================
# OPTIONAL DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    fixtures = get_all_fixtures()

    print()
    print(
        "First 20 classified fixtures:"
    )

    for fixture in fixtures[:20]:

        print(
            fixture.get(
                "kickoff"
            ),
            "|",
            fixture.get(
                "home"
            ),
            "vs",
            fixture.get(
                "away"
            ),
            "|",
            fixture.get(
                "competition"
            ),
            "|",
            fixture.get(
                "competition_type"
            ),
            "|",
            fixture.get(
                "classification_status"
            ),
        )
