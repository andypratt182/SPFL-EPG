from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import re
import time


# ============================================================
# FIxtur.es SOURCE CONFIGURATION
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


# Domestic competition calendars.
#
# IMPORTANT:
# These feeds classify fixtures discovered from team calendars.
# They do NOT create new fixtures.

DOMESTIC_COMPETITION_CALENDARS = {
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
}


# UEFA competition calendars.
#
# These are deliberately separate from domestic competitions.
#
# UEFA classification is based ONLY on matching UEFA
# competition-calendar evidence. Date alone is never enough.

UEFA_COMPETITION_CALENDARS = {
    "Champions League":
        "https://ics.fixtur.es/v2/league/champions-league.ics",

    "Europa League":
        "https://ics.fixtur.es/v2/league/europa-league.ics",

    "UEFA Conference League":
        "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
}


# Backwards-compatible combined competition configuration.

COMPETITION_CALENDARS = {
    **DOMESTIC_COMPETITION_CALENDARS,
    **UEFA_COMPETITION_CALENDARS,
}


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

SEASON_LABEL = "2026/27"


# ============================================================
# TEAM CONFIGURATION
# ============================================================

SPFL_TEAM_NAMES = {
    "Rangers",
    "Celtic",
    "Aberdeen",
    "Dundee",
    "Dundee United",
    "Hearts",
    "Hibernian",
    "Kilmarnock",
    "Motherwell",
    "Falkirk",
    "St Johnstone",
    "St Mirren",
}


# Complete normalisation map for names commonly returned by
# Fixtur.es and competition calendars.

TEAM_NAME_MAP = {
    "rangers": "Rangers",
    "rangers fc": "Rangers",

    "celtic": "Celtic",
    "celtic fc": "Celtic",

    "aberdeen": "Aberdeen",
    "aberdeen fc": "Aberdeen",

    "dundee": "Dundee",
    "dundee fc": "Dundee",

    "dundee united": "Dundee United",
    "dundee united fc": "Dundee United",

    "hearts": "Hearts",
    "heart of midlothian": "Hearts",
    "heart of midlothian fc": "Hearts",

    "hibernian": "Hibernian",
    "hibernian fc": "Hibernian",

    "kilmarnock": "Kilmarnock",
    "kilmarnock fc": "Kilmarnock",

    "motherwell": "Motherwell",
    "motherwell fc": "Motherwell",

    "falkirk": "Falkirk",
    "falkirk fc": "Falkirk",

    "st johnstone": "St Johnstone",
    "st johnstone fc": "St Johnstone",
    "st. johnstone": "St Johnstone",
    "st. johnstone fc": "St Johnstone",

    "st mirren": "St Mirren",
    "st mirren fc": "St Mirren",
    "st. mirren": "St Mirren",
    "st. mirren fc": "St Mirren",
}


USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; SPFL-EPG/1.0; "
    "+https://github.com/andypratt182/SPFL-EPG)"
)

MAX_ATTEMPTS = 3
RETRY_DELAY = 2


# ============================================================
# TEAM NAME NORMALISATION
# ============================================================

def normalise_team_name(name):
    """
    Convert common Fixtur.es team-name variations to canonical
    SPFL names.

    UEFA markers such as [CL], [EL] and [Conf] are removed
    before normalisation because they are classification
    metadata, not part of the club name.
    """

    if not name:
        return ""

    name = str(name).strip()

    # Remove result suffixes if present.
    name = re.sub(
        r"\s*\(\d+\s*-\s*\d+\)\s*$",
        "",
        name,
    )

    # Remove Fixtur.es UEFA markers.
    name = re.sub(
        r"\s*\[(?:CL|EL|CONF|Conf)\]\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    )

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
        r"\s+tv$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    # Normalise whitespace.
    name = " ".join(
        name.split()
    )

    return TEAM_NAME_MAP.get(
        name.lower(),
        name,
    )


def is_spfl_team(name):
    return (
        normalise_team_name(name)
        in SPFL_TEAM_NAMES
    )


# ============================================================
# ICS DOWNLOADING
# ============================================================

def download_ics(url):
    """
    Download an ICS feed with retry handling.
    """

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
                "Downloaded ICS characters: "
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

    text = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
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

    Handles properties such as:

        DTSTART:
        DTSTART;TZID=Europe/London:
        DTSTART;VALUE=DATE:
    """

    prefix = (
        property_name.upper()
        + ":"
    )

    parameter_prefix = (
        property_name.upper()
        + ";"
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


# ============================================================
# DATE PARSING / SEASON FILTER
# ============================================================

def parse_ics_datetime(value):
    """
    Parse common Fixtur.es ICS datetime formats.

    The importer intentionally preserves the datetime represented
    by the feed. Naive timestamps are treated consistently as
    local feed times.
    """

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


def is_in_target_season(kickoff):
    """
    Explicitly restrict imported fixtures to 2026/27.
    """

    if kickoff is None:
        return False

    # Comparison is deliberately made using the date/time
    # represented by the parsed feed.
    if kickoff.tzinfo is not None:

        kickoff = kickoff.replace(
            tzinfo=None
        )

    return (
        SEASON_START
        <= kickoff
        <= SEASON_END
    )


# ============================================================
# SCORE / SUMMARY PARSING
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


def parse_match_summary(summary):
    if not summary:
        return (
            None,
            None,
            None,
            None,
        )

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

    home, away = (
        clean_summary.split(
            " - ",
            1,
        )
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

    # --------------------------------------------------------
    # CRITICAL:
    # Explicit 2026/27 filtering.
    #
    # This prevents historical Fixtur.es records such as
    # 2015/16 from entering the production fixture set.
    # --------------------------------------------------------

    if not is_in_target_season(
        kickoff
    ):
        return None

    end = parse_ics_datetime(
        dtend
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
    events = split_events(
        text
    )

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
# CANONICAL FIXTURE IDENTITY
# ============================================================

def fixture_signature(fixture):
    """
    Canonical fixture identity.

    EXACT matching consists of:

        date
        time
        home team
        away team

    No approximate date matching is performed.
    No team-only matching is performed.
    """

    kickoff = fixture.get(
        "kickoff"
    )

    if not isinstance(
        kickoff,
        datetime,
    ):
        return None

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

    if not home or not away:
        return None

    return (
        kickoff.year,
        kickoff.month,
        kickoff.day,
        kickoff.hour,
        kickoff.minute,
        home.lower(),
        away.lower(),
    )


# ============================================================
# TEAM CALENDARS
# ============================================================

def load_team_fixtures():
    """
    Load the 12 team calendars.

    TEAM CALENDARS ARE THE FIXTURE DISCOVERY AUTHORITY.

    Every valid 2026/27 fixture discovered here is retained,
    regardless of whether a competition calendar contains it.
    """

    all_fixtures = []

    print()
    print("=" * 70)
    print("LOADING FIxtur.es TEAM CALENDARS")
    print("=" * 70)

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
                f"2026/27 fixtures: "
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
    Load domestic or UEFA competition calendars.

    These feeds DO NOT create fixtures.

    They are classification sources only.
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
                f"2026/27 fixtures: "
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
# CLASSIFICATION
# ============================================================

def classify_fixture(
    fixture,
    competition_index,
):
    """
    Classify a fixture discovered by a team calendar.

    Authority order:

        1. UEFA competition calendar
        2. Domestic competition calendar
        3. Friendly
        4. Potentially missing competition
        5. Unknown

    Importantly, competition feeds only classify fixtures
    already discovered by team calendars.
    """

    signature = fixture_signature(
        fixture
    )

    if signature is None:

        return (
            None,
            "UNKNOWN",
            "UNKNOWN",
        )

    competitions = (
        competition_index.get(
            signature,
            set(),
        )
    )

    uefa_matches = (
        competitions
        & set(
            UEFA_COMPETITION_CALENDARS.keys()
        )
    )

    domestic_matches = (
        competitions
        & set(
            DOMESTIC_COMPETITION_CALENDARS.keys()
        )
    )

    # --------------------------------------------------------
    # UEFA
    # --------------------------------------------------------

    if uefa_matches:

        competition = sorted(
            uefa_matches
        )[0]

        return (
            competition,
            "UEFA",
            "CONFIRMED_COMPETITIVE",
        )

    # --------------------------------------------------------
    # Domestic
    # --------------------------------------------------------

    if domestic_matches:

        competition = sorted(
            domestic_matches
        )[0]

        return (
            competition,
            "DOMESTIC",
            "CONFIRMED_COMPETITIVE",
        )

    # --------------------------------------------------------
    # No competition match.
    #
    # Determine whether this is a friendly or a fixture
    # that potentially has missing competition classification.
    # --------------------------------------------------------

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

    home_spfl = is_spfl_team(
        home
    )

    away_spfl = is_spfl_team(
        away
    )

    # Both teams are SPFL clubs.
    #
    # Do NOT automatically call this a friendly.

    if (
        home_spfl
        and away_spfl
    ):

        return (
            None,
            "UNKNOWN",
            "POTENTIALLY_MISSING_COMPETITION",
        )

    # One SPFL club and one non-SPFL opponent.
    #
    # No domestic or UEFA calendar confirms it, therefore
    # classify it as a friendly.

    if home_spfl != away_spfl:

        return (
            "Friendly",
            "FRIENDLY",
            "FRIENDLY",
        )

    # Anything else is genuinely ambiguous.

    return (
        None,
        "UNKNOWN",
        "UNKNOWN",
    )


# ============================================================
# MERGE / DEDUPLICATION
# ============================================================

def merge_fixture_sources(
    team_fixtures,
    competition_fixtures,
):
    """
    Build the production fixture set.

    TEAM CALENDARS:
        establish fixture existence.

    COMPETITION CALENDARS:
        classify existing fixtures only.

    Competition-only fixtures are deliberately ignored.
    """

    # --------------------------------------------------------
    # First build the competition classification index.
    #
    # This does NOT add anything to the fixture set.
    # --------------------------------------------------------

    competition_index = {}

    for fixture in competition_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature is None:
            continue

        competition = fixture.get(
            "competition"
        )

        if not competition:
            continue

        competition_index.setdefault(
            signature,
            set(),
        ).add(
            competition
        )

    # --------------------------------------------------------
    # Team calendars establish the actual fixture set.
    # --------------------------------------------------------

    merged = {}

    for fixture in team_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature is None:
            continue

        if signature not in merged:

            merged[signature] = dict(
                fixture
            )

            merged[signature][
                "team_sources"
            ] = []

        existing = merged[
            signature
        ]

        source_name = fixture.get(
            "source_name"
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

        # Prefer a result if another team calendar has one.

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
    # Classify every discovered team fixture.
    # --------------------------------------------------------

    for signature, fixture in merged.items():

        (
            competition,
            competition_type,
            classification_status,
        ) = classify_fixture(
            fixture,
            competition_index,
        )

        fixture[
            "competition"
        ] = competition

        fixture[
            "competition_type"
        ] = competition_type

        fixture[
            "classification_status"
        ] = classification_status

        fixture[
            "verified_by_team_calendar"
        ] = True

        fixture[
            "competition_source"
        ] = bool(
            competition_index.get(
                signature
            )
        )

        fixture[
            "competition_sources"
        ] = sorted(
            competition_index.get(
                signature,
                set(),
            )
        )

    return list(
        merged.values()
    )


# ============================================================
# SORTING
# ============================================================

def fixture_sort_key(
    fixture,
):
    kickoff = fixture.get(
        "kickoff"
    )

    if isinstance(
        kickoff,
        datetime,
    ):
        return kickoff

    return datetime.max


# ============================================================
# SOURCE STATISTICS
# ============================================================

def print_source_statistics(
    team_fixtures,
    competition_fixtures,
    merged,
):
    print()
    print("=" * 70)
    print("FIXTUR.ES SOURCE / CLASSIFICATION AUDIT")
    print("=" * 70)

    print(
        f"Season: {SEASON_LABEL}"
    )

    print(
        f"Season window: "
        f"{SEASON_START} -> {SEASON_END}"
    )

    print()

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
        == "POTENTIALLY_MISSING_COMPETITION"
    )

    unknown = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == "UNKNOWN"
    )

    domestic = sum(
        1
        for fixture in merged
        if fixture.get(
            "competition_type"
        )
        == "DOMESTIC"
    )

    uefa = sum(
        1
        for fixture in merged
        if fixture.get(
            "competition_type"
        )
        == "UEFA"
    )

    print()
    print("CLASSIFICATION SUMMARY")
    print(
        f"Confirmed competitive: "
        f"{confirmed}"
    )

    print(
        f"  Domestic: "
        f"{domestic}"
    )

    print(
        f"  UEFA: "
        f"{uefa}"
    )

    print(
        f"Friendlies: "
        f"{friendlies}"
    )

    print(
        f"Potentially missing competition: "
        f"{potentially_missing}"
    )

    print(
        f"Unknown: "
        f"{unknown}"
    )

    print()
    print("COMPETITION BREAKDOWN")

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

    print()
    print("AUTHORITY MODEL")
    print(
        "  Team calendars: FIXTURE DISCOVERY"
    )
    print(
        "  Domestic calendars: CLASSIFICATION ONLY"
    )
    print(
        "  UEFA calendars: UEFA CLASSIFICATION ONLY"
    )

    print()
    print(
        "Exact fixture identity:"
    )

    print(
        "  date + time + home + away"
    )

    print()
    print(
        "No July/August UEFA inference is used."
    )

    print(
        "Competition-only fixtures are NOT imported."
    )


# ============================================================
# PUBLIC API
# ============================================================

def get_all_fixtures():
    """
    Main public interface.

    Architecture:

        12 TEAM CALENDARS
                 |
                 v
        2026/27 FILTER
                 |
                 v
        DEDUPLICATED FIXTURES
                 |
                 v
        +----------------------+
        |                      |
        v                      v
    DOMESTIC                UEFA
    CALENDARS               CALENDARS
        |                      |
        +----------+-----------+
                   |
                   v
             CLASSIFICATION
                   |
                   v
          PRODUCTION FIXTURES

    Team calendars establish whether a fixture exists.

    Competition calendars never create fixtures.

    No database is used.
    """

    print()
    print("=" * 70)
    print("FIXTUR.ES IMPORT")
    print("=" * 70)

    print()
    print(
        f"Target season: {SEASON_LABEL}"
    )

    print(
        f"Team calendars: "
        f"{len(TEAM_CALENDARS)}"
    )

    print(
        f"Domestic competition calendars: "
        f"{len(DOMESTIC_COMPETITION_CALENDARS)}"
    )

    print(
        f"UEFA competition calendars: "
        f"{len(UEFA_COMPETITION_CALENDARS)}"
    )

    # --------------------------------------------------------
    # STEP 1
    #
    # Team calendars are the only fixture discovery source.
    # --------------------------------------------------------

    team_fixtures = (
        load_team_fixtures()
    )

    # --------------------------------------------------------
    # STEP 2
    #
    # Competition calendars are classification sources only.
    # --------------------------------------------------------

    domestic_fixtures = (
        load_competition_fixtures(
            DOMESTIC_COMPETITION_CALENDARS
        )
    )

    uefa_fixtures = (
        load_competition_fixtures(
            UEFA_COMPETITION_CALENDARS
        )
    )

    competition_fixtures = (
        domestic_fixtures
        + uefa_fixtures
    )

    # --------------------------------------------------------
    # STEP 3
    #
    # Build the fixture set exclusively from team calendars,
    # then classify each discovered fixture.
    # --------------------------------------------------------

    merged = merge_fixture_sources(
        team_fixtures,
        competition_fixtures,
    )

    merged.sort(
        key=fixture_sort_key
    )

    print_source_statistics(
        team_fixtures,
        competition_fixtures,
        merged,
    )

    print()
    print("=" * 70)
    print("FIXTUR.ES IMPORT COMPLETE")
    print("=" * 70)

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
    print("First 20 classified fixtures:")

    for fixture in fixtures[:20]:

        print(
            f"{fixture.get('kickoff')} | "
            f"{fixture.get('home')} vs "
            f"{fixture.get('away')} | "
            f"{fixture.get('competition') or 'Unclassified'} | "
            f"{fixture.get('competition_type')} | "
            f"{fixture.get('classification_status')}"
        )
