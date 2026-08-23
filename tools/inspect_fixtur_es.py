"""
Fixtur.es full diagnostic audit.

This tool:

Loads all 12 SPFL team calendars.
Loads domestic competition calendars.
Loads UEFA Champions League, Europa League and Conference League calendars.
Builds unique 2026/27 fixtures.
Measures overlap between team and competition calendars.
Classifies unmatched team-calendar fixtures intelligently.

DIAGNOSTIC ONLY:
This script does NOT modify fixture data or the EPG.

Classification priority:

1. UEFA competition-calendar evidence
2. Domestic competition-calendar evidence
3. Friendly
4. Potentially missing competition classification
5. Unknown

IMPORTANT:

A July/August fixture is NOT classified as UEFA merely because of
its date.

The UEFA competition calendars are treated as the authority for
UEFA competitive classification.
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# PROJECT IMPORTS
#
# ICS parsing and team-name normalisation used to be reimplemented
# here as a second copy of sources/fixtur_es.py's logic. That's how
# they drifted apart: this diagnostic tool worked out the
# time-tolerant classification fix documented below, but production
# never got it, because there was no shared code forcing the two to
# stay in sync. Both files now import the same primitives from
# ics.py / normalisation.py.
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ics import (  # noqa: E402
    download_ics,
    parse_ics_datetime as _parse_ics_datetime,
    parse_match_summary,
    split_events,
    property_value,
)
from normalisation import SPFL_TEAMS as TEAM_NAMES  # noqa: E402
from normalisation import is_spfl_team  # noqa: E402
from normalisation import normalise_team_name  # noqa: E402
from sources.fixtur_es import (  # noqa: E402
    TEAM_CALENDARS,
    COMPETITION_CALENDARS,
)

logger = logging.getLogger(__name__)


# ============================================================
# DIAGNOSTIC-ONLY COMPETITION FEED EXTENSIONS
# ============================================================
#
# Keep the existing competition configuration from sources/fixtur_es.py
# intact, and additionally load the three UEFA competition feeds
# required for authoritative UEFA classification. This mapping is
# local to this diagnostic tool only.
#
AUDIT_COMPETITION_CALENDARS = dict(COMPETITION_CALENDARS)

AUDIT_COMPETITION_CALENDARS.update(
    {
        "Champions League": "https://ics.fixtur.es/v2/league/champions-league.ics",
        "Europa League": "https://ics.fixtur.es/v2/league/europa-league.ics",
        "UEFA Conference League": "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
    }
)


# ============================================================
# CONFIGURATION
# ============================================================

# This diagnostic tool works in naive (timezone-less) UTC throughout.
# Rather than round-tripping through the timezone-aware
# current_season_bounds() (which shifts the July 1st boundary by an
# hour once BST is accounted for), the same "1 July - 30 June"
# rollover rule is applied directly in naive terms here.
_now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
_season_start_year = _now_utc.year if _now_utc.month >= 7 else _now_utc.year - 1
SEASON_START = datetime(_season_start_year, 7, 1)
SEASON_END = datetime(_season_start_year + 1, 6, 30, 23, 59, 59)


DOMESTIC_COMPETITIONS = [
    "Scottish Premiership",
    "Scottish Championship",
    "Scottish League One",
    "Scottish League Two",
    "Scottish Cup",
    "Scottish League Cup",
]

UEFA_COMPETITIONS = [
    "Champions League",
    "Europa League",
    "UEFA Conference League",
]

ALL_COMPETITIONS = DOMESTIC_COMPETITIONS + UEFA_COMPETITIONS

# Fixtur.es team calendars may explicitly identify UEFA fixtures with
# these suffixes.
UEFA_TAG_TO_COMPETITION = {
    "CL": "Champions League",
    "EL": "Europa League",
    "CONF": "UEFA Conference League",
}


# ============================================================
# DOWNLOAD (shared with sources/fixtur_es.py via ics.download_ics)
# ============================================================

def fetch_ics(url: str, attempts: int = 3) -> str:
    return download_ics(url, max_attempts=attempts)


# ============================================================
# ICS PARSING (shared with sources/fixtur_es.py via ics.py)
# ============================================================

_TRACKED_PROPERTIES = ("UID", "DTSTART", "DTEND", "SUMMARY", "STATUS", "DESCRIPTION")


def parse_ics_events(text: str) -> list[dict[str, str]]:
    """
    Parse the small subset of ICS fields this diagnostic needs, using
    the shared ics.split_events()/property_value() parser rather than
    a second hand-rolled one.
    """

    events = []

    for event_lines in split_events(text):
        event = {}
        for prop in _TRACKED_PROPERTIES:
            value = property_value(event_lines, prop)
            if value is not None:
                event[prop] = value
        events.append(event)

    return events


def parse_ics_datetime(value: str) -> datetime | None:
    """
    Parse an ICS datetime, always returning a naive UTC datetime (to
    match this file's naive-datetime convention throughout).
    """

    dt = _parse_ics_datetime(value)

    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

    return dt


def clean_text(value: str | None) -> str:
    """Clean ICS text for diagnostic output (unescape ICS text escaping)."""

    if not value:
        return ""

    return value.replace("\n", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


# ============================================================
# FIXTURE PARSING
# ============================================================

def fixture_teams(summary: str) -> tuple[str, str] | None:
    """Extract (home, away) from a SUMMARY field, via the shared parser."""

    home, away, _, _ = parse_match_summary(summary)

    if not home or not away:
        return None

    return home, away


def is_season_fixture(event: dict[str, str]) -> bool:
    dt = parse_ics_datetime(event.get("DTSTART", ""))

    if dt is None:
        return False

    return SEASON_START <= dt <= SEASON_END



# ============================================================
# FIXTURE KEYS
# ============================================================

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

    UEFA suffixes such as [CL], [EL] and [Conf] are also removed.
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


# ============================================================
# UEFA MARKER DETECTION
# ============================================================

def get_uefa_tag(
    event: dict[str, str],
) -> str | None:
    """
    Return an explicit Fixtur.es UEFA marker.

    Examples:

        [CL]   -> CL
        [EL]   -> EL
        [Conf] -> CONF
    """

    summary = clean_text(
        event.get(
            "SUMMARY",
            "",
        )
    )

    import re

    match = re.search(
        r"\[(CL|EL|Conf)\]\s*(?:\(\d+\s*-\s*\d+\))?$",
        summary,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1).upper()


def get_explicit_uefa_competition(
    event: dict[str, str],
) -> str | None:

    tag = get_uefa_tag(
        event
    )

    if tag is None:
        return None

    return UEFA_TAG_TO_COMPETITION.get(
        tag
    )


# ============================================================
# COMPETITION MATCHING
# ============================================================

def get_competition_for_fixture(
    event: dict[str, str],
    competition_index: dict[tuple, set[str]],
) -> set[str]:

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
    Find corresponding UEFA competition-calendar fixtures.

    UEFA calendars are authoritative.

    Matching uses:

    - normalised teams
    - same calendar date
    - kickoff tolerance

    A fixture is NOT considered UEFA merely because it falls in
    July or August.
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

        if (
            candidate_teams
            != target_teams
        ):
            continue

        difference = abs(
            (
                target_dt
                - candidate_dt
            ).total_seconds()
        )

        if difference <= 24 * 3600:

            matches.append(
                (
                    competition,
                    candidate,
                )
            )

    return matches


# ============================================================
# LOADING TEAM CALENDARS
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

    team_events: dict[
        str,
        list[dict[str, str]]
    ] = {}

    total_events = 0
    total_season_events = 0
    failures = 0

    for team, url in TEAM_CALENDARS.items():

        print()
        print(team)

        try:

            text = fetch_ics(
                url
            )

            events = parse_ics_events(
                text
            )

            season_events = [
                event
                for event in events
                if is_season_fixture(
                    event
                )
            ]

            team_events[team] = (
                season_events
            )

            print(
                f"{len(events)} VEVENTs, "
                f"{len(season_events)} "
                f"in 2026/27"
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


# ============================================================
# LOADING COMPETITION CALENDARS
# ============================================================

def load_competition_calendars():

    print()
    print(
        "=" * 70
    )

    print(
        "COMPETITION CALENDAR SUMMARY"
    )

    print(
        f"Competition feeds configured: "
        f"{len(AUDIT_COMPETITION_CALENDARS)}"
    )

    print(
        "=" * 70
    )

    competition_events: dict[
        str,
        list[dict[str, str]]
    ] = {}

    total_events = 0
    total_season_events = 0
    failures = 0

    for competition, url in AUDIT_COMPETITION_CALENDARS.items():

        print()
        print(competition)

        print(
            f"URL: {url}"
        )

        try:

            text = fetch_ics(
                url
            )

            events = parse_ics_events(
                text
            )

            season_events = [
                event
                for event in events
                if is_season_fixture(
                    event
                )
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
            f"Failed competition feeds: "
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

    for competition, events in competition_events.items():

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
            ].add(
                competition
            )

    return (
        fixtures,
        fixture_competitions,
    )


# ============================================================
# INTELLIGENT CLASSIFICATION
# ============================================================

def classify_unmatched_fixture(
    event,
    all_competition_events,
    uefa_events,
):
    """
    Classify an unmatched team-calendar fixture.

    Priority:

    1. UEFA competition-calendar evidence
    2. Domestic competition-calendar evidence
    3. Friendly
    4. Potentially missing competition classification
    5. Unknown

    IMPORTANT:

    The date is never used by itself to determine UEFA status.
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
            "UNKNOWN",
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
        home_spfl != away_spfl
    )

    # --------------------------------------------------------
    # 1. UEFA competition-calendar authority
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
            "UEFA COMPETITIVE FIXTURE",
            "Confirmed by UEFA competition "
            f"calendar: {competitions}.",
        )

    # --------------------------------------------------------
    # 2. Explicit UEFA marker
    #
    # This is useful diagnostic evidence when a UEFA feed has
    # a naming difference, but the marker itself is NOT used
    # to override a contradictory competition-calendar result.
    # --------------------------------------------------------

    explicit_uefa = (
        get_explicit_uefa_competition(
            event
        )
    )

    if explicit_uefa:

        # If the UEFA calendar has no matching fixture, retain
        # this as a potential classification issue rather than
        # blindly declaring it UEFA.

        return (
            "POTENTIALLY MISSING COMPETITION CLASSIFICATION",
            "Fixtur.es team calendar explicitly marks this "
            f"fixture as {explicit_uefa}, but no matching "
            "fixture was found in the corresponding UEFA "
            "competition calendar.",
        )

    # --------------------------------------------------------
    # 3. Exact domestic competition evidence
    # --------------------------------------------------------

    domestic_events = [
        (
            competition,
            candidate,
        )
        for competition, candidate
        in all_competition_events
        if competition
        in DOMESTIC_COMPETITIONS
    ]

    domestic_matches = []

    target_key = fixture_key(
        event,
        include_time=True,
    )

    for competition, candidate in domestic_events:

        candidate_key = fixture_key(
            candidate,
            include_time=True,
        )

        if (
            candidate_key is not None
            and candidate_key == target_key
        ):

            domestic_matches.append(
                (
                    competition,
                    candidate,
                )
            )

    if domestic_matches:

        competitions = ", ".join(
            sorted(
                {
                    competition
                    for competition, _
                    in domestic_matches
                }
            )
        )

        return (
            "DOMESTIC COMPETITIVE FIXTURE",
            "Confirmed by domestic competition "
            f"calendar: {competitions}.",
        )

    # --------------------------------------------------------
    # 4. Domestic same-day/time mismatch
    # --------------------------------------------------------

    domestic_time_matches = (
        find_team_time_mismatch(
            event,
            domestic_events,
        )
    )

    if domestic_time_matches:

        details = ", ".join(
            competition
            for competition, _
            in domestic_time_matches[:3]
        )

        return (
            "POTENTIALLY MISSING COMPETITION CLASSIFICATION",
            "Same SPFL fixture found in domestic "
            "competition data with a different kickoff "
            f"time: {details}.",
        )

    # --------------------------------------------------------
    # 5. Two SPFL clubs
    #
    # If both clubs are SPFL clubs and no domestic calendar
    # contains the fixture, it is much more likely to be a
    # missing domestic competition classification than a
    # friendly/non-competitive fixture.
    # --------------------------------------------------------

    if both_spfl:

        return (
            "POTENTIALLY MISSING COMPETITION CLASSIFICATION",
            "Both clubs are SPFL teams, but the fixture "
            "is absent from all available domestic "
            "competition calendars.",
        )

    # --------------------------------------------------------
    # 6. Non-SPFL fixture with no UEFA evidence
    #
    # We deliberately classify these as FRIENDLY rather than
    # UEFA merely because they occur during July/August.
    #
    # This is the critical correction to the previous audit.
    # --------------------------------------------------------

    if has_non_spfl:

        return (
            "FRIENDLY",
            "SPFL club has a non-SPFL opponent, but "
            "no UEFA or domestic competition calendar "
            "confirms the fixture.",
        )

    # --------------------------------------------------------
    # 7. Unknown
    # --------------------------------------------------------

    return (
        "UNKNOWN",
        "Fixture does not match any current "
        "competition or friendly classification rule.",
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

    for competition, events in competition_events.items():

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
        if item[0]
        in UEFA_COMPETITIONS
    ]

    domestic_events = [
        item
        for item in all_competition_events
        if item[0]
        in DOMESTIC_COMPETITIONS
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

    # --------------------------------------------------------
    # Overall audit
    # --------------------------------------------------------

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
        f"Unique team-calendar fixtures:        "
        f"{len(team_fixtures)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(competition_fixtures)}"
    )

    print(
        f"Exact fixture overlap:                "
        f"{len(exact_overlap)}"
    )

    print(
        f"Team-calendar only:                   "
        f"{len(team_only_keys)}"
    )

    print(
        f"Competition-calendar only:            "
        f"{len(competition_only_keys)}"
    )

    # --------------------------------------------------------
    # Coverage
    # --------------------------------------------------------

    print()
    print(
        "COVERAGE"
    )

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
        f"Competition coverage of team fixtures: "
        f"{team_coverage:.1f}%"
    )

    print(
        f"Team coverage of competition fixtures: "
        f"{competition_coverage:.1f}%"
    )

    # --------------------------------------------------------
    # Overlap by competition
    # --------------------------------------------------------

    print()
    print(
        "OVERLAP BY COMPETITION"
    )

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

        matched = len(
            keys
            & set(team_fixtures.keys())
        )

        percentage = (
            matched
            / len(keys)
            * 100
            if keys
            else 0
        )

        print(
            f"{competition}: "
            f"{matched}/{len(keys)} "
            f"({percentage:.1f}%)"
        )

    # --------------------------------------------------------
    # Determine unmatched classifications
    # --------------------------------------------------------

    classifications = defaultdict(list)

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
        "UEFA COMPETITIVE FIXTURE",
        "DOMESTIC COMPETITIVE FIXTURE",
        "FRIENDLY",
        "POTENTIALLY MISSING COMPETITION CLASSIFICATION",
        "UNKNOWN",
    ]

    # --------------------------------------------------------
    # Unmatched classification summary
    # --------------------------------------------------------

    print()
    print(
        "UNMATCHED FIXTURE CLASSIFICATION"
    )

    for category in category_order:

        print(
            f"{category}: "
            f"{len(classifications.get(category, []))}"
        )

    print(
        f"TOTAL UNMATCHED: "
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
                get_event_datetime(
                    item[0]
                )
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
                f"{date_text} | "
                f"{summary}"
            )

            print(
                f"Reason: {reason}"
            )

    # --------------------------------------------------------
    # Confirm UEFA fixtures across ALL team fixtures
    #
    # This is intentionally separate from unmatched fixtures.
    #
    # The 16 UEFA fixtures are normally already part of the
    # exact competition overlap and therefore are NOT among
    # the 29 unmatched fixtures.
    # --------------------------------------------------------

    confirmed_uefa = []

    for key, event in team_fixtures.items():

        matches = (
            find_uefa_fixture_matches(
                event,
                uefa_events,
            )
        )

        if matches:

            competitions = sorted(
                {
                    competition
                    for competition, _
                    in matches
                }
            )

            confirmed_uefa.append(
                (
                    event,
                    competitions,
                )
            )

    # --------------------------------------------------------
    # Overall classification summary
    # --------------------------------------------------------

    domestic_competitive_keys = {
        key
        for key, competitions in fixture_competitions.items()
        if competitions & set(DOMESTIC_COMPETITIONS)
    }

    confirmed_domestic = (
        set(team_fixtures.keys())
        & domestic_competitive_keys
    )

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

    print(
        f"UEFA matches confirmed: "
        f"{len(confirmed_uefa)}"
    )

    print(
        f"Domestic competitive matches confirmed: "
        f"{len(confirmed_domestic)}"
    )

    print()
    print(
        "UNMATCHED FIXTURES"
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
        f"Team-calendar fixtures analysed: "
        f"{len(team_fixtures)}"
    )

    print(
        f"Competition-calendar fixtures analysed: "
        f"{len(competition_fixtures)}"
    )

    print(
        f"Exact overlaps: "
        f"{len(exact_overlap)}"
    )

    print(
        f"Unmatched team fixtures: "
        f"{len(team_only_keys)}"
    )

    print(
        f"Confirmed UEFA competitive fixtures: "
        f"{len(confirmed_uefa)}"
    )

    print(
        f"Unmatched friendlies: "
        f"{len(classifications.get('FRIENDLY', []))}"
    )

    print(
        "Potential competition issues: "
        f"{len(classifications.get('POTENTIALLY MISSING COMPETITION CLASSIFICATION', []))}"
    )

    print(
        f"Unknown: "
        f"{len(classifications.get('UNKNOWN', []))}"
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "UEFA classification is based on UEFA "
        "competition-calendar evidence."
    )

    print(
        "A July/August fixture is NOT classified "
        "as UEFA solely because of its date."
    )

    print(
        "Fixtur.es [CL], [EL] and [Conf] markers "
        "are recognised for diagnostics but do not "
        "override the UEFA competition calendars."
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

    competition_events = (
        load_competition_calendars()
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
