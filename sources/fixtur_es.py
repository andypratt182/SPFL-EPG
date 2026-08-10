from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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


# Domestic competition calendars.

# These calendars classify fixtures discovered by the team
# calendars. They do NOT create fixtures.

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


# UEFA competition calendars.

# These are deliberately separate from domestic calendars.
# UEFA classification is based on actual calendar evidence.
# No date-based UEFA inference is performed.

EUROPEAN_COMPETITION_CALENDARS = {
    "Champions League":
        "https://ics.fixtur.es/v2/league/champions-league.ics",

    "Europa League":
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
# CLASSIFICATION CONSTANTS
# ============================================================

DOMESTIC_COMPETITIONS = {
    "Scottish Premiership",
    "Scottish Championship",
    "Scottish League One",
    "Scottish League Two",
    "Scottish Cup",
}

UEFA_COMPETITIONS = {
    "Champions League",
    "Europa League",
    "UEFA Conference League",
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

CLASSIFICATION_CONFIRMED = (
    "CONFIRMED_COMPETITIVE"
)

CLASSIFICATION_FRIENDLY = (
    "FRIENDLY"
)

CLASSIFICATION_MISSING = (
    "POTENTIALLY_MISSING_COMPETITION"
)

CLASSIFICATION_UNKNOWN = (
    "UNKNOWN"
)

COMPETITION_TYPE_DOMESTIC = "DOMESTIC"
COMPETITION_TYPE_UEFA = "UEFA"
COMPETITION_TYPE_FRIENDLY = "FRIENDLY"
COMPETITION_TYPE_UNKNOWN = "UNKNOWN"


# Fixtur.es team calendars can contain explicit UEFA markers.

UEFA_TAG_TO_COMPETITION = {
    "CL": "Champions League",
    "EL": "Europa League",
    "CONF": "UEFA Conference League",
}


# ============================================================
# TEAM NAME NORMALISATION
# ============================================================

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

    "st mirren": "St Mirren",
    "st mirren fc": "St Mirren",
}


def normalise_team_name(name):
    if not name:
        return ""

    name = str(name).strip()

    # Remove explicit UEFA markers before normalisation.
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

    name = " ".join(name.split())

    return TEAM_NAME_MAP.get(
        name.lower(),
        name,
    )


def is_spfl_team(name):
    return (
        normalise_team_name(name)
        in SPFL_TEAMS
    )


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

    A line beginning with a space or tab continues
    the previous physical line.
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

    Handles parameters such as:

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

        if (
            line.upper().startswith(
                prefix + ":"
            )
            or
            line.upper().startswith(
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

    # All-day dates.
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

    # Local timestamp without timezone.
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


# ============================================================
# SCORE PARSING
# ============================================================

def parse_score_from_summary(
    summary,
):
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


def remove_score_from_summary(
    summary,
):
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

def parse_match_summary(
    summary,
):
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
# UEFA MARKERS
# ============================================================

def get_uefa_tag(
    fixture,
):
    """
    Return an explicit Fixtur.es UEFA marker.

    Examples:

        [CL]   -> CL
        [EL]   -> EL
        [Conf] -> CONF

    The marker is diagnostic evidence only.
    It does not override the UEFA competition calendar.
    """

    summary = fixture.get(
        "raw_summary",
        "",
    )

    match = re.search(
        r"\[(CL|EL|Conf)\]\s*"
        r"(?:\(\d+\s*-\s*\d+\))?$",
        summary,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1).upper()


def get_explicit_uefa_competition(
    fixture,
):
    tag = get_uefa_tag(
        fixture
    )

    if tag is None:
        return None

    return UEFA_TAG_TO_COMPETITION.get(
        tag
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
        "raw_summary": summary,
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
# FIXTURE SIGNATURE
# ============================================================

def fixture_signature(
    fixture,
):
    """
    Canonical fixture identity.

    Production matching is deliberately exact:

        date
        time
        home team
        away team

    No approximate-date or team-only matching is used here.
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
                f"Usable fixtures: "
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
                f"Usable fixtures: "
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
# TEAM FIXTURE DISCOVERY
# ============================================================

def build_unique_team_fixtures(
    team_fixtures,
):
    """
    Build the authoritative fixture set.

    ONLY fixtures discovered through team calendars are
    allowed into the production fixture set.

    Competition calendars can never create fixtures.
    """

    discovered = {}

    for fixture in team_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature is None:
            continue

        if signature not in discovered:

            discovered[signature] = dict(
                fixture
            )

            discovered[signature][
                "verified_by_team_calendar"
            ] = True

            discovered[signature][
                "team_sources"
            ] = []

        team_source = fixture.get(
            "source_name"
        )

        if (
            team_source
            and team_source
            not in discovered[signature][
                "team_sources"
            ]
        ):

            discovered[signature][
                "team_sources"
            ].append(
                team_source
            )

        # Prefer a result if another team calendar has one.
        if (
            discovered[signature].get(
                "home_score"
            ) is None
            and fixture.get(
                "home_score"
            ) is not None
        ):

            discovered[signature][
                "home_score"
            ] = fixture[
                "home_score"
            ]

            discovered[signature][
                "away_score"
            ] = fixture[
                "away_score"
            ]

    return discovered


# ============================================================
# COMPETITION INDEX
# ============================================================

def build_competition_index(
    competition_fixtures,
):
    """
    Index competition calendars by exact fixture identity.

    This index is used only to classify already-discovered
    team-calendar fixtures.
    """

    index = {}

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

        index.setdefault(
            signature,
            [],
        )

        index[signature].append(
            fixture
        )

    return index


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_fixture(
    fixture,
    competition_index,
):
    """
    Classify a fixture that has already been discovered
    by a team calendar.

    Authority order:

        1. UEFA competition calendar
        2. Domestic competition calendar
        3. Friendly
        4. Potentially missing competition
        5. Unknown

    Fixture existence is NEVER determined by the competition
    calendars.
    """

    signature = fixture_signature(
        fixture
    )

    if signature is None:

        return {
            "competition": None,
            "competition_type":
                COMPETITION_TYPE_UNKNOWN,
            "classification_status":
                CLASSIFICATION_UNKNOWN,
            "classification_reason":
                "Unable to construct exact fixture identity.",
        }

    matches = competition_index.get(
        signature,
        [],
    )

    uefa_matches = [
        match
        for match in matches
        if match.get("competition")
        in UEFA_COMPETITIONS
    ]

    domestic_matches = [
        match
        for match in matches
        if match.get("competition")
        in DOMESTIC_COMPETITIONS
    ]

    # --------------------------------------------------------
    # 1. UEFA calendar authority
    # --------------------------------------------------------

    if uefa_matches:

        competitions = sorted(
            {
                match.get(
                    "competition"
                )
                for match in uefa_matches
                if match.get(
                    "competition"
                )
            }
        )

        competition = competitions[0]

        fixture["competition_source"] = (
            "UEFA competition calendar"
        )

        fixture["competition_source_ids"] = [
            match.get("source_id")
            for match in uefa_matches
            if match.get("source_id")
        ]

        return {
            "competition": competition,
            "competition_type":
                COMPETITION_TYPE_UEFA,
            "classification_status":
                CLASSIFICATION_CONFIRMED,
            "classification_reason":
                "Exact match in UEFA competition calendar.",
        }

    # --------------------------------------------------------
    # 2. Explicit UEFA marker
    # --------------------------------------------------------

    explicit_uefa = (
        get_explicit_uefa_competition(
            fixture
        )
    )

    if explicit_uefa:

        fixture["competition_source"] = (
            "Fixtur.es team-calendar marker"
        )

        return {
            "competition": None,
            "competition_type":
                COMPETITION_TYPE_UNKNOWN,
            "classification_status":
                CLASSIFICATION_MISSING,
            "classification_reason":
                "Team calendar explicitly marks this "
                f"fixture as {explicit_uefa}, but no "
                "exact UEFA competition-calendar match "
                "was found.",
        }

    # --------------------------------------------------------
    # 3. Domestic competition authority
    # --------------------------------------------------------

    if domestic_matches:

        competitions = sorted(
            {
                match.get(
                    "competition"
                )
                for match in domestic_matches
                if match.get(
                    "competition"
                )
            }
        )

        competition = competitions[0]

        fixture["competition_source"] = (
            "Domestic competition calendar"
        )

        fixture["competition_source_ids"] = [
            match.get("source_id")
            for match in domestic_matches
            if match.get("source_id")
        ]

        return {
            "competition": competition,
            "competition_type":
                COMPETITION_TYPE_DOMESTIC,
            "classification_status":
                CLASSIFICATION_CONFIRMED,
            "classification_reason":
                "Exact match in domestic competition calendar.",
        }

    # --------------------------------------------------------
    # 4. No competition match
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

    # Both SPFL clubs, but no competition calendar confirms
    # the fixture. Retain it and flag it for investigation.
    if home_spfl and away_spfl:

        return {
            "competition": None,
            "competition_type":
                COMPETITION_TYPE_UNKNOWN,
            "classification_status":
                CLASSIFICATION_MISSING,
            "classification_reason":
                "Both clubs are SPFL teams, but the fixture "
                "does not appear in any available domestic "
                "or UEFA competition calendar.",
        }

    # An SPFL team against a non-SPFL opponent with no
    # competition-calendar evidence is classified as friendly.
    if home_spfl != away_spfl:

        return {
            "competition": None,
            "competition_type":
                COMPETITION_TYPE_FRIENDLY,
            "classification_status":
                CLASSIFICATION_FRIENDLY,
            "classification_reason":
                "SPFL club has a non-SPFL opponent and no "
                "domestic or UEFA competition calendar "
                "confirms the fixture.",
        }

    # --------------------------------------------------------
    # 5. Genuine ambiguity
    # --------------------------------------------------------

    return {
        "competition": None,
        "competition_type":
            COMPETITION_TYPE_UNKNOWN,
        "classification_status":
            CLASSIFICATION_UNKNOWN,
        "classification_reason":
            "Fixture does not match a known competition "
            "and cannot safely be classified as a friendly.",
    }


def apply_classification(
    fixture,
    competition_index,
):
    classification = classify_fixture(
        fixture,
        competition_index,
    )

    fixture[
        "competition"
    ] = classification[
        "competition"
    ]

    fixture[
        "competition_type"
    ] = classification[
        "competition_type"
    ]

    fixture[
        "classification_status"
    ] = classification[
        "classification_status"
    ]

    fixture[
        "classification_reason"
    ] = classification[
        "classification_reason"
    ]

    return fixture


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
        f"Team-calendar records: "
        f"{len(team_fixtures)}"
    )

    print(
        f"Competition-calendar records: "
        f"{len(competition_fixtures)}"
    )

    print(
        f"Unique team-discovered fixtures: "
        f"{len(merged)}"
    )

    confirmed = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == CLASSIFICATION_CONFIRMED
    )

    domestic = sum(
        1
        for fixture in merged
        if fixture.get(
            "competition_type"
        )
        == COMPETITION_TYPE_DOMESTIC
    )

    uefa = sum(
        1
        for fixture in merged
        if fixture.get(
            "competition_type"
        )
        == COMPETITION_TYPE_UEFA
    )

    friendlies = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == CLASSIFICATION_FRIENDLY
    )

    missing = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == CLASSIFICATION_MISSING
    )

    unknown = sum(
        1
        for fixture in merged
        if fixture.get(
            "classification_status"
        )
        == CLASSIFICATION_UNKNOWN
    )

    print()
    print(
        "CLASSIFICATION SUMMARY"
    )

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
        f"{missing}"
    )

    print(
        f"Unknown: "
        f"{unknown}"
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "Team calendars are the fixture-discovery authority."
    )

    print(
        "Competition calendars only classify "
        "already-discovered team fixtures."
    )

    print(
        "UEFA classification requires an exact "
        "UEFA competition-calendar match."
    )

    print(
        "July/August timing is never used to infer UEFA."
    )

    print(
        "Unmatched non-SPFL fixtures are classified "
        "as FRIENDLY."
    )

    print(
        "Unmatched fixtures between two SPFL clubs are "
        "flagged as POTENTIALLY_MISSING_COMPETITION."
    )

    print(
        "Unknown is used only where the fixture cannot "
        "safely be classified."
    )


# ============================================================
# PUBLIC API
# ============================================================

def get_all_fixtures():
    """
    Main public interface.

    Production architecture:

        12 team calendars
                ↓
        fixture discovery
                ↓
        exact deduplication
                ↓
        domestic / UEFA classification
                ↓
        friendly / missing / unknown classification
                ↓
        final fixture list

    Competition calendars never create fixtures.
    """

    print()
    print("=" * 70)
    print("FIXTUR.ES IMPORT")
    print("=" * 70)

    print()
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
    # 1. DISCOVERY AUTHORITY
    #
    # Team calendars determine which fixtures exist.
    # --------------------------------------------------------

    team_fixtures = (
        load_team_fixtures()
    )

    unique_team_fixtures = (
        build_unique_team_fixtures(
            team_fixtures
        )
    )

    print()
    print(
        f"Unique team-calendar fixtures discovered: "
        f"{len(unique_team_fixtures)}"
    )

    # --------------------------------------------------------
    # 2. CLASSIFICATION SOURCES
    #
    # Competition feeds are loaded only to classify the
    # fixtures already discovered above.
    # --------------------------------------------------------

    domestic_fixtures = (
        load_competition_fixtures(
            COMPETITION_CALENDARS
        )
    )

    uefa_fixtures = (
        load_competition_fixtures(
            EUROPEAN_COMPETITION_CALENDARS
        )
    )

    competition_fixtures = (
        domestic_fixtures
        + uefa_fixtures
    )

    print()
    print(
        f"Domestic classification records: "
        f"{len(domestic_fixtures)}"
    )

    print(
        f"UEFA classification records: "
        f"{len(uefa_fixtures)}"
    )

    # --------------------------------------------------------
    # 3. BUILD CLASSIFICATION INDEX
    # --------------------------------------------------------

    competition_index = (
        build_competition_index(
            competition_fixtures
        )
    )

    # --------------------------------------------------------
    # 4. CLASSIFY EVERY DISCOVERED FIXTURE
    #
    # No fixture is discarded because it lacks a competition
    # calendar match.
    # --------------------------------------------------------

    merged = []

    for signature, fixture in (
        unique_team_fixtures.items()
    ):

        fixture = dict(
            fixture
        )

        fixture = apply_classification(
            fixture,
            competition_index,
        )

        merged.append(
            fixture
        )

    merged.sort(
        key=fixture_sort_key
    )

    # --------------------------------------------------------
    # 5. AUDIT OUTPUT
    # --------------------------------------------------------

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
            or "Unknown",
            "|",
            fixture.get(
                "competition_type"
            ),
            "|",
            fixture.get(
                "classification_status"
            ),
        )
