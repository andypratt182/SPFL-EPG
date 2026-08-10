from datetime import datetime
from email.utils import parsedate_to_datetime
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


# Competition calendars classify fixtures discovered by the
# team calendars. They do NOT create new fixtures for the EPG.

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
}


# UEFA calendars are used only to classify fixtures already
# discovered through an SPFL team calendar.

EUROPEAN_COMPETITION_CALENDARS = {
    "UEFA Champions League":
        "https://ics.fixtur.es/v2/league/champions-league.ics",

    "UEFA Europa League":
        "https://ics.fixtur.es/v2/league/europa-league.ics",

    "UEFA Conference League":
        "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
}


USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; SPFL-EPG/1.0; "
    "+https://github.com/andypratt182/SPFL-EPG)"
)

MAX_ATTEMPTS = 3
RETRY_DELAY = 2


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


# ============================================================
# TEAM NAME NORMALISATION
# ============================================================

TEAM_NAME_MAP = {
    "rangers": "Rangers",
    "rangers fc": "Rangers",
    "rangers football club": "Rangers",

    "celtic": "Celtic",
    "celtic fc": "Celtic",
    "celtic football club": "Celtic",

    "aberdeen": "Aberdeen",
    "aberdeen fc": "Aberdeen",
    "aberdeen football club": "Aberdeen",

    "dundee": "Dundee",
    "dundee fc": "Dundee",
    "dundee football club": "Dundee",

    "dundee united": "Dundee United",
    "dundee united fc": "Dundee United",
    "dundee united football club": "Dundee United",

    "hearts": "Hearts",
    "hearts fc": "Hearts",
    "heart of midlothian": "Hearts",
    "heart of midlothian fc": "Hearts",
    "heart of midlothian football club": "Hearts",

    "hibernian": "Hibernian",
    "hibernian fc": "Hibernian",
    "hibernian football club": "Hibernian",

    "kilmarnock": "Kilmarnock",
    "kilmarnock fc": "Kilmarnock",
    "kilmarnock football club": "Kilmarnock",

    "motherwell": "Motherwell",
    "motherwell fc": "Motherwell",
    "motherwell football club": "Motherwell",

    "falkirk": "Falkirk",
    "falkirk fc": "Falkirk",
    "falkirk football club": "Falkirk",

    "st johnstone": "St Johnstone",
    "st johnstone fc": "St Johnstone",
    "st johnstone football club": "St Johnstone",
    "st. johnstone": "St Johnstone",
    "st. johnstone fc": "St Johnstone",

    "st mirren": "St Mirren",
    "st mirren fc": "St Mirren",
    "st mirren football club": "St Mirren",
    "st. mirren": "St Mirren",
    "st. mirren fc": "St Mirren",
}


SPFL_TEAMS = {
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


def normalise_team_name(name):
    if not name:
        return ""

    name = str(name).strip()

    # Remove competition/UEFA markers sometimes attached
    # to club names by Fixtur.es.
    name = re.sub(
        r"\s*\[(?:CL|EL|CONF|CONF|Conf)\]\s*$",
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

    name = " ".join(name.split())

    return TEAM_NAME_MAP.get(
        name.lower(),
        name,
    )


# ============================================================
# ICS DOWNLOADING
# ============================================================

def download_ics(url):
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):

        print(
            f"Request attempt {attempt}/{MAX_ATTEMPTS}"
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
                f"Downloaded ICS characters: {len(text)}"
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

    A line beginning with a space or tab continues
    the previous physical line.
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


def property_value(lines, property_name):
    """
    Return the first value for an ICS property.

    Handles parameters such as:

        DTSTART;TZID=Europe/London:
        DTSTART;VALUE=DATE:
    """

    prefix = property_name.upper() + ":"
    parameter_prefix = property_name.upper() + ";"

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


def property_line(lines, property_name):
    """
    Return the complete ICS property line.
    """

    prefix = property_name.upper()

    for line in lines:

        if line.upper().startswith(
            prefix + ":"
        ) or line.upper().startswith(
            prefix + ";"
        ):

            return line

    return None


# ============================================================
# DATE PARSING
# ============================================================

def parse_ics_datetime(value):
    """
    Parse common Fixtur.es date/time formats.

    Returns a naive datetime because Fixtur.es UTC/local
    handling is preserved exactly as in the existing importer.
    """

    if not value:
        return None

    value = value.strip()

    # All-day/date-only value.
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


def is_date_only_datetime(value):
    """
    Return True when DTSTART contains only a calendar date.

    These entries do not contain a real kickoff time and
    therefore cannot safely become EPG programmes.
    """

    if not value:
        return False

    return bool(
        re.fullmatch(
            r"\d{8}",
            value.strip(),
        )
    )


def has_explicit_time(value):
    """
    Return True when the ICS DTSTART contains an actual time.

    A date-only DTSTART is not considered timed.
    """

    if not value:
        return False

    return bool(
        re.fullmatch(
            r"\d{8}T\d{4,6}Z?",
            value.strip(),
        )
    )


def is_placeholder_datetime(
    dtstart_value,
    dtstart,
    dtend_value,
    dtend,
):
    """
    Detect Fixtur.es placeholder/date-only events.

    Rules:

    1. A DATE-only DTSTART is always a placeholder for our
       fixture importer because no kickoff time is supplied.

    2. A midnight DTSTART is treated as a placeholder when
       it contains no explicit time information and therefore
       represents a date rather than a confirmed kickoff.

    3. A genuine explicit 00:00 kickoff is retained because
       the source explicitly supplied a time.

    This prevents entries such as:

        20260701
        20260701T000000

    from becoming bogus EPG fixtures when they are merely
    date placeholders.
    """

    if is_date_only_datetime(
        dtstart_value
    ):
        return True

    if (
        dtstart is None
        or dtstart.hour != 0
        or dtstart.minute != 0
        or dtstart.second != 0
    ):
        return False

    # If DTSTART explicitly contains a time, preserve it.
    if has_explicit_time(
        dtstart_value
    ):
        return False

    # If we reach this point, the value was parsed but did not
    # contain an explicit time. Treat it conservatively as a
    # placeholder.
    return True


def is_in_season(dt):
    if dt is None:
        return False

    return (
        SEASON_START
        <= dt
        <= SEASON_END
    )


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
# MATCH PARSING
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
# FIXTURE CLASSIFICATION HELPERS
# ============================================================

def is_spfl_team(name):
    return (
        normalise_team_name(name)
        in SPFL_TEAMS
    )


def classify_fixture_without_competition(
    home,
    away,
):
    """
    Classification for a discovered team-calendar fixture
    that has not matched any competition calendar.

    No July/August UEFA inference is performed.
    """

    home_spfl = is_spfl_team(home)
    away_spfl = is_spfl_team(away)

    if home_spfl and away_spfl:

        return (
            "Unclassified",
            "POTENTIALLY_MISSING_COMPETITION",
        )

    if home_spfl or away_spfl:

        return (
            "Friendly",
            "FRIENDLY",
        )

    return (
        "Unknown",
        "UNKNOWN",
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

    dtstart_value = property_value(
        lines,
        "DTSTART",
    )

    dtend_value = property_value(
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

    if not summary or not dtstart_value:
        return None

    # --------------------------------------------------------
    # Explicit season filtering.
    # --------------------------------------------------------

    kickoff = parse_ics_datetime(
        dtstart_value
    )

    if kickoff is None:
        return None

    if not is_in_season(kickoff):
        return None

    # --------------------------------------------------------
    # Reject date-only / placeholder fixtures.
    # --------------------------------------------------------

    end = parse_ics_datetime(
        dtend_value
    )

    if is_placeholder_datetime(
        dtstart_value,
        kickoff,
        dtend_value,
        end,
    ):
        return None

    # --------------------------------------------------------
    # Parse teams.
    # --------------------------------------------------------

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

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "end": end,
        "competition": competition,
        "competition_type": None,
        "classification_status": None,
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
# EXACT FIXTURE SIGNATURE
# ============================================================

def fixture_signature(fixture):
    """
    Exact fixture identity.

    Matching requires:

        date
        time
        home
        away

    No fuzzy matching is used for competition classification.
    """

    kickoff = fixture.get(
        "kickoff"
    )

    if isinstance(
        kickoff,
        datetime,
    ):

        kickoff_key = (
            kickoff.year,
            kickoff.month,
            kickoff.day,
            kickoff.hour,
            kickoff.minute,
            kickoff.second,
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
                f"Usable 2026/27 fixtures: "
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
    competition,
):
    if not competition:
        return None

    if competition in (
        "Scottish Premiership",
        "Scottish Championship",
        "Scottish League One",
        "Scottish League Two",
        "Scottish Cup",
    ):
        return "DOMESTIC"

    if competition in (
        "UEFA Champions League",
        "UEFA Europa League",
        "UEFA Conference League",
    ):
        return "UEFA"

    if competition == "Friendly":
        return "FRIENDLY"

    return None


# ============================================================
# DEDUPLICATION / CLASSIFICATION
# ============================================================

def merge_fixture_sources(
    team_fixtures,
    competition_fixtures,
):
    """
    Team calendars are the fixture discovery authority.

    Competition calendars can only classify fixtures already
    discovered by a team calendar.

    Therefore a competition-only fixture is deliberately NOT
    added to the returned fixture set.
    """

    merged = {}

    # --------------------------------------------------------
    # 1. Team calendars establish fixture discovery.
    # --------------------------------------------------------

    for fixture in team_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature not in merged:

            merged[signature] = dict(
                fixture
            )

            merged[signature][
                "verified_by_team_calendar"
            ] = True

            merged[signature][
                "team_sources"
            ] = [
                fixture.get(
                    "source_name"
                )
            ]

            merged[signature][
                "competition_source"
            ] = False

            (
                fallback_competition,
                fallback_status,
            ) = classify_fixture_without_competition(
                fixture.get("home"),
                fixture.get("away"),
            )

            merged[signature][
                "competition"
            ] = fallback_competition

            merged[signature][
                "competition_type"
            ] = (
                "FRIENDLY"
                if fallback_status == "FRIENDLY"
                else None
            )

            merged[signature][
                "classification_status"
            ] = fallback_status

        else:

            existing = merged[
                signature
            ]

            existing[
                "verified_by_team_calendar"
            ] = True

            team_source = fixture.get(
                "source_name"
            )

            existing.setdefault(
                "team_sources",
                [],
            )

            if (
                team_source
                and team_source
                not in existing[
                    "team_sources"
                ]
            ):

                existing[
                    "team_sources"
                ].append(
                    team_source
                )

            # Prefer a result if one feed has it.
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
    # 2. Competition calendars classify discovered fixtures.
    #
    # They do NOT add new fixtures.
    # --------------------------------------------------------

    for fixture in competition_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature not in merged:
            continue

        existing = merged[
            signature
        ]

        competition = fixture.get(
            "competition"
        )

        if not competition:
            continue

        existing[
            "competition"
        ] = competition

        existing[
            "competition_type"
        ] = competition_type_for(
            competition
        )

        existing[
            "classification_status"
        ] = (
            "CONFIRMED_COMPETITIVE"
        )

        existing[
            "competition_source"
        ] = True

        competition_id = fixture.get(
            "source_id"
        )

        existing.setdefault(
            "competition_source_ids",
            [],
        )

        if (
            competition_id
            and competition_id
            not in existing[
                "competition_source_ids"
            ]
        ):

            existing[
                "competition_source_ids"
            ].append(
                competition_id
            )

        # Prefer a competition-feed score if available.
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

    verified = sum(
        1
        for fixture in merged
        if fixture.get(
            "verified_by_team_calendar"
        )
    )

    classified = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        ) == "CONFIRMED_COMPETITIVE"
    )

    friendly = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        ) == "FRIENDLY"
    )

    potentially_missing = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        ) == "POTENTIALLY_MISSING_COMPETITION"
    )

    print(
        f"Team-calendar verified: "
        f"{verified}"
    )

    print(
        f"Confirmed competitive: "
        f"{classified}"
    )

    print(
        f"Friendlies: "
        f"{friendly}"
    )

    print(
        f"Potentially missing competition: "
        f"{potentially_missing}"
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

        team calendars
              |
              v
        fixture discovery
              |
              v
        2026/27 filtering
              |
              v
        exact competition matching
              |
              v
        classification

    Team calendars are the discovery authority.

    Competition calendars only classify discovered fixtures.

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
        "Season start: "
        f"{SEASON_START}"
    )

    print(
        "Season end: "
        f"{SEASON_END}"
    )

    print(
        "Team calendars: "
        f"{len(TEAM_CALENDARS)}"
    )

    print(
        "Domestic competition calendars: "
        f"{len(COMPETITION_CALENDARS)}"
    )

    print(
        "UEFA competition calendars: "
        f"{len(EUROPEAN_COMPETITION_CALENDARS)}"
    )

    # --------------------------------------------------------
    # Team calendars are always loaded first.
    # --------------------------------------------------------

    team_fixtures = (
        load_team_fixtures()
    )

    # --------------------------------------------------------
    # Competition feeds are classification sources only.
    # --------------------------------------------------------

    competition_fixtures = (
        load_competition_fixtures(
            COMPETITION_CALENDARS
        )
    )

    european_fixtures = (
        load_competition_fixtures(
            EUROPEAN_COMPETITION_CALENDARS
        )
    )

    competition_fixtures.extend(
        european_fixtures
    )

    # --------------------------------------------------------
    # Merge without allowing competition-only fixtures into
    # the discovered fixture set.
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
            )
            or "Unclassified",
            "|",
            fixture.get(
                "competition_type"
            )
            or "UNKNOWN",
            "|",
            fixture.get(
                "classification_status"
            )
            or "UNKNOWN",
        )
