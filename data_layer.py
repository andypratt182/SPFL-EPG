"""
data_layer.py

Fixture data ingestion and storage layer.

External fixture source
        ↓
    data_layer.py
        ↓
data/fixtures.json
        ↓
    fixtures.py
        ↓
    generator.py

The EPG does not communicate directly with any external fixture
provider.

This allows the fixture source to be replaced later without
changing the EPG generation system.
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
    Validate and normalise a fixture.

    Internal fixture format:

        {
            "home": "Rangers",
            "away": "Celtic",
            "kickoff": "2026-08-15T12:30:00Z",
            "competition": "Scottish Premiership"
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

        kickoff = (
            parsed
            .astimezone(timezone.utc)
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


def save_fixtures(
    fixtures: list[dict],
):
    """
    Safely save normalised fixtures.

    The existing fixtures.json structure is preserved:

        {
            "generated_at": "...",
            "fixtures": [...]
        }

    The file is replaced atomically so a failed write cannot leave
    a partially written fixtures.json.
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
        "generated_at": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
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
    Load the current fixture store.
    """

    if not FIXTURES_FILE.exists():

        print(
            f"WARNING: fixture file not found: "
            f"{FIXTURES_FILE}"
        )

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
            f"WARNING: unable to load "
            f"{FIXTURES_FILE}: {exc}"
        )

        return []

    fixtures = data.get(
        "fixtures",
        [],
    )

    if not isinstance(
        fixtures,
        list,
    ):
        print(
            "WARNING: 'fixtures' is not "
            "a list."
        )

        return []

    return fixtures


def test_data_layer():
    """
    Run a safe self-test.

    This does NOT contact ESPN.

    It tests fixture validation without modifying the real
    fixtures.json file.
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

    result = normalise_fixture(
        test_fixture
    )

    if result is None:

        raise RuntimeError(
            "Data-layer self-test failed."
        )

    print(
        "Fixture validation: OK"
    )

    print(
        "Normalised fixture:"
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        "Data layer test passed."
    )


if __name__ == "__main__":
    test_data_layer()
