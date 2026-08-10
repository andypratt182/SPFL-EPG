from pathlib import Path
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.request import Request, urlopen


# ============================================================================
# REPOSITORY ROOT
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# FIxtur.es CALENDAR DEFINITIONS
# ============================================================================

from sources.fixtur_es import (
    TEAM_CALENDARS,
    COMPETITION_CALENDARS,
)


# ============================================================================
# SETTINGS
# ============================================================================

SEASON_START = datetime(
    2026,
    7,
    1,
    tzinfo=timezone.utc,
)

SEASON_END = datetime(
    2027,
    7,
    1,
    tzinfo=timezone.utc,
)


# ============================================================================
# DOWNLOAD
# ============================================================================

def download_calendar(url):
    """
    Download an ICS calendar.

    This diagnostic deliberately performs its own download so that it does
    not depend on internal helper function names in sources.fixtur_es.
    """

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Fixtur.es Diagnostic",
        },
    )

    with urlopen(request, timeout=30) as response:
        status = response.status
        data = response.read()

    if status != 200:
        raise RuntimeError(
            f"HTTP status {status}"
        )

    return data.decode(
        "utf-8",
        errors="replace",
    )


# ============================================================================
# ICS PARSING
# ============================================================================

def unfold_ics(text):
    """
    Unfold RFC5545 continuation lines.
    """

    lines = text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).split("\n")

    unfolded = []

    for line in lines:

        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


def parse_ics_events(text):
    """
    Minimal ICS parser.

    We only need the fields required for fixture comparison:

        UID
        DTSTART
        DTEND
        SUMMARY
        STATUS
    """

    lines = unfold_ics(text)

    events = []
    current = None

    for line in lines:

        line = line.strip("\n")

        if line == "BEGIN:VEVENT":
            current = {}
            continue

        if line == "END:VEVENT":

            if current is not None:
                events.append(current)

            current = None
            continue

        if current is None:
            continue

        if ":" not in line:
            continue

        field, value = line.split(
            ":",
            1,
        )

        field_name = field.split(
            ";",
            1,
        )[0].upper()

        current[field_name] = value.strip()

    return events


# ============================================================================
# DATETIME
# ============================================================================

def parse_datetime(value):
    if not value:
        return None

    value = str(value).strip()

    # UTC format used by Fixtur.es.
    if value.endswith("Z"):

        try:
            return datetime.strptime(
                value,
                "%Y%m%dT%H%M%SZ",
            ).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass

    # Date/time without Z.
    try:
        return datetime.strptime(
            value,
            "%Y%m%dT%H%M%S",
        ).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        pass

    # Date-only event.
    try:
        return datetime.strptime(
            value,
            "%Y%m%d",
        ).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


# ============================================================================
# SEASON FILTER
# ============================================================================

def season_events(events):

    result = []

    for event in events:

        dt = parse_datetime(
            event.get("DTSTART")
        )

        if dt is None:
            continue

        if SEASON_START <= dt < SEASON_END:
            result.append(event)

    return result


# ============================================================================
# TEAM NORMALISATION
# ============================================================================

def normalise_team_name(name):

    name = name.strip().lower()

    replacements = {
        "dundee fc": "dundee",
        "dundee": "dundee",

        "st. johnstone": "st johnstone",
        "st johnstone": "st johnstone",

        "st mirren": "st mirren",

        "heart of midlothian": "hearts",
        "hearts": "hearts",

        "rangers": "rangers",
        "celtic": "celtic",
        "aberdeen": "aberdeen",
        "hibernian": "hibernian",
        "kilmarnock": "kilmarnock",
        "motherwell": "motherwell",
        "falkirk": "falkirk",
        "dundee united": "dundee united",
    }

    return replacements.get(
        name,
        name,
    )


# ============================================================================
# SUMMARY PARSING
# ============================================================================

def clean_summary(summary):

    value = summary.strip()

    # Remove competition markers.
    for suffix in (
        "[EL]",
        "[CL]",
        "[Conf]",
        "[ECL]",
    ):

        if value.endswith(suffix):
            value = value[
                :-len(suffix)
            ].strip()

    # Remove result.
    if value.endswith(")") and " (" in value:

        value = value.rsplit(
            " (",
            1,
        )[0]

    return value


def parse_fixture(summary):

    if not summary:
        return None, None

    value = clean_summary(
        summary
    )

    if " - " not in value:
        return None, None

    home, away = value.split(
        " - ",
        1,
    )

    home = home.strip()
    away = away.strip()

    if not home or not away:
        return None, None

    return (
        home,
        away,
    )


# ============================================================================
# FIXTURE KEY
# ============================================================================

def fixture_key(event):

    dt = parse_datetime(
        event.get("DTSTART")
    )

    if dt is None:
        return None

    home, away = parse_fixture(
        event.get(
            "SUMMARY",
            "",
        )
    )

    if not home or not away:
        return None

    return (
        dt,
        normalise_team_name(home),
        normalise_team_name(away),
    )


def display_fixture(key):

    dt, home, away = key

    return (
        f"{dt.strftime('%Y-%m-%d %H:%M UTC')} | "
        f"{home} - {away}"
    )


# ============================================================================
# LOAD CALENDAR GROUP
# ============================================================================

def load_calendars(
    calendars,
    label,
):

    loaded = {}

    print()
    print("=" * 70)
    print(f"LOADING {label.upper()}")
    print("=" * 70)

    for name, url in calendars.items():

        print()
        print(name)
        print(f"URL: {url}")

        try:

            raw = download_calendar(
                url
            )

            events = parse_ics_events(
                raw
            )

            loaded[name] = events

            season = season_events(
                events
            )

            print(
                f"HTTP status: 200"
            )

            print(
                f"Downloaded ICS characters: "
                f"{len(raw)}"
            )

            print(
                f"VEVENT records: "
                f"{len(events)}"
            )

            print(
                f"2026/27 events: "
                f"{len(season)}"
            )

        except Exception as exc:

            loaded[name] = []

            print(
                f"ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

    return loaded


# ============================================================================
# BUILD FIXTURE INDEX
# ============================================================================

def build_fixture_index(
    calendars,
):

    index = defaultdict(list)

    for calendar_name, events in calendars.items():

        for event in season_events(events):

            key = fixture_key(
                event
            )

            if key is None:
                continue

            index[key].append(
                calendar_name
            )

    return index


# ============================================================================
# SUMMARY
# ============================================================================

def print_summary(
    calendars,
    label,
):

    total_events = 0
    total_season = 0

    print()
    print("=" * 70)
    print(f"{label.upper()} SUMMARY")
    print("=" * 70)

    for name, events in calendars.items():

        season = season_events(
            events
        )

        total_events += len(events)
        total_season += len(season)

        print(
            f"{name}: "
            f"{len(events)} VEVENTs, "
            f"{len(season)} in 2026/27"
        )

    print()
    print(
        f"Total VEVENT records: "
        f"{total_events}"
    )

    print(
        f"Total 2026/27 events: "
        f"{total_season}"
    )


# ============================================================================
# OVERLAP
# ============================================================================

def print_overlap(
    team_index,
    competition_index,
):

    team_keys = set(
        team_index
    )

    competition_keys = set(
        competition_index
    )

    overlap = (
        team_keys
        & competition_keys
    )

    team_only = (
        team_keys
        - competition_keys
    )

    competition_only = (
        competition_keys
        - team_keys
    )

    print()
    print("=" * 70)
    print("FULL OVERLAP / CLASSIFICATION AUDIT")
    print("=" * 70)

    print()
    print(
        f"Unique team-calendar fixtures:        "
        f"{len(team_keys)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(competition_keys)}"
    )

    print(
        f"Exact fixture overlap:                "
        f"{len(overlap)}"
    )

    print(
        f"Team-calendar only:                   "
        f"{len(team_only)}"
    )

    print(
        f"Competition-calendar only:            "
        f"{len(competition_only)}"
    )

    print()
    print("COVERAGE")

    if team_keys:

        print(
            "Competition coverage of team fixtures: "
            f"{len(overlap) / len(team_keys) * 100:.1f}%"
        )

    if competition_keys:

        print(
            "Team coverage of competition fixtures: "
            f"{len(overlap) / len(competition_keys) * 100:.1f}%"
        )

    # -----------------------------------------------------------------------
    # Overlap by competition
    # -----------------------------------------------------------------------

    competition_overlap = defaultdict(int)

    for key in overlap:

        for competition in set(
            competition_index[key]
        ):

            competition_overlap[
                competition
            ] += 1

    print()
    print("=" * 70)
    print("OVERLAP BY COMPETITION")
    print("=" * 70)

    for competition in sorted(
        competition_overlap
    ):

        total = sum(
            1
            for key in competition_keys
            if competition
            in competition_index[key]
        )

        matched = competition_overlap[
            competition
        ]

        percentage = (
            matched / total * 100
            if total
            else 0
        )

        print(
            f"{competition}: "
            f"{matched}/{total} "
            f"({percentage:.1f}%)"
        )

    # -----------------------------------------------------------------------
    # Team-only
    # -----------------------------------------------------------------------

    print()
    print("=" * 70)
    print("TEAM-ONLY FIXTURES")
    print("=" * 70)

    if not team_only:

        print(
            "None"
        )

    else:

        for key in sorted(
            team_only
        ):

            print(
                display_fixture(key)
            )

            print(
                "  Team calendars: "
                + ", ".join(
                    sorted(
                        set(
                            team_index[key]
                        )
                    )
                )
            )

    # -----------------------------------------------------------------------
    # Competition-only
    # -----------------------------------------------------------------------

    print()
    print("=" * 70)
    print("COMPETITION-ONLY FIXTURES")
    print("=" * 70)

    if not competition_only:

        print(
            "None"
        )

    else:

        for key in sorted(
            competition_only
        ):

            print(
                display_fixture(key)
            )

            print(
                "  Competition calendars: "
                + ", ".join(
                    sorted(
                        set(
                            competition_index[key]
                        )
                    )
                )
            )


# ============================================================================
# TEAM INTERNAL VERIFICATION
# ============================================================================

def print_team_verification(
    team_index,
):

    multi_team = 0
    single_team = 0

    for calendars in team_index.values():

        if len(set(calendars)) >= 2:
            multi_team += 1
        else:
            single_team += 1

    print()
    print("=" * 70)
    print("TEAM-CALENDAR INTERNAL VERIFICATION")
    print("=" * 70)

    print()
    print(
        "Fixtures appearing in multiple "
        f"team calendars: {multi_team}"
    )

    print(
        "Fixtures appearing in only one "
        f"team calendar: {single_team}"
    )


# ============================================================================
# COMPETITION CLASSIFICATION
# ============================================================================

def print_competition_classification(
    competition_index,
):

    counts = defaultdict(int)

    for competitions in (
        competition_index.values()
    ):

        for competition in set(
            competitions
        ):

            counts[
                competition
            ] += 1

    print()
    print("=" * 70)
    print("COMPETITION CLASSIFICATION")
    print("=" * 70)

    for competition in sorted(
        counts
    ):

        print(
            f"{competition}: "
            f"{counts[competition]}"
        )


# ============================================================================
# ARCHITECTURE ASSESSMENT
# ============================================================================

def print_architecture_assessment(
    team_index,
    competition_index,
):

    team_keys = set(
        team_index
    )

    competition_keys = set(
        competition_index
    )

    overlap = (
        team_keys
        & competition_keys
    )

    team_coverage = (
        len(overlap) / len(team_keys)
        if team_keys
        else 0
    )

    competition_coverage = (
        len(overlap) / len(competition_keys)
        if competition_keys
        else 0
    )

    print()
    print("=" * 70)
    print("ARCHITECTURE ASSESSMENT")
    print("=" * 70)

    print()

    print(
        f"Team-calendar unique fixtures: "
        f"{len(team_keys)}"
    )

    print(
        f"Competition-calendar unique fixtures: "
        f"{len(competition_keys)}"
    )

    print(
        f"Fixtures in both sources: "
        f"{len(overlap)}"
    )

    print(
        f"Team fixture coverage by competitions: "
        f"{team_coverage * 100:.1f}%"
    )

    print(
        f"Competition fixture coverage by teams: "
        f"{competition_coverage * 100:.1f}%"
    )

    print()

    if competition_coverage >= 0.8:

        print(
            "LIKELY ARCHITECTURE:"
        )

        print(
            "Competition feeds → primary fixture source"
        )

        print(
            "Team feeds        → supplementary verification"
        )

    elif team_coverage >= 0.8:

        print(
            "LIKELY ARCHITECTURE:"
        )

        print(
            "Team feeds        → fixture source"
        )

        print(
            "Competition feeds → competition classification"
        )

    else:

        print(
            "RESULT: Coverage is mixed."
        )

        print(
            "No architecture change should be made yet."
        )


# ============================================================================
# MAIN
# ============================================================================

def main():

    team_calendars = load_calendars(
        TEAM_CALENDARS,
        "Fixtur.es team calendars",
    )

    competition_calendars = load_calendars(
        COMPETITION_CALENDARS,
        "Fixtur.es competition calendars",
    )

    print_summary(
        team_calendars,
        "TEAM CALENDAR",
    )

    print_summary(
        competition_calendars,
        "COMPETITION CALENDAR",
    )

    team_index = build_fixture_index(
        team_calendars
    )

    competition_index = build_fixture_index(
        competition_calendars
    )

    print_overlap(
        team_index,
        competition_index,
    )

    print_team_verification(
        team_index
    )

    print_competition_classification(
        competition_index
    )

    print_architecture_assessment(
        team_index,
        competition_index
    )

    print()
    print("=" * 70)
    print("FIXTUR.ES FULL DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
