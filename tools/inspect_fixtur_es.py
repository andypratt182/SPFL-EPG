import sys
from pathlib import Path

# Make the repository root importable.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

from sources.fixtur_es import (
    TEAM_CALENDARS,
    build_team_feed_url,
    download_ics,
    parse_events,
)


def main():

    print()
    print("=" * 70)
    print("FIXTUR.ES RAW ICS FIELD INSPECTION")
    print("=" * 70)

    # -----------------------------------------------------
    # Inspect the first few events from every team
    # -----------------------------------------------------

    for team_name, slug in TEAM_CALENDARS.items():

        print()
        print("=" * 70)
        print(f"TEAM: {team_name}")
        print(
            f"URL: {build_team_feed_url(slug)}"
        )
        print("=" * 70)

        try:

            ics_text = download_ics(
                build_team_feed_url(slug)
            )

            events = parse_events(
                ics_text
            )

        except Exception as error:

            print(
                f"ERROR: {error}"
            )

            continue

        print(
            f"VEVENT records: {len(events)}"
        )

        # -------------------------------------------------
        # Show first 3 complete raw events
        # -------------------------------------------------

        for index, event in enumerate(
            events[:3],
            start=1
        ):

            print()
            print(
                f"--- RAW EVENT {index} ---"
            )

            for key, value in event.items():

                print(
                    f"{key}: {value}"
                )

    # -----------------------------------------------------
    # Property frequency analysis
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("PROPERTY FREQUENCY ANALYSIS")
    print("=" * 70)

    property_counts = {}

    for team_name, slug in TEAM_CALENDARS.items():

        print(
            f"\nScanning {team_name}..."
        )

        try:

            ics_text = download_ics(
                build_team_feed_url(slug)
            )

            events = parse_events(
                ics_text
            )

        except Exception as error:

            print(
                f"ERROR: {error}"
            )

            continue

        for event in events:

            for key in event:

                if key not in property_counts:
                    property_counts[key] = 0

                property_counts[key] += 1

    print()

    for key, count in sorted(
        property_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):

        print(
            f"{count:6}  {key}"
        )

    print()
    print("=" * 70)
    print("RAW ICS INSPECTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":

    main()
