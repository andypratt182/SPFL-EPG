from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Make the repository root importable when this file is run directly:
#
#     python tools/inspect_fixtur_es.py
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from sources.fixtur_es import (  # noqa: E402
    TEAM_CALENDARS,
    COMPETITION_CALENDARS,
    parse_ics,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEASON_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 6, 30, 23, 59, 59, tzinfo=timezone.utc)

REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 3

# UEFA qualifying/playoff activity can begin in July and continue through
# August. This is deliberately broad because this is a diagnostic.
UEFA_PERIOD_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
UEFA_PERIOD_END = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

# A kickoff difference within this period is considered potentially the same
# fixture if the teams otherwise match.
KICKOFF_MISMATCH_TOLERANCE = timedelta(hours=24)


# ---------------------------------------------------------------------------
# SPFL team identity
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Competition names
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def download(url: str) -> str:
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"Request attempt {attempt}/{MAX_ATTEMPTS}")

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

            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                status = getattr(response, "status", 200)
                data = response.read()

            print(f"HTTP status: {status}")
            print(f"Downloaded ICS characters: {len(data)}")

            return data.decode("utf-8", errors="replace")

        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            print(f"HTTP error: {exc}")

    raise RuntimeError(
        f"Unable to download Fixtur.es feed after "
        f"{MAX_ATTEMPTS} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def normalise_team_name(name: str) -> str:
    """
    Convert Fixtur.es team-name variants into a stable identity.

    This is intentionally conservative. We only normalise known SPFL names.
    Unknown clubs retain a simplified lowercase representation.
    """

    if not name:
        return ""

    value = name.strip().lower()

    # Remove common punctuation.
    value = value.replace(".", "")
    value = value.replace(",", "")
    value = " ".join(value.split())

    if value in SPFL_TEAM_ALIASES:
        return SPFL_TEAM_ALIASES[value]

    # Generic cleanup for non-SPFL teams.
    if value.endswith(" fc"):
        value = value[:-3].strip()

    return value


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    value = value.strip()

    # UTC format from Fixtur.es.
    formats = (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
    )

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed

        except ValueError:
            continue

    return None


def in_season(dt: datetime | None) -> bool:
    if dt is None:
        return False

    return SEASON_START <= dt <= SEASON_END


def in_uefa_period(dt: datetime | None) -> bool:
    if dt is None:
        return False

    return UEFA_PERIOD_START <= dt <= UEFA_PERIOD_END


def is_july_fixture(dt: datetime | None) -> bool:
    return dt is not None and dt.year == 2026 and dt.month == 7


def format_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "UNKNOWN"

    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Fixture extraction
# ---------------------------------------------------------------------------

def event_to_fixture(event: dict, competition: str | None = None) -> dict | None:
    """
    Convert an ICS event into the small fixture representation required by
    this diagnostic.

    The parser in sources.fixtur_es is expected to return ordinary event
    dictionaries. This function deliberately accepts several common field
    spellings so the diagnostic remains independent of the importer.
    """

    summary = (
        event.get("SUMMARY")
        or event.get("summary")
        or event.get("title")
        or ""
    ).strip()

    start_raw = (
        event.get("DTSTART")
        or event.get("dtstart")
        or event.get("start")
    )

    start = parse_datetime(start_raw)

    if start is None:
        return None

    # Fixtur.es summaries are normally:
    #
    #     Rangers - Celtic (2-1)
    #
    # or:
    #
    #     Rangers - Celtic [EL]
    #
    if " - " not in summary:
        return None

    home, away = summary.split(" - ", 1)

    # Remove result / competition suffixes from the away side.
    for marker in (" [EL]", " [CL]", " [Conf]"):
        if marker in away:
            away = away.split(marker, 1)[0]

    # Remove result in parentheses.
    if " (" in away:
        away = away.split(" (", 1)[0]

    home = home.strip()
    away = away.strip()

    if not home or not away:
        return None

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


def load_events(url: str, competition: str | None = None) -> list[dict]:
    ics_text = download(url)

    events = parse_ics(ics_text)

    fixtures = []

    for event in events:
        fixture = event_to_fixture(event, competition)

        if fixture is None:
            continue

        if not in_season(fixture["date"]):
            continue

        fixtures.append(fixture)

    return fixtures


# ---------------------------------------------------------------------------
# Fixture identity
# ---------------------------------------------------------------------------

def exact_key(fixture: dict) -> tuple:
    return (
        fixture["date"],
        fixture["home_norm"],
        fixture["away_norm"],
    )


def team_key(fixture: dict) -> tuple:
    return (
        fixture["home_norm"],
        fixture["away_norm"],
    )


def unordered_team_key(fixture: dict) -> tuple:
    return tuple(sorted(
        (
            fixture["home_norm"],
            fixture["away_norm"],
        )
    ))


def same_teams(a: dict, b: dict) -> bool:
    return (
        a["home_norm"] == b["home_norm"]
        and a["away_norm"] == b["away_norm"]
    )


def same_teams_ignoring_order(a: dict, b: dict) -> bool:
    return unordered_team_key(a) == unordered_team_key(b)


def is_spfl_team(name: str) -> bool:
    return normalise_team_name(name) in set(SPFL_TEAM_ALIASES.values())


def involves_spfl_opponent(fixture: dict) -> bool:
    return (
        is_spfl_team(fixture["home"])
        and is_spfl_team(fixture["away"])
    )


def has_non_spfl_opponent(fixture: dict) -> bool:
    return not involves_spfl_opponent(fixture)


# ---------------------------------------------------------------------------
# Loading team calendars
# ---------------------------------------------------------------------------

def load_team_calendars() -> tuple[list[dict], dict]:
    all_team_fixtures = []
    team_results = {}

    print("=" * 70)
    print("TEAM CALENDAR SUMMARY")
    print("=" * 70)

    for team, url in TEAM_CALENDARS.items():
        print()
        print(team)

        try:
            fixtures = load_events(url)

            team_results[team] = fixtures
            all_team_fixtures.extend(fixtures)

            print(
                f"{len(fixtures)} 2026/27 fixtures"
            )

        except Exception as exc:
            print(f"ERROR: {exc}")
            team_results[team] = []

    # De-duplicate team-calendar fixtures.
    unique = {}

    for fixture in all_team_fixtures:
        unique[exact_key(fixture)] = fixture

    print()
    print(f"Unique team-calendar fixtures: {len(unique)}")

    return list(unique.values()), team_results


# ---------------------------------------------------------------------------
# Loading competition calendars
# ---------------------------------------------------------------------------

def load_competition_calendars() -> tuple[list[dict], dict]:
    all_competition_fixtures = []
    competition_results = {}

    print()
    print("=" * 70)
    print("COMPETITION CALENDAR SUMMARY")
    print("=" * 70)

    for competition, url in COMPETITION_CALENDARS.items():
        print()
        print(competition)
        print(f"URL: {url}")

        try:
            fixtures = load_events(url, competition)

            competition_results[competition] = fixtures
            all_competition_fixtures.extend(fixtures)

            print(
                f"VEVENTs represented: {len(fixtures)}"
            )

        except Exception as exc:
            print(f"ERROR: {exc}")
            competition_results[competition] = []

    unique = {}

    for fixture in all_competition_fixtures:
        unique[exact_key(fixture)] = fixture

    print()
    print(
        f"Unique competition-calendar fixtures: {len(unique)}"
    )

    return list(unique.values()), competition_results


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def build_exact_index(fixtures: list[dict]) -> dict:
    index = {}

    for fixture in fixtures:
        index.setdefault(exact_key(fixture), []).append(fixture)

    return index


def build_team_index(fixtures: list[dict]) -> dict:
    index = {}

    for fixture in fixtures:
        index.setdefault(team_key(fixture), []).append(fixture)

    return index


def build_unordered_team_index(fixtures: list[dict]) -> dict:
    index = {}

    for fixture in fixtures:
        index.setdefault(
            unordered_team_key(fixture),
            [],
        ).append(fixture)

    return index


# ---------------------------------------------------------------------------
# Unmatched fixture classification
# ---------------------------------------------------------------------------

CLASSIFICATIONS = (
    "FRIENDLY",
    "POSSIBLE MISSING UEFA",
    "POSSIBLE MISSING DOMESTIC CUP",
    "POSSIBLE COMPETITION DATE/TIME MISMATCH",
    "NAME MISMATCH",
    "GENUINE UNCLASSIFIED",
)


def find_name_mismatch(
    fixture: dict,
    competition_fixtures: list[dict],
) -> list[dict]:
    """
    Find likely name mismatches where the actual fixture exists but one or
    both names differ from the team-calendar representation.

    We first compare date and then look for fixtures with the same pair of
    clubs after conservative normalisation.
    """

    matches = []

    for candidate in competition_fixtures:
        if candidate["date"].date() != fixture["date"].date():
            continue

        if same_teams(candidate, fixture):
            continue

        # Exact textual names differ, but normalised identities match.
        if (
            candidate["home_norm"] == fixture["home_norm"]
            and candidate["away_norm"] == fixture["away_norm"]
        ):
            matches.append(candidate)

    return matches


def find_time_mismatch(
    fixture: dict,
    competition_fixtures: list[dict],
) -> list[dict]:
    matches = []

    for candidate in competition_fixtures:
        if not same_teams(candidate, fixture):
            continue

        difference = abs(candidate["date"] - fixture["date"])

        if (
            difference > timedelta(0)
            and difference <= KICKOFF_MISMATCH_TOLERANCE
        ):
            matches.append(candidate)

    return matches


def find_order_mismatch(
    fixture: dict,
    competition_fixtures: list[dict],
) -> list[dict]:
    matches = []

    for candidate in competition_fixtures:
        if not same_teams_ignoring_order(candidate, fixture):
            continue

        if candidate["date"].date() == fixture["date"].date():
            matches.append(candidate)

    return matches


def classify_unmatched_fixture(
    fixture: dict,
    competition_fixtures: list[dict],
) -> tuple[str, str, list[dict]]:
    """
    Classify a fixture that was not an exact match.

    Priority deliberately favours evidence of a matching competition fixture
    over assumptions about friendlies.
    """

    # ---------------------------------------------------------------
    # 1. Name mismatch
    # ---------------------------------------------------------------

    name_matches = find_name_mismatch(
        fixture,
        competition_fixtures,
    )

    if name_matches:
        return (
            "NAME MISMATCH",
            "Same fixture/date found after team-name normalisation",
            name_matches,
        )

    # ---------------------------------------------------------------
    # 2. Same teams, different kickoff
    # ---------------------------------------------------------------

    time_matches = find_time_mismatch(
        fixture,
        competition_fixtures,
    )

    if time_matches:
        return (
            "POSSIBLE COMPETITION DATE/TIME MISMATCH",
            "Same home/away teams found in competition data with a different kickoff",
            time_matches,
        )

    # ---------------------------------------------------------------
    # 3. Reversed home/away representation
    # ---------------------------------------------------------------

    order_matches = find_order_mismatch(
        fixture,
        competition_fixtures,
    )

    if order_matches:
        return (
            "NAME MISMATCH",
            "Same two teams/date found but home/away representation differs",
            order_matches,
        )

    # ---------------------------------------------------------------
    # 4. Domestic SPFL fixture
    # ---------------------------------------------------------------

    if involves_spfl_opponent(fixture):
        return (
            "POSSIBLE MISSING DOMESTIC CUP",
            "Both clubs are SPFL teams and no competition-calendar match was found",
            [],
        )

    # ---------------------------------------------------------------
    # 5. Non-SPFL opponent during UEFA period
    # ---------------------------------------------------------------

    if (
        has_non_spfl_opponent(fixture)
        and in_uefa_period(fixture["date"])
    ):
        return (
            "POSSIBLE MISSING UEFA",
            "Non-SPFL opponent during the UEFA qualifying/playoff period",
            [],
        )

    # ---------------------------------------------------------------
    # 6. Likely friendly
    # ---------------------------------------------------------------

    if (
        has_non_spfl_opponent(fixture)
        and is_july_fixture(fixture["date"])
    ):
        return (
            "FRIENDLY",
            "Non-SPFL opponent in July/pre-season with no competition classification",
            [],
        )

    # ---------------------------------------------------------------
    # 7. Nothing explains it
    # ---------------------------------------------------------------

    return (
        "GENUINE UNCLASSIFIED",
        "No matching competition fixture or reliable classification rule applies",
        [],
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_fixture_detail(
    fixture: dict,
    reason: str,
    matches: list[dict],
) -> None:

    print(
        f"{format_datetime(fixture['date'])} | "
        f"{fixture['home']} - {fixture['away']}"
    )

    print(f"Reason: {reason}")

    if matches:
        for match in matches:
            competition = match.get("competition") or "Unknown"
            print(
                f"  Candidate: "
                f"{format_datetime(match['date'])} | "
                f"{match['home']} - {match['away']} "
                f"[{competition}]"
            )

    print()


def print_classification_report(
    classifications: dict[str, list[tuple]],
) -> None:

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
        print(f"{category}")
        print(f"  Count: {len(classifications[category])}")

    print()
    print("=" * 70)
    print("CLASSIFICATION TOTAL")
    print("=" * 70)

    print(
        f"Team-calendar-only fixtures: {total}"
    )

    classified = total - len(
        classifications["GENUINE UNCLASSIFIED"]
    )

    print(
        f"Classified:                  {classified}"
    )

    print(
        f"Unclassified:                "
        f"{len(classifications['GENUINE UNCLASSIFIED'])}"
    )

    print()

    for category in CLASSIFICATIONS:
        items = classifications[category]

        if not items:
            continue

        print()
        print("-" * 70)
        print(f"{category}: {len(items)}")
        print("-" * 70)

        for fixture, reason, matches in items:
            print_fixture_detail(
                fixture,
                reason,
                matches,
            )


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def main() -> None:

    team_fixtures, team_results = load_team_calendars()

    competition_fixtures, competition_results = (
        load_competition_calendars()
    )

    print()
    print("=" * 70)
    print("FULL OVERLAP / CLASSIFICATION AUDIT")
    print("=" * 70)

    team_index = build_exact_index(team_fixtures)
    competition_index = build_exact_index(
        competition_fixtures
    )

    team_keys = set(team_index)
    competition_keys = set(competition_index)

    overlap = team_keys & competition_keys

    team_only = team_keys - competition_keys
    competition_only = (
        competition_keys - team_keys
    )

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
            f"Competition coverage of team fixtures: "
            f"{len(overlap) / len(team_keys) * 100:.1f}%"
        )
    else:
        print(
            "Competition coverage of team fixtures: 0.0%"
        )

    if competition_keys:
        print(
            f"Team coverage of competition fixtures: "
            f"{len(overlap) / len(competition_keys) * 100:.1f}%"
        )
    else:
        print(
            "Team coverage of competition fixtures: 0.0%"
        )

    # ---------------------------------------------------------------
    # Competition-specific coverage of team fixtures
    # ---------------------------------------------------------------

    print()
    print("COMPETITION COVERAGE")

    for competition, fixtures in competition_results.items():

        if not fixtures:
            print(
                f"{competition}: 0 competition fixtures"
            )
            continue

        competition_keys_for_comp = {
            exact_key(fixture)
            for fixture in fixtures
        }

        matched = (
            team_keys
            & competition_keys_for_comp
        )

        print(
            f"{competition}: "
            f"{len(matched)}/{len(competition_keys_for_comp)} "
            f"({len(matched) / len(competition_keys_for_comp) * 100:.1f}%)"
        )

    # ---------------------------------------------------------------
    # Classify unmatched team fixtures
    # ---------------------------------------------------------------

    classifications = {
        category: []
        for category in CLASSIFICATIONS
    }

    competition_fixture_list = competition_fixtures

    for key in sorted(
        team_only,
        key=lambda value: value[0],
    ):
        fixture = team_index[key][0]

        classification, reason, matches = (
            classify_unmatched_fixture(
                fixture,
                competition_fixture_list,
            )
        )

        classifications[classification].append(
            (
                fixture,
                reason,
                matches,
            )
        )

    print_classification_report(
        classifications
    )

    # ---------------------------------------------------------------
    # Final status
    # ---------------------------------------------------------------

    print()
    print("=" * 70)
    print("DIAGNOSTIC RESULT")
    print("=" * 70)

    unclassified = len(
        classifications["GENUINE UNCLASSIFIED"]
    )

    print(
        f"Team-calendar fixtures analysed: {len(team_keys)}"
    )

    print(
        f"Competition-calendar fixtures analysed: "
        f"{len(competition_keys)}"
    )

    print(
        f"Exact overlaps: {len(overlap)}"
    )

    print(
        f"Unmatched team fixtures: {len(team_only)}"
    )

    print(
        f"Classified unmatched fixtures: "
        f"{len(team_only) - unclassified}"
    )

    print(
        f"Genuine unclassified: {unclassified}"
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

    if unclassified:
        print()
        print(
            "RESULT: Investigation required for "
            "genuine unclassified fixtures."
        )
    else:
        print()
        print(
            "RESULT: All unmatched team fixtures "
            "have an explicit diagnostic classification."
        )


if __name__ == "__main__":
    main()
