import os
import requests


SPORTMONKS_API_TOKEN = os.getenv("SPORTMONKS_API_TOKEN")

if not SPORTMONKS_API_TOKEN:
    raise RuntimeError(
        "SPORTMONKS_API_TOKEN environment variable is not set"
    )


BASE_URL = "https://api.sportmonks.com/v3/football"


SEARCH_GROUPS = {
    "FK Shkendija 79": [
        "Shkendija",
        "FK Shkendija",
        "Shkendija Tetovo",
    ],
    "St Johnstone": [
        "St Johnstone",
        "St. Johnstone",
        "St Johnstone FC",
    ],
    "St Mirren": [
        "St Mirren",
        "St. Mirren",
        "St Mirren FC",
    ],
}


def search_team(name):
    """Search Sportmonks for a team name."""

    url = f"{BASE_URL}/teams/search/{name}"

    params = {
        "api_token": SPORTMONKS_API_TOKEN,
        "include": "venue",
    }

    print()
    print("=" * 70)
    print(f"SEARCH: {name}")
    print("=" * 70)

    try:
        response = requests.get(
            url,
            params=params,
            timeout=30,
        )

        print(f"HTTP status: {response.status_code}")

        if response.status_code != 200:
            print(
                f"Request failed: "
                f"{response.text[:500]}"
            )
            return []

        data = response.json()

        teams = data.get("data", [])

        if not teams:
            print("No teams found.")
            return []

        print(f"Teams returned: {len(teams)}")

        for team in teams:

            print()
            print("TEAM")
            print("-" * 40)

            print(
                f"Name:     {team.get('name')}"
            )

            print(
                f"ID:       {team.get('id')}"
            )

            print(
                f"Shortcode: {team.get('short_code')}"
            )

            print(
                f"Country:  {team.get('country_id')}"
            )

            venue = team.get("venue")

            if venue:

                print()
                print("VENUE")
                print("-" * 40)

                print(
                    f"Venue ID:   {venue.get('id')}"
                )

                print(
                    f"Venue Name: {venue.get('name')}"
                )

                print(
                    f"Address:    {venue.get('address')}"
                )

                print(
                    f"City:       {venue.get('city')}"
                )

                print(
                    f"Capacity:   {venue.get('capacity')}"
                )

            else:

                print()
                print("VENUE")
                print("-" * 40)
                print("No venue returned.")

        return teams

    except requests.RequestException as exc:

        print(
            f"Request error: {exc}"
        )

        return []


def main():

    print("=" * 70)
    print("SPORTMONKS ALTERNATIVE TEAM NAME DIAGNOSTIC")
    print("=" * 70)

    all_results = {}

    for canonical_name, alternatives in SEARCH_GROUPS.items():

        print()
        print()
        print("#" * 70)
        print(f"CANONICAL TEAM: {canonical_name}")
        print("#" * 70)

        found = False

        for search_name in alternatives:

            teams = search_team(search_name)

            if teams:

                found = True

                all_results[canonical_name] = {
                    "search": search_name,
                    "teams": teams,
                }

                print()
                print(
                    f"FOUND using search: {search_name}"
                )

                # Stop after the first successful search.
                break

        if not found:

            print()
            print(
                f"NOT FOUND: {canonical_name}"
            )

            all_results[canonical_name] = None

    print()
    print()
    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    for canonical_name, result in all_results.items():

        if result:

            print(
                f"{canonical_name}: FOUND "
                f"using '{result['search']}'"
            )

            for team in result["teams"]:

                venue = team.get("venue")

                venue_name = (
                    venue.get("name")
                    if venue
                    else "NO VENUE"
                )

                venue_id = (
                    venue.get("id")
                    if venue
                    else "NO VENUE ID"
                )

                print(
                    f"  Team: {team.get('name')} "
                    f"(ID {team.get('id')})"
                )

                print(
                    f"  Venue: {venue_name} "
                    f"(ID {venue_id})"
                )

        else:

            print(
                f"{canonical_name}: NOT FOUND"
            )


if __name__ == "__main__":
    main()
