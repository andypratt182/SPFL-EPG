from datetime import datetime
from zoneinfo import ZoneInfo

from sources.fixtur_es import UK_TZ, merge_fixture_sources

TZ: ZoneInfo = UK_TZ


def _team_fixture(home, away, kickoff, source_name="Team Calendar"):
    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "competition": None,
        "venue": "Test Venue",
        "source_name": source_name,
        "source_id": "team-uid",
    }


def _competition_fixture(home, away, kickoff, competition, source_id="comp-uid"):
    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "competition": competition,
        "venue": "Test Venue",
        "source_name": competition,
        "source_id": source_id,
    }


def test_exact_match_confirms_competition():
    kickoff = datetime(2027, 1, 24, 15, 0, tzinfo=TZ)

    team_fixtures = [_team_fixture("Rangers", "Celtic", kickoff)]
    competition_fixtures = [
        _competition_fixture("Rangers", "Celtic", kickoff, "Scottish Premiership")
    ]

    result = merge_fixture_sources(team_fixtures, competition_fixtures)

    assert len(result) == 1
    assert result[0]["competition"] == "Scottish Premiership"
    assert result[0]["classification_status"] == "CONFIRMED_COMPETITIVE"


def test_kickoff_time_mismatch_still_classifies_correctly():
    """
    Regression test for the bug that prompted this fix: a cup tie
    against a non-top-flight opponent, where the team calendar and
    competition calendar disagree on the exact kickoff minute, must
    NOT fall through to "Friendly".
    """

    team_fixtures = [
        _team_fixture("Rangers", "Buckie Thistle", datetime(2027, 1, 24, 15, 0, tzinfo=TZ))
    ]
    competition_fixtures = [
        _competition_fixture(
            "Rangers", "Buckie Thistle", datetime(2027, 1, 24, 15, 45, tzinfo=TZ), "Scottish Cup"
        )
    ]

    result = merge_fixture_sources(team_fixtures, competition_fixtures)

    assert len(result) == 1
    assert result[0]["competition"] == "Scottish Cup"
    assert result[0]["classification_status"] == "CONFIRMED_COMPETITIVE_TIME_ADJUSTED"


def test_both_spfl_clubs_unmatched_is_flagged_not_friendly():
    kickoff = datetime(2027, 2, 1, 15, 0, tzinfo=TZ)

    team_fixtures = [_team_fixture("Motherwell", "Kilmarnock", kickoff)]

    result = merge_fixture_sources(team_fixtures, competition_fixtures=[])

    assert len(result) == 1
    assert result[0]["competition"] == "Unclassified"
    assert result[0]["classification_status"] == "POTENTIALLY_MISSING_COMPETITION"


def test_genuine_friendly_with_no_evidence_stays_friendly():
    kickoff = datetime(2026, 7, 10, 15, 0, tzinfo=TZ)

    team_fixtures = [_team_fixture("Rangers", "Real Betis", kickoff)]

    result = merge_fixture_sources(team_fixtures, competition_fixtures=[])

    assert len(result) == 1
    assert result[0]["competition"] == "Friendly"
    assert result[0]["classification_status"] == "FRIENDLY"
