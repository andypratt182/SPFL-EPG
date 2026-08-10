"""
Fixtur.es full diagnostic audit.

This tool:

Loads all 12 SPFL team calendars.
Loads domestic competition calendars.
Loads UEFA Champions League, Europa League and Conference League calendars.
Builds unique 2026/27 fixtures.
Measures overlap between team and competition calendars.
Classifies every unmatched team-calendar fixture by likely reason.

DIAGNOSTIC ONLY:
This script does NOT modify fixture data or the EPG.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================
# PROJECT PATH
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from sources.fixtur_es import (  # noqa: E402
    TEAM_CALENDARS,
    COMPETITION_CALENDARS,
)


# ============================================================
# CONFIGURATION
# ============================================================

SEASON_START = datetime(2026, 7, 1)
SEASON_END = datetime(2027, 6, 30, 23, 59, 59)


TEAM_NAMES = {
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


# Names that commonly appear in Fixtur.es feeds
# but represent an SPFL club.

TEAM_ALIASES = {
    "rangers": "Rangers",
    "celtic": "Celtic",
    "aberdeen": "Aberdeen",
    "dundee": "Dundee",
    "dundee fc": "Dundee",
    "dundee united": "Dundee United",
    "hearts": "Hearts",
    "heart of midlothian": "Hearts",
    "hibernian": "Hibernian",
    "kilmarnock": "Kilmarnock",
    "motherwell": "Motherwell",
    "falkirk": "Falkirk",
    "st johnstone": "St Johnstone",
    "st. johnstone": "St Johnstone",
    "st mirren": "St Mirren",
}


# Domestic competitions.

DOMESTIC_COMPETITIONS = [
    "Scottish Premiership",
    "Scottish Championship",
    "Scottish League One",
    "Scottish League Two",
    "Scottish Cup",
]


# UEFA competitions.

UEFA_COMPETITIONS = [
    "Champions League",
    "Europa League",
    "UEFA Conference League",
]


ALL_COMPETITIONS = (
    DOMESTIC_COMPETITIONS
    + UEFA_COMPETITIONS
)


# The exact UEFA Fixtur.es URLs previously confirmed.

UEFA_COMPETITION_CALENDARS = {
    "Champions League":
        "https://ics.fixtur.es/v2/league/champions-league.ics",

    "Europa League":
        "https://ics.fixtur.es/v2/league/europa-league.ics",

    "UEFA Conference League":
        "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
}


# Broad UEFA qualifying/playoff period.
#
# This is deliberately a diagnostic window rather than an
# assertion that every fixture in this period is UEFA.

UEFA_PERIOD_START = datetime(2026, 7, 1)
UEFA_PERIOD_END = datetime(2026, 8, 31, 23, 59, 59)


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def fetch_ics(url: str, attempts: int = 3) -> str:
    """Download an ICS feed with simple retries."""

    last_error = None

    for attempt in range(1, attempts + 1):

        print(
            f"Request attempt {attempt}/{attempts}"
        )

        try:

            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(compatible; SPFL-EPG-FixturES-Audit/1.0)"
                    )
                },
            )

            with urlopen(
                request,
                timeout=30,
            ) as response:

                status = getattr(
                    response,
                    "status",
                    200,
                )

                data = response.read()

            text = data.decode(
                "utf-8",
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

        except (
            HTTPError,
            URLError,
            OSError,
            ValueError,
        ) as exc:

            last_error = exc

            print(
                f"HTTP error: {exc}"
            )

    raise RuntimeError(
        f"Unable to download Fixtur.es feed after "
        f"{attempts} attempts: {last_error}"
    )


def unfold_ics(text: str) -> list[str]:
    """
    Unfold RFC5545 continuation lines.

    Lines beginning with a space or tab continue the previous line.
    """

    raw_lines = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    )

    lines: list[str] = []

    for line in raw_lines:

        if (
            line.startswith((" ", "\t"))
            and lines
        ):

            lines[-1] += line[1:]

        else:

            lines.append(line)

    return lines


def parse_ics_events(
    text: str,
) -> list[dict[str, str]]:
    """
    Parse the small subset of ICS fields required by this diagnostic.
    """

    lines = unfold_ics(text)

    events: list[dict[str, str]] = []

    current: dict[str, str] | None = None

    for line in lines:

        if line == "BEGIN:VEVENT":

            current = {}

        elif line == "END:VEVENT":

            if current is not None:
                events.append(current)

            current = None

        elif (
            current is not None
            and ":" in line
        ):

            key, value = line.split(
                ":",
                1,
            )

            # Strip parameters:
            # DTSTART;TZID=Europe/London
            # DTSTART;VALUE=DATE

            base_key = (
                key
                .split(";", 1)[0]
                .upper()
            )

            if base_key in {
                "UID",
                "DTSTART",
                "DTEND",
                "SUMMARY",
                "STATUS",
                "DESCRIPTION",
            }:

                current[base_key] = value

    return events


def parse_ics_datetime(
    value: str,
) -> datetime | None:
    """Parse common Fixtur.es UTC/local ICS datetime formats."""

    if not value:
        return None

    value = value.strip()

    formats = [
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
        "%Y%m%d",
    ]

    for fmt in formats:

        try:

            return datetime.strptime(
                value,
                fmt,
            )

        except ValueError:
            pass

    return None


def clean_text(
    value: str | None,
) -> str:
    """Clean ICS text for diagnostic output."""

    if not value:
        return ""

    return (
        value
        .replace("\n", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def normalise_team_name(
    name: str,
) -> str:
    """Normalise common team-name variations."""

    value = (
        clean_text(name)
        .lower()
        .strip()
    )

    return TEAM_ALIASES.get(
        value,
        name.strip(),
    )


def split_fixture(
    summary: str,
) -> tuple[str, str] | None:
    """
    Split:

        Rangers - Celtic
        Dundee FC - Rangers (1-1)

    Returns:

        home, away
    """

    summary = clean_text(summary)

    # Remove result.

    if " (" in summary:
        summary = summary.split(
            " (",
            1,
        )[0]

    if " - " not in summary:
        return None

    home, away = summary.split(
        " - ",
        1,
    )

    return (
        home.strip(),
        away.strip(),
    )


def fixture_teams(
    summary: str,
) -> tuple[str, str] | None:

    pair = split_fixture(summary)

    if pair is None:
        return None

    home, away = pair

    return (
        normalise_team_name(home),
        normalise_team_name(away),
    )


def is_season_fixture(
    event: dict[str, str],
) -> bool:

    dt = parse_ics_datetime(
        event.get(
            "DTSTART",
            "",
        )
    )

    if dt is None:
        return False

    return (
        SEASON_START
        <= dt
        <= SEASON_END
    )


def fixture_key(
    event: dict[str, str],
    include_time: bool = True,
) -> tuple | None:
    """
    Canonical fixture key.

    Team names are normalised so that:

    Dundee / Dundee FC
    Hearts / Heart of Midlothian
    St Johnstone / St. Johnstone

    resolve to the same teams.
    """

    dt = parse_ics_datetime(
        event.get(
            "DTSTART",
            "",
        )
    )

    teams = fixture_teams(
        event.get(
            "SUMMARY",
            "",
        )
    )

    if dt is None or teams is None:
        return None

    home, away = teams

    if include_time:

        return (
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            home,
            away,
        )

    return (
        dt.year,
        dt.month,
        dt.day,
        home,
        away,
    )


def team_fixture_key(
    event: dict[str, str],
) -> tuple | None:

    return fixture_key(
        event,
        include_time=True,
    )


def fixture_date_key(
    event: dict[str, str],
) -> tuple | None:

    return fixture_key(
        event,
        include_time=False,
    )


def get_event_datetime(
    event: dict[str, str],
) -> datetime | None:

    return parse_ics_datetime(
        event.get(
            "DTSTART",
            "",
        )
    )


def is_spfl_team(
    name: str,
) -> bool:

    return (
        normalise_team_name(name)
        in TEAM_NAMES
    )


def get_competition_for_fixture(
    event: dict[str, str],
    competition_index: dict[
        tuple,
        set[str],
    ],
) -> set[str]:
    """Return competition names matching an exact fixture key."""

    key = fixture_key(
        event,
        include_time=True,
    )

    if key is None:
        return set()

    return competition_index.get(
        key,
        set(),
    )


def get_date_matches(
    event: dict[str, str],
    competition_events: list[
        tuple[str, dict[str, str]]
    ],
) -> list[
    tuple[str, dict[str, str]]
]:

    """
    Find competition events with the same teams/date
    but potentially different kickoff time.
    """

    target = fixture_date_key(
        event
    )

    if target is None:
        return []

    matches = []

    for competition, candidate in competition_events:

        if (
            fixture_date_key(candidate)
            == target
        ):

            matches.append(
                (
                    competition,
                    candidate,
                )
            )

    return matches


def same_teams_ignoring_date(
    event: dict[str, str],
    candidate: dict[str, str],
) -> bool:

    a = fixture_teams(
        event.get(
            "SUMMARY",
            "",
        )
    )

    b = fixture_teams(
        candidate.get(
            "SUMMARY",
            "",
        )
    )

    if a is None or b is None:
        return False

    return a == b


def find_team_name_variation_matches(
    event: dict[str, str],
    competition_events: list[
        tuple[str, dict[str, str]]
    ],
) -> list[
    tuple[str, dict[str, str]]
]:
    """
    Detect likely name mismatches.

    This intentionally compares raw names against normalised names
    rather than merely looking for an exact canonical key.
    """

    raw_pair = split_fixture(
        event.get(
            "SUMMARY",
            "",
        )
    )

    if raw_pair is None:
        return []

    raw_home, raw_away = raw_pair

    target_dt = get_event_datetime(
        event
    )

    if target_dt is None:
        return []

    matches = []

    for competition, candidate in competition_events:

        candidate_dt = get_event_datetime(
            candidate
        )

        if candidate_dt is None:
            continue

        if (
            abs(
                (
                    candidate_dt
                    - target_dt
                ).total_seconds()
            )
            > 15 * 60
        ):

            continue

        candidate_pair = split_fixture(
            candidate.get(
                "SUMMARY",
                "",
            )
        )

        if candidate_pair is None:
            continue

        cand_home, cand_away = candidate_pair

        if (
            normalise_team_name(raw_home)
            == normalise_team_name(cand_home)
            and normalise_team_name(raw_away)
            == normalise_team_name(cand_away)
            and (
                raw_home.strip().lower()
                != cand_home.strip().lower()
                or raw_away.strip().lower()
                != cand_away.strip().lower()
            )
        ):

            matches.append(
                (
                    competition,
                    candidate,
                )
            )

    return matches


def find_team_time_mismatch(
    event: dict[str, str],
    competition_events: list[
        tuple[str, dict[str, str]]
    ],
) -> list[
    tuple[str, dict[str, str]]
]:
    """
    Detect same fixture on same date where kickoff differs.

    This is deliberately kept separate from name mismatch detection.
    """

    target_date = fixture_date_key(
        event
    )

    if target_date is None:
        return []

    matches = []

    for competition, candidate in competition_events:

        if (
            fixture_date_key(candidate)
            != target_date
        ):

            continue

        if not same_teams_ignoring_date(
            event,
            candidate,
        ):

            continue

        target_dt = get_event_datetime(
            event
        )

        candidate_dt = get_event_datetime(
            candidate
        )

        if (
            target_dt is None
            or candidate_dt is None
        ):

            continue

        difference = abs(
            (
                target_dt
                - candidate_dt
            ).total_seconds()
        )

        # More than 15 minutes is considered
        # a meaningful mismatch.

        if difference > 15 * 60:

            matches.append(
                (
                    competition,
                    candidate,
                )
            )

    return matches


def find_uefa_fixture_matches(
    event: dict[str, str],
    uefa_events: list[
        tuple[str, dict[str, str]]
    ],
) -> list[
    tuple[str, dict[str, str]]
]:
    """
    Find a corresponding UEFA fixture using:

    - canonical teams
    - same date
    - small kickoff tolerance

    This is the strongest UEFA signal available
    to this diagnostic.
    """

    target_dt = get_event_datetime(
        event
    )

    target_teams = fixture_teams(
        event.get(
            "SUMMARY",
            "",
        )
    )

    if (
        target_dt is None
        or target_teams is None
    ):

        return []

    matches = []

    for competition, candidate in uefa_events:

        candidate_dt = get_event_datetime(
            candidate
        )

        candidate_teams = fixture_teams(
            candidate.get(
                "SUMMARY",
                "",
            )
        )

        if (
            candidate_dt is None
            or candidate_teams is None
        ):

            continue

        if candidate_teams != target_teams:
            continue

        if (
            abs(
                (
                    candidate_dt
                    - target_dt
                ).total_seconds()
            )
            <= 24 * 3600
        ):

            matches.append(
                (
                    competition,
                    candidate,
                )
            )

    return matches


# ============================================================
# LOADING
# ============================================================

def load_team_calendars():

    print(
        "=" * 70
    )

    print(
        "TEAM CALENDAR SUMMARY"
    )

    print(
        "=" * 70
    )

    team_events = {}

    total_events = 0
    total_season_events = 0
    failures = 0

    for team, url in TEAM_CALENDARS.items():

        print()
        print(team)

        try:

            text = fetch_ics(url)

            events = parse_ics_events(
                text
            )

            season_events = [
                event
                for event in events
                if is_season_fixture(event)
            ]

            team_events[team] = (
                season_events
            )

            print(
                f"{len(events)} VEVENTs, "
                f"{len(season_events)} in 2026/27"
            )

            total_events += len(events)

            total_season_events += (
                len(season_events)
            )

        except Exception as exc:

            print(
                f"ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            failures += 1

            team_events[team] = []

    print()

    print(
        f"Total VEVENT records: "
        f"{total_events}"
    )

    print(
        f"Total 2026/27 events: "
        f"{total_season_events}"
    )

    if failures:

        print(
            f"Failed team feeds: "
            f"{failures}"
        )

    return team_events


def load_competition_calendars():

    print()
    print(
        "=" * 70
    )

    print(
        "DOMESTIC COMPETITION CALENDAR SUMMARY"
    )

    print(
        "=" * 70
    )

    competition_events = {}

    total_events = 0
    total_season_events = 0
    failures = 0

    for competition in DOMESTIC_COMPETITIONS:

        url = COMPETITION_CALENDARS.get(
            competition
        )

        print()
        print(competition)
        print(f"URL: {url}")

        if not url:

            print(
                "ERROR: No URL configured."
            )

            competition_events[
                competition
            ] = []

            failures += 1

            continue

        try:

            text = fetch_ics(url)

            events = parse_ics_events(
                text
            )

            season_events = [
                event
                for event in events
                if is_season_fixture(event)
            ]

            competition_events[
                competition
            ] = season_events

            print(
                f"VEVENTs: "
                f"{len(events)}"
            )

            print(
                f"2026/27 events: "
                f"{len(season_events)}"
            )

            total_events += len(events)

            total_season_events += (
                len(season_events)
            )

        except Exception as exc:

            print(
                f"ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            failures += 1

            competition_events[
                competition
            ] = []

    print()

    print(
        f"Total VEVENT records: "
        f"{total_events}"
    )

    print(
        f"Total 2026/27 events: "
        f"{total_season_events}"
    )

    if failures:

        print(
            f"Failed domestic feeds: "
            f"{failures}"
        )

    return competition_events


def load_uefa_calendars():

    print()
    print(
        "=" * 70
    )

    print(
        "UEFA COMPETITION CALENDAR SUMMARY"
    )

    print(
        "=" * 70
    )

    competition_events = {}

    total_events = 0
    total_season_events = 0
    failures = 0

    for competition, url in (
        UEFA_COMPETITION_CALENDARS.items()
    ):

        print()
        print(competition)
        print(f"URL: {url}")

        try:

            text = fetch_ics(url)

            events = parse_ics_events(
                text
            )

            season_events = [
                event
                for event in events
                if is_season_fixture(event)
            ]

            competition_events[
                competition
            ] = season_events

            print(
                f"VEVENTs: "
                f"{len(events)}"
            )

            print(
                f"2026/27 events: "
                f"{len(season_events)}"
            )

            total_events += len(events)

            total_season_events += (
                len(season_events)
            )

        except Exception as exc:

            print(
                f"ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            failures += 1

            competition_events[
                competition
            ] = []

    print()

    print(
        f"Total UEFA VEVENT records: "
        f"{total_events}"
    )

    print(
        f"Total UEFA 2026/27 events: "
        f"{total_season_events}"
    )

    if failures:

        print(
            f"Failed UEFA feeds: "
            f"{failures}"
        )

    return competition_events


# ============================================================
# UNIQUE FIXTURE CONSTRUCTION
# ============================================================

def build_unique_team_fixtures(
    team_events,
):

    fixtures = {}

    for team, events in team_events.items():

        for event in events:

            key = team_fixture_key(
                event
            )

            if key is not None:

                fixtures.setdefault(
                    key,
                    event,
                )

    return fixtures


def build_unique_competition_fixtures(
    competition_events,
):

    fixtures = {}

    fixture_competitions = (
        defaultdict(set)
    )

    for competition, events in (
        competition_events.items()
    ):

        for event in events:

            key = team_fixture_key(
                event
            )

            if key is None:
                continue

            fixtures.setdefault(
                key,
                event,
            )

            fixture_competitions[
                key
            ].add(competition)

    return (
        fixtures,
        fixture_competitions,
    )


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_unmatched_fixture(
    event,
    all_competition_events,
    uefa_events,
):
    """
    Classify an unmatched team-calendar fixture.

    Priority is intentional:

    1. UEFA exact/near match
    2. Competition date/time mismatch
    3. Name mismatch
    4. SPFL-v-SPFL domestic cup candidate
    5. Non-SPFL opponent during UEFA period
    6. Friendly
    7. Genuine unclassified
    """

    dt = get_event_datetime(
        event
    )

    teams = fixture_teams(
        event.get(
            "SUMMARY",
            "",
        )
    )

    if (
        dt is None
        or teams is None
    ):

        return (
            "GENUINE UNCLASSIFIED",
            "Unable to parse fixture date or team names.",
        )

    home, away = teams

    home_spfl = is_spfl_team(
        home
    )

    away_spfl = is_spfl_team(
        away
    )

    both_spfl = (
        home_spfl
        and away_spfl
    )

    has_non_spfl = (
        home_spfl
        != away_spfl
    )

    # --------------------------------------------------------
    # 1. UEFA calendar evidence
    # --------------------------------------------------------

    uefa_matches = (
        find_uefa_fixture_matches(
            event,
            uefa_events,
        )
    )

    if uefa_matches:

        competitions = ", ".join(
            sorted(
                {
                    competition
                    for competition, _
                    in uefa_matches
                }
            )
        )

        return (
            "POSSIBLE MISSING UEFA",
            "Matching fixture found in UEFA "
            f"calendar(s): {competitions}.",
        )

    # --------------------------------------------------------
    # 2. Same teams/date, different kickoff
    # --------------------------------------------------------

    time_matches = (
        find_team_time_mismatch(
            event,
            all_competition_events,
        )
    )

    if time_matches:

        details = ", ".join(
            f"{competition} "
            f"({candidate.get('DTSTART', '?')})"
            for competition, candidate
            in time_matches[:3]
        )

        return (
            "POSSIBLE COMPETITION DATE/TIME MISMATCH",
            "Same fixture found in competition data "
            "with different kickoff: "
            f"{details}.",
        )

    # --------------------------------------------------------
    # 3. Raw-name mismatch
    # --------------------------------------------------------

    name_matches = (
        find_team_name_variation_matches(
            event,
            all_competition_events,
        )
    )

    if name_matches:

        details = ", ".join(
            competition
            for competition, _
            in name_matches[:3]
        )

        return (
            "NAME MISMATCH",
            "Likely same fixture exists with "
            "different team naming in: "
            f"{details}.",
        )

    # --------------------------------------------------------
    # 4. Both teams are SPFL clubs
    # --------------------------------------------------------

    if both_spfl:

        return (
            "POSSIBLE MISSING DOMESTIC CUP",
            "Both clubs are SPFL teams but no "
            "domestic competition-calendar match "
            "was found.",
        )

    # --------------------------------------------------------
    # 5. Non-SPFL opponent during UEFA period
    #
    # IMPORTANT:
    #
    # We no longer assume that every fixture in this
    # window is UEFA.
    #
    # We only call it "possible missing UEFA" when
    # the date is in the UEFA period AND the fixture
    # is against a genuinely non-SPFL opponent.
    # --------------------------------------------------------

    if (
        has_non_spfl
        and UEFA_PERIOD_START
        <= dt
        <= UEFA_PERIOD_END
    ):

        return (
            "POSSIBLE MISSING UEFA",
            "SPFL club has a non-SPFL opponent during "
            "the UEFA qualifying/playoff period, but "
            "no matching UEFA calendar fixture was found.",
        )

    # --------------------------------------------------------
    # 6. Pre-season / friendly
    # --------------------------------------------------------

    if (
        has_non_spfl
        and dt.month == 7
    ):

        return (
            "FRIENDLY",
            "Non-SPFL opponent in July with no "
            "competition calendar classification.",
        )

    # --------------------------------------------------------
    # 7. Genuine unknown
    # --------------------------------------------------------

    return (
        "GENUINE UNCLASSIFIED",
        "Fixture does not match any current diagnostic rule.",
    )


# ============================================================
# AUDIT
# ============================================================

def run_audit(
    team_events,
    competition_events,
):

    team_fixtures = (
        build_unique_team_fixtures(
            team_events
        )
    )

    (
        competition_fixtures,
        fixture_competitions,
    ) = build_unique_competition_fixtures(
        competition_events
    )

    # Flatten competition events for detailed matching.

    all_competition_events = []

    for competition, events in (
        competition_events.items()
    ):

        for event in events:

            all_competition_events.append(
                (
                    competition,
                    event,
                )
            )

    uefa_events = [
        item
        for item in all_competition_events
        if item[0] in UEFA_COMPETITIONS
    ]

    exact_overlap = (
        set(team_fixtures.keys())
        & set(competition_fixtures.keys())
    )

    team_only_keys = (
        set(team_fixtures.keys())
        - set(competition_fixtures.keys())
    )

    competition_only_keys = (
        set(competition_fixtures.keys())
        - set(team_fixtures.keys())
    )

    print()
    print(
        "=" * 70
    )

    print(
        "FULL OVERLAP / CLASSIFICATION AUDIT"
    )

    print(
        "=" * 70
    )

    print(
        "Unique team-calendar fixtures:        "
        f"{len(team_fixtures)}"
    )

    print(
        "Unique competition-calendar fixtures: "
        f"{len(competition_fixtures)}"
    )

    print(
        "Exact fixture overlap:                "
        f"{len(exact_overlap)}"
    )

    print(
        "Team-calendar only:                   "
        f"{len(team_only_keys)}"
    )

    print(
        "Competition-calendar only:            "
        f"{len(competition_only_keys)}"
    )

    # --------------------------------------------------------
    # Coverage
    # --------------------------------------------------------

    print()
    print("COVERAGE")

    if team_fixtures:

        team_coverage = (
            len(exact_overlap)
            / len(team_fixtures)
            * 100
        )

    else:

        team_coverage = 0

    if competition_fixtures:

        competition_coverage = (
            len(exact_overlap)
            / len(competition_fixtures)
            * 100
        )

    else:

        competition_coverage = 0

    print(
        "Competition coverage of team fixtures: "
        f"{team_coverage:.1f}%"
    )

    print(
        "Team coverage of competition fixtures: "
        f"{competition_coverage:.1f}%"
    )

    # --------------------------------------------------------
    # Competition overlap
    # --------------------------------------------------------

    print()
    print("OVERLAP BY COMPETITION")

    for competition in ALL_COMPETITIONS:

        events = competition_events.get(
            competition,
            [],
        )

        keys = {
            team_fixture_key(event)
            for event in events
            if team_fixture_key(event)
            is not None
        }

        matched = (
            keys
            & set(team_fixtures.keys())
        )

        percentage = (
            len(matched)
            / len(keys)
            * 100
            if keys
            else 0
        )

        print(
            f"{competition}: "
            f"{len(matched)}/{len(keys)} "
            f"({percentage:.1f}%)"
        )

    # --------------------------------------------------------
    # Classify unmatched team fixtures
    # --------------------------------------------------------

    classifications = (
        defaultdict(list)
    )

    for key in sorted(
        team_only_keys
    ):

        event = team_fixtures[key]

        category, reason = (
            classify_unmatched_fixture(
                event,
                all_competition_events,
                uefa_events,
            )
        )

        classifications[
            category
        ].append(
            (
                event,
                reason,
            )
        )

    category_order = [
        "FRIENDLY",
        "POSSIBLE MISSING UEFA",
        "POSSIBLE MISSING DOMESTIC CUP",
        "POSSIBLE COMPETITION DATE/TIME MISMATCH",
        "NAME MISMATCH",
        "GENUINE UNCLASSIFIED",
    ]

    print()

    for category in category_order:

        print(
            f"{category}: "
            f"{len(classifications.get(category, []))}"
        )

    print()

    print(
        "TOTAL UNMATCHED: "
        f"{len(team_only_keys)}"
    )

    # --------------------------------------------------------
    # Detailed unmatched fixtures
    # --------------------------------------------------------

    for category in category_order:

        fixtures = classifications.get(
            category,
            [],
        )

        if not fixtures:
            continue

        print()
        print(
            "-" * 70
        )

        print(
            f"## {category}: "
            f"{len(fixtures)}"
        )

        print(
            "-" * 70
        )

        for event, reason in sorted(
            fixtures,
            key=lambda item: (
                get_event_datetime(item[0])
                or datetime.max,
                clean_text(
                    item[0].get(
                        "SUMMARY"
                    )
                ),
            ),
        ):

            dt = get_event_datetime(
                event
            )

            if dt is None:

                date_text = (
                    "UNKNOWN DATE"
                )

            else:

                date_text = dt.strftime(
                    "%Y-%m-%d %H:%M"
                )

            summary = clean_text(
                event.get(
                    "SUMMARY",
                    "UNKNOWN FIXTURE",
                )
            )

            print()
            print(
                f"{date_text} | {summary}"
            )

            print(
                f"Reason: {reason}"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )

    print(
        "CLASSIFICATION SUMMARY"
    )

    print(
        "=" * 70
    )

    for category in category_order:

        count = len(
            classifications.get(
                category,
                [],
            )
        )

        percentage = (
            count
            / len(team_only_keys)
            * 100
            if team_only_keys
            else 0
        )

        print(
            f"{category}: "
            f"{count} "
            f"({percentage:.1f}%)"
        )

    print()

    print(
        "Team-calendar fixtures analysed: "
        f"{len(team_fixtures)}"
    )

    print(
        "Competition-calendar fixtures analysed: "
        f"{len(competition_fixtures)}"
    )

    print(
        f"Exact overlaps: "
        f"{len(exact_overlap)}"
    )

    print(
        "Unmatched team fixtures: "
        f"{len(team_only_keys)}"
    )

    print(
        "Classified unmatched fixtures: "
        f"{sum(len(v) for v in classifications.values())}"
    )

    print(
        "Genuine unclassified: "
        f"{len(classifications.get('GENUINE UNCLASSIFIED', []))}"
    )

    print()

    print(
        "This classification is diagnostic only."
    )

    print(
        "No fixture data has been modified."
    )

    print(
        "sources/fixtur_es.py was not modified."
    )

    print(
        "fixtures.py was not modified."
    )

    print(
        "generator.py was not modified."
    )

    return (
        team_fixtures,
        competition_fixtures,
        classifications,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    team_events = (
        load_team_calendars()
    )

    domestic_events = (
        load_competition_calendars()
    )

    uefa_events = (
        load_uefa_calendars()
    )

    # Combine domestic and UEFA calendars for the audit.
    #
    # The individual feeds remain separately identifiable
    # by their competition names.

    competition_events = {}

    competition_events.update(
        domestic_events
    )

    competition_events.update(
        uefa_events
    )

    run_audit(
        team_events,
        competition_events,
    )

    print()

    print(
        "RESULT: All available team, domestic "
        "and UEFA competition calendars were processed."
    )


if __name__ == "__main__":
    main()
