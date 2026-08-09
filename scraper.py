"""
scraper.py

Pulls fixtures for a single SPFL club directly from its ESPN team
fixtures page - no API key required.

Data source:
    https://africa.espn.com/football/team/fixtures/_/id/{ESPN_ID}/{slug}

This page lists that club's full upcoming schedule across all
competitions (Premiership, Scottish Cup, League Cup, European
competition, etc.), grouped under month headings, as a simple table:
    DATE | MATCH | TIME | COMPETITION | TV

Because we fetch one page PER TEAM (using the ESPN ID mapped in
espn_team_ids.py), there's no need to fuzzy-match team names against
a big combined list - every fixture on a team's page already belongs
to that team.

NOTE: this was built against ESPN's page structure as observed in
August 2026. If parsing stops finding fixtures, run with debug=True
(see fetch_team_fixtures below) - it prints the raw extracted text so
the parsing rules below can be adjusted against real output.
"""

import re
import time
from datetime import datetime, date

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

BASE_URL = "https://africa.espn.com/football/team/fixtures/_/id"

WANTED_COMPETITIONS = {
    "Scottish Premiership",
    "Scottish Cup",
    "Scottish League Cup",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.0  # be polite between team requests

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_MONTH_HEADER_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|"
    r"October|November|December),\s*(\d{4})$"
)
_DATE_ROW_RE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*(\d{1,2})\s*"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$"
)
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)


def fetch_team_fixtures(team_name: str, espn_id: int, debug: bool = False) -> list[dict]:
    """
    Fetch and parse the fixtures table for a single team.
    Returns a list of dicts:
        {
            "home": str,
            "away": str,
            "kickoff": datetime | None,   # None if ESPN shows "TBD"
            "competition": str,
        }
    """
    slug = team_name.lower().replace(" ", "-")
    url = f"{BASE_URL}/{espn_id}/{slug}"
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    body = soup.find("body")
    if body is None:
        return []

    lines = [line.strip() for line in body.get_text("\n").split("\n")]
    lines = [line for line in lines if line]

    if debug:
        print(f"\n--- DEBUG: extracted text for {team_name} (first 4000 chars) ---")
        print("\n".join(lines)[:4000])
        print("--- END DEBUG ---\n")

    return _parse_lines(lines, team_name)


def _parse_lines(lines: list[str], team_name: str) -> list[dict]:
    fixtures = []
    current_year = date.today().year
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        month_match = _MONTH_HEADER_RE.match(line)
        if month_match:
            current_year = int(month_match.group(2))
            i += 1
            continue

        date_match = _DATE_ROW_RE.match(line)
        if date_match:
            day = int(date_match.group(2))
            month_abbr = date_match.group(3)
            month = MONTHS[month_abbr]

            # Expected shape following a date row:
            #   home_team
            #   v
            #   away_team
            #   time (or "TBD")
            #   competition
            #   [tv line(s) - ignored]
            if i + 5 >= n:
                break  # not enough lines left to form a full fixture

            home = lines[i + 1]
            separator = lines[i + 2]
            away = lines[i + 3]
            time_str = lines[i + 4]
            competition = lines[i + 5]

            if separator != "v":
                # Doesn't match expected shape - skip just this date line
                # and keep scanning rather than aborting the whole parse.
                i += 1
                continue

            kickoff = None
            if _TIME_RE.match(time_str):
                try:
                    parsed_time = datetime.strptime(time_str.upper(), "%I:%M %p")
                    kickoff = datetime(
                        current_year, month, day,
                        parsed_time.hour, parsed_time.minute,
                        tzinfo=UK_TZ,
                    )
                except ValueError:
                    kickoff = None

            if competition in WANTED_COMPETITIONS:
                fixtures.append(
                    {
                        "home": home,
                        "away": away,
                        "kickoff": kickoff,
                        "competition": competition,
                    }
                )

            i += 6  # advance past this fixture's block
            continue

        i += 1

    return fixtures


def fetch_all_teams(team_espn_ids: dict, debug_first: bool = False) -> dict:
    """
    team_espn_ids: dict mapping team_name -> espn_id (int or None)
    Returns dict mapping team_name -> list of fixture dicts.
    Skips (with a warning) any team whose ID is None or whose request fails.
    """
    results = {}
    first = True
    for team_name, espn_id in team_espn_ids.items():
        if espn_id is None:
            print(f"WARNING: no ESPN id set for {team_name} - skipping. "
                  f"Fill it in in espn_team_ids.py")
            results[team_name] = []
            continue

        try:
            fixtures = fetch_team_fixtures(team_name, espn_id, debug=(debug_first and first))
            first = False
            print(f"{team_name}: found {len(fixtures)} fixture(s)")
            results[team_name] = fixtures
        except requests.RequestException as e:
            print(f"WARNING: failed to fetch fixtures for {team_name}: {e}")
            results[team_name] = []

        time.sleep(REQUEST_DELAY_SECONDS)

    return results


if __name__ == "__main__":
    # Quick manual test / debug entry point: python scraper.py
    from espn_team_ids import ESPN_TEAM_IDS

    all_fixtures = fetch_all_teams(ESPN_TEAM_IDS, debug_first=True)
    total = sum(len(v) for v in all_fixtures.values())
    print(f"\nTotal fixtures found across all teams: {total}")
    for team, fixtures in all_fixtures.items():
        for fx in fixtures[:3]:
            print(team, fx)
