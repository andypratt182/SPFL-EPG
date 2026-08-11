from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sources.fixtur_es import get_all_fixtures
from teams import SPFL_TEAMS

UK_TZ = ZoneInfo("Europe/London")

FIXTURE_DAYS = 24

_ALL_FIXTURES = None


def normalise_team_name(name: str) -> str:
    if not name:
        return ""

    name = str(name).lower().strip()

    if name.endswith(" tv"):
        name = name[:-3]

    for suffix in (
        " football club",
        " fc",
    ):
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()

    return " ".join(name.split())


def _load_fixtures() -> list[dict]:
    """
    Download the Fixtur.es calendars once per generator run.

    The generator calls get_fixtures() once for each of the
    twelve channels, so caching here prevents twelve copies
    of the twelve feeds being downloaded.
    """

    global _ALL_FIXTURES

    if _ALL_FIXTURES is None:
        _ALL_FIXTURES = get_all_fixtures()

    return _ALL_FIXTURES


def _parse_kickoff(value):
    if not value:
        return None

    if isinstance(value, datetime):
        kickoff = value

    else:
        try:
            normalised = str(value).strip()

            if normalised.endswith("Z"):
                normalised = (
                    normalised[:-1]
                    + "+00:00"
                )

            kickoff = datetime.fromisoformat(
                normalised
            )

        except ValueError:
            return None

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(
            tzinfo=UK_TZ
        )

    return kickoff.astimezone(UK_TZ)


def _stadium_for(home: str) -> str:
    """
    Return the known stadium for the home team.

    This uses the existing SPFL_TEAMS configuration,
    so stadium data does not need to be duplicated
    in the Fixtur.es importer.
    """

    target = normalise_team_name(home)

    for team in SPFL_TEAMS.values():

        if (
            normalise_team_name(
                team.get("name", "")
            )
            == target
        ):
            return team.get(
                "stadium",
                "Venue TBC",
            )

    return "Venue TBC"


def get_fixtures(team: dict) -> list[dict]:
    """
    Public fixture interface used by generator.py.

    Fixtur.es is now the live fixture source.
    """

    team_name = team.get(
        "name",
        "",
    )

    target = normalise_team_name(
        team_name
    )

    now = datetime.now(
        UK_TZ
    )

    window_end = (
        now
        + timedelta(
            days=FIXTURE_DAYS
        )
    )

    fixtures = []

    for fixture in _load_fixtures():

        home = fixture.get(
            "home",
            "",
        )

        away = fixture.get(
            "away",
            "",
        )

        if not home or not away:
            continue

        if (
            normalise_team_name(home)
            != target
            and
            normalise_team_name(away)
            != target
        ):
            continue

        kickoff = _parse_kickoff(
            fixture.get("kickoff")
        )

        if kickoff is None:
            continue

        if kickoff < now:
            continue

        if kickoff > window_end:
            continue

        fixtures.append(
            {
                "home": home,
                "away": away,
                "kickoff": kickoff,
                "competition": fixture.get(
                    "competition",
                    "Unknown",
                ),
                "competition_type": fixture.get(
                    "competition_type",
                    "UNKNOWN",
                ),
                "classification_status": fixture.get(
                    "classification_status",
                    "UNKNOWN",
                ),
                "venue": fixture.get(
                    "venue",
                    "Venue TBC",
                ),
            }
        )

    fixtures.sort(
        key=lambda fixture:
        fixture["kickoff"]
    )

    return fixtures
