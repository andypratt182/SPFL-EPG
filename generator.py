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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
