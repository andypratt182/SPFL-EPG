"""
scraper.py

Pulls Scottish football fixtures/results directly from BBC Sport's
public "scores-fixtures" feed - no API key required.

Data source:
    https://www.bbc.com/sport/football/scottish/scores-fixtures/YYYY-MM-DD

BBC groups every match on a given day under a competition heading, e.g.:
    Scottish Premiership
    Scottish Cup
    Scottish League Cup
    Scottish Championship
    ...

This module fetches a range of dates, parses out matches belonging to
the competitions we care about, and returns them in a normalised
format that fixtures.py can filter down to just our 12 SPFL_TEAMS.

NOTE: This was designed against BBC's markup as observed in mid-2026.
BBC redesigns their site occasionally. If scraping stops returning
results, run scraper.py directly (see bottom of file) to print raw
debug output and adjust the SELECTORS / parsing logic below.
"""

import re
import time
from datetime import datetime, date, timedelta

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

BASE_URL = "https://www.bbc.com/sport/football/scottish/scores-fixtures"

# Competition headings on the BBC page we want to keep.
# (BBC's exact heading text - update here if they rename anything.)
WANTED_COMPETITIONS = {
    "Scottish Premiership": "Scottish Premiership",
    "Scottish Cup": "Scottish Cup",
    "Scottish League Cup": "Scottish League Cup",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.0  # be polite - avoid hammering BBC


def fetch_day(target_date: date) -> list[dict]:
    """
    Fetch and parse all wanted-competition fixtures for a single date.
    Returns a list of dicts:
        {
            "date": date,
            "kickoff": datetime | None,   # None if not yet known / TBC
            "home": str,
            "away": str,
            "home_score": int | None,
            "away_score": int | None,
            "status": str,                # e.g. "Full time", "Kick off 15:00", "Postponed"
            "competition": str,
        }
    """
    url = f"{BASE_URL}/{target_date.isoformat()}"
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    fixtures = []

    # BBC Sport renders each competition as a heading followed by a
    # list of fixture "cards". We walk headings in document order and
    # collect the fixture blocks that follow each one, stopping when
    # we hit the next heading.
    headings = soup.find_all(["h2", "h3"])

    for heading in headings:
        comp_name = heading.get_text(strip=True)
        if comp_name not in WANTED_COMPETITIONS:
            continue

        # Walk forward through siblings collecting fixture cards until
        # the next heading of the same level.
        for sibling in heading.find_all_next():
            if sibling.name in ("h2", "h3"):
                break

            card_text = sibling.get_text(" ", strip=True)
            match = _parse_fixture_card(sibling)
            if match:
                match["competition"] = WANTED_COMPETITIONS[comp_name]
                match["date"] = target_date
                fixtures.append(match)

    return _dedupe_fixtures(fixtures)


def _parse_fixture_card(node) -> dict | None:
    """
    Attempt to parse a single fixture "card" element into a match dict.
    BBC fixture cards typically expose the two team names and either
    a score (for played matches) or a kickoff time (for upcoming ones).

    Returns None if this node doesn't look like a fixture card.
    """
    # Fixture cards commonly carry a data-testid attribute in BBC's markup.
    testid = node.get("data-testid", "") if hasattr(node, "get") else ""
    if "fixture" not in testid and "match" not in testid:
        return None

    home_el = node.select_one('[data-testid*="home"]')
    away_el = node.select_one('[data-testid*="away"]')
    if not home_el or not away_el:
        return None

    home_name = home_el.get_text(strip=True)
    away_name = away_el.get_text(strip=True)
    if not home_name or not away_name:
        return None

    status_el = node.select_one('[data-testid*="status"]')
    status_text = status_el.get_text(strip=True) if status_el else ""

    time_el = node.find("time")
    kickoff_str = time_el.get("datetime") if time_el else None

    home_score = away_score = None
    score_els = node.select('[data-testid*="score"]')
    if len(score_els) >= 2:
        home_score = _safe_int(score_els[0].get_text(strip=True))
        away_score = _safe_int(score_els[1].get_text(strip=True))

    kickoff = None
    if kickoff_str:
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            kickoff = kickoff.astimezone(UK_TZ)
        except ValueError:
            kickoff = None

    return {
        "home": home_name,
        "away": away_name,
        "home_score": home_score,
        "away_score": away_score,
        "status": status_text,
        "kickoff": kickoff,
    }


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe_fixtures(fixtures: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for fx in fixtures:
        key = (fx["home"], fx["away"], fx["competition"], fx.get("date"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(fx)
    return unique


def fetch_range(start_date: date, days: int) -> list[dict]:
    """
    Fetch fixtures across a range of `days` starting at `start_date`.
    Skips (rather than fails) any single day that errors, printing a
    warning - one bad day shouldn't kill the whole run.
    """
    all_fixtures = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        try:
            day_fixtures = fetch_day(day)
            if day_fixtures:
                print(f"{day.isoformat()}: found {len(day_fixtures)} fixture(s)")
            all_fixtures.extend(day_fixtures)
        except requests.RequestException as e:
            print(f"WARNING: failed to fetch {day.isoformat()}: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_fixtures


if __name__ == "__main__":
    # Quick manual test / debug entry point.
    # Run with: python scraper.py
    # (Requires network access - this environment does not have any,
    # so run this locally or in your GitHub Actions workflow.)
    today = date.today()
    results = fetch_range(today, days=7)
    print(f"\nTotal fixtures found: {len(results)}")
    for r in results[:20]:
        print(r)
