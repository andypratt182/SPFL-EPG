"""
scraper.py

Fetches SPFL club fixtures directly from ESPN's JSON schedule endpoints.

No API key is required.

Competitions:
    Scottish Premiership -> sco.1
    Scottish Cup         -> sco.tennents
    Scottish League Cup  -> sco.cis

The public interface is intentionally unchanged so that fixtures.py,
generator.py and xmltv.py do not need to change.

Returns fixtures in the format expected by fixtures.py:

    {
        "home": str,
        "away": str,
        "kickoff": datetime | None,
        "competition": str,
    }
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


UK_TZ = ZoneInfo("Europe/London")

BASE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer"
)

# ESPN competition identifiers.
COMPETITIONS = (
    "sco.1",          # Scottish Premiership
    "sco.tennents",   # Scottish Cup
    "sco.cis",        # Scottish League Cup
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 20

# Delay between ESPN requests.
REQUEST_DELAY_SECONDS = 1.0


def _parse_kickoff(value: str | None) -> datetime | None:
    """
    Convert ESPN's UTC ISO timestamp into a Europe/London datetime.

    Example:
        2026-07-31T19:00Z

    becomes a timezone-aware datetime in UK_TZ.
    """
    if not value:
        return None

    try:
        # ESPN normally supplies timestamps ending in Z.
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

        return dt.astimezone(UK_TZ)

    except ValueError:
        print(f"WARNING: unable to parse ESPN date: {value}")
        return None


def _get_competitor_team(competitor: dict) -> str | None:
    """
    Extract the display name of a team from an ESPN competitor object.
    """
    team = competitor.get("team") or {}

    return (
        team.get("displayName")
        or team.get("shortDisplayName")
        or team.get("name")
    )


def fetch_team_competition_fixtures(
    team_name: str,
    espn_id: int,
    competition_id: str,
    debug: bool = False,
) -> list[dict]:
    """
    Fetch fixtures for one team from one ESPN competition.

    Returns:
        [
            {
                "home": str,
                "away": str,
                "kickoff": datetime | None,
                "competition": str,
                "_espn_id": str,
            }
        ]
    """

    url = (
        f"{BASE_URL}/{competition_id}"
        f"/teams/{espn_id}/schedule"
    )

    print(f"  Fetching {competition_id} for {team_name}...")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"ESPN returned invalid JSON for {team_name} "
            f"({competition_id})"
        ) from exc

    if data.get("status") != "success":
        raise RuntimeError(
            f"ESPN returned unsuccessful status for "
            f"{team_name} ({competition_id}): "
            f"{data.get('status')}"
        )

    events = data.get("events") or []

    if debug:
        print(
            f"    ESPN returned {len(events)} event(s)"
        )

    fixtures = []

    for event in events:
        event_id = event.get("id")

        if not event_id:
            print(
                f"WARNING: ESPN event without ID for "
                f"{team_name} ({competition_id})"
            )
            continue

        date_value = event.get("date")

        kickoff = _parse_kickoff(date_value)

        competitions = event.get("competitions") or []

        if not competitions:
            print(
                f"WARNING: ESPN event {event_id} has no "
                f"competition data"
            )
            continue

        competition = competitions[0]

        competitors = competition.get("competitors") or []

        if len(competitors) < 2:
            print(
                f"WARNING: ESPN event {event_id} has fewer "
                f"than two competitors"
            )
            continue

        home = None
        away = None

        for competitor in competitors:
            home_away = competitor.get("homeAway")
            name = _get_competitor_team(competitor)

            if not name:
                continue

            if home_away == "home":
                home = name
            elif home_away == "away":
                away = name

        if not home or not away:
            print(
                f"WARNING: unable to determine home/away teams "
                f"for ESPN event {event_id}"
            )
            continue

        # Prefer ESPN's own league name.
        league = data.get("league") or {}

        competition_name = (
            league.get("name")
            or event.get("season", {}).get("displayName")
            or competition_id
        )

        fixtures.append(
            {
                "home": home,
                "away": away,
                "kickoff": kickoff,
                "competition": competition_name,
                "_espn_id": str(event_id),
            }
        )

    return fixtures


def fetch_team_fixtures(
    team_name: str,
    espn_id: int,
    debug: bool = False,
) -> list[dict]:
    """
    Fetch all supported competitions for one team.

    Returns a combined, de-duplicated list of fixtures.
    """

    all_fixtures = []
    seen_event_ids = set()

    for index, competition_id in enumerate(COMPETITIONS):

        try:
            fixtures = fetch_team_competition_fixtures(
                team_name=team_name,
                espn_id=espn_id,
                competition_id=competition_id,
                debug=debug,
            )

            for fixture in fixtures:
                event_id = fixture.pop("_espn_id", None)

                if event_id and event_id in seen_event_ids:
                    continue

                if event_id:
                    seen_event_ids.add(event_id)

                all_fixtures.append(fixture)

        except requests.RequestException as exc:
            raise RuntimeError(
                f"Failed to fetch ESPN data for "
                f"{team_name} ({competition_id}): {exc}"
            ) from exc

        except RuntimeError:
            raise

        # Don't sleep after the final request.
        if index < len(COMPETITIONS) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    all_fixtures.sort(
        key=lambda fixture: (
            fixture["kickoff"] is None,
            fixture["kickoff"],
        )
    )

    return all_fixtures


def fetch_all_teams(
    team_espn_ids: dict,
    debug_first: bool = False,
) -> dict:
    """
    Fetch all supported fixtures for every team.

    team_espn_ids:
        Dictionary mapping team name -> ESPN team ID.

    Returns:
        {
            "Rangers": [
                {
                    "home": "...",
                    "away": "...",
                    "kickoff": datetime | None,
                    "competition": "..."
                }
            ],
            ...
        }

    A failed ESPN request raises an exception rather than silently
    returning an empty list. This prevents GitHub Actions from
    accidentally publishing an empty/broken EPG.
