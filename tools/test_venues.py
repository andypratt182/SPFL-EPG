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
