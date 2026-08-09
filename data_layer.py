"""
data_layer.py

Small source-independent data layer for SPFL fixture data.

Source adapters write normalised fixture data to:

    data/fixtures.json

The rest of the EPG system reads that file through fixtures.py.

This keeps external fixture sources completely separate from
the EPG generation code.
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

    Existing fixture data is replaced with the newly downloaded
    dataset. This is intentional because the source adapter is
    responsible for providing the current fixture list.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "fixtures": fixtures,
    }

    temporary_file = FIXTURES_FILE.with_suffix(
        ".tmp"
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

    temporary_file.replace(
        FIXTURES_FILE
    )


def load_fixtures() -> list[dict]:
    """
    Load normalised fixtures from data/fixtures.json.

    Returns an empty list if the file does not exist
    or cannot be read.
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
            []
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):

        return []
