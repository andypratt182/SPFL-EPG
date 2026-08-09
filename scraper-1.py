"""
scraper.py

Pulls Scottish football fixtures/results from BBC's server-rendered
sport feed - no API key required.

IMPORTANT: we use feeds.bbci.co.uk, NOT www.bbc.com/sport.
www.bbc.com/sport is a JavaScript-rendered React app - a plain
`requests` call only gets an empty page shell with none of the
fixture data in it. feeds.bbci.co.uk is BBC's older, server-rendered
version of the same data and works fine with requests + BeautifulSoup.

Data source:
    https://feeds.bbci.co.uk/sport/football/scottish/scores-fixtures/YYYY-MM-DD

This single feed covers ALL Scottish competitions on a given day
(Premiership, Championship, League One/Two, Scottish Cup, League Cup,
Highland/Lowland leagues, etc), grouped under headings. We keep only
the competitions we care about and, within those, only matches
involving our 12 SPFL_TEAMS (filtering happens in fixtures.py).
"""

import re
import time
from datetime import datetime, date, timedelta

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

BASE_URL = "https://feeds.bbci.co.uk/sport/football/scottish/scores-fixtures"

# Competition headings on the BBC page we want to keep.
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


def fetch_day(target_date: date, debug: bool = False) -> list[dict]:
    """
    Fetch and parse all wanted-competition fixtures for a single date.
    Returns a list of dicts:
        {
            "date": date,
            "kickoff": datetime | None,
            "home": str,
            "away": str,
            "home_score": int | None,
            "away_score": int | None,
            "status": str,
            "competition": str,
        }
    """
    url = f"{BASE_URL}/{target_date.isoformat()}"
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    if debug:
        print(f"\n--- DEBUG: raw HTML length for {target_date}: {len(response.text)} chars ---")
        body = soup.find("body")
        text_preview = body.get_text("\n", strip=True)[:3000] if body else "(no body tag found)"
        print(f"--- DEBUG: first 3000 chars of extracted text ---\n{text_preview}\n--- END DEBUG ---\n")

    fixtures = _parse_page(soup, target_date)
    return fixtures


def _parse_page(soup: BeautifulSoup, target_date: date) -> list[dict]:
    """
    BBC's server-rendered feed lays the page out as a flat sequence of
    headings (competition names) followed by repeated blocks of team
    names, scores/times, and statuses. Rather than depend on specific
    CSS classes (which BBC changes periodically and which we can't
    verify without live access), we walk the page's visible text nodes
    in order and use the competition headings to bucket fixture lines.
    """
    body = soup.find("body")
    if body is None:
        return []

    # Get every heading (h2/h3) and every fixture-ish block in document
    # order so we know which competition each fixture belongs to.
    elements = body.find_all(["h2", "h3", "div"], recursive=True)

    fixtures = []
    current_competition = None

    for el in elements:
        # Headings mark a new competition section.
        if el.name in ("h2", "h3"):
            heading_text = el.get_text(strip=True)
            if heading_text in WANTED_COMPETITIONS:
                current_competition = WANTED_COMPETITIONS[heading_text]
            elif heading_text:
                # Any other heading (e.g. "Scottish Championship") means
                # we've left a section we cared about.
                current_competition = None
            continue

        if current_competition is None:
            continue

        match = _try_parse_fixture_div(el)
        if match:
            match["competition"] = current_competition
            match["date"] = target_date
            fixtures.append(match)

    return _dedupe_fixtures(fixtures)


def _try_parse_fixture_div(el) -> dict | None:
    """
    Try to interpret a <div> as a single fixture block. BBC's feed
    typically renders each match as: home name (repeated), score or
    time, away name (repeated), score, status (Full time/FT/kickoff
    time). We only accept divs that directly contain this shape - not
    ancestor divs that wrap the whole day - by requiring the element
    have no nested <div> children of its own.
    """
    if el.find("div"):
        # Not a leaf fixture block - it's a wrapper. Skip; we'll reach
        # the actual leaf div(s) later in iteration.
        return None

    text = el.get_text(" ", strip=True)
    if not text:
        return None

    # Look for the pattern: "Team A <score> , Team B <score> at <status>"
    # e.g. "Aberdeen 0 , Livingston 0 at Full time"
    score_pattern = re.match(
        r"^(?P<home>.+?)\s+(?P<home_score>\d+)\s*,\s*(?P<away>.+?)\s+(?P<away_score>\d+)\s+at\s+(?P<status>.+)$",
        text,
    )
    if score_pattern:
        return {
            "home": score_pattern.group("home").strip(),
            "away": score_pattern.group("away").strip(),
            "home_score": int(score_pattern.group("home_score")),
            "away_score": int(score_pattern.group("away_score")),
            "status": score_pattern.group("status").strip(),
            "kickoff": None,  # already played - no kickoff datetime needed
        }

    # Look for the pattern for an upcoming fixture with a kickoff time.
    time_el = el.find("time")
    if time_el:
        kickoff_attr = time_el.get("datetime")
        vs_match = re.match(r"^(?P<home>.+?)\s+v\s+(?P<away>.+)$", text)
        if vs_match and kickoff_attr:
            try:
                kickoff = datetime.fromisoformat(kickoff_attr.replace("Z", "+00:00")).astimezone(UK_TZ)
            except ValueError:
                kickoff = None
            return {
                "home": vs_match.group("home").strip(),
                "away": vs_match.group("away").strip(),
                "home_score": None,
                "away_score": None,
                "status": "Scheduled",
                "kickoff": kickoff,
            }

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


def fetch_range(start_date: date, days: int, debug_first_day: bool = True) -> list[dict]:
    """
    Fetch fixtures across a range of `days` starting at `start_date`.
    Skips (rather than fails) any single day that errors.

    debug_first_day: if True, prints raw-text diagnostics for the
    first day fetched - helpful for tuning the parser against BBC's
    real markup without needing a second round trip.
    """
    all_fixtures = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        try:
            day_fixtures = fetch_day(day, debug=(debug_first_day and offset == 0))
            if day_fixtures:
                print(f"{day.isoformat()}: found {len(day_fixtures)} fixture(s)")
            all_fixtures.extend(day_fixtures)
        except requests.RequestException as e:
            print(f"WARNING: failed to fetch {day.isoformat()}: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_fixtures


if __name__ == "__main__":
    # Quick manual test / debug entry point: python scraper.py
    today = date.today()
    results = fetch_range(today, days=7, debug_first_day=True)
    print(f"\nTotal fixtures found: {len(results)}")
    for r in results[:20]:
        print(r)
