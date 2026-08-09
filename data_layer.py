"""
data_layer.py

Fixture data ingestion layer.

This module sits between external fixture sources and the EPG.

External source
        ↓
    data_layer.py
        ↓
data/fixtures.json
        ↓
    fixtures.py
        ↓
    generator.py

The EPG itself never communicates with an external fixture provider.

The source can therefore be replaced later without changing the EPG.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"


def ensure_data_directory():
    """
    Make sure the data directory exists.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def normalise_fixture(fixture: dict) -> dict | None:
    """
    Validate and normalise one fixture.

    Expected internal format:

        {
            "home": "...",
            "away": "...",
            "kickoff": "...",
            "competition": "..."
        }

    Returns None if the fixture is invalid.
    """

    if not isinstance(fixture, dict):
        return None

    home = str(
        fixture.get("home", "")
    ).strip()

    away = str(
        fixture.get("away", "")
    ).strip()

    kickoff = str(
        fixture.get("kickoff", "")
    ).strip()

    competition = str(
        fixture.get(
            "competition",
            "Unknown",
        )
    ).strip()

    if not home:
        return None

    if not away:
        return None

    if not kickoff:
        return None

    # Make sure the timestamp is valid.
    try:
        parsed = datetime.fromisoformat(
            kickoff.replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc,
            )

        # Store consistently as UTC ISO-8601.
        kickoff = (
            parsed.astimezone(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        )

    except ValueError:
        print(
            "WARNING: invalid kickoff "
            f"timestamp: {kickoff}"
        )
        return None

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "competition": (
            competition
            or "Unknown"
        ),
    }


def save_fixtures(fixtures: list[dict]):
    """
    Safely write normalised fixtures to fixtures.json.

    The existing file is replaced only after the new data has
    successfully been prepared.
    """

    ensure_data_directory()

    normalised = []

    for fixture in fixtures:

        item = normalise_fixture(
            fixture
        )

        if item is not None:
            normalised.append(item)

    normalised.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    output = {
        "updated": datetime.now(
            timezone.utc
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        ),
        "fixtures": normalised,
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

        f.write("\n")

    temporary_file.replace(
        FIXTURES_FILE
    )

    print(
        f"Saved {len(normalised)} "
        f"fixture(s) to "
        f"{FIXTURES_FILE}"
    )


def load_fixtures() -> list[dict]:
    """
    Load the current normalised fixture data.

    This is primarily useful for testing and for future data-source
    implementations.
    """

    if not FIXTURES_FILE.exists():
        return []

    try:

        with open(
            FIXTURES_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:

        print(
            "WARNING: unable to load "
            f"{FIXTURES_FILE}: {exc}"
        )

        return []

    fixtures = data.get(
        "fixtures",
        []
    )

    if not isinstance(
        fixtures,
        list,
    ):
        return []

    return fixtures


def test_data_layer():
    """
    Basic self-test.

    This deliberately does not contact ESPN.

    It verifies that the data layer can create, write and read the
    normalised fixture store.
    """

    print(
        "=============================="
    )
    print(
        "TESTING FIXTURE DATA LAYER"
    )
    print(
        "=============================="
    )

    test_fixture = {
        "home": "Rangers",
        "away": "Test Opponent",
        "kickoff": (
            "2026-08-10T19:45:00Z"
        ),
        "competition": (
            "Test Competition"
        ),
    }

    # Keep the test fixture in memory only.
    normalised = normalise_fixture(
        test_fixture
    )

    if normalised is None:
        raise RuntimeError(
            "Data-layer self-test failed: "
            "fixture could not be normalised."
        )

    print(
        "Fixture normalisation: OK"
    )

    print(
        "Data layer is ready."
    )


if __name__ == "__main__":
    test_data_layer()
