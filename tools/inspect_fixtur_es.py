from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import sys
import re


# ---------------------------------------------------------------------------
# Make the repository root importable when this script is run directly
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ---------------------------------------------------------------------------
# Import the existing 12 team-calendar definitions
#
# IMPORTANT:
# We deliberately do not modify or recreate these URLs here.
# The working TEAM_CALENDARS definitions in sources/fixtur_es.py remain
# authoritative.
# ---------------------------------------------------------------------------

from sources.fixtur_es import TEAM_CALENDARS


# ---------------------------------------------------------------------------
# Competition calendars
#
# Existing Scottish competition calendars plus the three UEFA calendars.
#
# These are used ONLY by this diagnostic at this stage.
# fixtures.py and generator.py are not changed.
# ---------------------------------------------------------------------------

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

    # UEFA competitions
    "Champions League":
        "https://ics.fixtur.es/v2/league/champions-league.ics",

    "Europa League":
        "https://ics.fixtur.es/v2/league/europa-league.ics",

    "UEFA Conference League":
        "https://ics.fixtur.es/v2/league/uefa-conference-league.ics",
}


SEASON_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 7, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def download_ics(url):
    request = Request(
        url,
        headers={
            "User-Agent": "SPFL-EPG Fixtur.es Diagnostic/1.0",
        },
    )

    last_error = None

    for attempt in range(1, 4):
        print()
        print(f"Request attempt {attempt}/3")

        try:
            with urlopen(request, timeout=30) as response:
                status = response.status
                data = response.read()

            text = data.decode("utf-8-sig", errors="replace")

            print(f"HTTP status: {status}")
            print(f"Downloaded ICS characters: {len(text)}")

            return text

        except HTTPError as exc:
            last_error = exc
            print(f"HTTP error: {exc.code}")

        except URLError as exc:
            last_error = exc
            print(f"URL error: {exc.reason}")

        except Exception as exc:
            last_error = exc
            print(f"ERROR: {type(exc).__name__}: {exc}")

    raise RuntimeError(
        f"Unable to download Fixtur.es feed after 3 attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# ICS parsing
# ---------------------------------------------------------------------------

def unfold_ics(text):
    """
    RFC-style ICS line unfolding.

    Continuation lines begin with a space or tab.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    unfolded = []

    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


def parse_ics(text):
    """
    Parse VEVENT blocks into dictionaries.

    We intentionally keep this parser lightweight because this diagnostic
    only needs the fields required for fixture matching.
    """

    lines = unfold_ics(text)

    events = []
    current = None

    for line in lines:
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

        key, value = line.split(":", 1)

        # Remove ICS parameters, e.g. DTSTART;TZID=Europe/London
        key = key.split(";", 1)[0].upper()

        current[key] = value

    return events


# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------

def parse_ics_datetime(value):
    if not value:
        return None

    value = value.strip()

    # DATE value
    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(
            value,
            "%Y%m%d",
        ).replace(tzinfo=timezone.utc)

    # UTC datetime
    if value.endswith("Z"):
        value = value[:-1]

        try:
            return datetime.strptime(
                value,
                "%Y%m%dT%H%M%S",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Local/unqualified datetime
    for fmt in (
        "%Y%m%dT%H%M%S",
        "%Y%m%dT%H%M",
    ):
        try:
            return datetime.strptime(
                value,
                fmt,
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def is_2026_27(dt):
    if dt is None:
        return False

    return SEASON_START <= dt < SEASON_END


# ---------------------------------------------------------------------------
# Team normalisation
# ---------------------------------------------------------------------------

TEAM_ALIASES = {
    "rangers": "Rangers",
    "rangers fc": "Rangers",

    "celtic": "Celtic",
    "celtic fc": "Celtic",

    "aberdeen": "Aberdeen",
    "aberdeen fc": "Aberdeen",

    "dundee": "Dundee",
    "dundee fc": "Dundee",

    "dundee united": "Dundee United",
    "dundee united fc": "Dundee United",

    "heart of midlothian": "Hearts",
    "hearts": "Hearts",

    "hibernian": "Hibernian",
    "hibernian fc": "Hibernian",

    "kilmarnock": "Kilmarnock",
    "kilmarnock fc": "Kilmarnock",

    "motherwell": "Motherwell",
    "motherwell fc": "Motherwell",

    "falkirk": "Falkirk",
    "falkirk fc": "Falkirk",

    "st johnstone": "St Johnstone",
    "st. johnstone": "St Johnstone",
    "st johnstone fc": "St Johnstone",

    "st mirren": "St Mirren",
    "st. mirren": "St Mirren",
    "st mirren fc": "St Mirren",
}


TRACKED_TEAMS = {
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


def normalise_team(name):
    name = name.strip()

    key = name.lower()

    return TEAM_ALIASES.get(
        key,
        name,
    )


# ---------------------------------------------------------------------------
# Fixture extraction
# ---------------------------------------------------------------------------

def clean_summary(summary):
    if not summary:
        return ""

    # Fixtur.es team feeds often include results:
    #
    # Rangers - Hibernian (1-2)
    #
    # Remove the result because it prevents exact matching against upcoming
    # competition-calendar entries.
    summary = re.sub(
        r"\s+\([^)]*\)\s*$",
        "",
        summary,
    )

    return summary.strip()


def split_fixture(summary):
    """
    Split a fixture summary into home and away teams.

    Fixtur.es uses " - " for fixture separation.
    """

    summary = clean_summary(summary)

    if " - " not in summary:
        return None, None

    home, away = summary.split(" - ", 1)

    return (
        normalise_team(home),
        normalise_team(away),
    )


def fixture_key(event):
    """
    Create a normalised fixture key.

    We deliberately use:
        date/time + home + away

    because the objective of this audit is to determine whether the same
    fixture exists in both sources.
    """

    dt = parse_ics_datetime(event.get("DTSTART"))

    if dt is None:
        return None

    home, away = split_fixture(
        event.get("SUMMARY", "")
    )

    if not home or not away:
        return None

    return (
        dt,
        home,
        away,
    )


def event_involves_tracked_team(event):
    home, away = split_fixture(
        event.get("SUMMARY", "")
    )

    return (
        home in TRACKED_TEAMS
        or away in TRACKED_TEAMS
    )


# ---------------------------------------------------------------------------
# Feed audit
# ---------------------------------------------------------------------------

def audit_feed(name, url):
    text = download_ics(url)
    events = parse_ics(text)

    season_events = []

    for event in events:
        dt = parse_ics_datetime(
            event.get("DTSTART")
        )

        if is_2026_27(dt):
            season_events.append(event)

    return {
        "name": name,
        "url": url,
        "events": events,
        "season_events": season_events,
    }


# ---------------------------------------------------------------------------
# Main diagnostic
# ---------------------------------------------------------------------------

def main():

    print("=" * 70)
    print("FIXTUR.ES FULL OVERLAP / CLASSIFICATION DIAGNOSTIC")
    print("=" * 70)

    # ------------------------------------------------------------------
    # TEAM CALENDARS
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print("TEAM CALENDAR SUMMARY")
    print("=" * 70)

    team_feeds = {}
    team_fixture_keys = {}

    total_team_events = 0
    total_team_season_events = 0

    failed_team_feeds = []

    for team_name, url in TEAM_CALENDARS.items():

        print()
        print(f"{team_name}")

        try:
            result = audit_feed(
                team_name,
                url,
            )

            events = result["events"]
            season_events = result["season_events"]

            team_feeds[team_name] = result

            total_team_events += len(events)
            total_team_season_events += len(season_events)

            fixture_keys = set()

            for event in season_events:
                key = fixture_key(event)

                if key is not None:
                    fixture_keys.add(key)

            team_fixture_keys[team_name] = fixture_keys

            print(
                f"{len(events)} VEVENTs, "
                f"{len(season_events)} in 2026/27"
            )

        except Exception as exc:
            failed_team_feeds.append(
                (team_name, str(exc))
            )

            print(
                f"FAILED: {type(exc).__name__}: {exc}"
            )

    all_team_keys = set()

    for keys in team_fixture_keys.values():
        all_team_keys.update(keys)

    print()
    print(f"Total VEVENT records: {total_team_events}")
    print(f"Total 2026/27 events: {total_team_season_events}")
    print(
        f"Unique team-calendar fixtures: "
        f"{len(all_team_keys)}"
    )

    # ------------------------------------------------------------------
    # COMPETITION CALENDARS
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print("COMPETITION CALENDAR SUMMARY")
    print("=" * 70)

    competition_feeds = {}
    competition_fixture_keys = {}

    total_competition_events = 0
    total_competition_season_events = 0

    failed_competition_feeds = []

    for competition_name, url in COMPETITION_CALENDARS.items():

        print()
        print(competition_name)
        print(f"URL: {url}")

        try:
            result = audit_feed(
                competition_name,
                url,
            )

            events = result["events"]
            season_events = result["season_events"]

            competition_feeds[competition_name] = result

            total_competition_events += len(events)
            total_competition_season_events += len(
                season_events
            )

            fixture_keys = set()

            for event in season_events:
                key = fixture_key(event)

                if key is not None:
                    fixture_keys.add(key)

            competition_fixture_keys[
                competition_name
            ] = fixture_keys

            print(
                f"VEVENTs: {len(events)}"
            )

            print(
                f"2026/27 events: "
                f"{len(season_events)}"
            )

        except Exception as exc:
            failed_competition_feeds.append(
                (competition_name, str(exc))
            )

            print(
                f"FAILED: {type(exc).__name__}: {exc}"
            )

    all_competition_keys = set()

    for keys in competition_fixture_keys.values():
        all_competition_keys.update(keys)

    print()
    print(
        f"Total VEVENT records: "
        f"{total_competition_events}"
    )

    print(
        f"Total 2026/27 events: "
        f"{total_competition_season_events}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(all_competition_keys)}"
    )

    # ------------------------------------------------------------------
    # FULL OVERLAP
    # ------------------------------------------------------------------

    overlap = (
        all_team_keys
        & all_competition_keys
    )

    team_only = (
        all_team_keys
        - all_competition_keys
    )

    competition_only = (
        all_competition_keys
        - all_team_keys
    )

    print()
    print("=" * 70)
    print("FULL OVERLAP / CLASSIFICATION AUDIT")
    print("=" * 70)

    print(
        f"Unique team-calendar fixtures: "
        f"{len(all_team_keys)}"
    )

    print(
        f"Unique competition-calendar fixtures: "
        f"{len(all_competition_keys)}"
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

    # ------------------------------------------------------------------
    # COVERAGE
    # ------------------------------------------------------------------

    print()
    print("COVERAGE")

    if all_team_keys:
        competition_coverage = (
            len(overlap)
            / len(all_team_keys)
            * 100
        )
    else:
        competition_coverage = 0

    if all_competition_keys:
        team_coverage = (
            len(overlap)
            / len(all_competition_keys)
            * 100
        )
    else:
        team_coverage = 0

    print(
        "Competition coverage of team fixtures: "
        f"{competition_coverage:.1f}%"
    )

    print(
        "Team coverage of competition fixtures: "
        f"{team_coverage:.1f}%"
    )

    # ------------------------------------------------------------------
    # OVERLAP BY COMPETITION
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print("OVERLAP BY COMPETITION")
    print("=" * 70)

    for competition_name, keys in competition_fixture_keys.items():

        matched = keys & all_team_keys

        percentage = (
            len(matched)
            / len(keys)
            * 100
            if keys
            else 0
        )

        print(
            f"{competition_name}: "
            f"{len(matched)}/{len(keys)} "
            f"({percentage:.1f}%)"
        )

    # ------------------------------------------------------------------
    # TEAM COVERAGE BY COMPETITION
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print("TRACKED-TEAM FIXTURES FOUND IN EACH COMPETITION")
    print("=" * 70)

    for competition_name, keys in competition_fixture_keys.items():

        tracked = {
            key
            for key in keys
            if key[1] in TRACKED_TEAMS
            or key[2] in TRACKED_TEAMS
        }

        matched = tracked & all_team_keys

        percentage = (
            len(matched)
            / len(tracked)
            * 100
            if tracked
            else 0
        )

        print(
            f"{competition_name}: "
            f"{len(matched)}/{len(tracked)} "
            f"({percentage:.1f}%)"
        )

    # ------------------------------------------------------------------
    # TEAM-ONLY FIXTURES
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "TEAM-CALENDAR-ONLY FIXTURES"
    )
    print("=" * 70)

    if not team_only:
        print("None")
    else:
        for key in sorted(team_only):

            dt, home, away = key

            print(
                f"{dt.strftime('%Y-%m-%d %H:%M')} | "
                f"{home} - {away}"
            )

    # ------------------------------------------------------------------
    # COMPETITION-ONLY TRACKED FIXTURES
    # ------------------------------------------------------------------

    tracked_competition_only = {
        key
        for key in competition_only
        if key[1] in TRACKED_TEAMS
        or key[2] in TRACKED_TEAMS
    }

    print()
    print("=" * 70)
    print(
        "COMPETITION-ONLY FIXTURES INVOLVING "
        "TRACKED TEAMS"
    )
    print("=" * 70)

    if not tracked_competition_only:
        print("None")
    else:
        for key in sorted(tracked_competition_only):

            dt, home, away = key

            print(
                f"{dt.strftime('%Y-%m-%d %H:%M')} | "
                f"{home} - {away}"
            )

    # ------------------------------------------------------------------
    # CLASSIFICATION OF TEAM-ONLY FIXTURES
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "TEAM-ONLY FIXTURE CLASSIFICATION HINTS"
    )
    print("=" * 70)

    if not team_only:
        print("None")
    else:

        for key in sorted(team_only):

            dt, home, away = key

            matching_events = []

            for team_name, result in team_feeds.items():

                for event in result["season_events"]:

                    event_key = fixture_key(event)

                    if event_key == key:
                        matching_events.append(event)

            summaries = {
                clean_summary(
                    event.get("SUMMARY", "")
                )
                for event in matching_events
            }

            summary = (
                sorted(summaries)[0]
                if summaries
                else f"{home} - {away}"
            )

            hints = []

            upper = summary.upper()

            if "[CL]" in upper:
                hints.append("Champions League marker")

            if "[EL]" in upper:
                hints.append("Europa League marker")

            if "[CONF]" in upper:
                hints.append(
                    "Conference League marker"
                )

            if not hints:
                hints.append(
                    "No UEFA marker in team calendar"
                )

            print(
                f"{dt.strftime('%Y-%m-%d %H:%M')} | "
                f"{summary} | "
                f"{', '.join(hints)}"
            )

    # ------------------------------------------------------------------
    # FAILED FEEDS
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print("FAILED FEEDS")
    print("=" * 70)

    if not failed_team_feeds and not failed_competition_feeds:
        print("None")
    else:

        for name, error in failed_team_feeds:
            print(
                f"TEAM | {name} | {error}"
            )

        for name, error in failed_competition_feeds:
            print(
                f"COMPETITION | {name} | {error}"
            )

    # ------------------------------------------------------------------
    # FINAL RESULT
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print("DIAGNOSTIC RESULT")
    print("=" * 70)

    if failed_team_feeds or failed_competition_feeds:

        print(
            "RESULT: One or more feeds failed."
        )

        return 1

    print(
        "RESULT: All team and competition "
        "calendars loaded successfully."
    )

    print()
    print(
        "UEFA competition calendars included:"
    )

    print(
        "  Champions League"
    )

    print(
        "  Europa League"
    )

    print(
        "  UEFA Conference League"
    )

    print()
    print(
        "No changes were made to fixtures.py "
        "or generator.py."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
