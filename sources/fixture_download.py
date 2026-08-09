"""
sources/fixture_download.py

Diagnostic test for Fixture Download.

This version deliberately tests ONE team only:
    Rangers

It fetches the Fixture Download "JSON" page and determines where
the actual JSON feed is located.

It does NOT modify data/fixtures.json.
"""

import re
from pathlib import Path
from urllib.parse import urljoin

import requests


# ================================================================
# CONFIGURATION
# ================================================================

BASE_URL = "https://fixturedownload.com"

TEST_URL = (
    "https://fixturedownload.com/"
    "view/json/"
    "scottish-premiership-2026/"
    "rangers"
)


# ================================================================
# HTTP SESSION
# ================================================================

session = requests.Session()

session.headers.update(
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
        "Referer": BASE_URL + "/",
    }
)


# ================================================================
# MAIN
# ================================================================

def main():

    print(
        "=============================="
    )

    print(
        "FIXTURE DOWNLOAD JSON DIAGNOSTIC"
    )

    print(
        "=============================="
    )

    print(
        "Testing Rangers only"
    )

    print(
        f"URL: {TEST_URL}"
    )

    print(
        "--------------------------------"
    )

    try:

        response = session.get(
            TEST_URL,
            timeout=30,
        )

    except requests.RequestException as exc:

        print(
            f"REQUEST ERROR: {exc}"
        )

        return

    print(
        f"HTTP status: "
        f"{response.status_code}"
    )

    print(
        f"Content-Type: "
        f"{response.headers.get('Content-Type')}"
    )

    if response.status_code != 200:

        print(
            "REQUEST FAILED"
        )

        print(
            response.text[:2000]
        )

        return

    html = response.text

    print(
        f"Response length: "
        f"{len(html)} bytes"
    )

    print(
        "--------------------------------"
    )

    # ------------------------------------------------------------
    # Look for JSON-related URLs
    # ------------------------------------------------------------

    print(
        "JSON / FEED URLS FOUND:"
    )

    urls = set()

    # Absolute URLs
    for match in re.findall(
        r'https?://[^"\'<>\s]+',
        html,
        re.IGNORECASE,
    ):

        urls.add(match)

    # Relative URLs
    for match in re.findall(
        r'(?:href|src|data-url|data-src)\s*=\s*["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    ):

        urls.add(
            urljoin(
                TEST_URL,
                match,
            )
        )

    interesting_urls = []

    for url in sorted(urls):

        lower = url.lower()

        if any(
            keyword in lower
            for keyword in (
                "json",
                "feed",
                "download",
                "api",
                "fixture",
            )
        ):

            interesting_urls.append(
                url
            )

            print(
                url
            )

    if not interesting_urls:

        print(
            "NONE FOUND"
        )

    # ------------------------------------------------------------
    # Look for JSON-looking blocks
    # ------------------------------------------------------------

    print(
        "\n--------------------------------"
    )

    print(
        "JSON-LIKE CONTENT BLOCKS:"
    )

    found_blocks = []

    # <pre>
    for match in re.findall(
        r"<pre[^>]*>(.*?)</pre>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):

        found_blocks.append(
            (
                "<pre>",
                match,
            )
        )

    # <code>
    for match in re.findall(
        r"<code[^>]*>(.*?)</code>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):

        found_blocks.append(
            (
                "<code>",
                match,
            )
        )

    # <textarea>
    for match in re.findall(
        r"<textarea[^>]*>(.*?)</textarea>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):

        found_blocks.append(
            (
                "<textarea>",
                match,
            )
        )

    if not found_blocks:

        print(
            "No pre/code/textarea blocks found."
        )

    else:

        for tag, content in found_blocks:

            print(
                f"\nBLOCK: {tag}"
            )

            print(
                content[:3000]
            )

    # ------------------------------------------------------------
    # Search for JSON markers
    # ------------------------------------------------------------

    print(
        "\n--------------------------------"
    )

    print(
        "JSON MARKERS:"
    )

    markers = [
        "MatchNumber",
        "HomeTeam",
        "AwayTeam",
        "DateUtc",
        "Date",
        "Home Team",
        "Away Team",
    ]

    for marker in markers:

        count = html.lower().count(
            marker.lower()
        )

        print(
            f"{marker}: {count}"
        )

    # ------------------------------------------------------------
    # Print useful snippets around JSON markers
    # ------------------------------------------------------------

    print(
        "\n--------------------------------"
    )

    print(
        "CONTENT AROUND MATCH DATA:"
    )

    for marker in (
        "MatchNumber",
        "HomeTeam",
        "AwayTeam",
        "DateUtc",
    ):

        position = html.find(
            marker
        )

        if position != -1:

            start = max(
                0,
                position - 500,
            )

            end = min(
                len(html),
                position + 1500,
            )

            print(
                f"\n--- {marker} ---"
            )

            print(
                html[start:end]
            )

    # ------------------------------------------------------------
    # Search for JavaScript variables
    # ------------------------------------------------------------

    print(
        "\n--------------------------------"
    )

    print(
        "JAVASCRIPT DATA:"
    )

    script_blocks = re.findall(
        r"<script[^>]*>(.*?)</script>",
        html,
        re.IGNORECASE | re.DOTALL,
    )

    for script in script_blocks:

        lower = script.lower()

        if any(
            marker.lower() in lower
            for marker in markers
        ):

            print(
                script[:5000]
            )

    print(
        "\n=============================="
    )

    print(
        "DIAGNOSTIC COMPLETE"
    )

    print(
        "=============================="
    )


if __name__ == "__main__":

    main()
