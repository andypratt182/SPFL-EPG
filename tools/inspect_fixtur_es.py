import sys
from pathlib import Path
from collections import Counter
from datetime import datetime

# ---------------------------------------------------------
# Make repository root importable
# ---------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(
    0,
    str(ROOT_DIR)
)

from sources.fixtur_es import (
    TEAM_CALENDARS,
    build_team_feed_url,
    download_ics,
    parse_events,
)


# =========================================================
# COMPETITION CALENDARS TO TEST
# =========================================================
#
# These are deliberately kept separate from the team
# calendars. We want to establish exactly which Fixtur.es
# competition feeds exist and what they contain.
#
# If a URL returns 404, that is recorded as a failed
# candidate rather than causing the diagnostic to stop.
# =========================================================

COMPETITION_CALENDARS = {
    "Scottish Premiership": [
        "https://ics.fixtur.es/v2/league/scottish-premier-league.ics",
        "https://ics.fixtur.es/v2/league/scottish-premiership.ics",
    ],

    "Scottish Championship": [
        "https://ics.fixtur.es/v2/league/scottish-championship.ics",
    ],

    "Scottish League One": [
        "https://ics.fixtur.es/v2/league/scottish-league-one.ics",
    ],

    "Scottish League Two": [
        "https://ics.fixtur.es/v2/league/scottish-league-two.ics",
    ],

    "Scottish Cup": [
        "https://ics.fixtur.es/v2/league/scottish-cup.ics",
    ],

    "Scottish League Cup": [
        "https://ics.fixtur.es/v2/league/scottish-league-cup.ics",
        "https://ics.fixtur.es/v2/league/scottish-league-cup.ics",
    ],
}


# =========================================================
# HELPERS
# =========================================================

def parse_ics_events_raw(ics_text):
    """
    Parse VEVENT blocks directly without relying on the
    normal fixture importer.

    Returns a list of dictionaries containing every raw
    ICS property found in each event.
    """

    events = []

    blocks = ics_text.split("BEGIN:VEVENT")

    for block in blocks[1:]:

        if "END:VEVENT" not in block:
            continue

        block = block.split(
            "END:VEVENT",
            1
        )[0]

        event = {}

        for raw_line in block.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1
            )

            event[key] = value

        if event:
            events.append(event)

    return events


def get_event_date(event, field):

    value = event.get(field)

    if not value:
        return None

    # Handle common UTC format.
    for fmt in (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
        "%Y%m%d",
    ):

        try:
            return datetime.strptime(
                value,
                fmt
            )
        except ValueError:
            pass

    return None


def event_signature(event):

    return (
        event.get("DTSTART"),
        event.get("SUMMARY"),
    )


def contains_competition_information(event):

    competition_words = (
        "competition",
        "league",
        "premiership",
        "championship",
        "scottish cup",
        "league cup",
        "champions league",
        "europa league",
        "conference league",
        "cup",
        "uefa",
    )

    fields_to_check = (
        "SUMMARY",
        "DESCRIPTION",
        "LOCATION",
        "CATEGORIES",
        "CLASS",
        "UID",
    )

    for field in fields_to_check:

        value = str(
            event.get(field, "")
        ).lower()

        for word in competition_words:

            if word in value:
                return True

    return False


def date_range(events):

    dates = []

    for event in events:

        date = get_event_date(
            event,
            "DTSTART"
        )

        if date:
            dates.append(date)

    if not dates:
        return None, None

    return (
        min(dates),
        max(dates),
    )


def contains_2026_27(events):

    for event in events:

        date = get_event_date(
            event,
            "DTSTART"
        )

        if not date:
            continue

        if (
            datetime(2026, 7, 1)
            <= date
            <= datetime(2027, 6, 30)
        ):
            return True

    return False


def build_team_signatures():

    signatures = set()

    print()
    print("=" * 70)
    print("BUILDING TEAM-CALENDAR REFERENCE DATASET")
    print("=" * 70)

    for team_name, slug in TEAM_CALENDARS.items():

        print(
            f"Loading {team_name}..."
        )

        try:

            url = build_team_feed_url(
                slug
            )

            ics = download_ics(
                url
            )

            events = parse_ics_events_raw(
                ics
            )

            for event in events:

                signatures.add(
                    event_signature(event)
                )

        except Exception as error:

            print(
                f"ERROR loading "
                f"{team_name}: {error}"
            )

    print()
    print(
        f"Unique team-calendar "
        f"signatures: {len(signatures)}"
    )

    return signatures


# =========================================================
# MAIN DIAGNOSTIC
# =========================================================

def main():

    print()
    print("=" * 70)
    print("FIXTUR.ES COMPETITION-CALENDAR DIAGNOSTIC")
    print("=" * 70)

    print()
    print(
        "Testing competition calendar candidates."
    )

    team_signatures = (
        build_team_signatures()
    )

    all_successful_competitions = []

    # -----------------------------------------------------
    # Test every competition candidate
    # -----------------------------------------------------

    for competition_name, urls in (
        COMPETITION_CALENDARS.items()
    ):

        print()
        print("#" * 70)
        print(
            f"COMPETITION: {competition_name}"
        )
        print("#" * 70)

        successful = False

        for url in urls:

            print()
            print(
                f"URL: {url}"
            )

            try:

                ics = download_ics(
                    url
                )

                print(
                    "HTTP status: 200"
                )

                print(
                    f"Downloaded ICS "
                    f"characters: {len(ics)}"
                )

                events = parse_ics_events_raw(
                    ics
                )

                print(
                    f"VEVENT count: "
                    f"{len(events)}"
                )

                if not events:
                    print(
                        "No VEVENT records found."
                    )
                    continue

                successful = True

                all_successful_competitions.append(
                    (
                        competition_name,
                        url,
                        events,
                    )
                )

                # -------------------------------------------------
                # Raw events
                # -------------------------------------------------

                print()
                print(
                    "--- FIRST RAW EVENTS ---"
                )

                for index, event in enumerate(
                    events[:3],
                    start=1
                ):

                    print()
                    print(
                        f"RAW EVENT {index}"
                    )

                    for key, value in event.items():

                        print(
                            f"{key}: {value}"
                        )

                # -------------------------------------------------
                # Competition metadata
                # -------------------------------------------------

                competition_events = [
                    event
                    for event in events
                    if contains_competition_information(
                        event
                    )
                ]

                print()
                print(
                    "--- COMPETITION INFORMATION ---"
                )

                print(
                    f"Events containing "
                    f"competition-related information: "
                    f"{len(competition_events)}"
                )

                if competition_events:

                    example = (
                        competition_events[0]
                    )

                    print(
                        "Example fields:"
                    )

                    for key, value in (
                        example.items()
                    ):

                        lower = str(
                            value
                        ).lower()

                        if any(
                            word in lower
                            for word in (
                                "competition",
                                "league",
                                "premiership",
                                "championship",
                                "cup",
                                "uefa",
                            )
                        ):

                            print(
                                f"  {key}: "
                                f"{value}"
                            )

                # -------------------------------------------------
                # Date range
                # -------------------------------------------------

                first_date, last_date = (
                    date_range(events)
                )

                print()
                print(
                    "--- DATE RANGE ---"
                )

                print(
                    f"First fixture: "
                    f"{first_date}"
                )

                print(
                    f"Last fixture: "
                    f"{last_date}"
                )

                # -------------------------------------------------
                # 2026/27 coverage
                # -------------------------------------------------

                has_current_season = (
                    contains_2026_27(
                        events
                    )
                )

                print()
                print(
                    "--- 2026/27 COVERAGE ---"
                )

                print(
                    f"2026/27 fixtures present: "
                    f"{has_current_season}"
                )

                current_events = []

                for event in events:

                    date = get_event_date(
                        event,
                        "DTSTART"
                    )

                    if not date:
                        continue

                    if (
                        datetime(2026, 7, 1)
                        <= date
                        <= datetime(2027, 6, 30)
                    ):

                        current_events.append(
                            event
                        )

                print(
                    f"2026/27 event count: "
                    f"{len(current_events)}"
                )

                if current_events:

                    print()
                    print(
                        "First 10 2026/27 fixtures:"
                    )

                    for event in current_events[:10]:

                        print(
                            f"  "
                            f"{event.get('DTSTART')} | "
                            f"{event.get('SUMMARY')}"
                        )

                # -------------------------------------------------
                # Team-calendar overlap
                # -------------------------------------------------

                competition_signatures = {
                    event_signature(event)
                    for event in events
                }

                overlap = (
                    competition_signatures
                    & team_signatures
                )

                print()
                print(
                    "--- TEAM-CALENDAR OVERLAP ---"
                )

                print(
                    f"Competition fixtures: "
                    f"{len(competition_signatures)}"
                )

                print(
                    f"Matching team-calendar fixtures: "
                    f"{len(overlap)}"
                )

                if competition_signatures:

                    percentage = (
                        len(overlap)
                        / len(competition_signatures)
                        * 100
                    )

                    print(
                        f"Overlap percentage: "
                        f"{percentage:.1f}%"
                    )

                # -------------------------------------------------
                # Duplicate records inside competition feed
                # -------------------------------------------------

                counts = Counter(
                    event_signature(event)
                    for event in events
                )

                duplicates = [
                    signature
                    for signature, count
                    in counts.items()
                    if count > 1
                ]

                print()
                print(
                    "--- DUPLICATES ---"
                )

                print(
                    f"Duplicate fixture "
                    f"signatures: "
                    f"{len(duplicates)}"
                )

                # -------------------------------------------------
                # Property inventory
                # -------------------------------------------------

                properties = Counter()

                for event in events:

                    for key in event:

                        properties[key] += 1

                print()
                print(
                    "--- ICS PROPERTY INVENTORY ---"
                )

                for key, count in sorted(
                    properties.items()
                ):

                    print(
                        f"{count:6}  {key}"
                    )

                # We found a working URL, so don't
                # test further candidates for this
                # competition.
                break

            except Exception as error:

                print(
                    f"FAILED: {error}"
                )

        if not successful:

            print()
            print(
                "NO WORKING CALENDAR FOUND "
                f"FOR {competition_name}"
            )

    # -----------------------------------------------------
    # Overall summary
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("COMPETITION CALENDAR SUMMARY")
    print("=" * 70)

    print()
    print(
        f"Successful competition calendars: "
        f"{len(all_successful_competitions)}"
    )

    for (
        competition_name,
        url,
        events,
    ) in all_successful_competitions:

        first_date, last_date = (
            date_range(events)
        )

        current_count = sum(
            1
            for event in events
            if (
                get_event_date(
                    event,
                    "DTSTART"
                )
                and
                datetime(2026, 7, 1)
                <= get_event_date(
                    event,
                    "DTSTART"
                )
                <= datetime(2027, 6, 30)
            )
        )

        overlap = len(
            {
                event_signature(event)
                for event in events
            }
            & team_signatures
        )

        print()
        print(
            f"{competition_name}"
        )

        print(
            f"  URL: {url}"
        )

        print(
            f"  Events: {len(events)}"
        )

        print(
            f"  Date range: "
            f"{first_date} -> {last_date}"
        )

        print(
            f"  2026/27 events: "
            f"{current_count}"
        )

        print(
            f"  Team-calendar overlap: "
            f"{overlap}"
        )

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
