import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


UK_TZ = ZoneInfo("Europe/London")

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# ESPN competition identifiers
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
REQUEST_DELAY_SECONDS = 1.0


def parse_kickoff(value):
    """Convert ESPN UTC timestamp to Europe/London."""
    if not value:
        return None

    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=ZoneInfo("UTC")
            )

        return dt.astimezone(UK_TZ)

    except ValueError:
        print(
            f"WARNING: Could not parse ESPN date: {value}"
        )
        return None


def get_team_name(competitor):
    team = competitor.get("team") or {}

    return (
        team.get("displayName")
        or team.get("shortDisplayName")
        or team.get("name")
    )


def fetch_team_competition_fixtures(
    team_name,
    espn_id,
    competition_id,
    debug=False,
):
    url = (
        f"{BASE_URL}/{competition_id}"
        f"/teams/{espn_id}/schedule"
    )

    print(
        f"  Fetching {competition_id} "
        f"for {team_name}..."
    )

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
            f"ESPN returned invalid JSON for "
            f"{team_name} ({competition_id})"
        ) from exc

    if data.get("status") != "success":
        raise RuntimeError(
            f"ESPN returned status "
            f"{data.get('status')} for "
            f"{team_name} ({competition_id})"
        )

    events = data.get("events") or []

    if debug:
        print(
            f"    {competition_id}: "
            f"{len(events)} event(s)"
        )

    fixtures = []

    for event in events:
        event_id = event.get("id")

        if not event_id:
            print(
                f"WARNING: event without ID for "
                f"{team_name} ({competition_id})"
            )
            continue

        competitions = event.get("competitions") or []

        if not competitions:
            print(
                f"WARNING: event {event_id} has "
                f"no competition data"
            )
            continue

        competition_data = competitions[0]
        competitors = (
            competition_data.get("competitors")
            or []
        )

        home = None
        away = None

        for competitor in competitors:
            team = get_team_name(competitor)

            if not team:
                continue

            if competitor.get("homeAway") == "home":
                home = team

            elif competitor.get("homeAway") == "away":
                away = team

        if not home or not away:
            print(
                f"WARNING: Could not determine "
                f"home/away for ESPN event {event_id}"
            )
            continue

        league = data.get("league") or {}

        competition_name = (
            league.get("name")
            or competition_id
        )

        fixture = {
            "home": home,
            "away": away,
            "kickoff": parse_kickoff(
                event.get("date")
            ),
            "competition": competition_name,
            "_espn_id": str(event_id),
        }

        fixtures.append(fixture)

    return fixtures


def fetch_team_fixtures(
    team_name,
    espn_id,
    debug=False,
):
    all_fixtures = []
    seen_event_ids = set()

    for index, competition_id in enumerate(
        COMPETITIONS
    ):
        fixtures = fetch_team_competition_fixtures(
            team_name=team_name,
            espn_id=espn_id,
            competition_id=competition_id,
            debug=debug,
        )

        for fixture in fixtures:
            event_id = fixture.pop(
                "_espn_id",
                None,
            )

            if event_id in seen_event_ids:
                continue

            if event_id:
                seen_event_ids.add(event_id)

            all_fixtures.append(fixture)

        if index < len(COMPETITIONS) - 1:
            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    all_fixtures.sort(
        key=lambda fixture: (
            fixture["kickoff"] is None,
            fixture["kickoff"],
        )
    )

    return all_fixtures


def fetch_all_teams(
    team_espn_ids,
    debug_first=False,
):
    results = {}

    print()
    print("==============================")
    print("FETCHING FIXTURES FROM ESPN JSON")
    print("==============================")

    first = True

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
                debug=(
                    debug_first and first
                ),
            )

            first = False

            print(
                f"{team_name}: found "
                f"{len(fixtures)} fixture(s)"
            )

            results[team_name] = fixtures

        except Exception as exc:
            print(
                f"ERROR: failed to fetch "
                f"fixtures for {team_name}: "
                f"{exc}"
            )
            raise

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    return results


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
    print(
        f"TOTAL FIXTURES FOUND: {total}"
    )
    print("==============================")

    for team, fixtures in all_fixtures.items():
        print()
        print(f"{team}:")

        for fixture in fixtures:
            print(
                f"  {fixture['kickoff']} | "
                f"{fixture['home']} vs "
                f"{fixture['away']} | "
                f"{fixture['competition']}"
            )
