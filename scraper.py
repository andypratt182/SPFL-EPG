"""
Rangers-only ESPN regional API diagnostic.

Makes exactly three requests:

1. Scottish Premiership
2. Scottish Cup
3. Scottish League Cup

This is a diagnostic only. It does not modify fixtures.py,
generator.py, or any EPG output.
"""

import requests


RANGERS_ID = 257

# Regional ESPN API host.
ESPN_BASE_URL = (
    "https://africa.espn.com/apis/site/v2/sports/soccer"
)

COMPETITIONS = {
    "Scottish Premiership": "sco.1",
    "Scottish Cup": "sco.cup",
    "Scottish League Cup": "sco.league_cup",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.espn.com/",
    "Origin": "https://www.espn.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

TIMEOUT = 20


def test_competition(
    session,
    competition_name,
    competition_code,
):
    url = (
        f"{ESPN_BASE_URL}/"
        f"{competition_code}/"
        f"teams/{RANGERS_ID}/schedule"
    )

    print()
    print("--------------------------------")
    print(competition_name)
    print("--------------------------------")
    print(f"URL: {url}")

    try:
        response = session.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        print(f"HTTP status: {response.status_code}")

        if response.status_code != 200:
            print("REQUEST FAILED")

            print(
                "Response preview:"
            )

            print(
                response.text[:500]
            )

            return False

        data = response.json()

        print(
            f"JSON status: "
            f"{data.get('status')}"
        )

        season = data.get("season", {})

        print(
            f"Season: "
            f"{season.get('displayName')}"
        )

        team = data.get("team", {})

        print(
            f"Team: "
            f"{team.get('displayName')}"
        )

        events = data.get(
            "events",
            []
        )

        print(
            f"Events returned: "
            f"{len(events)}"
        )

        for event in events:

            print(
                f"  {event.get('date')} | "
                f"{event.get('name')} | "
                f"{event.get('shortName')}"
            )

        return True

    except requests.RequestException as exc:

        print(
            f"REQUEST ERROR: {exc}"
        )

        return False

    except ValueError as exc:

        print(
            f"INVALID JSON: {exc}"
        )

        return False


def main():

    print("==============================")
    print("ESPN REGIONAL API TEST")
    print("==============================")

    print(
        f"Testing Rangers "
        f"(ESPN ID {RANGERS_ID})"
    )

    print(
        f"Endpoint host: {ESPN_BASE_URL}"
    )

    session = requests.Session()

    successful = 0

    for competition_name, competition_code in COMPETITIONS.items():

        if test_competition(
            session,
            competition_name,
            competition_code,
        ):
            successful += 1

    print()
    print("==============================")
    print("TEST RESULT")
    print("==============================")

    print(
        f"Successful requests: "
        f"{successful}/3"
    )

    if successful == 3:

        print(
            "SUCCESS: regional ESPN API "
            "is accessible from GitHub Actions."
        )

    elif successful > 0:

        print(
            "PARTIAL SUCCESS: some regional "
            "ESPN endpoints are accessible."
        )

    else:

        print(
            "FAILURE: regional ESPN API "
            "is also inaccessible from "
            "GitHub Actions."
        )


if __name__ == "__main__":
    main()
