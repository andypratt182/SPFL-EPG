from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Make the repository root importable when this script is run directly from
# GitHub Actions, e.g.:
#
#     python tools/inspect_fixtur_es.py
#
# This allows:
#
#     from sources.fixtur_es import ...
#
# without requiring PYTHONPATH changes in the workflow.
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from datetime import datetime, timezone
from collections import defaultdict

from sources.fixtur_es import (
    TEAM_CALENDARS,
    COMPETITION_CALENDARS,
    download_ics,
    parse_ics,
)


TARGET_SEASON_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
TARGET_SEASON_END = datetime(2027, 7, 1, tzinfo=timezone.utc)


def normalise_team_name(name):
    """Normalise common team-name variations for comparison."""

    name = name.lower().strip()

    replacements = {
        "dundee fc": "dundee",
        "dundee": "dundee",
        "dundee united": "dundee united",
        "st. johnstone": "st johnstone",
        "st johnstone": "st johnstone",
        "st mirren": "st mirren",
        "heart of midlothian": "hearts",
        "hearts": "hearts",
        "hibernian": "hibernian",
        "rangers": "rangers",
        "celtic": "celtic",
        "aberdeen": "aberdeen",
        "kilmarnock": "kilmarnock",
        "motherwell": "motherwell",
        "falkirk": "falkirk",
    }

    return replacements.get(name, name)


def parse_datetime(value):
    """Convert a parsed DTSTART value to timezone-aware UTC."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except ValueError:
        pass

    formats = (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
        "%Y%m%d",
    )

    original_value = value.replace("+00:00", "")

    for fmt in formats:
        try:
            dt = datetime.strptime(original_value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def get_field(event, *names):
    """Safely retrieve a field from a parsed event."""

    if isinstance(event, dict):
        for name in names:
            if name in event:
                return event[name]

    return ""


def event_datetime(event):
    return parse_datetime(
        get_field(event, "DTSTART", "dtstart", "start")
    )


def event_uid(event):
    return str(
        get_field(event, "UID", "uid", "id")
    ).strip()


def event_summary(event):
    return str(
        get_field(event, "SUMMARY", "summary", "title")
    ).strip()


def season_events(events):
    """Return events falling inside the 2026/27 season."""

    result = []

    for event in events:
        dt = event_datetime(event)

        if dt is None:
            continue

        if TARGET_SEASON_START <= dt < TARGET_SEASON_END:
            result.append(event)

    return result


def clean_team_name(name):
    """Remove common competition suffixes."""

    name = name.strip()

    suffixes = (
        " [EL]",
        " [CL]",
        " [Conf]",
        " [ECL]",
    )

    changed = True

    while changed:
        changed = False

        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
                changed = True

    return name


def parse_fixture_summary(summary):
    """
    Parse summaries such as:

        Rangers - Hibernian
        Rangers - Hibernian (2-1)
        Rangers - Jagiellonia Białystok [EL]
    """

    if not summary or " - " not in summary:
        return None, None

    value = summary.strip()

    # Remove a final result such as "(2-1)".
    if value.endswith(")") and " (" in value:
        value = value.rsplit(" (", 1)[0]

    # Remove competition suffixes.
    value = clean_team_name(value)

    parts = value.split(" - ", 1)

    if len(parts) != 2:
        return None, None

    home = clean_team_name(parts[0])
    away = clean_team_name(parts[1])

    return home.strip(), away.strip()


def fixture_key(event):
    """
    Build a source-independent fixture key.

    UID is intentionally NOT used because team and competition
    calendars have different UID systems.

    Key:

        kickoff UTC
        home team
        away team
    """

    dt = event_datetime(event)
    summary = event_summary(event)

    if dt is None:
        return None

    home, away = parse_fixture_summary(summary)

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


def load_calendars(calendars, source_type):
    """Download and parse a group of calendars."""

    loaded = {}

    print()
    print("=" * 70)
    print(f"LOADING {source_type.upper()} CALENDARS")
    print("=" * 70)

    for name, url in calendars.items():

        print()
        print(name)
        print(f"URL: {url}")

        try:
            raw = download_ics(url)
            events = parse_ics(raw)

            loaded[name] = events

            print(f"VEVENT records: {len(events)}")
            print(
                f"2026/27 events: "
                f"{len(season_events(events))}"
            )

        except Exception as exc:
            print(
                f"ERROR: {type(exc).__name__}: {exc}"
            )

            loaded[name] = []

    return loaded


def build_fixture_index(calendars):
    """
    Build:

        fixture_key -> list of calendars containing fixture
    """

    index = defaultdict(list)

    for calendar_name, events in calendars.items():

        for event in season_events(events):

            key = fixture_key(event)

            if key is None:
                continue

            index[key].append(calendar_name)

    return index


def print_team_summary(team_calendars):
    print()
    print("=" * 70)
    print("TEAM CALENDAR SUMMARY")
    print("=" * 70)

    total_events = 0
    total_season = 0

    for name, events in team_calendars.items():

        season = season_events(events)

        total_events += len(events)
        total_season += len(season)

        print(
            f"{name}: "
            f"{len(events)} VEVENTs, "
            f"{len(season)} in 2026/27"
        )

    print()
    print(f"Total VEVENT records: {total_events}")
    print(f"Total 2026/27 events: {total_season}")


def print_competition_summary(competition_calendars):
    print()
    print("=" * 70)
    print("COMPETITION CALENDAR SUMMARY")
    print("=" * 70)

    total_events = 0
    total_season = 0

    for name, events in competition_calendars.items():

        season = season_events(events)

        total_events += len(events)
        total_season += len(season)

        print(
            f"{name}: "
            f"{len(events)} VEVENTs, "
            f"{len(season)} in 2026/27"
        )

    print()
    print(f"Total VEVENT records: {total_events}")
    print(f"Total 2026/27 events: {total_season}")


def print_overlap(team_index, competition_index):
    print()
    print("=" * 70)
    print("FULL OVERLAP / CLASSIFICATION AUDIT")
    print("=" * 70)

    team_keys = set(team_index)
    competition_keys = set(competition_index)

    overlap = team_keys & competition_keys
    team_only = team_keys - competition_keys
    competition_only = competition_keys - team_keys

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
    print("Coverage percentages")

    if team_keys:
        print(
            "Competition coverage of team fixtures: "
            f"{len(overlap) / len(team_keys) * 100:.1f}%"
        )
    else:
        print(
            "Competition coverage of team fixtures: "
            "0.0%"
        )

    if competition_keys:
        print(
            "Team coverage of competition fixtures: "
            f"{len(overlap) / len(competition_keys) * 100:.1f}%"
        )
    else:
        print(
            "Team coverage of competition fixtures: "
            "0.0%"
        )

    print()
    print("=" * 70)
    print("OVERLAPPING FIXTURES")
    print("=" * 70)

    for key in sorted(overlap):

        teams = sorted(set(team_index[key]))
        competitions = sorted(set(competition_index[key]))

        print()
        print(display_fixture(key))
        print(
            f"  Team calendars: "
            f"{', '.join(teams)}"
        )
        print(
            f"  Competition calendars: "
            f"{', '.join(competitions)}"
        )

    print()
    print("=" * 70)
    print("TEAM-ONLY FIXTURES")
    print("=" * 70)

    for key in sorted(team_only):

        teams = sorted(set(team_index[key]))

        print()
        print(display_fixture(key))
        print(
            f"  Team calendars: "
            f"{', '.join(teams)}"
        )

    print()
    print("=" * 70)
    print("COMPETITION-ONLY FIXTURES")
    print("=" * 70)

    for key in sorted(competition_only):

        competitions = sorted(set(competition_index[key]))

        print()
        print(display_fixture(key))
        print(
            f"  Competition calendars: "
            f"{', '.join(competitions)}"
        )


def print_team_verification(team_index):
    print()
    print("=" * 70)
    print("TEAM-CALENDAR INTERNAL VERIFICATION")
    print("=" * 70)

    multi_team = 0
    single_team = 0

    for key, calendars in team_index.items():

        unique_calendars = set(calendars)

        if len(unique_calendars) >= 2:
            multi_team += 1
        else:
            single_team += 1

    print()
    print(
        "Fixtures appearing in multiple team calendars: "
        f"{multi_team}"
    )

    print(
        "Fixtures appearing in only one team calendar: "
        f"{single_team}"
    )

    print()
    print("Interpretation:")
    print(
        "  Two tracked teams = expected for a fixture "
        "between two tracked clubs."
    )
    print(
        "  One tracked team = expected for fixtures "
        "against clubs outside the tracked 12."
    )


def print_competition_classification(competition_index):
    print()
    print("=" * 70)
    print("COMPETITION CLASSIFICATION")
    print("=" * 70)

    counts = defaultdict(int)

    for competitions in competition_index.values():

        for competition in set(competitions):
            counts[competition] += 1

    for competition in sorted(counts):
        print(
            f"{competition}: "
            f"{counts[competition]}"
        )


def print_architecture_assessment(
    team_index,
    competition_index,
):
    team_keys = set(team_index)
    competition_keys = set(competition_index)

    overlap = team_keys & competition_keys

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

    if team_keys:
        print(
            f"Team-calendar fixture coverage: "
            f"{team_coverage * 100:.1f}%"
        )

    if competition_keys:
        print(
            f"Competition-calendar fixture coverage: "
            f"{competition_coverage * 100:.1f}%"
        )

    print()

    if competition_coverage >= 0.8:
        print(
            "Competition calendars cover the large majority "
            "of team-calendar fixtures."
        )

        print()
        print(
            "LIKELY ARCHITECTURE:"
        )

        print(
            "  Competition feeds → primary fixture source"
        )
        print(
            "  Team feeds        → supplementary verification"
        )

    elif team_coverage >= 0.8:
        print(
            "Team calendars cover the large majority "
            "of competition-calendar fixtures."
        )

        print()
        print(
            "LIKELY ARCHITECTURE:"
        )

        print(
            "  Team feeds        → fixture source"
        )
        print(
            "  Competition feeds → competition classification"
        )

    else:
        print(
            "Coverage is mixed."
        )

        print()
        print(
            "Do not modify fixtures.py or generator.py yet."
        )

        print(
            "Review the source-specific fixtures first."
        )


def main():

    team_calendars = load_calendars(
        TEAM_CALENDARS,
        "Fixtur.es team",
    )

    competition_calendars = load_calendars(
        COMPETITION_CALENDARS,
        "Fixtur.es competition",
    )

    print_team_summary(team_calendars)

    print_competition_summary(
        competition_calendars
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
