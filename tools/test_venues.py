from venues import get_venue, has_venue


def test_known_venue_exact_name():
    assert get_venue("Rangers") == "Ibrox Stadium"


def test_known_venue_normalised_name():
    assert get_venue("Rangers FC") == "Ibrox Stadium"
    assert get_venue("Heart of Midlothian") != "Venue TBC"


def test_unknown_venue_returns_placeholder():
    assert get_venue("A Made Up Football Club") == "Venue TBC"


def test_empty_input():
    assert get_venue("") == "Venue TBC"
    assert get_venue(None) == "Venue TBC"


def test_has_venue():
    assert has_venue("Rangers") is True
    assert has_venue("A Made Up Football Club") is False


def test_known_fixture_name_aliases():
    """
    Regression test: these team names as they actually appear in
    Fixtur.es fixture data ("FK Jablonec 97", "LASK Linz", "SK Rapid
    Wien") don't match venues.json's keys ("Jablonec", "LASK",
    "Rapid Wien") directly or via normalise_team_name() -- they carry
    extra club-type prefixes / city qualifiers that aren't stripped.
    Confirmed by inspecting a real generated XMLTV file where these
    fixtures showed "Venue TBC" despite venues.json actually having
    the data under a different key.
    """
    assert get_venue("FK Jablonec 97") == "Stadion Střelnice"
    assert get_venue("LASK Linz") == "Raiffeisen Arena"
    assert get_venue("SK Rapid Wien") == "Allianz Stadion"


def test_european_club_name_alias_batch():
    """
    Regression test for a larger batch of fixture-name variants
    identified from a real generator run's warnings.log and verified
    against venues.json. A sample across different variant types
    (transliteration, abbreviation, Dutch-language rendering, city
    qualifier) rather than the full ~80-entry list.
    """
    assert get_venue("FC Porto") == "Estádio do Dragão"
    assert get_venue("Sporting Portugal") == "Estádio José Alvalade"
    assert get_venue("Hamilton") == "New Douglas Park"
    assert get_venue("Inverness CT") == "Caledonian Stadium"
    assert get_venue("Olympique Lyonnais") == "Groupama Stadium"
    assert get_venue("FK Partizan") == "Stadion Partizana"
    assert get_venue("Ilves Tampere") == "Tammelan Stadion"
    assert get_venue("Inter Club D'Escaldes") == "Estadi Nacional"
    assert get_venue("Sporting Braga") == "Estádio Municipal de Braga"


def test_status_prefix_stripped_before_venue_lookup():
    """The ⚠️ Suspended: prefix fix (normalisation.py) must cascade
    through to venue lookup, not just team-name comparison."""
    assert get_venue("⚠️ Suspended: Rangers") == "Ibrox Stadium"
    assert get_venue("⚠️ Suspended: Hibernian") == "Easter Road"


def test_newly_added_venues():
    """
    These were previously entirely absent from venues.json (not an
    aliasing problem -- no entry existed under any name). Added after
    manual verification of each club/ground; a sample here rather
    than the full batch.
    """
    assert get_venue("Ross County") == "Victoria Park"
    assert get_venue("Dunfermline") == "East End Park"
    assert get_venue("Queen of the South") == "Palmerston Park"
    assert get_venue("Brechin City") == "Glebe Park"
    assert get_venue("East Kilbride") == "K-Park"


def test_second_batch_of_newly_added_venues():
    """
    Second batch, added from a secondhand AI-search result the user
    supplied. That source carried its own "may include mistakes"
    disclaimer and contained internally-contradictory answers for
    some clubs (different stadiums for the same club across its own
    two tables) and claims that conflicted with already-verified
    venues.json entries (e.g. claiming FC Avan Academy and FC
    Saburtalo Tbilisi had "rebranded" into other clubs that already
    exist here as separate entries). Those were excluded; only
    internally-consistent, unambiguous entries were added.
    """
    assert get_venue("AF Elbasani") == "Elbasan Arena"
    assert get_venue("GAIS") == "Gamla Ullevi"
    assert get_venue("Mjällby") == "Strandvallen"
    assert get_venue("St Joseph's") == "Victoria Stadium"
