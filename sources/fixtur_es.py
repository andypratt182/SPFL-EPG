"""
sources/fixtur_es.py

Generic Fixtur.es SPFL team-calendar importer.

Downloads the individual Fixtur.es ICS calendars for all
12 SPFL teams and converts them into the source-independent
fixture format used by the SPFL EPG.

The team calendars are used instead of the Scottish
Premiership league calendar because team calendars can contain
domestic and European fixtures.

This module does NOT modify:
    fixtures.py
    generator.py
    xmltv.py
    data/football.db
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# =========================================================
# Configuration
# =========================================================

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2

SEASON = "2026/27"


# =========================================================
# Fixtur.es team calendars
# =========================================================
#
# These slugs have been checked against the actual Fixtur.es
# team pages.
#
# =========================================================

TEAM_CALENDARS = {
    "Rangers": "rangers",
    "Celtic": "celtic",
    "Aberdeen": "aberdeen",
    "Dundee": "dundee-fc",
    "Dundee United": "dundee-united",
    "Hearts": "heart-of-midlothian",
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


# =========================================================
# Team name normalisation
# =========================================================

TEAM_NAME_MAP = {
    "Heart of Midlothian": "Hearts",
    "Hearts FC": "Hearts",

    "St. Johnstone": "St Johnstone",
    "St Johnstone FC": "St Johnstone",

    "St. Mirren": "St Mirren",
    "St Mirren FC": "St Mirren",

    "Dundee United FC": "Dundee United",
    "Dundee FC": "Dundee",

    "Celtic FC": "Celtic",
    "Rangers FC": "Rangers",

    "Aberdeen FC": "Aberdeen",
    "Hibernian FC": "Hibernian",
    "Kilmarnock FC": "Kilmarnock",
    "Motherwell FC": "Motherwell",
    "Falkirk FC": "Falkirk",
}


def normalise_team_name(name: str) -> str:
    """
    Convert Fixtur.es team names into the naming convention
    used by the SPFL EPG.
    """

    if not name:
        return ""

    name = name.strip()

    if name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[name]

    name = re.sub(
        r"\s+Football Club$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+FC$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    return TEAM_NAME_MAP.get(
        name,
        name,
    )


# =========================================================
# ICS handling
# =========================================================

def unfold_ics_lines(text: str) -> list[str]:
    """
    Unfold RFC 5545 continuation lines.
    """

    physical_lines = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    )

    lines: list[str] = []

    for line in physical_lines:

        if (
            line.startswith(" ")
            or line.startswith("\t")
        ):

            if lines:
                lines[-1] += line[1:]

        else:
            lines.append(line)

    return lines


def parse_property(line: str) -> tuple[str, str]:
    """
    Parse an ICS property.

    Parameters attached to the property are ignored.
    """

    if ":" not in line:
        return "", ""

    property_part, value = line.split(
        ":",
        1,
    )

    property_name = property_part.split(
        ";",
        1,
    )[0].upper()

    return property_name, value


# =========================================================
# ICS datetime
# =========================================================

def parse_ics_datetime(
    value: str,
) -> datetime | None:
    """
    Convert an ICS datetime into a timezone-aware UTC
    datetime.

    Fixtur.es provides UTC timestamps in its ICS feeds.
    """

    if not value:
        return None

    value = value.strip()

    if re.fullmatch(r"\d{8}", value):

        try:

            dt = datetime.strptime(
                value,
                "%Y%m%d",
            )

            return dt.replace(
                tzinfo=timezone.utc
            )

        except ValueError:
            return None

    try:

        if value.endswith("Z"):

            dt = datetime.strptime(
                value,
                "%Y%m%dT%H%M%SZ",
            )

            return dt.replace(
                tzinfo=timezone.utc
            )

        dt = datetime.strptime(
            value,
            "%Y%m%dT%H%M%S",
        )

        return dt.replace(
            tzinfo=timezone.utc
        )

    except ValueError:

        return None


# =========================================================
# HTTP download
# =========================================================

def download_ics(
    url: str,
) -> str:
    """
    Download a Fixtur.es ICS feed.

    Retries temporary failures before raising an error.
    """

    headers = {
        "User-Agent": "SPFL-EPG/1.0",
        "Accept": "text/calendar,text/plain,*/*",
    }

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        print(
            f"Request attempt "
            f"{attempt}/{MAX_RETRIES}"
        )

        request = Request(
            url,
            headers=headers,
        )

        try:

            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:

                status = response.status

                print(
                    f"HTTP status: {status}"
                )

                body = response.read()

            return body.decode(
                "utf-8-sig",
                errors="replace",
            )

        except HTTPError as error:

            last_error = error

            print(
                f"HTTP error: {error.code}"
            )

        except URLError as error:

            last_error = error

            print(
                f"URL error: {error.reason}"
            )

        except TimeoutError as error:

            last_error = error

            print(
                "Request timed out."
            )

        except Exception as error:

            last_error = error

            print(
                f"Unexpected error: {error}"
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    raise RuntimeError(
        "Unable to download Fixtur.es feed "
        f"after {MAX_RETRIES} attempts: "
        f"{last_error}"
    )


# =========================================================
# VEVENT parser
# =========================================================

def parse_events(
    ics_text: str,
) -> list[dict]:
    """
    Parse VEVENT records from an ICS feed.
    """

    lines = unfold_ics_lines(
        ics_text
    )

    events: list[dict] = []

    current_event: dict | None = None

    for raw_line in lines:

        line = raw_line.strip()

        if line == "BEGIN:VEVENT":

            current_event = {}

            continue

        if line == "END:VEVENT":

            if current_event is not None:

                events.append(
                    current_event
                )

            current_event = None

            continue

        if current_event is None:
            continue

        property_name, value = parse_property(
            line
        )

        if not property_name:
            continue

        current_event[property_name] = value

    return events


# =========================================================
# Match summary
# =========================================================

def parse_match_summary(
    summary: str,
) -> tuple[str, str, int | None, int | None] | None:
    """
    Parse a Fixtur.es match summary.

    Examples:

        Rangers - Celtic

        Rangers - Celtic (2-1)
    """

    if not summary:
        return None

    summary = summary.strip()

    match = re.match(
        r"^(.*?)\s+-\s+(.*?)"
        r"(?:\s+\((\d+)\s*-\s*(\d+)\))?$",
        summary,
    )

    if not match:
        return None

    home = normalise_team_name(
        match.group(1)
    )

    away = normalise_team_name(
        match.group(2)
    )

    home_score = None
    away_score = None

    if match.group(3) is not None:

        home_score = int(
            match.group(3)
        )

        away_score = int(
            match.group(4)
        )

    if not home or not away:
        return None

    return (
        home,
        away,
        home_score,
        away_score,
    )


# =========================================================
# Competition extraction
# =========================================================

def extract_competition(
    event: dict,
) -> str:
    """
    Extract competition information from an ICS event.

    Fixtur.es can expose competition information through
    different properties depending on the calendar version.
    """

    candidates = (
        event.get("CATEGORIES"),
        event.get("X-CATEGORY"),
        event.get("X-COMPETITION"),
        event.get("COMPETITION"),
    )

    for value in candidates:

        if not value:
            continue

        value = value.strip()

        if value:
            return value

    return "Unknown"


# =========================================================
# Fixture parser
# =========================================================

def parse_fixture(
    event: dict,
    source_team: str,
) -> dict | None:
    """
    Convert one Fixtur.es VEVENT into the common
    SPFL EPG fixture format.
    """

    summary = event.get(
        "SUMMARY",
        "",
    ).strip()

    if not summary:
        return None

    kickoff = parse_ics_datetime(
        event.get(
            "DTSTART",
            "",
        )
    )

    if kickoff is None:
        return None

    end = parse_ics_datetime(
        event.get(
            "DTEND",
            "",
        )
    )

    parsed = parse_match_summary(
        summary
    )

    if parsed is None:

        print(
            "WARNING: unable to parse fixture: "
            f"{summary}"
        )

        return None

    (
        home,
        away,
        home_score,
        away_score,
    ) = parsed

    return {
        "source": "fixtur.es",

        "source_id": event.get(
            "UID",
            "",
        ),

        "source_team": source_team,

        "home": home,

        "away": away,

        "kickoff": kickoff.isoformat(),

        "end": (
            end.isoformat()
            if end is not None
            else None
        ),

        "competition": extract_competition(
            event
        ),

        "season": SEASON,

        "status": event.get(
            "STATUS",
            "CONFIRMED",
        ),

        "home_score": home_score,

        "away_score": away_score,

        "last_modified": event.get(
            "LAST-MODIFIED",
            "",
        ),

        "sequence": event.get(
            "SEQUENCE",
            "0",
        ),

        "created": event.get(
            "CREATED",
            "",
        ),
    }


# =========================================================
# Single team calendar
# =========================================================

def get_team_fixtures(
    team_name: str,
) -> list[dict]:
    """
    Download and parse one team's Fixtur.es calendar.
    """

    if team_name not in TEAM_CALENDARS:

        raise ValueError(
            f"Unknown SPFL team: {team_name}"
        )

    slug = TEAM_CALENDARS[
        team_name
    ]

    url = build_team_feed_url(
        slug
    )

    print()
    print(
        "------------------------------"
    )

    print(
        f"TEAM: {team_name}"
    )

    print(
        f"Feed: {url}"
    )

    print(
        "------------------------------"
    )

    ics_text = download_ics(
        url
    )

    print(
        f"Downloaded ICS characters: "
        f"{len(ics_text)}"
    )

    events = parse_events(
        ics_text
    )

    print(
        f"VEVENT records found: "
        f"{len(events)}"
    )

    fixtures: list[dict] = []

    for event in events:

        fixture = parse_fixture(
            event,
            team_name,
        )

        if fixture is None:
            continue

        fixtures.append(
            fixture
        )

    fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    print(
        f"Usable fixtures: "
        f"{len(fixtures)}"
    )

    return fixtures


# =========================================================
# All SPFL calendars
# =========================================================

def get_all_fixtures() -> list[dict]:
    """
    Download all 12 SPFL team calendars.

    Fixtures are combined into one dataset and duplicates
    are removed.
    """

    print()
    print(
        "=========================================="
    )

    print(
        "FIXTUR.ES SPFL TEAM-CALENDAR SOURCE"
    )

    print(
        "=========================================="
    )

    print(
        f"Team calendars: "
        f"{len(TEAM_CALENDARS)}"
    )

    print(
        "=========================================="
    )

    all_fixtures: list[dict] = []

    seen: set[str] = set()

    successful_teams = 0
    failed_teams = 0

    for team_name in TEAM_CALENDARS:

        try:

            fixtures = get_team_fixtures(
                team_name
            )

            successful_teams += 1

        except Exception as error:

            failed_teams += 1

            print()
            print(
                f"ERROR loading "
                f"{team_name}: {error}"
            )

            continue

        for fixture in fixtures:

            source_id = fixture.get(
                "source_id",
                "",
            )

            if source_id:

                dedupe_key = (
                    f"uid:{source_id}"
                )

            else:

                dedupe_key = (
                    f"{fixture.get('home', '')}|"
                    f"{fixture.get('away', '')}|"
                    f"{fixture.get('kickoff', '')}"
                )

            if dedupe_key in seen:
                continue

            seen.add(
                dedupe_key
            )

            all_fixtures.append(
                fixture
            )

    all_fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    print()
    print(
        "=========================================="
    )

    print(
        "FIXTUR.ES IMPORT COMPLETE"
    )

    print(
        "=========================================="
    )

    print(
        f"Successful team feeds: "
        f"{successful_teams}/"
        f"{len(TEAM_CALENDARS)}"
    )

    print(
        f"Failed team feeds: "
        f"{failed_teams}"
    )

    print(
        f"Unique fixtures: "
        f"{len(all_fixtures)}"
    )

    print(
        "=========================================="
    )

    return all_fixtures


# =========================================================
# Backwards-compatible interface
# =========================================================

def get_fixtures() -> list[dict]:
    """
    Backwards-compatible alias for get_all_fixtures().
    """

    return get_all_fixtures()


# =========================================================
# Standalone test
# =========================================================

def main() -> int:
    """
    Standalone importer test.

    Does not write any repository data.
    """

    try:

        fixtures = get_all_fixtures()

    except Exception as error:

        print()
        print(
            "ERROR:"
        )

        print(error)

        return 1

    print()
    print(
        "=========================================="
    )

    print(
        "FIRST 30 FIXTURES"
    )

    print(
        "=========================================="
    )

    for fixture in fixtures[:30]:

        score = ""

        if (
            fixture.get("home_score")
            is not None
        ):

            score = (
                f" "
                f"({fixture['home_score']}"
                f"-"
                f"{fixture['away_score']})"
            )

        print(
            f"{fixture['kickoff']} | "
            f"{fixture['home']} - "
            f"{fixture['away']}"
            f"{score} | "
            f"{fixture['competition']}"
        )

    print()
    print(
        "Fixtur.es SPFL importer test "
        "completed successfully."
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
