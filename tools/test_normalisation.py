from normalisation import is_spfl_team, normalise_team_name


def test_strips_fc_suffix():
    assert normalise_team_name("Rangers FC") == "Rangers"
    assert normalise_team_name("Rangers Football Club") == "Rangers"


def test_strips_tv_suffix():
    assert normalise_team_name("Rangers TV") == "Rangers"


def test_strips_uefa_tag():
    assert normalise_team_name("Malmo [CL]") == "Malmo"
    assert normalise_team_name("Hibernian [Conf]") == "Hibernian"


def test_saint_and_st_prefixes_are_unified():
    assert normalise_team_name("St. Johnstone") == "St Johnstone"
    assert normalise_team_name("Saint Mirren") == "St Mirren"


def test_known_alias():
    assert normalise_team_name("Heart of Midlothian") == "Hearts"


def test_empty_input():
    assert normalise_team_name("") == ""
    assert normalise_team_name(None) == ""


def test_is_spfl_team():
    assert is_spfl_team("Rangers FC") is True
    assert is_spfl_team("Heart of Midlothian") is True
    assert is_spfl_team("Buckie Thistle") is False
    assert is_spfl_team("") is False


def test_status_prefix_stripped():
    """
    Regression test: Fixtur.es prefixes a team name with a match
    status marker for suspended/postponed fixtures (e.g. "⚠️
    Suspended: Rangers"). Left unstripped this breaks both venue
    lookup and competition matching for that fixture.
    """
    assert normalise_team_name("⚠️ Suspended: Rangers") == "Rangers"
    assert normalise_team_name("Postponed: Celtic") == "Celtic"
