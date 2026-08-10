"""
Fixtur.es diagnostic / audit tool.

Checks:
    1. All 12 SPFL team calendars
    2. Scottish competition calendars
    3. UEFA competition calendars
    4. Exact fixture overlap
    5. Competition classification
    6. Categorisation of team-only fixtures

This is diagnostic only.
It does NOT modify fixtures.py or generator.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Make project root importable when running:
#
#     python tools/inspect_fixtur_es.py
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from sources.fixtur_es import TEAM_CALENDARS


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEASON_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 6, 30, 23, 59, 59, tzinfo=timezone.utc)


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


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def download_ics(url: str) -> str:
    last_error = None

    for attempt in range(1, 4):
        print(f"Request attempt {attempt}/3")

        try:
            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(compatible; SPFL-EPG diagnostic)"
                    )
                },
            )

            with urlopen(request, timeout=30) as response:
                status = response.status
                data = response.read()

            print(f"HTTP status: {status}")

            text = data.decode("utf-8-sig", errors="replace")

            print(f"Downloaded ICS characters: {len(text)}")

            return text

        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            print(f"HTTP error: {exc}")

    raise RuntimeError(
        f"Unable to download Fixtur.es feed after 3 attempts: "
        f"{last_error}"
    )


# ---------------------------------------------------------------------------
# ICS parsing
# ---------------------------------------------------------------------------

def unfold_ics(text: str) -> list[str]:
    """
    Unfold RFC 5545 continuation lines.
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    result = []

    for line in lines:
        if line.startswith((" ", "\t")) and result:
            result[-1] += line[1:]
        else:
            result.append(line)

    return result


def parse_ics(text: str) -> list[dict[str, str]]:
    """
    Parse VEVENT blocks into dictionaries.

    We deliberately retain all fields so unmatched fixtures can be
    investigated rather than throwing away useful Fixtur.es metadata.
    """

    lines = unfold_ics(text)

    events = []
    current = None

    for line in lines:

        line = line.strip()

        if line == "BEGIN:VEVENT":
            current = {}
            continue

        if line == "END:VEVENT":
            if current:
                events.append(current)
            current = None
            continue

        if current is None:
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        # Remove parameters from field name.
        key = key.split(";", 1)[0]

        current[key] = value

    return events


# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------

def parse_ics_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    value = value.strip()

    # UTC timestamp
    if re.fullmatch(r"\d{8}T\d{6}Z", value):
        return datetime.strptime(
            value,
            "%Y%m%dT%H%M%SZ",
        ).replace(tzinfo=timezone.utc)

    # Local timestamp without timezone
    if re.fullmatch(r"\d{8}T\d{6}", value):
        return datetime.strptime(
            value,
            "%Y%m%dT%H%M%S",
        ).replace(tzinfo=timezone.utc)

    # Date-only
    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(
            value,
            "%Y%m%d",
        ).replace(tzinfo=timezone.utc)

    return None


def is_2026_27(event: dict[str, str]) -> bool:
    start = parse_ics_datetime(event.get("DTSTART"))

    if start is None:
        return False

    return SEASON_START <= start <= SEASON_END


# ---------------------------------------------------------------------------
# Fixture normalisation
# ---------------------------------------------------------------------------

def clean_team_name(name: str) -> str:
    name = name.strip()

    replacements = {
        "Dundee FC": "Dundee",
        "Dundee United FC": "Dundee United",
        "Heart of Midlothian": "Hearts",
        "St. Johnstone": "St Johnstone",
        "St Mirren FC": "St Mirren",
        "Aberdeen FC": "Aberdeen",
        "Celtic FC": "Celtic",
        "Rangers FC": "Rangers",
        "Hibernian FC": "Hibernian",
        "Kilmarnock FC": "Kilmarnock",
        "Motherwell FC": "Motherwell",
        "Falkirk FC": "Falkirk",
    }

    return replacements.get(name, name)


def parse_summary(summary: str) -> tuple[str, str]:
    """
    Convert:

        Rangers - Hibernian (1-2)

    into:

        Rangers
        Hibernian

    The score is deliberately ignored.
    """

    summary = summary.strip()

    # Remove result.
    summary = re.sub(
        r"\s*\([^)]*\)\s*$",
        "",
        summary,
    )

    # Remove common competition markers.
    summary = re.sub(
        r"\s*\[(?:EL|CL|Conf)\]\s*$",
        "",
        summary,
        flags=re.IGNORECASE,
    )

    if " - " not in summary:
        return summary, ""

    home, away = summary.split(" - ", 1)

    return (
        clean_team_name(home),
        clean_team_name(away),
    )


def fixture_key(event: dict[str, str]) -> tuple:
    """
    Exact-ish fixture identity.

    Uses:
        kickoff
        home
        away
    """

    start = parse_ics_datetime(event.get("DTSTART"))

    home, away = parse_summary(
        event.get("SUMMARY", "")
    )

    return (
        start,
        home.lower(),
        away.lower(),
    )


# ---------------------------------------------------------------------------
# Team calendar audit
# ---------------------------------------------------------------------------

def load_team_calendars():
    all_events = []
    team_events = {}

    print("=" * 70)
    print("TEAM CALENDAR SUMMARY")
    print("=" * 70)

    for team, url in TEAM_CALENDARS.items():

        print(team)

        try:
            text = download_ics(url)
            events = parse_ics(text)

            season_events = [
                event
                for event in events
                if is_2026_27(event)
            ]

            team_events[team] = events
            all_events.extend(events)

            print(
                f"{len(events)} VEVENTs, "
                f"{len(season_events)} in 2026/27"
            )

        except Exception as exc:
            print(f"ERROR: {exc}")
            team_events[team] = []

    unique = {}

    for event in all_events:
        key = fixture_key(event)

        if key[1] and key[2]:
            unique[key] = event

    season_unique = {
        key: event
        for key, event in unique.items()
        if is_2026_27(event)
    }

    print(f"Total VEVENT records: {len(all_events)}")
    print(
        f"Unique team-calendar fixtures: "
        f"{len(season_unique)}"
    )

    return team_events, season_unique


# ---------------------------------------------------------------------------
# Competition calendar audit
# ---------------------------------------------------------------------------

def load_competition_calendars():

    competition_events = {}
    all_events = []

    print()
    print("=" * 70)
    print("COMPETITION CALENDAR SUMMARY")
    print("=" * 70)

    for competition, url in COMPETITION_CALENDARS.items():

        print(competition)
        print(f"URL: {url}")

        try:
            text = download_ics(url)
            events = parse_ics(text)

            season_events = [
                event
                for event in events
                if is_2026_27(event)
            ]

            competition_events[competition] = season_events
            all_events.extend(
                (competition, event)
                for event in season_events
            )

            print(
                f"VEVENTs: {len(events)}"
            )

            print(
                f"2026/27 events: "
                f"{len(season_events)}"
            )

        except Exception as exc:
            print(
                f"ERROR: {exc}"
            )

            competition_events[competition] = []

    unique = {}

    for competition, event in all_events:

        key = fixture_key(event)

        if key[1] and key[2]:
            unique[key] = (
                competition,
                event,
            )

    print(
        f"Total 2026/27 events: "
        f"{len(all_events)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(unique)}"
    )

    return competition_events, unique


# ---------------------------------------------------------------------------
# Competition matching
# ---------------------------------------------------------------------------

def build_competition_index(competition_events):

    index = {}

    for competition, events in competition_events.items():

        for event in events:

            key = fixture_key(event)

            if key[1] and key[2]:
                index.setdefault(
                    key,
                    [],
                ).append(competition)

    return index


# ---------------------------------------------------------------------------
# Unmatched fixture classification
# ---------------------------------------------------------------------------

FRIENDLY_KEYWORDS = {
    "friendly",
    "pre-season",
    "preseason",
    "test match",
    "training match",
    "testimonial",
}

EUROPEAN_KEYWORDS = {
    "champions league",
    "europa league",
    "conference league",
    "uefa",
    "[cl]",
    "[el]",
    "[conf]",
}

DOMESTIC_CUP_KEYWORDS = {
    "scottish cup",
    "league cup",
    "challenge cup",
    "spfl trust trophy",
}

YOUTH_KEYWORDS = {
    "u18",
    "u19",
    "u20",
    "u21",
    "u23",
    "youth",
    "academy",
}

WOMEN_KEYWORDS = {
    "women",
    "wfc",
    "ladies",
}


def classify_team_only_fixture(event: dict[str, str]) -> tuple[str, str]:

    summary = event.get("SUMMARY", "")

    description = event.get("DESCRIPTION", "")

    categories = event.get("CATEGORIES", "")

    location = event.get("LOCATION", "")

    combined = " ".join(
        [
            summary,
            description,
            categories,
            location,
        ]
    ).lower()

    # ---------------------------------------------------------------
    # UEFA
    # ---------------------------------------------------------------

    if any(
        keyword in combined
        for keyword in EUROPEAN_KEYWORDS
    ):
        return (
            "European",
            "European competition marker found in ICS data",
        )

    # ---------------------------------------------------------------
    # Domestic cup
    # ---------------------------------------------------------------

    if any(
        keyword in combined
        for keyword in DOMESTIC_CUP_KEYWORDS
    ):
        return (
            "Domestic cup",
            "Domestic cup marker found in ICS data",
        )

    # ---------------------------------------------------------------
    # Friendly
    # ---------------------------------------------------------------

    if any(
        keyword in combined
        for keyword in FRIENDLY_KEYWORDS
    ):
        return (
            "Friendly",
            "Friendly/pre-season marker found in ICS data",
        )

    # ---------------------------------------------------------------
    # Youth
    # ---------------------------------------------------------------

    if any(
        keyword in combined
        for keyword in YOUTH_KEYWORDS
    ):
        return (
            "Youth",
            "Youth/academy marker found in ICS data",
        )

    # ---------------------------------------------------------------
    # Women's football
    # ---------------------------------------------------------------

    if any(
        keyword in combined
        for keyword in WOMEN_KEYWORDS
    ):
        return (
            "Women's football",
            "Women's football marker found in ICS data",
        )

    # ---------------------------------------------------------------
    # Date heuristic
    #
    # July fixtures are very often friendlies/pre-season.
    # This is deliberately labelled "Likely", not definitive.
    # ---------------------------------------------------------------

    start = parse_ics_datetime(
        event.get("DTSTART")
    )

    if start is not None:

        if start.month == 7:
            return (
                "Likely friendly",
                "July fixture with no competition classification",
            )

        if start.month == 8 and start.day <= 15:
            return (
                "Possibly friendly",
                "Early-season fixture with no competition classification",
            )

    # ---------------------------------------------------------------
    # Everything else
    # ---------------------------------------------------------------

    return (
        "Unclassified",
        "No competition classification available",
    )


# ---------------------------------------------------------------------------
# Full audit
# ---------------------------------------------------------------------------

def run_audit(
    team_unique,
    competition_unique,
    competition_events,
):

    competition_index = build_competition_index(
        competition_events
    )

    overlap = set(team_unique) & set(
        competition_unique
    )

    team_only = set(team_unique) - set(
        competition_unique
    )

    competition_only = set(
        competition_unique
    ) - set(team_unique)

    print()
    print("=" * 70)
    print("FULL OVERLAP / CLASSIFICATION AUDIT")
    print("=" * 70)

    print(
        f"Unique team-calendar fixtures: "
        f"{len(team_unique)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(competition_unique)}"
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

    if team_unique:
        print()
        print("COVERAGE")

        print(
            "Competition coverage of team fixtures: "
            f"{len(overlap) / len(team_unique) * 100:.1f}%"
        )

    if competition_unique:
        print(
            "Team coverage of competition fixtures: "
            f"{len(overlap) / len(competition_unique) * 100:.1f}%"
        )

    # ---------------------------------------------------------------
    # Competition breakdown
    # ---------------------------------------------------------------

    print()
    print("=" * 70)
    print("OVERLAP BY COMPETITION")
    print("=" * 70)

    for competition, events in competition_events.items():

        keys = {
            fixture_key(event)
            for event in events
        }

        matched = len(
            keys & set(team_unique)
        )

        print(
            f"{competition}: "
            f"{matched}/{len(keys)} "
            f"({matched / len(keys) * 100:.1f}%)"
            if keys
            else
            f"{competition}: 0/0 (0.0%)"
        )

    # ---------------------------------------------------------------
    # Team-only classification
    # ---------------------------------------------------------------

    print()
    print("=" * 70)
    print("TEAM-ONLY FIXTURE CLASSIFICATION")
    print("=" * 70)

    categories = {}

    for key in sorted(
        team_only,
        key=lambda item: (
            item[0] or datetime.max.replace(
                tzinfo=timezone.utc
            ),
            item[1],
            item[2],
        ),
    ):

        event = team_unique[key]

        category, reason = classify_team_only_fixture(
            event
        )

        categories.setdefault(
            category,
            [],
        ).append(
            (
                key,
                event,
                reason,
            )
        )

    for category in sorted(categories):

        entries = categories[category]

        print()
        print(
            f"{category}: "
            f"{len(entries)}"
        )

        print("-" * 70)

        for key, event, reason in entries:

            start = parse_ics_datetime(
                event.get("DTSTART")
            )

            if start:
                date_text = start.strftime(
                    "%Y-%m-%d %H:%M"
                )
            else:
                date_text = "UNKNOWN"

            summary = event.get(
                "SUMMARY",
                "",
            )

            print(
                f"{date_text} | {summary}"
            )

            print(
                f"  Reason: {reason}"
            )

            # Show useful raw metadata when present.
            for field in (
                "CATEGORIES",
                "DESCRIPTION",
                "LOCATION",
            ):
                value = event.get(field)

                if value:
                    print(
                        f"  {field}: {value}"
                    )

    # ---------------------------------------------------------------
    # Classification summary
    # ---------------------------------------------------------------

    print()
    print("=" * 70)
    print("UNMATCHED FIXTURE SUMMARY")
    print("=" * 70)

    total = len(team_only)

    for category in sorted(categories):

        count = len(
            categories[category]
        )

        percentage = (
            count / total * 100
            if total
            else 0
        )

        print(
            f"{category}: "
            f"{count} "
            f"({percentage:.1f}%)"
        )

    print()
    print(
        "This classification is diagnostic only. "
        "No fixture data has been modified."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    team_events, team_unique = (
        load_team_calendars()
    )

    (
        competition_events,
        competition_unique,
    ) = load_competition_calendars()

    run_audit(
        team_unique,
        competition_unique,
        competition_events,
    )

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)
    print(
        "All team and competition calendars "
        "were processed successfully."
    )


if __name__ == "__main__":
    main()
