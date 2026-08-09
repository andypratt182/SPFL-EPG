"""
data_layer.py

Small data layer between external fixture sources and the EPG.

External sources should write normalised fixture data through
this module.

The rest of the EPG only reads:

    data/fixtures.json

This keeps the EPG independent from the actual fixture source.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"


def save_fixtures(fixtures: list[dict]) -> None:
    """
    Save normalised fixtures to data/fixtures.json.

    Existing data is replaced only after the new fixture list
    has been validated and successfully written.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    normalised = []

    for fixture in fixtures:

        required = (
            "home",
            "away",
            "kickoff",
        )

        if not all(
            fixture.get(field)
            for field in required
        ):
            continue

        normalised.append(
            {
                "home": str(
                    fixture["home"]
                ),
                "away": str(
                    fixture["away"]
                ),
                "kickoff": str(
                    fixture["kickoff"]
                ),
                "competition": str(
                    fixture.get(
                        "competition",
                        "Unknown",
                    )
                ),
            }
        )

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
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
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.write("\n")

    temporary_file.replace(
        FIXTURES_FILE
    )

    print(
        f"Saved {len(normalised)} fixtures "
        f"to {FIXTURES_FILE}"
    )


def load_fixtures() -> list[dict]:
    """
    Load the current normalised fixture data.
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

        return data.get(
            "fixtures",
            [],
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):

        return []
