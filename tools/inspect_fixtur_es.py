#!/usr/bin/env python3

"""
Full Fixtur.es team-calendar / competition-calendar diagnostic.

This file is diagnostic only.

It:
- Loads all 12 SPFL team calendars.
- Loads domestic competition calendars.
- Loads UEFA Champions League, Europa League and Conference League calendars.
- Restricts analysis to the 2026/27 season.
- Normalises team names for comparison.
- Performs exact fixture matching.
- Detects likely date/time mismatches.
- Detects likely name mismatches.
- Classifies unmatched team-calendar fixtures into:
    FRIENDLY
    POSSIBLE MISSING UEFA
    POSSIBLE MISSING DOMESTIC CUP
    POSSIBLE COMPETITION DATE/TIME MISMATCH
    NAME MISMATCH
    GENUINE UNCLASSIFIED

No fixture data is written or modified.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# Make repository root importable
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEASON_START = datetime(2026, 7, 1, tzinfo=ZoneInfo("Europe/London"))
SEASON_END = datetime(2027, 6, 30, 23, 59, 59, tzinfo=ZoneInfo("Europe/London"))

REQUEST_TIMEOUT = 30
REQUEST_ATTEMPTS = 3

UK_TZ = ZoneInfo("Europe/London")


TEAM_CALENDARS = {
    "Rangers": "https://ics.fixtur.es/v2/team/rangers.ics",
    "Celtic": "https://ics.fixtur.es/v2/team/celtic.ics",
    "Aberdeen": "https://ics.fixtur.es/v2/team/aberdeen.ics",
    "Dundee": "https://ics.fixtur.es/v2/team/dundee-fc.ics",
    "Dundee United": "https://ics.fixtur.es/v2/team/dundee-united.ics",
    "Hearts": "https://ics.fixtur.es/v2/team/heart-of-midlothian.ics",
    "Hibernian": "https://ics.fixtur.es/v2/team/hibernian.ics",
    "Kilmarnock": "https://ics.fixtur.es/v2/team/kilmarnock.ics",
    "Motherwell": "https://ics.fixtur.es/v2/team/motherwell.ics",
    "Falkirk": "https://ics.fixtur.es/v2/team/falkirk.ics",
    "St Johnstone": "https://ics.fixtur.es/v2/team/st-johnstone.ics",
    "St Mirren": "https://ics.fixtur.es/v2/team/st-mirren.ics",
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

    "Champions League":
        "https://ics.fixtur.es/v2/league/champions-league.ics",

    "Europa League":
        "https://ics.fixtur.es/v2/league/europa-league.ics",

    "UEFA Conference League":
        "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
}


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


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

TEAM_NAME_ALIASES = {
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

    # Common Fixtur.es / UEFA variants
    "m. haifa": "maccabi haifa",
    "maccabi haifa": "maccabi haifa",

    "saint-etienne": "saint etienne",
    "as saint-etienne": "saint etienne",
    "saint etienne": "saint etienne",

    "hjk helsinki": "hjk helsinki",

    "lask linz": "lask linz",

    "sk sturm graz": "sturm graz",
    "sturm graz": "sturm graz",

    "fk shkendija 79": "shkendija",
    "shkendija": "shkendija",

    "hb torshavn": "hb torshavn",

    "jagiellonia bialystok": "jagiellonia bialystok",
    "jagiellonia białystok": "jagiellonia bialystok",

    "sporting portugal": "sporting",
    "sporting cp": "sporting",
    "sporting lisbon": "sporting",

    "heart of midlothian": "hearts",
}


def normalise_team_name(name: str) -> str:
    """
    Normalise a team name for fixture comparison.
    """

    value = name.strip().lower()

    value = value.replace("[cl]", "")
    value = value.replace("[el]", "")
    value = value.replace("[conf]", "")

    value = " ".join(value.split())

    if value in TEAM_NAME_ALIASES:
        return TEAM_NAME_ALIASES[value]

    return value


# ---------------------------------------------------------------------------
# ICS downloading
# ---------------------------------------------------------------------------

def download_ics(url: str) -> str:
    """
    Download an ICS feed with retries.
    """

    headers = {
        "User-Agent": "SPFL-EPG-FixturES-Diagnostic/1.0"
    }

    last_error = None

    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        try:
            print(f"Request attempt {attempt}/{REQUEST_ATTEMPTS}")

            request = Request(url, headers=headers)

            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                status = getattr(response, "status", 200)
                content = response.read()

            print(f"HTTP status: {status}")
            print(f"Downloaded ICS characters: {len(content)}")

            return content.decode("utf-8", errors="replace")

        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            print(f"Request failed: {exc}")

    raise RuntimeError(
        f"Unable to download Fixtur.es feed after "
        f"{REQUEST_ATTEMPTS} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# ICS parsing
# ---------------------------------------------------------------------------

def unfold_ics(text: str) -> list[str]:
    """
    Unfold RFC 5545 continuation lines.
    """

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    unfolded = []

    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


def parse_ics_events(text: str) -> list[dict]:
    """
    Parse VEVENT blocks without requiring external dependencies.
    """

    lines = unfold_ics(text)

    events = []
    current = None

    for line in lines:
        line = line.strip()

        if line == "BEGIN:VEVENT":
            current = {}

        elif line == "END:VEVENT":
            if current:
                events.append(current)

            current = None

        elif current is not None and ":" in line:
            key, value = line.split(":", 1)

            # Remove parameters from property name.
            key = key.split(";", 1)[0].upper()

            current[key] = value.strip()

    return events


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_ics_datetime(value: str) -> datetime | None:
    """
    Parse common ICS date/time formats.
    """

    value = value.strip()

    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.replace(tzinfo=timezone.utc).astimezone(UK_TZ)

        if "T" in value:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
            return dt.replace(tzinfo=UK_TZ)

        dt = datetime.strptime(value, "%Y%m%d")
        return dt.replace(tzinfo=UK_TZ)

    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Fixture extraction
# ---------------------------------------------------------------------------

def clean_team_name(name: str) -> str:
    """
    Clean common suffixes/prefixes from event team names.
    """

    value = name.strip()

    value = value.replace("  ", " ")

    return value


def extract_fixture(event: dict, competition: str | None = None) -> dict | None:
    """
    Convert a VEVENT into a fixture dictionary.
    """

    dtstart = event.get("DTSTART")

    if not dtstart:
        return None

    start = parse_ics_datetime(dtstart)

    if start is None:
        return None

    if start < SEASON_START or start > SEASON_END:
        return None

    summary = event.get("SUMMARY", "").strip()

    if not summary:
        return None

    description = event.get("DESCRIPTION", "").strip()

    location = event.get("LOCATION", "").strip()

    # Fixtur.es generally uses:
    #
    # HOME - AWAY
    #
    # but occasionally additional metadata can appear.
    if " - " in summary:
        home, away = summary.split(" - ", 1)
    elif " – " in summary:
        home, away = summary.split(" – ", 1)
    elif " vs " in summary.lower():
        parts = summary.lower().split(" vs ", 1)

        original_lower = summary.lower()

        home_start = original_lower.find(parts[0])
        separator = original_lower.find(" vs ", home_start)

        home = summary[:separator]
        away = summary[separator + 4:]
    else:
        return None

    home = clean_team_name(home)
    away = clean_team_name(away)

    return {
        "datetime": start,
        "home": home,
        "away": away,
        "summary": summary,
        "description": description,
        "location": location,
        "competition": competition,
        "event": event,
    }


def fixture_key(fixture: dict) -> tuple:
    """
    Exact normalised fixture key including kickoff.
    """

    return (
        fixture["datetime"].replace(second=0, microsecond=0),
        normalise_team_name(fixture["home"]),
        normalise_team_name(fixture["away"]),
    )


def teams_key(fixture: dict) -> tuple:
    """
    Fixture identity without kickoff time.
    """

    return (
        normalise_team_name(fixture["home"]),
        normalise_team_name(fixture["away"]),
    )


def unordered_teams_key(fixture: dict) -> frozenset:
    """
    Fixture identity ignoring home/away direction.

    Useful for detecting unusual calendar representation differences.
    """

    return frozenset(
        (
            normalise_team_name(fixture["home"]),
            normalise_team_name(fixture["away"]),
        )
    )


# ---------------------------------------------------------------------------
# UEFA detection
# ---------------------------------------------------------------------------

def has_uefa_marker(fixture: dict) -> bool:
    """
    Detect UEFA markers in summary or description.
    """

    text = " ".join(
        [
            fixture.get("summary", ""),
            fixture.get("description", ""),
            fixture.get("location", ""),
        ]
    ).lower()

    markers = [
        "[cl]",
        "[el]",
        "[conf]",
        "champions league",
        "europa league",
        "conference league",
        "uefa",
    ]

    return any(marker in text for marker in markers)


def is_uefa_period(dt: datetime) -> bool:
    """
    Broad 2026/27 UEFA qualifying/playoff window.

    This intentionally errs toward flagging possible UEFA fixtures rather
    than silently calling them friendlies.
    """

    month_day = (dt.month, dt.day)

    return (
        (7, 1) <= month_day <= (8, 31)
    )


# ---------------------------------------------------------------------------
# SPFL opponent detection
# ---------------------------------------------------------------------------

NORMALISED_SPFL_TEAMS = {
    normalise_team_name(team)
    for team in SPFL_TEAMS
}


def fixture_involves_spfl_team(fixture: dict) -> bool:
    return (
        normalise_team_name(fixture["home"]) in NORMALISED_SPFL_TEAMS
        or
        normalise_team_name(fixture["away"]) in NORMALISED_SPFL_TEAMS
    )


def fixture_has_two_spfl_teams(fixture: dict) -> bool:
    return (
        normalise_team_name(fixture["home"]) in NORMALISED_SPFL_TEAMS
        and
        normalise_team_name(fixture["away"]) in NORMALISED_SPFL_TEAMS
    )


def fixture_has_non_spfl_opponent(fixture: dict) -> bool:
    return fixture_involves_spfl_team(fixture) and not fixture_has_two_spfl_teams(
        fixture
    )


# ---------------------------------------------------------------------------
# Feed loading
# ---------------------------------------------------------------------------

def load_team_calendars():
    all_fixtures = []
    raw_count = 0
    successful = 0
    failed = 0

    print("=" * 70)
    print("TEAM CALENDAR SUMMARY")
    print("=" * 70)

    for team, url in TEAM_CALENDARS.items():
        print(team)

        try:
            ics = download_ics(url)
            events = parse_ics_events(ics)

            raw_count += len(events)

            fixtures = []

            for event in events:
                fixture = extract_fixture(event)

                if fixture:
                    fixture["team_source"] = team
                    fixtures.append(fixture)
                    all_fixtures.append(fixture)

            successful += 1

            print(
                f"{len(events)} VEVENTs, "
                f"{len(fixtures)} in 2026/27"
            )

        except Exception as exc:
            failed += 1
            print(f"FAILED: {exc}")

    print(f"Total VEVENT records: {raw_count}")
    print(f"Total 2026/27 events: {len(all_fixtures)}")

    return all_fixtures, successful, failed


def load_competition_calendars():
    all_fixtures = []
    raw_count = 0

    print("=" * 70)
    print("COMPETITION CALENDAR SUMMARY")
    print("=" * 70)

    for competition, url in COMPETITION_CALENDARS.items():
        print()
        print(competition)
        print(f"URL: {url}")

        try:
            ics = download_ics(url)
            events = parse_ics_events(ics)

            raw_count += len(events)

            fixtures = []

            for event in events:
                fixture = extract_fixture(
                    event,
                    competition=competition,
                )

                if fixture:
                    fixtures.append(fixture)
                    all_fixtures.append(fixture)

            print(f"VEVENTs: {len(events)}")
            print(f"2026/27 events: {len(fixtures)}")

        except Exception as exc:
            print(f"FAILED: {exc}")

    print()
    print(f"Total VEVENT records: {raw_count}")
    print(f"Total 2026/27 events: {len(all_fixtures)}")

    return all_fixtures


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_fixtures(fixtures: list[dict]) -> list[dict]:
    """
    Deduplicate exact fixture keys.
    """

    result = {}
    
    for fixture in fixtures:
        key = fixture_key(fixture)

        if key not in result:
            result[key] = fixture

    return list(result.values())


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def build_indexes(fixtures: list[dict]):
    exact = {}
    by_teams = defaultdict(list)
    by_unordered_teams = defaultdict(list)

    for fixture in fixtures:
        exact[fixture_key(fixture)] = fixture

        by_teams[teams_key(fixture)].append(fixture)

        by_unordered_teams[
            unordered_teams_key(fixture)
        ].append(fixture)

    return exact, by_teams, by_unordered_teams


# ---------------------------------------------------------------------------
# Competition classification
# ---------------------------------------------------------------------------

def competition_is_domestic(competition: str | None) -> bool:
    return competition in DOMESTIC_COMPETITIONS


def competition_is_uefa(competition: str | None) -> bool:
    return competition in UEFA_COMPETITIONS


# ---------------------------------------------------------------------------
# Mismatch detection
# ---------------------------------------------------------------------------

def detect_name_mismatch(
    team_fixture: dict,
    competition_fixtures: list[dict],
) -> bool:
    """
    Look for the same fixture where raw names differ but normalised names
    identify the same clubs.

    Because our exact matching already normalises names, this primarily
    exists to document/name-match cases.
    """

    target_home = normalise_team_name(team_fixture["home"])
    target_away = normalise_team_name(team_fixture["away"])

    for candidate in competition_fixtures:
        if (
            normalise_team_name(candidate["home"]) == target_home
            and
            normalise_team_name(candidate["away"]) == target_away
        ):
            raw_same = (
                candidate["home"].strip().lower()
                == team_fixture["home"].strip().lower()
                and
                candidate["away"].strip().lower()
                == team_fixture["away"].strip().lower()
            )

            if not raw_same:
                return True

    return False


def detect_datetime_mismatch(
    team_fixture: dict,
    candidates: list[dict],
    max_minutes: int = 180,
) -> bool:
    """
    Detect same fixture with a kickoff difference.

    Only considered a date/time mismatch when the same normalised teams
    appear in competition data.
    """

    target_time = team_fixture["datetime"]

    for candidate in candidates:
        delta = abs(
            (candidate["datetime"] - target_time).total_seconds()
        )

        if 0 < delta <= max_minutes * 60:
            return True

    return False


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

CATEGORY_FRIENDLY = "FRIENDLY"
CATEGORY_UEFA = "POSSIBLE MISSING UEFA"
CATEGORY_DOMESTIC = "POSSIBLE MISSING DOMESTIC CUP"
CATEGORY_TIME = "POSSIBLE COMPETITION DATE/TIME MISMATCH"
CATEGORY_NAME = "NAME MISMATCH"
CATEGORY_UNKNOWN = "GENUINE UNCLASSIFIED"


def classify_unmatched_fixture(
    fixture: dict,
    competition_fixtures: list[dict],
    competition_by_teams: dict,
):
    """
    Classify one unmatched team-calendar fixture.

    Important ordering:

    1. Name mismatch
    2. Date/time mismatch
    3. Explicit UEFA marker
    4. Possible UEFA period
    5. Domestic SPFL v SPFL
    6. July non-SPFL friendly
    7. Genuine unclassified
    """

    candidates = competition_by_teams.get(
        teams_key(fixture),
        [],
    )

    # ---------------------------------------------------------------
    # Same normalised teams, but raw names differ
    # ---------------------------------------------------------------

    if detect_name_mismatch(
        fixture,
        candidates,
    ):
        return (
            CATEGORY_NAME,
            "The same fixture exists in competition data but team names "
            "are represented differently."
        )

    # ---------------------------------------------------------------
    # Same teams, different kickoff
    # ---------------------------------------------------------------

    if detect_datetime_mismatch(
        fixture,
        candidates,
    ):
        return (
            CATEGORY_TIME,
            "The same teams appear in competition data but the kickoff "
            "time differs."
        )

    # ---------------------------------------------------------------
    # Explicit UEFA marker
    # ---------------------------------------------------------------

    if has_uefa_marker(fixture):
        return (
            CATEGORY_UEFA,
            "Fixture contains an explicit UEFA competition marker but "
            "no matching UEFA competition-calendar fixture was found."
        )

    # ---------------------------------------------------------------
    # Non-SPFL opponent during UEFA qualifying/playoff period
    # ---------------------------------------------------------------

    if (
        fixture_has_non_spfl_opponent(fixture)
        and
        is_uefa_period(fixture["datetime"])
    ):
        return (
            CATEGORY_UEFA,
            "SPFL club has a non-SPFL opponent during the UEFA "
            "qualifying/playoff period, but no matching UEFA calendar "
            "fixture was found."
        )

    # ---------------------------------------------------------------
    # Two SPFL teams
    # ---------------------------------------------------------------

    if fixture_has_two_spfl_teams(fixture):
        return (
            CATEGORY_DOMESTIC,
            "Both clubs are SPFL teams but no domestic competition-calendar "
            "match was found."
        )

    # ---------------------------------------------------------------
    # July non-SPFL fixture
    # ---------------------------------------------------------------

    if (
        fixture_has_non_spfl_opponent(fixture)
        and
        fixture["datetime"].month == 7
        and
        not has_uefa_marker(fixture)
    ):
        return (
            CATEGORY_FRIENDLY,
            "July fixture involving a non-SPFL opponent with no competition "
            "classification."
        )

    # ---------------------------------------------------------------
    # Nothing else fits
    # ---------------------------------------------------------------

    return (
        CATEGORY_UNKNOWN,
        "Fixture does not match any current diagnostic rule."
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_fixture(fixture: dict) -> str:
    dt = fixture["datetime"].strftime("%Y-%m-%d %H:%M")

    return (
        f"{dt} | "
        f"{fixture['home']} - {fixture['away']}"
    )


def print_category(
    category: str,
    fixtures: list[tuple[dict, str]],
):
    print()
    print(f"## {category}: {len(fixtures)}")
    print()

    if not fixtures:
        return

    for fixture, reason in fixtures:
        print(format_fixture(fixture))
        print(f"Reason: {reason}")

        competition = fixture.get("competition")

        if competition:
            print(f"Competition source: {competition}")

        print()


# ---------------------------------------------------------------------------
# Main diagnostic
# ---------------------------------------------------------------------------

def main():
    print()
    print("=" * 70)
    print("FULL FIXTUR.ES OVERLAP / CLASSIFICATION AUDIT")
    print("=" * 70)
    print()

    team_fixtures, successful, failed = load_team_calendars()

    print()
    print(
        f"Unique team-calendar fixtures: "
        f"{len(deduplicate_fixtures(team_fixtures))}"
    )

    competition_fixtures = load_competition_calendars()

    team_unique = deduplicate_fixtures(team_fixtures)
    competition_unique = deduplicate_fixtures(
        competition_fixtures
    )

    print()
    print("=" * 70)
    print("OVERLAP AUDIT")
    print("=" * 70)

    team_exact, team_by_teams, team_unordered = build_indexes(
        team_unique
    )

    comp_exact, comp_by_teams, comp_unordered = build_indexes(
        competition_unique
    )

    exact_overlap = []

    for key, fixture in team_exact.items():
        if key in comp_exact:
            exact_overlap.append(fixture)

    team_only = [
        fixture
        for key, fixture in team_exact.items()
        if key not in comp_exact
    ]

    competition_only = [
        fixture
        for key, fixture in comp_exact.items()
        if key not in team_exact
    ]

    print(
        f"Unique team-calendar fixtures:        "
        f"{len(team_unique)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(competition_unique)}"
    )

    print(
        f"Exact fixture overlap:                "
        f"{len(exact_overlap)}"
    )

    print(
        f"Team-calendar only:                   "
        f"{len(team_only)}"
    )

    print(
        f"Competition-calendar only:            "
        f"{len(competition_only)}"
    )

    if team_unique:
        competition_coverage = (
            len(exact_overlap)
            / len(team_unique)
            * 100
        )
    else:
        competition_coverage = 0

    if competition_unique:
        team_coverage = (
            len(exact_overlap)
            / len(competition_unique)
            * 100
        )
    else:
        team_coverage = 0

    print()
    print("COVERAGE")

    print(
        f"Competition coverage of team fixtures: "
        f"{competition_coverage:.1f}%"
    )

    print(
        f"Team coverage of competition fixtures: "
        f"{team_coverage:.1f}%"
    )

    # ------------------------------------------------------------------
    # Competition overlap
    # ------------------------------------------------------------------

    print()
    print("OVERLAP BY COMPETITION")

    for competition in COMPETITION_CALENDARS:
        fixtures = [
            f
            for f in competition_unique
            if f.get("competition") == competition
        ]

        matched = [
            f
            for f in fixtures
            if fixture_key(f) in team_exact
        ]

        total = len(fixtures)
        matches = len(matched)

        percentage = (
            matches / total * 100
            if total
            else 0
        )

        print(
            f"{competition}: "
            f"{matches}/{total} "
            f"({percentage:.1f}%)"
        )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    classifications = defaultdict(list)

    for fixture in team_only:
        category, reason = classify_unmatched_fixture(
            fixture,
            competition_unique,
            comp_by_teams,
        )

        classifications[category].append(
            (fixture, reason)
        )

    category_order = [
        CATEGORY_FRIENDLY,
        CATEGORY_UEFA,
        CATEGORY_DOMESTIC,
        CATEGORY_TIME,
        CATEGORY_NAME,
        CATEGORY_UNKNOWN,
    ]

    print()

    for category in category_order:
        print(
            f"{category}: "
            f"{len(classifications[category])}"
        )

    print()
    print(
        f"TOTAL UNMATCHED: "
        f"{len(team_only)}"
    )

    # ------------------------------------------------------------------
    # Detailed classifications
    # ------------------------------------------------------------------

    for category in category_order:
        print_category(
            category,
            sorted(
                classifications[category],
                key=lambda item: item[0]["datetime"],
            ),
        )

    # ------------------------------------------------------------------
    # Percentages
    # ------------------------------------------------------------------

    total_unmatched = len(team_only)

    print()
    print("CLASSIFICATION SUMMARY")

    for category in category_order:
        count = len(classifications[category])

        percentage = (
            count / total_unmatched * 100
            if total_unmatched
            else 0
        )

        print(
            f"{category}: "
            f"{count} "
            f"({percentage:.1f}%)"
        )

    # ------------------------------------------------------------------
    # Final integrity report
    # ------------------------------------------------------------------

    classified_count = sum(
        len(classifications[category])
        for category in category_order
    )

    genuine_unclassified = len(
        classifications[CATEGORY_UNKNOWN]
    )

    print()
    print(
        f"Team-calendar fixtures analysed: "
        f"{len(team_unique)}"
    )

    print(
        f"Competition-calendar fixtures analysed: "
        f"{len(competition_unique)}"
    )

    print(
        f"Exact overlaps: "
        f"{len(exact_overlap)}"
    )

    print(
        f"Unmatched team fixtures: "
        f"{len(team_only)}"
    )

    print(
        f"Classified unmatched fixtures: "
        f"{classified_count}"
    )

    print(
        f"Genuine unclassified: "
        f"{genuine_unclassified}"
    )

    print()
    print("This classification is diagnostic only.")
    print("No fixture data has been modified.")
    print("sources/fixtur_es.py was not modified.")
    print("fixtures.py was not modified.")
    print("generator.py was not modified.")

    if successful == len(TEAM_CALENDARS) and failed == 0:
        print()
        print(
            "RESULT: All available team and competition calendars "
            "were processed."
        )
    else:
        print()
        print(
            f"RESULT: Team calendars successful: "
            f"{successful}/{len(TEAM_CALENDARS)}"
        )

        print(
            f"Team calendars failed: {failed}"
        )


if __name__ == "__main__":
    main()
