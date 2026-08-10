import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

from sources.fixtur_es import get_all_fixtures


def main():
    fixtures = get_all_fixtures()

    print()
    print("=" * 70)
    print("FIXTUR.ES DATASET DIAGNOSTIC")
    print("=" * 70)

    print(f"Total unique fixtures: {len(fixtures)}")

    # -----------------------------------------------------
    # Competition summary
    # -----------------------------------------------------

    competitions = Counter(
        fixture.get("competition", "Unknown")
        for fixture in fixtures
    )

    print()
    print("=" * 70)
    print("COMPETITION SUMMARY")
    print("=" * 70)

    for competition, count in competitions.most_common():
        print(f"{count:5}  {competition}")

    # -----------------------------------------------------
    # Team/source summary
    # -----------------------------------------------------

    teams = Counter(
        fixture.get("source_team", "Unknown")
        for fixture in fixtures
    )

    print()
    print("=" * 70)
    print("SOURCE TEAM SUMMARY")
    print("=" * 70)

    for team, count in sorted(teams.items()):
        print(f"{count:5}  {team}")

    # -----------------------------------------------------
    # Examples by competition
    # -----------------------------------------------------

    examples = defaultdict(list)

    for fixture in fixtures:

        competition = fixture.get(
            "competition",
            "Unknown",
        )

        if len(examples[competition]) < 5:
            examples[competition].append(
                fixture
            )

    print()
    print("=" * 70)
    print("COMPETITION EXAMPLES")
    print("=" * 70)

    for competition in sorted(examples):

        print()
        print(f"[{competition}]")

        for fixture in examples[competition]:

            print(
                f"  {fixture.get('kickoff')} | "
                f"{fixture.get('home')} - "
                f"{fixture.get('away')}"
            )

    # -----------------------------------------------------
    # Unknown competition records
    # -----------------------------------------------------

    unknown = [
        fixture
        for fixture in fixtures
        if fixture.get("competition", "Unknown")
        == "Unknown"
    ]

    print()
    print("=" * 70)
    print("UNKNOWN COMPETITION")
    print("=" * 70)

    print(
        f"Unknown competition fixtures: "
        f"{len(unknown)}"
    )

    for fixture in unknown[:20]:

        print()
        print(
            f"{fixture.get('kickoff')} | "
            f"{fixture.get('home')} - "
            f"{fixture.get('away')}"
        )

        print(
            f"  source_team: "
            f"{fixture.get('source_team')}"
        )

        print(
            f"  source_id: "
            f"{fixture.get('source_id')}"
        )

        print(
            f"  competition: "
            f"{fixture.get('competition')}"
        )

    # -----------------------------------------------------
    # Raw representative records
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("RAW REPRESENTATIVE RECORDS")
    print("=" * 70)

    shown = set()

    for fixture in fixtures:

        competition = fixture.get(
            "competition",
            "Unknown",
        )

        if competition in shown:
            continue

        shown.add(competition)

        print()
        print(
            f"--- {competition} ---"
        )

        for key, value in fixture.items():
            print(
                f"{key}: {value}"
            )

        if len(shown) >= 15:
            break

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
