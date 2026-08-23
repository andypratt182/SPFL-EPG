"""
generator.py

Entry point: fetches fixtures for every SPFL channel and writes the
combined XMLTV output to output/spfl.xml.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fixtures import get_fixtures
from teams import SPFL_TEAMS
from xmltv import create_xmltv

logger = logging.getLogger(__name__)

OUTPUT_FOLDER = Path("output")
OUTPUT_FILE = OUTPUT_FOLDER / "spfl.xml"

# Kept separate from OUTPUT_FOLDER: everything in output/ gets
# published to the public GitHub Pages site by the workflow, and
# this log is an internal debugging aid, not something to publish.
LOG_FOLDER = Path("logs")
WARNINGS_LOG_FILE = LOG_FOLDER / "warnings.log"


def main() -> None:
    OUTPUT_FOLDER.mkdir(exist_ok=True)

    all_fixtures = []

    for channel_id, team in SPFL_TEAMS.items():
        logger.info("Fetching fixtures for %s", team["name"])

        try:
            fixtures = get_fixtures(team)
        except Exception as error:  # noqa: BLE001 - one team failing shouldn't stop the rest
            logger.error("Error loading %s: %s", team["name"], error)
            continue

        if not fixtures:
            logger.info("  No upcoming fixtures")
            continue

        for match in fixtures:
            # Tag with the IPTV channel ID so XMLTV knows where to place it.
            match["channel_id"] = channel_id
            logger.info(
                "  %s - %s vs %s - %s",
                match["kickoff"], match["home"], match["away"], match["competition"],
            )
            all_fixtures.append(match)

    logger.info("Total fixtures found: %d", len(all_fixtures))

    create_xmltv(all_fixtures, str(OUTPUT_FILE))

    logger.info("SPFL EPG generated successfully")


if __name__ == "__main__":
    LOG_FOLDER.mkdir(exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    # WARNING and above only -- venue/logo gaps, unparseable
    # fixtures, download errors. Kept separate from the console
    # output so they're easy to find without scrolling a full run's
    # INFO-level fixture listing in the Actions log.
    file_handler = logging.FileHandler(WARNINGS_LOG_FILE, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])

    main()

    if WARNINGS_LOG_FILE.stat().st_size > 0:
        logger.info("Warnings were logged this run -- see %s", WARNINGS_LOG_FILE)
