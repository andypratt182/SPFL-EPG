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


def test_status_prefix_stripped_before_venue_lookup():
    """The ⚠️ Suspended: prefix fix (normalisation.py) must cascade
    through to venue lookup, not just team-name comparison."""
    assert get_venue("⚠️ Suspended: Rangers") == "Ibrox Stadium"
    assert get_venue("⚠️ Suspended: Hibernian") == "Easter Road"
