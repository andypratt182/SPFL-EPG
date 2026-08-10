```python
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================================
# REPOSITORY IMPORT PATH
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from sources.fixtur_es import (  # noqa: E402
    TEAM_CALENDARS,
    COMPETITION_CALENDARS,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

SEASON_START = datetime(
    2026, 7, 1, tzinfo=timezone.utc
)

SEASON_END = datetime(
    2027, 6, 30, 23, 59, 59, tzinfo=timezone.utc
)

REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 3

# Broad UEFA qualifying/playoff diagnostic window.
UEFA_PERIOD_START = datetime(
    2026, 7, 1, tzinfo=timezone.utc
)

UEFA_PERIOD_END = datetime(
    2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc
)

# Same teams but kickoff differs by up to this amount.
KICKOFF_MISMATCH_TOLERANCE = timedelta(
    hours=24
)


# ============================================================================
# SPFL TEAM NAME NORMALISATION
# ============================================================================

SPFL_TEAM_ALIASES = {
    "rangers": "rangers",
    "rangers fc": "rangers",

    "celtic": "celtic",
    "celtic fc": "celtic",

    "aberdeen": "aberdeen",
    "aberdeen fc": "aberdeen",

    "dundee": "dundee",
    "dundee fc": "dundee",

    "dundee united": "dundee united",
    "dundee united fc": "dundee united",

    "hearts": "hearts",
    "heart of midlothian": "hearts",
    "heart of midlothian fc": "hearts",

    "hibernian": "hibernian",
    "hibernian fc": "hibernian",

    "kilmarnock": "kilmarnock",
    "kilmarnock fc": "kilmarnock",

    "motherwell": "motherwell",
    "motherwell fc": "motherwell",

    "falkirk": "falkirk",
    "falkirk fc": "falkirk",

    "st johnstone": "st johnstone",
    "st. johnstone": "st johnstone",
    "st johnstone fc": "st johnstone",
    "st. johnstone fc": "st johnstone",

    "st mirren": "st mirren",
    "st. mirren": "st mirren",
    "st mirren fc": "st mirren",
    "st. mirren fc": "st mirren",
}


SPFL_TEAM_IDS = set(
    SPFL_TEAM_ALIASES.values()
)


# ============================================================================
# COMPETITION GROUPS
# ============================================================================

UEFA_COMPETITIONS = {
    "Champions League",
    "Europa League",
    "UEFA Conference League",
}

DOMESTIC_COMPETITIONS = {
    "Scottish Premiership",
    "Scottish Championship",
    "Scottish League One",
    "Scottish League Two",
    "Scottish Cup",
}


# ============================================================================
# HTTP DOWNLOAD
# ============================================================================

def download(url: str) -> str:

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):

        print(
            f"Request attempt {attempt}/{MAX_ATTEMPTS}"
        )

        try:

            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(compatible; SPFL-EPG Fixtur.es diagnostic)"
                    )
                },
            )

            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:

                status = getattr(
                    response,
                    "status",
                    200,
                )

                data = response.read()

            print(
                f"HTTP status: {status}"
            )

            print(
                f"Downloaded ICS characters: {len(data)}"
            )

            return data.decode(
                "utf-8",
                errors="replace",
            )

        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
        ) as exc:

            last_error = exc

            print(
                f"HTTP error: {exc}"
            )

    raise RuntimeError(
        "Unable to download Fixtur.es feed "
        f"after {MAX_ATTEMPTS} attempts: "
        f"{last_error}"
    )


# ============================================================================
# ICS PARSER
# ============================================================================

def unfold_ics(text: str) -> list[str]:
    """
    RFC-style ICS line unfolding.

    Continuation lines begin with a space or tab and are appended to the
    previous line.
    """

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    lines = text.split("\n")

    unfolded = []

    for line in lines:

        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


def parse_ics_events(text: str) -> list[dict]:
    """
    Self-contained ICS parser used only by this diagnostic.

    This intentionally does NOT depend on sources.fixtur_es exposing a
    parse_ics() function.
    """

    lines = unfold_ics(text)

    events = []

    current = None
    inside_event = False

    for line in lines:

        line = line.strip()

        if line == "BEGIN:VEVENT":
            current = {}
            inside_event = True
            continue

        if line == "END:VEVENT":

            if current is not None:
                events.append(current)

            current = None
            inside_event = False

            continue

        if not inside_event:
            continue

        if ":" not in line:
            continue

        field, value = line.split(
            ":",
            1,
        )

        # Strip parameters from:
        #
        # DTSTART;VALUE=DATE-TIME
        #
        field_name = field.split(
            ";",
            1,
        )[0].upper()

        current[field_name] = value

    return events


# ============================================================================
# DATE PARSING
# ============================================================================

def parse_datetime(
    value: str | None,
) -> datetime | None:

    if not value:
        return None

    value = value.strip()

    formats = (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
    )

    for fmt in formats:

        try:

            parsed = datetime.strptime(
                value,
                fmt,
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        except ValueError:
            continue

    return None


# ============================================================================
# TEAM NAME NORMALISATION
# ============================================================================

def normalise_team_name(
    name: str,
) -> str:

    if not name:
        return ""

    value = name.strip().lower()

    value = value.replace(
        ".",
        "",
    )

    value = value.replace(
        ",",
        "",
    )

    value = " ".join(
        value.split()
    )

    if value in SPFL_TEAM_ALIASES:
        return SPFL_TEAM_ALIASES[value]

    # Conservative generic normalisation.
    if value.endswith(" fc"):
        value = value[:-3].strip()

    return value


def is_spfl_team(
    name: str,
) -> bool:

    return (
        normalise_team_name(name)
        in SPFL_TEAM_IDS
    )


# ============================================================================
# FIXTURE PARSING
# ============================================================================

def clean_team_name(
    value: str,
) -> str:

    value = value.strip()

    # Remove common Fixtur.es suffixes.
    value = re.sub(
        r"\s+\[(?:EL|CL|Conf)\]\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return value.strip()


def parse_summary(
    summary: str,
) -> tuple[str, str] | None:

    if not summary:
        return None

    if " - " not in summary:
        return None

    home, away = summary.split(
        " - ",
        1,
    )

    # Remove result:
    #
    # Celtic - Rangers (2-1)
    #
    away = re.sub(
        r"\s+\([^)]*\)\s*$",
        "",
        away,
    )

    away = clean_team_name(
        away
    )

    home = clean_team_name(
        home
    )

    if not home or not away:
        return None

    return home, away


def event_to_fixture(
    event: dict,
    competition: str | None = None,
) -> dict | None:

    summary = event.get(
        "SUMMARY",
        "",
    ).strip()

    start = parse_datetime(
        event.get("DTSTART")
    )

    if start is None:
        return None

    if not (
        SEASON_START
        <= start
        <= SEASON_END
    ):
        return None

    parsed = parse_summary(
        summary
    )

    if parsed is None:
        return None

    home, away = parsed

    return {
        "date": start,
        "home": home,
        "away": away,
        "home_norm": normalise_team_name(home),
        "away_norm": normalise_team_name(away),
        "summary": summary,
        "competition": competition,
        "raw": event,
    }


def parse_fixtures(
    text: str,
    competition: str | None = None,
) -> tuple[list[dict], int]:

    events = parse_ics_events(
        text
    )

    fixtures = []

    for event in events:

        fixture = event_to_fixture(
            event,
            competition,
        )

        if fixture is not None:
            fixtures.append(
                fixture
            )

    return fixtures, len(events)


# ============================================================================
# FIXTURE KEYS
# ============================================================================

def exact_key(
    fixture: dict,
) -> tuple:

    return (
        fixture["date"],
        fixture["home_norm"],
        fixture["away_norm"],
    )


def team_key(
    fixture: dict,
) -> tuple:

    return (
        fixture["home_norm"],
        fixture["away_norm"],
    )


def unordered_team_key(
    fixture: dict,
) -> tuple:

    return tuple(
        sorted(
            (
                fixture["home_norm"],
                fixture["away_norm"],
            )
        )
    )


def same_teams(
    a: dict,
    b: dict,
) -> bool:

    return (
        a["home_norm"]
        == b["home_norm"]
        and
        a["away_norm"]
        == b["away_norm"]
    )


def same_teams_any_order(
    a: dict,
    b: dict,
) -> bool:

    return (
        unordered_team_key(a)
        == unordered_team_key(b)
    )


# ============================================================================
# SEASON / DATE HELPERS
# ============================================================================

def is_july(
    dt: datetime,
) -> bool:

    return (
        dt.year == 2026
        and dt.month == 7
    )


def in_uefa_period(
    dt: datetime,
) -> bool:

    return (
        UEFA_PERIOD_START
        <= dt
        <= UEFA_PERIOD_END
    )


def format_datetime(
    dt: datetime,
) -> str:

    return dt.strftime(
        "%Y-%m-%d %H:%M"
    )


# ============================================================================
# LOAD TEAM CALENDARS
# ============================================================================

def load_team_calendars():

    all_fixtures = []

    print()
    print("=" * 70)
    print("TEAM CALENDAR SUMMARY")
    print("=" * 70)

    for team, url in TEAM_CALENDARS.items():

        print()
        print(team)

        try:

            text = download(
                url
            )

            fixtures, event_count = parse_fixtures(
                text
            )

            all_fixtures.extend(
                fixtures
            )

            print(
                f"{event_count} VEVENTs, "
                f"{len(fixtures)} in 2026/27"
            )

        except Exception as exc:

            print(
                f"ERROR: {exc}"
            )

    unique = {}

    for fixture in all_fixtures:
        unique[
            exact_key(fixture)
        ] = fixture

    print()
    print(
        f"Total VEVENT records: "
        f"{sum(1 for _ in all_fixtures)}"
    )

    print(
        f"Unique team-calendar fixtures: "
        f"{len(unique)}"
    )

    return list(
        unique.values()
    )


# ============================================================================
# LOAD COMPETITION CALENDARS
# ============================================================================

def load_competition_calendars():

    all_fixtures = []

    competition_fixtures = {}

    print()
    print("=" * 70)
    print("COMPETITION CALENDAR SUMMARY")
    print("=" * 70)

    for competition, url in COMPETITION_CALENDARS.items():

        print()
        print(competition)
        print(
            f"URL: {url}"
        )

        try:

            text = download(
                url
            )

            fixtures, event_count = parse_fixtures(
                text,
                competition,
            )

            competition_fixtures[
                competition
            ] = fixtures

            all_fixtures.extend(
                fixtures
            )

            print(
                f"VEVENTs: {event_count}"
            )

            print(
                f"2026/27 events: "
                f"{len(fixtures)}"
            )

        except Exception as exc:

            print(
                f"ERROR: {exc}"
            )

            competition_fixtures[
                competition
            ] = []

    unique = {}

    for fixture in all_fixtures:
        unique[
            exact_key(fixture)
        ] = fixture

    print()
    print(
        f"Total 2026/27 events: "
        f"{len(all_fixtures)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(unique)}"
    )

    return (
        list(unique.values()),
        competition_fixtures,
    )


# ============================================================================
# MATCH SEARCH
# ============================================================================

def find_same_teams(
    fixture: dict,
    competition_fixtures: list[dict],
) -> list[dict]:

    return [
        candidate
        for candidate in competition_fixtures
        if same_teams(
            fixture,
            candidate,
        )
    ]


def find_same_teams_different_time(
    fixture: dict,
    competition_fixtures: list[dict],
) -> list[dict]:

    matches = []

    for candidate in competition_fixtures:

        if not same_teams(
            fixture,
            candidate,
        ):
            continue

        difference = abs(
            candidate["date"]
            - fixture["date"]
        )

        if (
            difference > timedelta(0)
            and
            difference <= KICKOFF_MISMATCH_TOLERANCE
        ):
            matches.append(
                candidate
            )

    return matches


def find_same_fixture_different_names(
    fixture: dict,
    competition_fixtures: list[dict],
) -> list[dict]:

    matches = []

    for candidate in competition_fixtures:

        if (
            candidate["date"].date()
            != fixture["date"].date()
        ):
            continue

        if (
            candidate["home_norm"]
            == fixture["home_norm"]
            and
            candidate["away_norm"]
            == fixture["away_norm"]
        ):

            # Raw names must differ for this to be a
            # genuine NAME MISMATCH classification.
            if (
                candidate["home"]
                != fixture["home"]
                or
                candidate["away"]
                != fixture["away"]
            ):
                matches.append(
                    candidate
                )

    return matches


def find_reversed_fixture(
    fixture: dict,
    competition_fixtures: list[dict],
) -> list[dict]:

    matches = []

    for candidate in competition_fixtures:

        if not same_teams_any_order(
            fixture,
            candidate,
        ):
            continue

        if (
            candidate["date"].date()
            == fixture["date"].date()
        ):
            matches.append(
                candidate
            )

    return matches


# ============================================================================
# CLASSIFICATION
# ============================================================================

CLASSIFICATIONS = (
    "FRIENDLY",
    "POSSIBLE MISSING UEFA",
    "POSSIBLE MISSING DOMESTIC CUP",
    "POSSIBLE COMPETITION DATE/TIME MISMATCH",
    "NAME MISMATCH",
    "GENUINE UNCLASSIFIED",
)


def classify_fixture(
    fixture: dict,
    competition_fixtures: list[dict],
):

    # ------------------------------------------------------------
    # NAME MISMATCH
    # ------------------------------------------------------------

    name_matches = (
        find_same_fixture_different_names(
            fixture,
            competition_fixtures,
        )
    )

    if name_matches:

        return (
            "NAME MISMATCH",
            "Same fixture/date exists in competition data "
            "but team names differ.",
            name_matches,
        )

    # ------------------------------------------------------------
    # DATE/TIME MISMATCH
    # ------------------------------------------------------------

    time_matches = (
        find_same_teams_different_time(
            fixture,
            competition_fixtures,
        )
    )

    if time_matches:

        return (
            "POSSIBLE COMPETITION DATE/TIME MISMATCH",
            "Same home/away teams exist in competition data "
            "but kickoff differs.",
            time_matches,
        )

    # ------------------------------------------------------------
    # HOME/AWAY REPRESENTATION
    # ------------------------------------------------------------

    reversed_matches = (
        find_reversed_fixture(
            fixture,
            competition_fixtures,
        )
    )

    if reversed_matches:

        return (
            "NAME MISMATCH",
            "Same two teams/date exist but home/away "
            "representation differs.",
            reversed_matches,
        )

    # ------------------------------------------------------------
    # DOMESTIC CUP
    # ------------------------------------------------------------

    home_spfl = is_spfl_team(
        fixture["home"]
    )

    away_spfl = is_spfl_team(
        fixture["away"]
    )

    if home_spfl and away_spfl:

        return (
            "POSSIBLE MISSING DOMESTIC CUP",
            "Both clubs are SPFL teams but no domestic "
            "competition-calendar match was found.",
            [],
        )

    # ------------------------------------------------------------
    # UEFA
    # ------------------------------------------------------------

    if (
        (home_spfl or away_spfl)
        and
        not (home_spfl and away_spfl)
        and
        in_uefa_period(
            fixture["date"]
        )
    ):

        return (
            "POSSIBLE MISSING UEFA",
            "SPFL club has a non-SPFL opponent during "
            "the UEFA qualifying/playoff period.",
            [],
        )

    # ------------------------------------------------------------
    # FRIENDLY
    # ------------------------------------------------------------

    if (
        (home_spfl or away_spfl)
        and
        not (home_spfl and away_spfl)
        and
        is_july(
            fixture["date"]
        )
    ):

        return (
            "FRIENDLY",
            "SPFL club playing a non-SPFL opponent in "
            "July/pre-season with no competition match.",
            [],
        )

    # ------------------------------------------------------------
    # UNKNOWN
    # ------------------------------------------------------------

    return (
        "GENUINE UNCLASSIFIED",
        "No reliable classification rule applies.",
        [],
    )


# ============================================================================
# PRINT CLASSIFICATION
# ============================================================================

def print_classification_report(
    classifications,
):

    print()
    print("=" * 70)
    print("UNMATCHED FIXTURE CLASSIFICATION")
    print("=" * 70)

    total = sum(
        len(items)
        for items in classifications.values()
    )

    for category in CLASSIFICATIONS:

        print()
        print(
            f"{category}: "
            f"{len(classifications[category])}"
        )

    print()
    print(
        f"TOTAL UNMATCHED: {total}"
    )

    # ------------------------------------------------------------
    # Detailed lists
    # ------------------------------------------------------------

    for category in CLASSIFICATIONS:

        items = classifications[
            category
        ]

        if not items:
            continue

        print()
        print(
            "-" * 70
        )

        print(
            f"{category}: {len(items)}"
        )

        print(
            "-" * 70
        )

        for fixture, reason, matches in items:

            print(
                f"{format_datetime(fixture['date'])} | "
                f"{fixture['home']} - "
                f"{fixture['away']}"
            )

            print(
                f"Reason: {reason}"
            )

            for match in matches:

                competition = (
                    match.get(
                        "competition"
                    )
                    or "Unknown"
                )

                print(
                    "  Competition candidate: "
                    f"{format_datetime(match['date'])} | "
                    f"{match['home']} - "
                    f"{match['away']} | "
                    f"{competition}"
                )

            print()


# ============================================================================
# MAIN AUDIT
# ============================================================================

def main():

    team_fixtures = (
        load_team_calendars()
    )

    (
        competition_fixtures,
        competition_groups,
    ) = load_competition_calendars()

    print()
    print("=" * 70)
    print("FULL OVERLAP / CLASSIFICATION AUDIT")
    print("=" * 70)

    team_index = {
        exact_key(fixture): fixture
        for fixture in team_fixtures
    }

    competition_index = {
        exact_key(fixture): fixture
        for fixture in competition_fixtures
    }

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

    print(
        f"Unique team-calendar fixtures: "
        f"{len(team_keys)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(competition_keys)}"
    )

    print(
        f"Exact fixture overlap: "
        f"{len(overlap)}"
    )

    print(
        f"Team-calendar only: "
        f"{len(team_only)}"
    )

    print(
        f"Competition-calendar only: "
        f"{len(competition_only)}"
    )

    # ------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # Competition breakdown
    # ------------------------------------------------------------

    print()
    print("OVERLAP BY COMPETITION")

    for competition, fixtures in (
        competition_groups.items()
    ):

        competition_keys = {
            exact_key(fixture)
            for fixture in fixtures
        }

        matched = (
            team_keys
            & competition_keys
        )

        if competition_keys:

            percentage = (
                len(matched)
                / len(competition_keys)
                * 100
            )

        else:

            percentage = 0.0

        print(
            f"{competition}: "
            f"{len(matched)}/"
            f"{len(competition_keys)} "
            f"({percentage:.1f}%)"
        )

    # ------------------------------------------------------------
    # Classify every team-only fixture
    # ------------------------------------------------------------

    classifications = {
        category: []
        for category in CLASSIFICATIONS
    }

    for key in sorted(
        team_only,
        key=lambda item: item[0],
    ):

        fixture = team_index[
            key
        ]

        classification, reason, matches = (
            classify_fixture(
                fixture,
                competition_fixtures,
            )
        )

        classifications[
            classification
        ].append(
            (
                fixture,
                reason,
                matches,
            )
        )

    print_classification_report(
        classifications
    )

    # ------------------------------------------------------------
    # Final result
    # ------------------------------------------------------------

    genuine_unclassified = len(
        classifications[
            "GENUINE UNCLASSIFIED"
        ]
    )

    print()
    print("=" * 70)
    print("DIAGNOSTIC RESULT")
    print("=" * 70)

    print(
        f"Team-calendar fixtures analysed: "
        f"{len(team_keys)}"
    )

    print(
        f"Competition-calendar fixtures analysed: "
        f"{len(competition_keys)}"
    )

    print(
        f"Exact overlaps: "
        f"{len(overlap)}"
    )

    print(
        f"Unmatched team fixtures: "
        f"{len(team_only)}"
    )

    print(
        f"Classified unmatched fixtures: "
        f"{len(team_only) - genuine_unclassified}"
    )

    print(
        f"Genuine unclassified: "
        f"{genuine_unclassified}"
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

    print()

    if genuine_unclassified:

        print(
            "RESULT: Investigation required for "
            "genuine unclassified fixtures."
        )

    else:

        print(
            "RESULT: All unmatched team fixtures "
            "have an explicit classification."
        )


if __name__ == "__main__":
    main()
```
