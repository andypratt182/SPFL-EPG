"""
sources/fixtur_es.py

Fixtur.es Scottish Premiership source adapter.

Downloads the Scottish Premiership calendar from Fixtur.es,
parses the ICS/iCalendar data, and converts it into the
source-independent fixture format used by the SPFL EPG.

This file is intentionally standalone.

It does NOT modify:
    fixtures.py
    data_layer.py
    generator.py
    data/fixtures.json

The adapter can therefore be tested safely before connecting
it to the existing EPG pipeline.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------
# Repository root
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

COMPETITION = "Scottish Premiership"

SEASON = "2026/27"

FEED_URL = (
    "https://ics.fixtur.es/v2/league/"
    "scottish-premier-league.ics"
)

REQUEST_TIMEOUT = 30

MAX_RETRIES = 3


# ---------------------------------------------------------
# Team name normalisation
# ---------------------------------------------------------

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

    name = name.strip()

    return TEAM_NAME_MAP.get(
        name,
        name,
    )


# ---------------------------------------------------------
# ICS text handling
# ---------------------------------------------------------

def unfold_ics_lines(text: str) -> list[str]:
    """
    Unfold RFC 5545 continuation lines.

    In an ICS file, a line beginning with a space or tab is a
    continuation of the previous line.
    """

    physical_lines = text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).split("\n")

    lines = []

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

    Example:

        DTSTART:20260809T123000Z

    returns:

        ("DTSTART", "20260809T123000Z")

    Parameters attached to a property are ignored.

    Example:

        DTSTART;TZID=Europe/London:20260809T133000

    becomes:

        ("DTSTART", "20260809T133000")
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


# ---------------------------------------------------------
# ICS datetime
# ---------------------------------------------------------

def parse_ics_datetime(
    value: str,
) -> datetime | None:
    """
    Convert an ICS datetime into a timezone-aware UTC datetime.

    Supports:

        20260809T123000Z

    and:

        20260809T123000

    For the latter, UTC is assumed because the Fixtur.es feed
    used by this project provides UTC fixture times.
    """

    if not value:
        return None

    value = value.strip()

    try:

        if value.endswith("Z"):

            dt = datetime.strptime(
                value,
                "%Y%m%dT%H%M%SZ",
            )

            return dt.replace(
                tzinfo=timezone.utc,
            )

        dt = datetime.strptime(
            value,
            "%Y%m%dT%H%M%S",
        )

        return dt.replace(
            tzinfo=timezone.utc,
        )

    except ValueError:

        return None


# ---------------------------------------------------------
# HTTP download
# ---------------------------------------------------------

def download_ics(
    url: str,
) -> str:
    """
    Download the Fixtur.es ICS feed.

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

    raise RuntimeError(
        "Unable to download Fixtur.es feed "
        f"after {MAX_RETRIES} attempts: "
        f"{last_error}"
    )


# ---------------------------------------------------------
# VEVENT parser
# ---------------------------------------------------------

def parse_events(
    ics_text: str,
) -> list[dict]:
    """
    Parse VEVENT records from the Fixtur.es ICS feed.
    """

    lines = unfold_ics_lines(
        ics_text
    )

    events = []

    current_event = None

    for line in lines:

        line = line.strip()

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

        # Keep the first occurrence of normal
        # properties but preserve the fields
        # required by this source.
        current_event[property_name] = value

    return events


# ---------------------------------------------------------
# Fixture parser
# ---------------------------------------------------------

def parse_fixture(
    event: dict,
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

    # -----------------------------------------------------
    # Fixtur.es summaries use:
    #
    #     Rangers - Hibernian
    #
    # and completed matches may use:
    #
    #     Rangers - Hibernian (2-1)
    # -----------------------------------------------------

    match = re.match(
        r"^(.*?)\s+-\s+(.*?)(?:\s+\((\d+)\s*-\s*(\d+)\))?$",
        summary,
    )

    if not match:
        print(
            f"WARNING: unable to parse fixture: "
            f"{summary}"
        )

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

    return {
        "source": "fixtur.es",

        "source_id": event.get(
            "UID",
            "",
        ),

        "home": home,

        "away": away,

        "kickoff": kickoff.isoformat(),

        "end": (
            end.isoformat()
            if end is not None
            else None
        ),

        "competition": COMPETITION,

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


# ---------------------------------------------------------
# Public source interface
# ---------------------------------------------------------

def get_fixtures() -> list[dict]:
    """
    Download and return all usable Scottish Premiership
    fixtures from Fixtur.es.
    """

    print(
        "=============================="
    )

    print(
        "FIXTUR.ES SOURCE"
    )

    print(
        "=============================="
    )

    print(
        f"Feed: {FEED_URL}"
    )

    print(
        f"Competition: {COMPETITION}"
    )

    print(
        f"Season: {SEASON}"
    )

    print(
        "=============================="
    )

    ics_text = download_ics(
        FEED_URL
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

    fixtures = []

    for event in events:

        fixture = parse_fixture(
            event
        )

        if fixture is not None:

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


# ---------------------------------------------------------
# Standalone test
# ---------------------------------------------------------

def main() -> int:
    """
    Standalone test.

    This does NOT write data/fixtures.json.
    It only downloads, parses and displays the feed.
    """

    try:

        fixtures = get_fixtures()

    except Exception as error:

        print()
        print(
            "ERROR:"
        )

        print(error)

        return 1

    print()
    print(
        "=============================="
    )

    print(
        "FIRST 20 FIXTURES"
    )

    print(
        "=============================="
    )

    for fixture in fixtures[:20]:

        score = ""

        if (
            fixture["home_score"]
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
            f"{score}"
        )

    print()
    print(
        "Fixtur.es test completed successfully."
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
  )
