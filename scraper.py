"""
scraper.py

Fetches SPFL fixtures directly from ESPN's JSON endpoints.

Competitions:
    Scottish Premiership
    Scottish Cup
    Scottish League Cup

The scraper uses one ESPN JSON request per team per competition.

The public interface remains:

    fetch_team_fixtures(team_name, espn_id)
    fetch_all_teams(team_espn_ids)

Each fixture is returned as:

    {
        "home": str,
        "away": str,
        "kickoff": datetime | None,
        "competition": str,
    }

The ESPN API can return HTTP 403 from cloud-hosted environments such
as GitHub Actions. A browser-style requests.Session is therefore used
to make the request resemble a normal browser request.

If ESPN still returns 403 from GitHub Actions, the workflow output
will clearly identify the endpoint and response so that we can switch
to the regional ESPN endpoint if necessary.
"""

import time
from datetime import datetime

import requests
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")


# ------------------------------------------------------------------
# ESPN endpoints
# ------------------------------------------------------------------

ESPN_BASE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer"
)

COMPETITIONS = {
    "Scottish Premiership": "sco.1",
    "Scottish Cup": "sco.cup",
    "Scottish League Cup": "sco.league_cup",
}


# ------------------------------------------------------------------
# HTTP configuration
# ------------------------------------------------------------------

REQUEST_TIMEOUT = 20

REQUEST_DELAY_SECONDS = 1.0

MAX_RETRIES = 3

RETRY_STATUS_CODES = {
    403,
    429,
    500,
    502,
    503,
    504,
}


# Browser-style headers.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/json, text/plain, */*"
    ),
    "Accept-Language": (
        "en-GB,en-US;q=0.9,en;q=0.8"
    ),
    "Accept-Encoding": (
        "gzip, deflate, br"
    ),
    "Referer": (
        "https://www.espn.com/"
    ),
    "Origin": (
        "https://www.espn.com"
    ),
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "Connection": "keep-alive",
}


# ------------------------------------------------------------------
# HTTP session
# ------------------------------------------------------------------

def create_session() -> requests.Session:
    """
    Create a persistent browser-style HTTP session.

    Using a Session gives ESPN a normal browser-like sequence of
    requests rather than repeatedly creating completely independent
    HTTP connections.
    """

    session = requests.Session()

    session.headers.update(HEADERS)

    return session


SESSION = create_session()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_kickoff(value):
    """
    Convert ESPN's ISO timestamp into a timezone-aware datetime.

    ESPN normally returns UTC timestamps such as:

        2026-08-09T15:00Z

    They are converted to Europe/London.
    """

    if not value:
        return None

    try:
        # ESPN uses Z for UTC.
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        return parsed.astimezone(UK_TZ)

    except (TypeError, ValueError):
        print(
            f"WARNING: unable to parse ESPN date: {value}"
        )

        return None


def _extract_team_names(event):
    """
    Extract home and away team names from an ESPN event.
    """

    competitions = event.get("competitions", [])

    if not competitions:
        return None, None

    competitors = competitions[0].get(
        "competitors",
        []
    )

    home = None
    away = None

    for competitor in competitors:

        team = competitor.get("team", {})

        name = (
            team.get("displayName")
            or team.get("name")
            or team.get("location")
        )

        if not name:
            continue

        if competitor.get("homeAway") == "home":
            home = name

        elif competitor.get("homeAway") == "away":
            away = name

    return home, away


# ------------------------------------------------------------------
# ESPN request
# ------------------------------------------------------------------

def _request_json(
    url: str,
    team_name: str,
    competition_name: str,
):
    """
    Fetch JSON from ESPN using the browser-style session.

    Retries temporary failures and prints useful diagnostics for
    HTTP 403 responses.
    """

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = SESSION.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )

            print(
                f"    HTTP {response.status_code} "
                f"for {competition_name}"
            )

            if response.status_code == 403:

                print(
                    f"    ESPN returned HTTP 403 for "
                    f"{team_name} / {competition_name}"
                )

                print(
                    f"    URL: {url}"
                )

                print(
                    f"    Attempt {attempt}/{MAX_RETRIES}"
                )

                if attempt < MAX_RETRIES:

                    delay = attempt * 2

                    print(
                        f"    Retrying in {delay}s..."
                    )

                    time.sleep(delay)

                    continue

                print(
                    "    ESPN is refusing this request "
                    "from the current environment."
                )

                return None

            if response.status_code in RETRY_STATUS_CODES:

                if attempt < MAX_RETRIES:

                    delay = attempt * 2

                    print(
                        f"    Temporary HTTP "
                        f"{response.status_code}; "
                        f"retrying in {delay}s..."
                    )

                    time.sleep(delay)

                    continue

                response.raise_for_status()

            response.raise_for_status()

            return response.json()

        except requests.RequestException as exc:

            print(
                f"    Request error for "
                f"{team_name} / {competition_name}: "
                f"{exc}"
            )

            if attempt < MAX_RETRIES:

                delay = attempt * 2

                print(
                    f"    Retrying in {delay}s..."
                )

                time.sleep(delay)

                continue

            return None

        except ValueError as exc:

            print(
                f"    Invalid JSON returned by ESPN "
                f"for {team_name} / "
                f"{competition_name}: {exc}"
            )

            return None

    return None


# ------------------------------------------------------------------
# Competition scraper
# ------------------------------------------------------------------

def fetch_team_competition_fixtures(
    team_name: str,
    espn_id: int,
    competition_name: str,
    competition_code: str,
) -> list[dict]:
    """
    Fetch fixtures for one team from one ESPN competition endpoint.
    """

    url = (
        f"{ESPN_BASE_URL}/"
        f"{competition_code}/"
        f"teams/{espn_id}/schedule"
    )

    print(
        f"  Fetching {competition_code} "
        f"for {team_name}..."
    )

    data = _request_json(
        url,
        team_name,
        competition_name,
    )

    if not data:
        return []

    events = data.get("events", [])

    fixtures = []

    for event in events:

        home, away = _extract_team_names(event)

        if not home or not away:
            continue

        kickoff = _parse_kickoff(
            event.get("date")
        )

        fixtures.append(
            {
                "home": home,
                "away": away,
                "kickoff": kickoff,
                "competition": competition_name,
            }
        )

    return fixtures


# ------------------------------------------------------------------
# Team scraper
# ------------------------------------------------------------------

def fetch_team_fixtures(
    team_name: str,
    espn_id: int,
) -> list[dict]:
    """
    Fetch all supported competitions for one team.

    Returns:

        [
            {
                "home": "Rangers",
                "away": "Celtic",
                "kickoff": datetime(...),
                "competition": "Scottish Premiership",
            },
            ...
        ]
    """

    all_fixtures = []

    for competition_name, competition_code in COMPETITIONS.items():

        fixtures = fetch_team_competition_fixtures(
            team_name=team_name,
            espn_id=espn_id,
            competition_name=competition_name,
            competition_code=competition_code,
        )

        print(
            f"    {competition_name}: "
            f"{len(fixtures)} fixture(s)"
        )

        all_fixtures.extend(fixtures)

        # Be polite between ESPN requests.
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_fixtures


# ------------------------------------------------------------------
# All teams
# ------------------------------------------------------------------

def fetch_all_teams(
    team_espn_ids: dict,
    debug_first: bool = False,
) -> dict:
    """
    Fetch fixtures for every team in ESPN_TEAM_IDS.

    Returns:

        {
            "Rangers": [...],
            "Celtic": [...],
            ...
        }

    Teams with no ESPN ID are skipped with a warning.
    """

    results = {}

    print()
    print("==============================")
    print("FETCHING FIXTURES FROM ESPN JSON")
    print("==============================")

    for team_name, espn_id in team_espn_ids.items():

        if espn_id is None:

            print(
                f"WARNING: no ESPN ID set for "
                f"{team_name} - skipping."
            )

            results[team_name] = []

            continue

        try:

            fixtures = fetch_team_fixtures(
                team_name,
                espn_id,
            )

            results[team_name] = fixtures

            print(
                f"{team_name}: "
                f"found {len(fixtures)} fixture(s)"
            )

        except Exception as exc:

            print(
                f"ERROR: failed to fetch fixtures "
                f"for {team_name}: {exc}"
            )

            results[team_name] = []

        # Delay between teams.
        time.sleep(REQUEST_DELAY_SECONDS)

    return results


# ------------------------------------------------------------------
# Manual test
# ------------------------------------------------------------------

if __name__ == "__main__":

    from espn_team_ids import ESPN_TEAM_IDS

    all_fixtures = fetch_all_teams(
        ESPN_TEAM_IDS,
        debug_first=True,
    )

    total = sum(
        len(fixtures)
        for fixtures in all_fixtures.values()
    )

    print()
    print("==============================")
    print("RESULT")
    print("==============================")

    print(
        f"Total fixtures found across all teams: "
        f"{total}"
    )

    for team, fixtures in all_fixtures.items():

        print()
        print(team)

        for fixture in fixtures:

            kickoff = fixture["kickoff"]

            if kickoff:
                kickoff_text = kickoff.isoformat()
            else:
                kickoff_text = "TBD"

            print(
                f"  {kickoff_text} | "
                f"{fixture['home']} vs "
                f"{fixture['away']} | "
                f"{fixture['competition']}"
)
