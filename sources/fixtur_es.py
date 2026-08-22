from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import re
import sys
import time


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from venues import get_venue


# ============================================================
# FIXTUR.ES SOURCE CONFIGURATION
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
        "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
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

UK_TZ = ZoneInfo("Europe/London")
UTC_TZ = ZoneInfo("UTC")


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
# TEAM NAME NORMALISATION
# ============================================================

TEAM_NAME_MAP = {
    "aberdeen": "Aberdeen",
    "aberdeen fc": "Aberdeen",
    "aberdeen f.c.": "Aberdeen",

    "celtic": "Celtic",
    "celtic fc": "Celtic",
    "celtic f.c.": "Celtic",

    "dundee": "Dundee",
    "dundee fc": "Dundee",
    "dundee f.c.": "Dundee",

    "dundee united": "Dundee United",
    "dundee united fc": "Dundee United",
    "dundee united f.c.": "Dundee United",

    "falkirk": "Falkirk",
    "falkirk fc": "Falkirk",
    "falkirk f.c.": "Falkirk",

    "hearts": "Hearts",
    "hearts fc": "Hearts",
    "hearts f.c.": "Hearts",
    "heart of midlothian": "Hearts",
    "heart of midlothian fc": "Hearts",
    "heart of midlothian f.c.": "Hearts",
    "heart of midlothian football club": "Hearts",

    "hibernian": "Hibernian",
    "hibernian fc": "Hibernian",
    "hibernian f.c.": "Hibernian",

    "kilmarnock": "Kilmarnock",
    "kilmarnock fc": "Kilmarnock",
    "kilmarnock f.c.": "Kilmarnock",

    "motherwell": "Motherwell",
    "motherwell fc": "Motherwell",
    "motherwell f.c.": "Motherwell",

    "rangers": "Rangers",
    "rangers fc": "Rangers",
    "rangers f.c.": "Rangers",
    "rangers football club": "Rangers",

    "st johnstone": "St Johnstone",
    "st. johnstone": "St Johnstone",
    "st johnstone fc": "St Johnstone",
    "st. johnstone fc": "St Johnstone",
    "st johnstone f.c.": "St Johnstone",
    "st. johnstone f.c.": "St Johnstone",
    "saint johnstone": "St Johnstone",
    "saint johnstone fc": "St Johnstone",

    "st mirren": "St Mirren",
    "st. mirren": "St Mirren",
    "st mirren fc": "St Mirren",
    "st. mirren fc": "St Mirren",
    "st mirren f.c.": "St Mirren",
    "st. mirren f.c.": "St Mirren",
    "saint mirren": "St Mirren",
}


def clean_competition_suffix(name):
    if not name:
        return ""

    name = str(name).strip()

    return re.sub(
        r"\s+\[(?:EL|CL|Conf)\]\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()


def normalise_team_name(name):
    if not name:
        return ""

    name = clean_competition_suffix(name)

    name = re.sub(
        r"\s+football\s+club$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+f\.?c\.$",
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

    name = re.sub(
        r"\bst\.\s*",
        "St ",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\bsaint\s+",
        "St ",
        name,
        flags=re.IGNORECASE,
    )

    name = " ".join(name.split())

    return TEAM_NAME_MAP.get(
        name.lower(),
        name,
    )


def is_spfl_team(name):
    return normalise_team_name(name) in SPFL_TEAMS


# ============================================================
# DOWNLOAD ICS
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
        if line.startswith((" ", "\t")):
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


def property_line(lines, property_name):
    prefix = property_name.upper()

    for line in lines:
        upper = line.upper()

        if (
            upper.startswith(prefix + ":")
            or upper.startswith(prefix + ";")
        ):
            return line

    return None


def property_value(lines, property_name):
    line = property_line(
        lines,
        property_name,
    )

    if not line or ":" not in line:
        return None

    return line.split(
        ":",
        1,
    )[1].strip()


def property_parameters(lines, property_name):
    line = property_line(
        lines,
        property_name,
    )

    if not line or ":" not in line:
        return {}

    left = line.split(
        ":",
        1,
    )[0]

    if ";" not in left:
        return {}

    parameters = {}

    for item in left.split(";")[1:]:

        if "=" not in item:
            continue

        key, value = item.split(
            "=",
            1,
        )

        parameters[key.upper()] = value

    return parameters


# ============================================================
# DATE PARSING
# ============================================================

def parse_ics_datetime(value):
    if not value:
        return None

    value = value.strip()

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

    if value.endswith("Z"):
        try:
            return datetime.strptime(
                value,
                "%Y%m%dT%H%M%SZ",
            ).replace(
                tzinfo=UTC_TZ
            )
        except ValueError:
            return None

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
# SEASON FILTER
# ============================================================

def is_in_2026_27_season(kickoff):
    if kickoff is None:
        return False

    local = localise_kickoff(kickoff)

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
# PLACEHOLDER DETECTION
# ============================================================

def is_placeholder_fixture(
    raw_kickoff,
    kickoff,
    home,
    away,
    competition,
):
    if kickoff is None:
        return False

    if competition:
        return False

    if not raw_kickoff:
        return False

    raw_value = raw_kickoff.strip()

    raw_midnight = bool(
        re.fullmatch(
            r"\d{8}T000000",
            raw_value,
        )
    )

    raw_midnight_short = bool(
        re.fullmatch(
            r"\d{8}T0000",
            raw_value,
        )
    )

    if not (
        raw_midnight
        or raw_midnight_short
    ):
        return False

    return (
        is_spfl_team(home)
        and is_spfl_team(away)
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
# MATCH SUMMARY PARSING
# ============================================================

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

    home, away = clean_summary.split(
        " - ",
        1,
    )

    home = normalise_team_name(home)
    away = normalise_team_name(away)

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
    """
    Convert one VEVENT into the internal fixture structure.

    IMPORTANT:
    The home and away teams MUST be parsed before venue lookup.
    """

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

    location = property_value(
        lines,
        "LOCATION",
    )

    # --------------------------------------------------------
    # Parse the match first.
    #
    # This fixes the original bug where get_venue(home)
    # was called before "home" had been assigned.
    # --------------------------------------------------------

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

    raw_kickoff = dtstart.strip()

    kickoff = parse_ics_datetime(
        raw_kickoff
    )

    if kickoff is None:
        return None

    # --------------------------------------------------------
    # Placeholder detection before timezone conversion.
    # --------------------------------------------------------

    if is_placeholder_fixture(
        raw_kickoff,
        kickoff,
        home,
        away,
        competition,
    ):
        return None

    kickoff = localise_kickoff(
        kickoff
    )

    # --------------------------------------------------------
    # Season filtering.
    # --------------------------------------------------------

    if not is_in_2026_27_season(
        kickoff
    ):
        return None

    # --------------------------------------------------------
    # End time.
    # --------------------------------------------------------

    end = parse_ics_datetime(
        dtend
    )

    if end is not None:
        end = localise_kickoff(end)

    # --------------------------------------------------------
    # Venue.
    #
    # Prefer the actual Fixtur.es LOCATION.
    # Fall back to our venue database using the canonical
    # home team.
    # --------------------------------------------------------

    if location:
        venue = location.strip()
    else:
        venue = get_venue(home)

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
            fixtures.append(fixture)

    return (
        events,
        fixtures,
    )


# ============================================================
# FIXTURE IDENTITY
# ============================================================

def fixture_signature(fixture):
    kickoff = fixture.get("kickoff")

    if isinstance(
        kickoff,
        datetime,
    ):
        kickoff = localise_kickoff(kickoff)

        kickoff_key = kickoff.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    else:
        kickoff_key = str(kickoff)

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
    print("=" * 70)
    print("LOADING FIXTUR.ES TEAM CALENDARS")
    print("=" * 70)

    for team, url in TEAM_CALENDARS.items():

        print()
        print(f"Loading {team}...")
        print(f"URL: {url}")

        try:
            text = download_ics(url)

            events, fixtures = parse_calendar(
                text,
                source_type="team",
                source_name=team,
            )

            print(
                f"VEVENT records: "
                f"{len(events)}"
            )

            print(
                f"Usable 2026/27 fixtures: "
                f"{len(fixtures)}"
            )

            all_fixtures.extend(fixtures)

        except Exception as error:
            print(
                f"ERROR loading "
                f"{team}: {error}"
            )

    return all_fixtures


# ============================================================
# COMPETITION CALENDARS
# ============================================================

def load_competition_fixtures(calendars):
    all_fixtures = []

    print()
    print("=" * 70)
    print("LOADING COMPETITION CALENDARS")
    print("=" * 70)

    for competition, url in calendars.items():

        print()
        print(
            f"Loading competition: "
            f"{competition}"
        )

        print(f"URL: {url}")

        try:
            text = download_ics(url)

            events, fixtures = parse_calendar(
                text,
                source_type="competition",
                source_name=competition,
                competition=competition,
            )

            print(
                f"VEVENT records: "
                f"{len(events)}"
            )

            print(
                f"Usable 2026/27 records: "
                f"{len(fixtures)}"
            )

            all_fixtures.extend(fixtures)

        except Exception as error:
            print(
                f"ERROR loading "
                f"{competition}: {error}"
            )

    return all_fixtures


# ============================================================
# COMPETITION TYPE
# ============================================================

def competition_type_for(competition):
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

def fixture_date_signature(fixture):
    """
    Same-day signature that ignores kickoff time.

    Used as a tolerant fallback when the team calendar and a
    competition calendar agree on the date and teams but disagree
    on the exact kickoff minute (e.g. a provisional vs. confirmed
    kickoff time). Without this, a fixture that is genuinely
    competitive can fall through to the "Friendly" default purely
    because of a kickoff-time discrepancy between feeds.
    """

    kickoff = fixture.get("kickoff")

    if not isinstance(kickoff, datetime):
        return None

    local = localise_kickoff(kickoff)

    home = normalise_team_name(
        fixture.get("home", "")
    )

    away = normalise_team_name(
        fixture.get("away", "")
    )

    return (
        local.date(),
        home.lower(),
        away.lower(),
    )


def build_competition_date_index(competition_fixtures):
    index = {}

    for fixture in competition_fixtures:

        signature = fixture_date_signature(
            fixture
        )

        if signature is None:
            continue

        index.setdefault(
            signature,
            [],
        ).append(fixture)

    return index


def _apply_competition_match(fixture, matches, status):
    selected = next(
        (
            item
            for item in matches
            if item.get("competition")
        ),
        matches[0],
    )

    competition = selected.get(
        "competition"
    )

    fixture["competition"] = competition

    fixture["competition_type"] = (
        competition_type_for(
            competition
        )
    )

    fixture["classification_status"] = status

    fixture["competition_source_ids"] = [
        item.get("source_id")
        for item in matches
        if item.get("source_id")
    ]

    fixture["matched_competition_sources"] = [
        item.get("source_name")
        for item in matches
        if item.get("source_name")
    ]

    return fixture


def classify_fixture(
    fixture,
    competition_index,
    competition_date_index=None,
):
    # --------------------------------------------------------
    # 1. Exact match: same date, same minute, same teams.
    # --------------------------------------------------------

    signature = fixture_signature(fixture)

    matches = competition_index.get(
        signature,
        [],
    )

    if matches:
        return _apply_competition_match(
            fixture,
            matches,
            "CONFIRMED_COMPETITIVE",
        )

    # --------------------------------------------------------
    # 2. Tolerant match: same date and teams, different kickoff
    #    time. This is the common case for cup ties and European
    #    fixtures where a provisional kickoff time in the team
    #    calendar hasn't yet been reconciled with the official
    #    competition calendar. Without this fallback these
    #    fixtures were being misclassified as "Friendly".
    # --------------------------------------------------------

    if competition_date_index:

        date_signature = fixture_date_signature(
            fixture
        )

        date_matches = competition_date_index.get(
            date_signature,
            [],
        )

        if date_matches:
            return _apply_competition_match(
                fixture,
                date_matches,
                "CONFIRMED_COMPETITIVE_TIME_ADJUSTED",
            )

    home = fixture.get("home", "")
    away = fixture.get("away", "")

    if (
        is_spfl_team(home)
        and is_spfl_team(away)
    ):
        fixture["competition"] = "Unclassified"
        fixture["competition_type"] = "UNKNOWN"
        fixture["classification_status"] = (
            "POTENTIALLY_MISSING_COMPETITION"
        )
        fixture["competition_source_ids"] = []
        fixture["matched_competition_sources"] = []

        return fixture

    fixture["competition"] = "Friendly"
    fixture["competition_type"] = "FRIENDLY"
    fixture["classification_status"] = "FRIENDLY"
    fixture["competition_source_ids"] = []
    fixture["matched_competition_sources"] = []

    return fixture


# ============================================================
# MERGE / DEDUPLICATE / SORT
# ============================================================

def merge_fixture_sources(
    team_fixtures,
    competition_fixtures,
):
    competition_index = {}

    for fixture in competition_fixtures:

        signature = fixture_signature(
            fixture
        )

        competition_index.setdefault(
            signature,
            [],
        ).append(fixture)

    competition_date_index = (
        build_competition_date_index(
            competition_fixtures
        )
    )

    merged = {}

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

        else:

            existing = merged[signature]

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
                not in existing["team_sources"]
            ):
                existing[
                    "team_sources"
                ].append(source_name)

            if (
                existing.get("home_score")
                is None
                and fixture.get("home_score")
                is not None
            ):
                existing["home_score"] = (
                    fixture["home_score"]
                )

                existing["away_score"] = (
                    fixture["away_score"]
                )

    classified = []

    for fixture in merged.values():

        classified.append(
            classify_fixture(
                fixture,
                competition_index,
                competition_date_index,
            )
        )

    classified.sort(
        key=lambda fixture:
        fixture.get("kickoff")
        or datetime.max.replace(
            tzinfo=UK_TZ
        )
    )

    return classified


# ============================================================
# SOURCE STATISTICS
# ============================================================

def print_source_statistics(
    team_fixtures,
    competition_fixtures,
    fixtures,
):
    print()
    print("=" * 70)
    print("FIXTUR.ES SOURCE / CLASSIFICATION AUDIT")
    print("=" * 70)

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
        f"{len(fixtures)}"
    )

    confirmed = sum(
        1
        for fixture in fixtures
        if fixture.get(
            "classification_status"
        )
        == "CONFIRMED_COMPETITIVE"
    )

    friendlies = sum(
        1
        for fixture in fixtures
        if fixture.get(
            "classification_status"
        )
        == "FRIENDLY"
    )

    potentially_missing = sum(
        1
        for fixture in fixtures
        if fixture.get(
            "classification_status"
        )
        == "POTENTIALLY_MISSING_COMPETITION"
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
    print("Classification breakdown:")

    counts = {}

    for fixture in fixtures:

        status = fixture.get(
            "classification_status",
            "UNKNOWN",
        )

        counts[status] = (
            counts.get(status, 0)
            + 1
        )

    for status, count in sorted(
        counts.items()
    ):
        print(
            f"  {status}: {count}"
        )

    print()
    print("Competition breakdown:")

    competition_counts = {}

    for fixture in fixtures:

        competition = (
            fixture.get("competition")
            or "Unclassified"
        )

        competition_counts[competition] = (
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
# COMPLETE FIXTURE AUDIT
# ============================================================

def print_complete_fixture_audit(fixtures):
    print()
    print("=" * 70)
    print("COMPLETE 2026/27 FIXTURE AUDIT")
    print("=" * 70)

    print(
        f"Total fixtures: {len(fixtures)}"
    )

    print()

    for number, fixture in enumerate(
        fixtures,
        start=1,
    ):

        kickoff = fixture.get("kickoff")

        if isinstance(
            kickoff,
            datetime,
        ):
            kickoff_text = kickoff.strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            )
        else:
            kickoff_text = str(kickoff)

        print(
            f"{number:04d} | "
            f"{kickoff_text} | "
            f"{fixture.get('home')} vs "
            f"{fixture.get('away')} | "
            f"{fixture.get('competition') or 'Unclassified'} | "
            f"{fixture.get('competition_type') or 'UNKNOWN'} | "
            f"{fixture.get('classification_status') or 'UNKNOWN'} | "
            f"VENUE=[{fixture.get('venue') or ''}] | "
            f"TEAM=[{', '.join(fixture.get('team_sources', []))}] | "
            f"COMP=[{', '.join(fixture.get('matched_competition_sources', []))}]"
        )


# ============================================================
# DETAILED AUDIT
# ============================================================

def print_detailed_audit(fixtures):
    print()
    print("=" * 70)
    print("DETAILED CLASSIFICATION AUDIT")
    print("=" * 70)

    competition_counts = {}

    for fixture in fixtures:

        competition = (
            fixture.get("competition")
            or "Unclassified"
        )

        competition_counts[competition] = (
            competition_counts.get(
                competition,
                0,
            )
            + 1
        )

    print()
    print("COMPETITION COUNTS")

    for competition, count in sorted(
        competition_counts.items()
    ):
        print(
            f"  {competition}: {count}"
        )

    classification_counts = {}

    for fixture in fixtures:

        status = (
            fixture.get(
                "classification_status"
            )
            or "UNKNOWN"
        )

        classification_counts[status] = (
            classification_counts.get(
                status,
                0,
            )
            + 1
        )

    print()
    print("CLASSIFICATION STATUS COUNTS")

    for status, count in sorted(
        classification_counts.items()
    ):
        print(
            f"  {status}: {count}"
        )

    type_counts = {}

    for fixture in fixtures:

        competition_type = (
            fixture.get(
                "competition_type"
            )
            or "UNKNOWN"
        )

        type_counts[competition_type] = (
            type_counts.get(
                competition_type,
                0,
            )
            + 1
        )

    print()
    print("COMPETITION TYPE COUNTS")

    for competition_type, count in sorted(
        type_counts.items()
    ):
        print(
            f"  {competition_type}: {count}"
        )

    missing = [
        fixture
        for fixture in fixtures
        if fixture.get(
            "classification_status"
        )
        == "POTENTIALLY_MISSING_COMPETITION"
    ]

    print()
    print(
        "POTENTIALLY MISSING COMPETITION FIXTURES"
    )

    if not missing:
        print("  None")
    else:
        for fixture in missing:

            kickoff = fixture.get(
                "kickoff"
            )

            if isinstance(
                kickoff,
                datetime,
            ):
                kickoff_text = kickoff.strftime(
                    "%Y-%m-%d %H:%M:%S %Z"
                )
            else:
                kickoff_text = str(kickoff)

            print(
                f"  {kickoff_text} | "
                f"{fixture.get('home')} vs "
                f"{fixture.get('away')} | "
                f"Team sources: "
                f"{', '.join(fixture.get('team_sources', []))}"
            )

    european = [
        fixture
        for fixture in fixtures
        if fixture.get(
            "competition_type"
        ) == "EUROPEAN"
    ]

    print()
    print("EUROPEAN FIXTURES")

    if not european:
        print("  None")
    else:
        for fixture in european:

            kickoff = fixture.get(
                "kickoff"
            )

            if isinstance(
                kickoff,
                datetime,
            ):
                kickoff_text = kickoff.strftime(
                    "%Y-%m-%d %H:%M:%S %Z"
                )
            else:
                kickoff_text = str(kickoff)

            print(
                f"  {kickoff_text} | "
                f"{fixture.get('home')} vs "
                f"{fixture.get('away')} | "
                f"{fixture.get('competition')}"
            )


# ============================================================
# PUBLIC API
# ============================================================

def get_all_fixtures():
    print()
    print("=" * 70)
    print("FIXTUR.ES IMPORT")
    print("=" * 70)

    print()
    print("Season: 2026/27")

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
        f"Team calendars: "
        f"{len(TEAM_CALENDARS)}"
    )

    print(
        f"Competition calendars: "
        f"{len(COMPETITION_CALENDARS)}"
    )

    team_fixtures = load_team_fixtures()

    competition_fixtures = (
        load_competition_fixtures(
            COMPETITION_CALENDARS
        )
    )

    fixtures = merge_fixture_sources(
        team_fixtures,
        competition_fixtures,
    )

    print_source_statistics(
        team_fixtures,
        competition_fixtures,
        fixtures,
    )

    print_detailed_audit(
        fixtures
    )

    print_complete_fixture_audit(
        fixtures
    )

    print()
    print("=" * 70)
    print("FIXTUR.ES IMPORT COMPLETE")
    print("=" * 70)

    print(
        f"Final fixture count: "
        f"{len(fixtures)}"
    )

    return fixtures


# ============================================================
# BACKWARDS COMPATIBILITY
# ============================================================

def build_fixtures():
    return get_all_fixtures()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    get_all_fixtures()
