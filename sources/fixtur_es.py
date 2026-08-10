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
    "Rangers": "rangers",
    "Celtic": "celtic",
    "Aberdeen": "aberdeen",
    "Dundee": "dundee",
    "Dundee United": "dundee-united",
    "Hearts": "hearts",
    "Hibernian": "hibernian",
    "Kilmarnock": "kilmarnock",
    "Motherwell": "motherwell",
    "Falkirk": "falkirk",
    "St Johnstone": "st-johnstone",
    "St Mirren": "st-mirren",
}


def build_team_feed_url(slug: str) -> str:
    """
    Build the Fixtur.es ICS URL for a team.
    """

    return (
        "https://ics.fixtur.es/v2/"
        f"{slug}.ics"
    )


# Competition calendars confirmed by the Fixtur.es diagnostic.
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


# Kept separate so European competitions can be added later
# without changing the importer architecture.
EUROPEAN_COMPETITION_CALENDARS = {}


USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; SPFL-EPG/1.0; +https://github.com/andypratt182/SPFL-EPG)"
)

MAX_ATTEMPTS = 3
RETRY_DELAY = 2


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

    # Remove common suffixes/prefixes.
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

    # Fixtur.es uses:
    #
    # Rangers - Celtic
    #
    # We split on the first separator.
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
# FIXTURE SIGNATURE
# ============================================================

def fixture_signature(fixture):
    kickoff = fixture.get(
        "kickoff"
    )

    if isinstance(
        kickoff,
        datetime,
    ):

        kickoff_key = (
            kickoff.isoformat()
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
# DEDUPLICATION
# ============================================================

def merge_fixture_sources(
    team_fixtures,
    competition_fixtures,
):
    merged = {}

    team_verified = set()

    # --------------------------------------------------------
    # Team calendars first.
    #
    # They establish that the fixture exists and provide
    # fallback coverage for fixtures not found in a
    # competition calendar.
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

        team_verified.add(
            signature
        )

    # --------------------------------------------------------
    # Competition calendars.
    #
    # Competition feeds are authoritative for competition
    # classification.
    # --------------------------------------------------------

    for fixture in competition_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature not in merged:

            merged[signature] = dict(
                fixture
            )

            merged[signature][
                "verified_by_team_calendar"
            ] = False

            merged[signature][
                "team_sources"
            ] = []

            merged[signature][
                "competition_source"
            ] = True

            continue

        existing = merged[
            signature
        ]

        competition = fixture.get(
            "competition"
        )

        if competition:

            existing[
                "competition"
            ] = competition

        existing[
            "competition_source"
        ] = True

        # Preserve the competition source ID.
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

        # Prefer a score if the competition calendar has one.
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
# COMPETITION FALLBACK
# ============================================================

def infer_fallback_competition(
    fixture,
):
    """
    Do not guess competitions from the teams.

    If a competition calendar has classified the fixture,
    retain that classification.

    Otherwise leave it as None/Unknown.

    This is deliberately conservative. A Rangers vs Celtic
    fixture, for example, could be a Premiership match,
    Scottish Cup match, League Cup match, or European match.
    Team names alone cannot safely determine the competition.
    """

    competition = fixture.get(
        "competition"
    )

    if competition:
        return competition

    return None


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
        "FIXTUR.ES SOURCE AUDIT"
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
        f"Unique fixtures: "
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
            "competition"
        )
    )

    competition_only = sum(
        1
        for fixture in merged
        if fixture.get(
            "competition_source"
        )
        and not fixture.get(
            "verified_by_team_calendar"
        )
    )

    team_only = sum(
        1
        for fixture in merged
        if fixture.get(
            "verified_by_team_calendar"
        )
        and not fixture.get(
            "competition_source"
        )
    )

    print(
        f"Team-calendar verified: "
        f"{verified}"
    )

    print(
        f"Competition classified: "
        f"{classified}"
    )

    print(
        f"Competition-only fixtures: "
        f"{competition_only}"
    )

    print(
        f"Team-only fixtures: "
        f"{team_only}"
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
            or "Unknown"
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

        competition calendars
                ↓
        competition classification
                ↑
        team calendars
                ↓
        deduplicated fixture set

    No database is used.

    The returned list is suitable for fixtures.py.
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
        "Team calendars: "
        f"{len(TEAM_CALENDARS)}"
    )

    print(
        "Competition calendars: "
        f"{len(COMPETITION_CALENDARS)}"
    )

    team_fixtures = (
        load_team_fixtures()
    )

    competition_fixtures = (
        load_competition_fixtures(
            COMPETITION_CALENDARS
        )
    )

    # European calendars are deliberately optional.
    if EUROPEAN_COMPETITION_CALENDARS:

        european_fixtures = (
            load_competition_fixtures(
                EUROPEAN_COMPETITION_CALENDARS
            )
        )

        competition_fixtures.extend(
            european_fixtures
        )

    merged = merge_fixture_sources(
        team_fixtures,
        competition_fixtures,
    )

    for fixture in merged:

        fixture[
            "competition"
        ] = infer_fallback_competition(
            fixture
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
        "First 20 normalised fixtures:"
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
        )
