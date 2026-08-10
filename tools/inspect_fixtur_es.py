from pathlib import Path
import sys
from datetime import datetime, timezone

# Allow imports from the repository root when running:
# python tools/inspect_fixtur_es.py
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sources import fixtur_es


def print_header(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main():
    print_header("FIXTUR.ES TEAM CALENDAR DIAGNOSTIC")

    # Find the team's configured feed mapping.
    possible_names = [
        "TEAM_FEEDS",
        "TEAM_CALENDARS",
        "TEAM_CALENDAR_URLS",
        "TEAM_FEED_URLS",
    ]

    team_feeds = None

    for name in possible_names:
        value = getattr(fixtur_es, name, None)
        if isinstance(value, dict) and value:
            team_feeds = value
            print(f"Using {name} from sources.fixtur_es")
            break

    if team_feeds is None:
        print()
        print("ERROR: Could not find the team-calendar URL mapping.")
        print()
        print("Available dictionaries in sources.fixtur_es:")

        for name, value in vars(fixtur_es).items():
            if isinstance(value, dict):
                print(f"  {name}: {len(value)} entries")

        return 1

    print(f"Team calendars found: {len(team_feeds)}")

    total_events = 0
    total_2026_27 = 0
    successful = 0
    failed = 0

    for team, url in team_feeds.items():

        print()
        print("-" * 70)
        print(f"TEAM: {team}")
        print(f"URL:  {url}")
        print("-" * 70)

        try:
            # Use the source module's own download/parser functions where
            # available. This keeps the diagnostic aligned with the importer.
            text = None

            download_functions = [
                "download_ics",
                "download_feed",
                "fetch_ics",
                "fetch_feed",
                "get_ics",
                "load_ics",
            ]

            for function_name in download_functions:
                function = getattr(fixtur_es, function_name, None)

                if callable(function):
                    try:
                        text = function(url)
                        break
                    except TypeError:
                        continue

            # If the importer doesn't expose a downloader, use urllib here.
            if text is None:
                import urllib.request

                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "SPFL-EPG/1.0",
                    },
                )

                with urllib.request.urlopen(request, timeout=30) as response:
                    status = response.status
                    text = response.read().decode("utf-8", errors="replace")

                print(f"HTTP status: {status}")

            if not text:
                print("ERROR: Empty calendar response")
                failed += 1
                continue

            # If the downloader returned bytes, decode them.
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")

            # Count raw VEVENT blocks.
            event_count = text.count("BEGIN:VEVENT")
            total_events += event_count

            print(f"Downloaded characters: {len(text)}")
            print(f"VEVENT records: {event_count}")

            # Parse the events using a lightweight ICS parser.
            events = parse_events(text)

            successful += 1

            print(f"Parsed events: {len(events)}")

            # Show first three raw/normalised events.
            for index, event in enumerate(events[:3], 1):
                print()
                print(f"RAW EVENT {index}")

                for key in (
                    "UID",
                    "DTSTART",
                    "DTEND",
                    "SUMMARY",
                    "STATUS",
                ):
                    if key in event:
                        print(f"{key}: {event[key]}")

            # Identify 2026/27 season events.
            season_events = []

            for event in events:
                start = parse_ics_datetime(event.get("DTSTART"))

                if start is None:
                    continue

                # Scottish 2026/27 season begins in July 2026.
                # Include fixtures through June 2027.
                if (
                    datetime(2026, 7, 1, tzinfo=timezone.utc)
                    <= start
                    < datetime(2027, 7, 1, tzinfo=timezone.utc)
                ):
                    season_events.append(event)

            total_2026_27 += len(season_events)

            print()
            print(f"2026/27 events: {len(season_events)}")

            if season_events:
                print("2026/27 fixtures:")

                for event in season_events[:10]:
                    print(
                        f"  {event.get('DTSTART')} | "
                        f"{event.get('SUMMARY')}"
                    )

            else:
                print("WARNING: No 2026/27 fixtures found")

        except Exception as exc:
            failed += 1
            print(f"ERROR: {type(exc).__name__}: {exc}")

    print_header("TEAM CALENDAR SUMMARY")

    print(f"Successful team feeds: {successful}/{len(team_feeds)}")
    print(f"Failed team feeds: {failed}")
    print(f"Total VEVENT records: {total_events}")
    print(f"Total 2026/27 events: {total_2026_27}")

    print()

    if successful == len(team_feeds):
        print("RESULT: All team calendars loaded successfully.")
    else:
        print("RESULT: One or more team calendars failed.")

    return 0 if failed == 0 else 1


def parse_events(text):
    """
    Minimal ICS VEVENT parser.

    We deliberately keep this independent of the rest of the EPG so this
    diagnostic can tell us whether the raw team calendars themselves work.
    """

    events = []

    blocks = text.split("BEGIN:VEVENT")

    for block in blocks[1:]:
        if "END:VEVENT" not in block:
            continue

        block = block.split("END:VEVENT", 1)[0]

        event = {}

        # Handle folded ICS lines.
        lines = block.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        unfolded = []

        for line in lines:
            if line.startswith((" ", "\t")) and unfolded:
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)

        for line in unfolded:
            if ":" not in line:
                continue

            key, value = line.split(":", 1)

            # Remove ICS parameters.
            key = key.split(";", 1)[0].upper()

            event[key] = value.strip()

        events.append(event)

    return events


def parse_ics_datetime(value):
    if not value:
        return None

    value = value.strip()

    try:
        if value.endswith("Z"):
            return datetime.strptime(
                value,
                "%Y%m%dT%H%M%SZ",
            ).replace(tzinfo=timezone.utc)

        return datetime.strptime(
            value,
            "%Y%m%dT%H%M%S",
        ).replace(tzinfo=timezone.utc)

    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
