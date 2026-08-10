import sys
from pathlib import Path
from collections import Counter

# Make the repository root importable when this script
# is run from the tools directory.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

from sources.fixtur_es import get_all_fixtures


def main():

    print()
    print("=" * 70)
    print("FIXTUR.ES DATASET DIAGNOSTIC")
    print("=" * 70)

    fixtures = get_all_fixtures()

    print()
    print(
        f"Total unique fixtures: {len(fixtures)}"
    )

    # -----------------------------------------------------
    # Competition summary
    # -----------------------------------------------------

    competition_counts = Counter()

    for fixture in fixtures:

        competition = fixture.get(
            "competition"
        )

        if not competition:
            competition = "Unknown"

        competition_counts[
            str(competition)
        ] += 1

    print()
    print("=" * 70)
    print("COMPETITION SUMMARY")
    print("=" * 70)

    for competition, count in (
        competition_counts.most_common()
    ):

        print(
            f"{count:5}  {competition}"
        )

    # -----------------------------------------------------
    # Source team summary
    # -----------------------------------------------------

    team_counts = Counter()

    for fixture in fixtures:

        team = fixture.get(
            "source_team"
        )

        if not team:
            team = "Unknown"

        team_counts[
            str(team)
        ] += 1

    print()
    print("=" * 70)
    print("SOURCE TEAM SUMMARY")
    print("=" * 70)

    for team in sorted(
        team_counts,
        key=lambda value: str(value)
    ):

        print(
            f"{team_counts[team]:5}  {team}"
        )

    # -----------------------------------------------------
    # Competition examples
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("COMPETITION EXAMPLES")
    print("=" * 70)

    shown = set()

    for fixture in fixtures:

        competition = fixture.get(
            "competition"
        )

        if not competition:
            competition = "Unknown"

        competition = str(
            competition
        )

        if competition in shown:
            continue

        shown.add(
            competition
        )

        print()
        print(
            f"[{competition}]"
        )

        print(
            f"  kickoff: "
            f"{fixture.get('kickoff')}"
        )

        print(
            f"  match: "
            f"{fixture.get('home')} "
            f"vs "
            f"{fixture.get('away')}"
        )

        print(
            f"  source team: "
            f"{fixture.get('source_team')}"
        )

        print(
            f"  source id: "
            f"{fixture.get('source_id')}"
        )

    # -----------------------------------------------------
    # Unknown competitions
    # -----------------------------------------------------

    unknown = [
        fixture
        for fixture in fixtures
        if (
            not fixture.get("competition")
            or fixture.get("competition")
            == "Unknown"
        )
    ]

    print()
    print("=" * 70)
    print("UNKNOWN COMPETITIONS")
    print("=" * 70)

    print(
        f"Unknown fixtures: {len(unknown)}"
    )

    for fixture in unknown[:20]:

        print(
            f"{fixture.get('kickoff')} | "
            f"{fixture.get('home')} vs "
            f"{fixture.get('away')} | "
            f"{fixture.get('source_team')}"
        )

    # -----------------------------------------------------
    # Raw field inspection
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("RAW NORMALISED FIELDS")
    print("=" * 70)

    if fixtures:

        fixture = fixtures[0]

        for key in sorted(
            fixture.keys()
        ):

            print(
                f"{key}: "
                f"{fixture.get(key)}"
            )

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":

    main()
