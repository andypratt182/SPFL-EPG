from datetime import datetime, timezone

from ics import (
    parse_ics_datetime,
    parse_match_summary,
    property_value,
    split_events,
    unfold_ics,
)


def test_unfold_ics_joins_continuation_lines():
    # RFC 5545 folding: a continuation line's single leading
    # whitespace character is the fold marker, not content, so a
    # real space before "Celtic" needs a second leading space here.
    text = "SUMMARY:Rangers -\n  Celtic\nDTSTART:20270115T150000Z"
    lines = unfold_ics(text)
    assert lines == ["SUMMARY:Rangers - Celtic", "DTSTART:20270115T150000Z"]


def test_split_events_extracts_vevents():
    text = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\nUID:1\nSUMMARY:Rangers - Celtic\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:2\nSUMMARY:Hearts - Hibernian\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )
    events = split_events(text)
    assert len(events) == 2
    assert property_value(events[0], "UID") == "1"
    assert property_value(events[1], "SUMMARY") == "Hearts - Hibernian"


def test_parse_ics_datetime_utc():
    dt = parse_ics_datetime("20270115T150000Z")
    assert dt == datetime(2027, 1, 15, 15, 0, 0, tzinfo=timezone.utc)


def test_parse_ics_datetime_floating_local():
    dt = parse_ics_datetime("20270115T150000")
    assert dt.tzinfo is None
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2027, 1, 15, 15, 0)


def test_parse_ics_datetime_date_only():
    dt = parse_ics_datetime("20270115")
    assert (dt.year, dt.month, dt.day) == (2027, 1, 15)


def test_parse_ics_datetime_invalid():
    assert parse_ics_datetime("not-a-date") is None
    assert parse_ics_datetime(None) is None


def test_parse_match_summary_with_score():
    home, away, home_score, away_score = parse_match_summary("Rangers - Celtic (2-1)")
    assert (home, away, home_score, away_score) == ("Rangers", "Celtic", 2, 1)


def test_parse_match_summary_without_score():
    home, away, home_score, away_score = parse_match_summary("Rangers - Celtic")
    assert (home, away, home_score, away_score) == ("Rangers", "Celtic", None, None)


def test_parse_match_summary_normalises_team_names():
    home, away, _, _ = parse_match_summary("Rangers FC - Heart of Midlothian")
    assert (home, away) == ("Rangers", "Hearts")


def test_parse_match_summary_malformed():
    assert parse_match_summary("not a fixture") == (None, None, None, None)
    assert parse_match_summary(None) == (None, None, None, None)
