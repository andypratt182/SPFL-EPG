import os
import sys
import requests


API_BASE = "https://api.sportmonks.com/v3/football"

TEAMS_TO_TEST = [
    "FK Shkendija 79",
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
]


def get_token():
    token = os.environ.get("SPORTMONKS_API_TOKEN")

    if not token:
        print("ERROR: SPORTMONKS_API_TOKEN is not set.")
        sys.exit(1)

    return token


def sportmonks_get(path, token):
    url = f"{API_BASE}/{path}"

    response = requests.get(
        url,
        params={
            "api_token": token
        },
        timeout=30,
    )

    print(
        f"HTTP {response.status_code}: "
        f"{url}"
    )

    if response.status_code != 200:
        print(response.text[:1000])
        return None

    return response.json()


def search_team(team_name, token):
    print()
    print("-" * 70)
    print(f"SEARCHING: {team_name}")

    data = sportmonks_get(
        f"teams/search/{team_name}",
        token,
    )

    if not data:
        return None

    results = data.get("data", [])

    if not results:
        print("  No teams found.")
        return None

    print(f"  Results found: {len(results)}")

    # Try to find the closest exact name first.
    exact = None

    for team in results:
        name = team.get("name", "")

        print(
            f"  Candidate: "
            f"{name} "
            f"(ID {team.get('id')})"
        )

        if name.lower() == team_name.lower():
            exact = team

    if exact:
        return exact

    # Fall back to the first result.
    return results[0]


def get_team_with_venue(team_id, token):
    print(
        f"  Getting team {team_id} "
        f"with venue..."
    )

    data = sportmonks_get(
        f"teams/{team_id}?include=venue",
        token,
    )

    if not data:
        return None

    return data.get("data")


def main():
    token = get_token()

    print("=" * 70)
    print("SPORTMONKS TEAM / VENUE TEST")
    print("=" * 70)
    print()
    print(
        f"Testing {len(TEAMS_TO_TEST)} teams"
    )
    print()

    successful = []
    failed = []

    for team_name in TEAMS_TO_TEST:

        search_result = search_team(
            team_name,
            token,
        )

        if not search_result:
            failed.append(
                (team_name, "Team not found")
            )
            continue

        team_id = search_result.get("id")

        if not team_id:
            failed.append(
                (team_name, "No team ID returned")
            )
            continue

        team = get_team_with_venue(
            team_id,
            token,
        )

        if not team:
            failed.append(
                (team_name, "Unable to retrieve team")
            )
            continue

        venue = team.get("venue")

        venue_id = None
        venue_name = None

        if isinstance(venue, dict):
            venue_id = venue.get("id")
            venue_name = venue.get("name")

        elif venue:
            print(
                f"  Unexpected venue format: "
                f"{type(venue).__name__}"
            )

        result = {
            "requested_name": team_name,
            "sportmonks_name": team.get("name"),
            "team_id": team.get("id"),
            "venue_id": venue_id,
            "venue_name": venue_name,
        }

        successful.append(result)

        print()
        print("  RESULT")
        print(
            f"    Requested name : "
            f"{result['requested_name']}"
        )
        print(
            f"    Sportmonks name: "
            f"{result['sportmonks_name']}"
        )
        print(
            f"    Team ID        : "
            f"{result['team_id']}"
        )
        print(
            f"    Venue ID       : "
            f"{result['venue_id']}"
        )
        print(
            f"    Venue name     : "
            f"{result['venue_name']}"
        )

    print()
    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    print()
    print("SUCCESSFUL")
    print("-" * 70)

    for result in successful:
        print(
            f"{result['requested_name']}"
            f" -> "
            f"{result['sportmonks_name']}"
            f" | Team ID: {result['team_id']}"
            f" | Venue ID: {result['venue_id']}"
            f" | Venue: {result['venue_name']}"
        )

    print()
    print("FAILED")
    print("-" * 70)

    if failed:
        for team_name, reason in failed:
            print(
                f"{team_name}: {reason}"
            )
    else:
        print("None")

    print()
    print("=" * 70)
    print(
        f"Successful: {len(successful)} / "
        f"{len(TEAMS_TO_TEST)}"
    )
    print(
        f"Failed:     {len(failed)} / "
        f"{len(TEAMS_TO_TEST)}"
    )
    print("=" * 70)

    # Make the GitHub Action fail if the API
    # itself could not provide any useful results.
    if not successful:
        print()
        print(
            "ERROR: No usable Sportmonks "
            "team/venue records were returned."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
