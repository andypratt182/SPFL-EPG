"""
sources/fixture_download.py

Fixture Download source adapter.

This version first tests the actual JSON export endpoint for
Rangers / Scottish Premiership before expanding to all teams.
"""

import sys
from pathlib import Path

import requests


# ------------------------------------------------------------
# Make repository root available to Python
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data_layer import save_fixtures


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

BASE_URL = "https://fixturedownload.com"

REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/json,"
        "text/plain,"
        "*/*"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


# ------------------------------------------------------------
# Test configurations
# ------------------------------------------------------------

TESTS = [
    {
        "name": "Rangers - Scottish Premiership",
        "url": (
            f"{BASE_URL}/"
            "football/scottish-premiership/"
            "rangers"
        ),
    },
]


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    print(
        "=============================="
    )

    print(
        "FIXTURE DOWNLOAD JSON TEST"
    )

    print(
        "=============================="
    )

    session = requests.Session()
    session.headers.update(HEADERS)

    all_fixtures = []

    for test in TESTS:

        print()
        print(
            "--------------------------------"
        )

        print(
            test["name"]
        )

        print(
            "--------------------------------"
        )

        url = test["url"]

        print(
            f"URL: {url}"
        )

        try:

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )

        except requests.RequestException as exc:

            print(
                f"REQUEST ERROR: {exc}"
            )

            continue

        print(
            f"HTTP status: "
            f"{response.status_code}"
        )

        print(
            f"Content-Type: "
            f"{response.headers.get('content-type')}"
        )

        print()

        print(
            "Response preview:"
        )

        print(
            response.text[:1000]
        )

        print()

        if response.status_code != 200:

            print(
                "REQUEST FAILED"
            )

            continue

        try:

            data = response.json()

        except ValueError:

            print(
                "Response is not JSON."
            )

            continue

        print(
            "JSON response received."
        )

        print(
            f"Python type: "
            f"{type(data).__name__}"
        )

        if isinstance(data, list):

            print(
                f"Records: {len(data)}"
            )

        elif isinstance(data, dict):

            print(
                "Top-level keys:"
            )

            print(
                list(data.keys())
            )

        # We are only testing the endpoint at this stage.
        # Do not attempt to save unverified data.

    print()
    print(
        "=============================="
    )

    print(
        "TEST COMPLETE"
    )

    print(
        "=============================="
    )


if __name__ == "__main__":
    main()
