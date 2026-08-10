"""
Fixtur.es fixture source.

This module provides a normalised fixture dataset for the SPFL EPG.

Architecture
------------
1. Team calendars provide the complete fixture universe for the
   12 SPFL teams, including league, cup and European fixtures.
2. Competition calendars provide authoritative competition
   classification where Fixtur.es exposes a competition feed.
3. Fixtures are deduplicated across all sources.
4. Competition calendars take priority for competition assignment.
5. Team calendars remain the fallback source for fixtures which are
   not present in a competition calendar.

The public entry point expected by fixtures.py is:

    get_all_fixtures()
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 3
RETRY_DELAY = 2


# ============================================================
# SPFL TEAM CALENDARS
# ============================================================

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


# ============================================================
# COMPETITION CALENDARS
# ============================================================
#
# These are competition feeds which have been confirmed during
# the Fixtur.es investigation.
#
# The Scottish League Cup is deliberately NOT represented here.
#
# Fixtur.es currently exposes a "League Cup" calendar, but that
# calendar is the English EFL League Cup, not the Scottish
# League Cup. We therefore must not attach it to SPFL fixtures.
#
# Scottish League Cup fixtures appearing in team calendars will
# remain available through the team-calendar layer.
# ============================================================

COMPETITION_CALENDARS = {
    "Scottish Premiership": (
        "https://ics.fixtur.es/v2/league/"
        "scottish-premier-league.ics"
    ),

    "Scottish Championship": (
        "https://ics.fixtur.es/v2/league/"
        "scottish-championship.ics"
    ),

    "Scottish League One": (
        "https://ics.fixtur.es/v2/league/"
        "scottish-league-one.ics"
    ),

    "Scottish League Two": (
        "https://ics.fixtur.es/v2/league/"
        "scottish-league-two.ics"
    ),

    "Scottish Cup": (
        "https://ics.fixtur.es/v2/league/"
        "scottish-cup.ics"
    ),
}


# ============================================================
# OPTIONAL EUROPEAN COMPETITION CALENDARS
# ============================================================
#
# These feeds contain European competition fixtures for all
# clubs, so they are filtered to the 12 SPFL teams.
#
# If a feed is unavailable, the importer simply continues.
# Team calendars still provide the fixture.
# ============================================================

EUROPEAN_COMPETITION_CALENDARS = {
    "UEFA Champions League": (
        "https://ics.fixtur.es/v2/league/"
        "champions-league.ics"
    ),

    "UEFA Europa League": (
        "https://ics.fixtur.es/v2/league/"
        "europa-league.ics"
    ),

    "UEFA Conference League": (
        "https://ics.fixtur.es/v2/league/"
        "uefa-conference-league.ics"
    ),
}


# ============================================================
# TEAM NAME NORMALISATION
# ============================================================

TEAM_ALIASES = {
    "Rangers FC": "Rangers",
    "Rangers": "Rangers",

    "Celtic FC": "Celtic",
    "Celtic": "Celtic",

    "Aberdeen FC": "Aberdeen",
    "Aberdeen": "Aberdeen",

    "Dundee FC": "Dundee",
    "Dundee": "Dundee",

    "Dundee United FC": "Dundee United",
    "Dundee United": "Dundee United",

    "Heart of Midlothian": "Hearts",
    "Hearts": "Hearts",
    "Heart of Midlothian FC": "Hearts",

    "Hibernian FC": "Hibernian",
    "Hibernian": "Hibernian",

    "Kilmarnock FC": "Kilmarnock",
    "Kilmarnock": "Kilmarnock",

    "Motherwell FC": "Motherwell",
    "Motherwell": "Motherwell",

    "Falkirk FC": "Falkirk",
    "Falkirk": "Falkirk",

    "St Johnstone FC": "St Johnstone",
    "St Johnstone": "St Johnstone",

    "St Mirren FC": "St Mirren",
    "St Mirren": "St Mirren",
}


ALLOWED_TEAMS = set(
    TEAM_CALENDARS.keys()
)


# ============================================================
# HTTP
# ============================================================

def download_ics(url: str) -> str:
    """
    Download an ICS feed with retry handling.
    """

    last_error = None

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1,
    ):

        print(
            f"Request attempt {attempt}/{MAX_ATTEMPTS}"
        )

        try:

            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "SPFL-EPG/1.0 "
                        "(Fixtur.es importer)"
                    )
                },
            )

            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:

                status = response.status

                data = response.read()

            print(
                f"HTTP status: {status}"
            )

            text = data.decode(
                "utf-8",
                errors="replace",
            )

            print(
                f"Downloaded ICS characters: "
                f"{len(text)}"
            )

            return text

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

        except Exception as error:

            last_error = error

            print(
                f"Request error: {error}"
            )

        if attempt < MAX_ATTEMPTS:
            time.sleep(
                RETRY_DELAY
            )

    raise RuntimeError(
        "Unable to download Fixtur.es feed "
        f"after {MAX_ATTEMPTS} attempts: "
        f"{last_error}"
    )


# ============================================================
# ICS PARSING
# ============================================================

def unfold_ics(text: str) -> list[str]:
    """
    Unfold RFC-style ICS continuation lines.
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

        if (
            line.startswith(" ")
            or line.startswith("\t")
        ) and unfolded:

            unfolded[-1] += line[1:]

        else:

            unfolded.append(line)

    return unfolded


def parse_events(ics_text: str) -> list[dict]:
    """
    Parse VEVENT records into dictionaries.

    Every raw ICS property is retained.
    """

    lines = unfold_ics(
        ics_text
    )

    events = []
    current = None

    for line in lines:

        if line == "BEGIN:VEVENT":

            current = {}

            continue

        if line == "END:VEVENT":

            if current:
                events.append(
                    current
                )

            current = None

            continue

        if current is None:
            continue

        if ":" not in line:
            continue

        property_name, value = line.split(
            ":",
            1,
        )

        # Parameters are stripped from the key.
        key = property_name.split(
            ";",
            1,
        )[0].upper()

        current[key] = value

    print(
        f"VEVENT records found: "
        f"{len(events)}"
    )

    return events


# ============================================================
# TEAM NAME HANDLING
# ============================================================

def normalise_team_name(
    name: str | None,
) -> str | None:

    if not name:
        return None

    cleaned = (
        name
        .replace(
            "\u00a0",
            " ",
        )
        .strip()
    )

    return TEAM_ALIASES.get(
        cleaned,
        cleaned,
    )


def is_allowed_team(
    name: str | None,
) -> bool:

    normalised = normalise_team_name(
        name
    )

    return normalised in ALLOWED_TEAMS


# ============================================================
# SUMMARY PARSING
# ============================================================

RESULT_PATTERN = re.compile(
    r"^(.*?)\s+-\s+(.*?)\s+\((\d+)-(\d+)\)$"
)


FIXTURE_PATTERN = re.compile(
    r"^(.*?)\s+-\s+(.*?)$"
)


def parse_summary(
    summary: str | None,
):
    """
    Parse:

        Rangers - Celtic (2-1)

    or:

        Rangers - Celtic

    Returns:

        home,
        away,
        home_score,
        away_score
    """

    if not summary:
        return (
            None,
            None,
            None,
            None,
        )

    summary = summary.strip()

    result_match = RESULT_PATTERN.match(
        summary
    )

    if result_match:

        home = result_match.group(
            1
        ).strip()

        away = result_match.group(
            2
        ).strip()

        home_score = int(
            result_match.group(3)
        )

        away_score = int(
            result_match.group(4)
        )

        return (
            home,
            away,
            home_score,
            away_score,
        )

    fixture_match = FIXTURE_PATTERN.match(
        summary
    )

    if fixture_match:

        return (
            fixture_match.group(1).strip(),
            fixture_match.group(2).strip(),
            None,
            None,
        )

    return (
        None,
        None,
        None,
        None,
    )


# ============================================================
# DATETIME
# ============================================================

def parse_ics_datetime(
    value: str | None,
) -> datetime | None:

    if not value:
        return None

    value = value.strip()

    formats = (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
        "%Y%m%d",
    )

    for fmt in formats:

        try:

            parsed = datetime.strptime(
                value,
                fmt,
            )

            if value.endswith("Z"):

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        except ValueError:
            continue

    return None


# ============================================================
# FIXTURE NORMALISATION
# ============================================================

def event_to_fixture(
    event: dict,
    source: str,
    competition: str | None = None,
):
    """
    Convert a raw ICS event into the common fixture format.
    """

    summary = event.get(
        "SUMMARY",
        "",
    )

    (
        home,
        away,
        home_score,
        away_score,
    ) = parse_summary(
        summary
    )

    if not home or not away:
        return None

    home = normalise_team_name(
        home
    )

    away = normalise_team_name(
        away
    )

    kickoff = parse_ics_datetime(
        event.get("DTSTART")
    )

    if not kickoff:
        return None

    fixture = {
        "source": source,

        "source_id": event.get(
            "UID"
        ),

        "kickoff": kickoff,

        "home": home,

        "away": away,

        "home_score": home_score,

        "away_score": away_score,

        "competition": competition,

        "status": event.get(
            "STATUS"
        ),

        "summary": summary,

        "description": event.get(
            "DESCRIPTION"
        ),
    }

    return fixture


# ============================================================
# FIXTURE SIGNATURE
# ============================================================

def fixture_signature(
    fixture: dict,
):
    """
    Stable cross-source identity.

    UID values differ between team and competition feeds,
    therefore UID alone cannot be used for deduplication.
    """

    kickoff = fixture.get(
        "kickoff"
    )

    if isinstance(
        kickoff,
        datetime,
    ):

        kickoff_key = kickoff.replace(
            second=0,
            microsecond=0,
        ).isoformat()

    else:

        kickoff_key = str(
            kickoff
        )

    return (
        kickoff_key,
        fixture.get("home"),
        fixture.get("away"),
    )


# ============================================================
# TEAM CALENDAR LOADER
# ============================================================

def load_team_fixtures():

    fixtures = []

    print()
    print("=" * 70)
    print("LOADING SPFL TEAM CALENDARS")
    print("=" * 70)

    successful = 0
    failed = 0

    for team_name, slug in (
        TEAM_CALENDARS.items()
    ):

        url = (
            "https://ics.fixtur.es/v2/team/"
            f"{slug}.ics"
        )

        print()
        print(
            f"TEAM: {team_name}"
        )

        print(
            f"URL: {url}"
        )

        try:

            ics = download_ics(
                url
            )

            events = parse_events(
                ics
            )

            team_fixture_count = 0

            for event in events:

                fixture = event_to_fixture(
                    event,
                    source="fixtur.es-team",
                )

                if not fixture:
                    continue

                # Team feeds contain fixtures involving
                # the selected team, so retain only the
                # target SPFL team universe.
                if not (
                    is_allowed_team(
                        fixture["home"]
                    )
                    or is_allowed_team(
                        fixture["away"]
                    )
                ):
                    continue

                # Ensure the target team names are normalised.
                fixture["home"] = normalise_team_name(
                    fixture["home"]
                )

                fixture["away"] = normalise_team_name(
                    fixture["away"]
                )

                # The team calendar itself does not tell
                # us the competition.
                fixture["competition"] = None

                fixture[
                    "team_calendar"
                ] = team_name

                fixtures.append(
                    fixture
                )

                team_fixture_count += 1

            print(
                f"Usable fixtures: "
                f"{team_fixture_count}"
            )

            successful += 1

        except Exception as error:

            failed += 1

            print(
                f"ERROR loading "
                f"{team_name}: {error}"
            )

    print()
    print(
        f"Successful team feeds: "
        f"{successful}/{len(TEAM_CALENDARS)}"
    )

    print(
        f"Failed team feeds: "
        f"{failed}"
    )

    return fixtures


# ============================================================
# COMPETITION CALENDAR LOADER
# ============================================================

def load_competition_fixtures(
    calendars: dict[str, str],
):

    fixtures = []

    print()
    print("=" * 70)
    print("LOADING COMPETITION CALENDARS")
    print("=" * 70)

    for competition, url in (
        calendars.items()
    ):

        print()
        print(
            f"COMPETITION: {competition}"
        )

        print(
            f"URL: {url}"
        )

        try:

            ics = download_ics(
                url
            )

            events = parse_events(
                ics
            )

            usable = 0

            for event in events:

                fixture = event_to_fixture(
                    event,
                    source="fixtur.es-competition",
                    competition=competition,
                )

                if not fixture:
                    continue

                # Competition calendars contain many clubs.
                # Keep only fixtures involving our SPFL teams.
                if not (
                    is_allowed_team(
                        fixture["home"]
                    )
                    or is_allowed_team(
                        fixture["away"]
                    )
                ):
                    continue

                fixture["home"] = (
                    normalise_team_name(
                        fixture["home"]
                    )
                )

                fixture["away"] = (
                    normalise_team_name(
                        fixture["away"]
                    )
                )

                fixtures.append(
                    fixture
                )

                usable += 1

            print(
                f"VEVENT records: "
                f"{len(events)}"
            )

            print(
                f"SPFL fixtures: "
                f"{usable}"
            )

        except Exception as error:

            print(
                f"ERROR loading "
                f"{competition}: {error}"
            )

    return fixtures


# ============================================================
# DEDUPLICATION AND MERGING
# ============================================================

def merge_fixture_sources(
    team_fixtures,
    competition_fixtures,
):

    merged = {}

    # --------------------------------------------------------
    # Team calendars first.
    # --------------------------------------------------------

    for fixture in team_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature not in merged:

            merged[signature] = dict(
                fixture
            )

        else:

            existing = merged[
                signature
            ]

            # Prefer a score if one exists.
            if (
                existing.get("home_score")
                is None
                and fixture.get("home_score")
                is not None
            ):

                existing["home_score"] = (
                    fixture["home_score"]
                )

                existing["away_score"] = (
                    fixture["away_score"]
                )

    # --------------------------------------------------------
    # Competition feeds enrich and classify.
    # --------------------------------------------------------

    for fixture in competition_fixtures:

        signature = fixture_signature(
            fixture
        )

        if signature not in merged:

            merged[signature] = dict(
                fixture
            )

            continue

        existing = merged[
            signature
        ]

        # Competition calendar wins for competition.
        if fixture.get(
            "competition"
        ):

            existing[
                "competition"
            ] = fixture[
                "competition"
            ]

        # Competition source can also provide a result.
        if (
            existing.get("home_score")
            is None
            and fixture.get("home_score")
            is not None
        ):

            existing["home_score"] = (
                fixture["home_score"]
            )

            existing["away_score"] = (
                fixture["away_score"]
            )

        # Keep source IDs from both systems.
        existing.setdefault(
            "source_ids",
            [],
        )

        source_id = fixture.get(
            "source_id"
        )

        if (
            source_id
            and source_id
            not in existing["source_ids"]
        ):

            existing[
                "source_ids"
            ].append(
                source_id
            )

    return list(
        merged.values()
    )


# ============================================================
# COMPETITION FALLBACKS
# ============================================================

def infer_fallback_competition(
    fixture: dict,
):
    """
    Deliberately conservative.

    We do NOT attempt to guess Cup/European competitions
    from the two teams.

    A fixture remains None if Fixtur.es has not supplied a
    competition calendar classification for it.
    """

    competition = fixture.get(
        "competition"
    )

    if competition:
        return competition

    return None


# ============================================================
# SORTING
# ============================================================

def fixture_sort_key(
    fixture: dict,
):

    kickoff = fixture.get(
        "kickoff"
    )

    if isinstance(
        kickoff,
        datetime,
    ):
        return kickoff

    return datetime.max


# ============================================================
# PUBLIC API
# ============================================================

def get_all_fixtures():

    print()
    print("=" * 70)
    print("FIXTUR.ES IMPORT")
    print("=" * 70)

    team_fixtures = (
        load_team_fixtures()
    )

    competition_fixtures = (
        load_competition_fixtures(
            COMPETITION_CALENDARS
        )
    )

    european_fixtures = (
        load_competition_fixtures(
            EUROPEAN_COMPETITION_CALENDARS
        )
    )

    competition_fixtures.extend(
        european_fixtures
    )

    merged = merge_fixture_sources(
        team_fixtures,
        competition_fixtures,
    )

    for fixture in merged:

        fixture[
            "competition"
        ] = infer_fallback_competition(
            fixture
        )

    merged.sort(
        key=fixture_sort_key
    )

    print()
    print("=" * 70)
    print("FIXTUR.ES IMPORT COMPLETE")
    print("=" * 70)

    print(
        f"Team-calendar records: "
        f"{len(team_fixtures)}"
    )

    print(
        f"Competition-calendar records: "
        f"{len(competition_fixtures)}"
    )

    print(
        f"Unique fixtures: "
        f"{len(merged)}"
    )

    competition_counts = {}

    for fixture in merged:

        competition = (
            fixture.get(
                "competition"
            )
            or "Unknown"
        )

        competition_counts[
            competition
        ] = (
            competition_counts.get(
                competition,
                0,
            )
            + 1
        )

    print()
    print(
        "Competition breakdown:"
    )

    for competition, count in sorted(
        competition_counts.items()
    ):

        print(
            f"  {competition}: "
            f"{count}"
        )

    return merged


# ============================================================
# BACKWARDS-COMPATIBLE ALIAS
# ============================================================

def build_fixtures():
    """
    Compatibility alias for older code.
    """

    return get_all_fixtures()
