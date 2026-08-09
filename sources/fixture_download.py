"""
sources/fixture_download.py

Fixture Download source adapter.

Fixture Download's "JSON" endpoint returns an HTML page containing
the raw JSON data. This adapter extracts that JSON and converts it
into the source-independent format used by the EPG data layer.

The rest of the EPG does not need to know that Fixture Download
exists.

Source:
    https://fixturedownload.com/
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# ================================================================
# PROJECT PATHS
# ================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

FIXTURES_FILE = DATA_DIR / "fixtures.json"


# ================================================================
# FIXTURE DOWNLOAD
# ================================================================

BASE_URL = (
    "https://fixturedownload.com/view/json"
)


COMPETITIONS = {
    "Scottish Premiership": {
        "slug": "scottish-premiership-2026",
    },
}


# ================================================================
# TEAMS
# ================================================================

TEAMS = [
    "Aberdeen",
    "Celtic",
    "Dundee",
    "Dundee United",
    "Falkirk",
    "Heart of Midlothian",
    "Hibernian",
    "Kilmarnock",
    "Motherwell",
    "Rangers",
    "St. Johnstone",
    "St. Mirren",
]


# ================================================================
# HTTP SESSION
# ================================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0.0.0 "
            "Safari/537.36"
        ),
        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "*/*;q=0.8"
        ),
        "Accept-Language": (
            "en-GB,en;q=0.9"
        ),
        "Referer": (
            "https://fixturedownload.com/"
        ),
    }
)


# ================================================================
# TEAM SLUG
# ================================================================

def team_slug(team_name: str) -> str:
    """
    Convert a team name into the Fixture Download slug.
    """

    value = team_name.strip().lower()

    value = value.replace(
        "&",
        "and",
    )

    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value,
    )

    return value.strip("-")


# ================================================================
# FETCH HTML
# ================================================================

def fetch_page(url: str):
    """
    Fetch a Fixture Download JSON page.

    Despite being called a JSON endpoint, Fixture Download returns
    an HTML page containing the raw JSON.
    """

    for attempt in range(1, 4):

        print(
            f"    Request attempt "
            f"{attempt}/3"
        )

        try:

            response = SESSION.get(
                url,
                timeout=30,
            )

            print(
                f"    HTTP status: "
                f"{response.status_code}"
            )

            if response.status_code == 200:

                return response.text

            print(
                "    Response preview:"
            )

            print(
                response.text[:500]
            )

        except requests.RequestException as exc:

            print(
                f"    Request error: {exc}"
            )

        if attempt < 3:

            delay = attempt * 2

            print(
                f"    Retrying in "
                f"{delay}s..."
            )

            time.sleep(delay)

    return None


# ================================================================
# EXTRACT JSON FROM HTML
# ================================================================

def extract_json_from_html(html: str):
    """
    Extract the raw JSON array from the Fixture Download page.

    The page contains JSON similar to:

        [{"MatchNumber":1,...}, ...]

    We locate the first JSON array beginning with MatchNumber.
    """

    if not html:

        return None

    # ------------------------------------------------------------
    # First attempt:
    #
    # Locate the raw JSON array directly.
    # ------------------------------------------------------------

    start = html.find(
        '[{"MatchNumber"'
    )

    if start == -1:

        # Some pages may contain whitespace
        # or different attribute ordering.
        match = re.search(
            r"\[\s*\{\s*"
            r'"MatchNumber"\s*:',
            html,
            re.DOTALL,
        )

        if not match:

            print(
                "    Could not locate "
                "raw JSON data in HTML."
            )

            return None

        start = match.start()

    # ------------------------------------------------------------
    # JSON arrays can contain nested objects.
    #
    # Use a small bracket counter instead of a greedy regex.
    # ------------------------------------------------------------

    depth = 0
    in_string = False
    escaped = False

    for index in range(
        start,
        len(html),
    ):

        char = html[index]

        if in_string:

            if escaped:

                escaped = False

            elif char == "\\" :

                escaped = True

            elif char == '"':

                in_string = False

            continue

        if char == '"':

            in_string = True

            continue

        if char == "[":

            depth += 1

        elif char == "]":

            depth -= 1

            if depth == 0:

                json_text = html[
                    start:index + 1
                ]

                try:

                    data = json.loads(
                        json_text
                    )

                    return data

                except json.JSONDecodeError as exc:

                    print(
                        "    JSON extraction "
                        "failed:"
                    )

                    print(
                        f"    {exc}"
                    )

                    print(
                        "    JSON preview:"
                    )

                    print(
                        json_text[:500]
                    )

                    return None

    print(
        "    Could not find the end "
        "of the JSON array."
    )

    return None


# ================================================================
# PARSE DATE
# ================================================================

def parse_date(value):
    """
    Convert Fixture Download's UTC date into a
    timezone-aware UTC ISO timestamp.
    """

    if not value:

        return None

    try:

        value = value.strip()

        # Fixture Download currently uses:
        #
        # 2026-08-22 14:00:00Z

        if value.endswith("Z"):

            value = value[:-1]

        kickoff = datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S",
        )

        kickoff = kickoff.replace(
            tzinfo=timezone.utc
        )

        return kickoff.isoformat()

    except ValueError:

        print(
            f"    Could not parse date: "
            f"{value}"
        )

        return None


# ================================================================
# NORMALISE FIXTURE
# ================================================================

def normalise_fixture(
    item: dict,
    competition: str,
):
    """
    Convert Fixture Download's schema into the
    internal fixture schema.
    """

    home = item.get(
        "HomeTeam"
    )

    away = item.get(
        "AwayTeam"
    )

    date_utc = item.get(
        "DateUtc"
    )

    if not home:

        return None

    if not away:

        return None

    kickoff = parse_date(
        date_utc
    )

    if kickoff is None:

        return None

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "competition": competition,
    }


# ================================================================
# SAVE FIXTURE DATA
# ================================================================

def save_fixtures(
    fixtures: list[dict],
):
    """
    Atomically save the normalised fixture database.

    The existing file is only replaced after the new file has
    been completely written.
    """

    DATA_DIR.mkdir(
        exist_ok=True
    )

    output = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "fixtures": fixtures,
    }

    temporary_file = (
        FIXTURES_FILE.with_suffix(
            ".tmp"
        )
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    temporary_file.replace(
        FIXTURES_FILE
    )


# ================================================================
# MAIN
# ================================================================

def main():

    print(
        "=============================="
    )

    print(
        "FIXTURE DOWNLOAD SOURCE ADAPTER"
    )

    print(
        "=============================="
    )

    print(
        f"Teams configured: "
        f"{len(TEAMS)}"
    )

    all_fixtures = []

    # ------------------------------------------------------------
    # Fetch each competition/team
    # ------------------------------------------------------------

    for (
        competition,
        config,
    ) in COMPETITIONS.items():

        competition_slug = (
            config["slug"]
        )

        print(
            "\n--------------------------------"
        )

        print(
            f"Competition: "
            f"{competition}"
        )

        print(
            f"Competition slug: "
            f"{competition_slug}"
        )

        print(
            "--------------------------------"
        )

        for team in TEAMS:

            slug = team_slug(
                team
            )

            url = (
                f"{BASE_URL}/"
                f"{competition_slug}/"
                f"{slug}"
            )

            print(
                f"\n{team}"
            )

            print(
                f"URL: {url}"
            )

            html = fetch_page(
                url
            )

            if html is None:

                print(
                    "    REQUEST FAILED"
                )

                continue

            data = extract_json_from_html(
                html
            )

            if data is None:

                print(
                    "    No JSON data "
                    "extracted."
                )

                continue

            if not isinstance(
                data,
                list,
            ):

                print(
                    "    Unexpected JSON "
                    "structure."
                )

                continue

            print(
                f"    Fixtures returned: "
                f"{len(data)}"
            )

            for item in data:

                fixture = normalise_fixture(
                    item,
                    competition,
                )

                if fixture is None:

                    continue

                all_fixtures.append(
                    fixture
                )

                print(
                    f"    "
                    f"{fixture['kickoff']} - "
                    f"{fixture['home']} vs "
                    f"{fixture['away']}"
                )

    # ------------------------------------------------------------
    # Remove duplicates
    # ------------------------------------------------------------

    unique = {}

    for fixture in all_fixtures:

        key = (
            fixture["kickoff"],
            fixture["home"],
            fixture["away"],
            fixture["competition"],
        )

        unique[key] = fixture

    all_fixtures = list(
        unique.values()
    )

    all_fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------

    print(
        "\n=============================="
    )

    print(
        f"TOTAL UNIQUE FIXTURES: "
        f"{len(all_fixtures)}"
    )

    print(
        "=============================="
    )

    # ------------------------------------------------------------
    # Safety protection
    #
    # Never replace a known-good fixture database with an empty
    # result caused by a source failure.
    # ------------------------------------------------------------

    if not all_fixtures:

        print(
            "\nERROR:"
        )

        print(
            "Fixture Download returned "
            "zero usable fixtures."
        )

        print(
            "Existing "
            "data/fixtures.json "
            "has NOT been replaced."
        )

        sys.exit(1)

    # ------------------------------------------------------------
    # Save
    # ------------------------------------------------------------

    save_fixtures(
        all_fixtures
    )

    print(
        "\nSaved fixture data to:"
    )

    print(
        FIXTURES_FILE
    )

    print(
        "\nFixture Download adapter "
        "completed successfully."
    )


if __name__ == "__main__":

    main()
