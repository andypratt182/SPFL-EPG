"""
ics.py

Shared iCalendar (.ics) parsing primitives.

This used to be implemented twice: once in sources/fixtur_es.py (the
production fixture source) and again, near-identically, in
tools/inspect_fixtur_es.py (the diagnostic audit tool). Two copies of
the same parser is exactly how they drift apart -- which is what
happened with fixture classification: the diagnostic tool had a
time-tolerant matching fallback that production never got, because
there was no shared code to keep the two in sync.

Both files should import from here instead.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from normalisation import normalise_team_name

logger = logging.getLogger(__name__)

UTC_TZ = ZoneInfo("UTC")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; SPFL-EPG/1.0; "
    "+https://github.com/andypratt182/SPFL-EPG)"
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 2


# ============================================================
# DOWNLOAD
# ============================================================

def download_ics(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay: int = DEFAULT_RETRY_DELAY_SECONDS,
) -> str:
    """Download an .ics feed, retrying on transient failures."""

    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        logger.debug("Request attempt %d/%d for %s", attempt, max_attempts, url)

        request = Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/calendar,*/*",
            },
        )

        try:
            with urlopen(request, timeout=30) as response:
                status = response.getcode()
                data = response.read()

            text = data.decode("utf-8-sig", errors="replace")

            logger.info(
                "Downloaded %s: HTTP %s, %d characters", url, status, len(text)
            )

            return text

        except HTTPError as error:
            last_error = error
            logger.warning("HTTP error fetching %s: %s", url, error.code)

        except URLError as error:
            last_error = error
            logger.warning("URL error fetching %s: %s", url, error)

        except Exception as error:  # noqa: BLE001 - want to retry on anything
            last_error = error
            logger.warning("Unexpected error fetching %s: %s", url, error)

        if attempt < max_attempts:
            time.sleep(retry_delay)

    raise RuntimeError(
        f"Unable to download {url} after {max_attempts} attempts: {last_error}"
    )


# ============================================================
# LOW-LEVEL ICS PARSING
# ============================================================

def unfold_ics(text: str) -> list[str]:
    """Undo RFC 5545 line folding (continuation lines start with whitespace)."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    unfolded: list[str] = []

    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


def split_events(text: str) -> list[list[str]]:
    """Split an .ics document into a list of VEVENT property-line lists."""

    lines = unfold_ics(text)

    events: list[list[str]] = []
    current: list[str] | None = None

    for line in lines:
        stripped = line.strip()

        if stripped == "BEGIN:VEVENT":
            current = []
            continue

        if stripped == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue

        if current is not None:
            current.append(line)

    return events


def property_line(lines: list[str], property_name: str) -> str | None:
    prefix = property_name.upper()

    for line in lines:
        upper = line.upper()
        if upper.startswith(prefix + ":") or upper.startswith(prefix + ";"):
            return line

    return None


def property_value(lines: list[str], property_name: str) -> str | None:
    line = property_line(lines, property_name)

    if not line or ":" not in line:
        return None

    return line.split(":", 1)[1].strip()


def property_parameters(lines: list[str], property_name: str) -> dict[str, str]:
    line = property_line(lines, property_name)

    if not line or ":" not in line:
        return {}

    left = line.split(":", 1)[0]

    if ";" not in left:
        return {}

    parameters: dict[str, str] = {}

    for item in left.split(";")[1:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parameters[key.upper()] = value

    return parameters


# ============================================================
# DATE PARSING
# ============================================================

_DATE_ONLY_RE = re.compile(r"\d{8}")

_DATETIME_FORMATS = ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M")


def parse_ics_datetime(value: str | None) -> datetime | None:
    """
    Parse an ICS DTSTART/DTEND value.

    Handles the plain-date form (YYYYMMDD), the UTC form
    (YYYYMMDDTHHMMSSZ), the floating-local form (YYYYMMDDTHHMMSS),
    and falls back to generic ISO 8601 parsing.
    """

    if not value:
        return None

    value = value.strip()

    if _DATE_ONLY_RE.fullmatch(value):
        try:
            return datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return None

    if value.endswith("Z"):
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC_TZ)
        except ValueError:
            return None

    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    try:
        normalised = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalised)
    except ValueError:
        return None


def localise(dt: datetime, tz: ZoneInfo) -> datetime:
    """Attach `tz` to a naive datetime, or convert an aware one to it."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    return dt.astimezone(tz)


# ============================================================
# MATCH SUMMARY PARSING
# ============================================================

_SCORE_RE = re.compile(r"\((\d+)\s*-\s*(\d+)\)\s*$")

# Any other trailing parenthetical annotation, e.g. "(Replay)",
# "(AET)", "(Behind Closed Doors)". Scottish Cup fixtures carry these
# far more often than league or European fixtures do (replays,
# extra time), and an unstripped one silently corrupts the away team
# name -- e.g. "Hibernian (Replay)" no longer matches the plain
# "Hibernian" from the team calendar, so the fixture can never be
# classified.
_TRAILING_ANNOTATION_RE = re.compile(r"\s*\([^()]*\)\s*$")

# Cup rounds are sometimes prefixed with a round/leg label ahead of
# the team names, e.g. "Round 4: Rangers - Hibernian" or
# "Replay: Rangers v Hibernian". League and European fixtures don't
# carry this. Leg labels have been seen in more than one form --
# "Leg 2:", "2nd Leg:", "Second Leg:" -- all covered here rather
# than assuming just one.
_ROUND_PREFIX_RE = re.compile(
    r"^\s*(?:round\s*\d+|r\d+|"
    r"leg\s*\d+|\d+(?:st|nd|rd|th)\s*leg|(?:first|second|third)\s*leg|"
    r"replay|quarter[\s-]?final|semi[\s-]?final|final)\b[^:]*:\s*",
    re.IGNORECASE,
)

# " - " is the common case; cup feeds have also been seen using
# " v " / " vs " between team names.
_SEPARATOR_RE = re.compile(r"\s+(?:-|vs?\.?)\s+", re.IGNORECASE)


def parse_score_from_summary(summary: str | None) -> tuple[int | None, int | None]:
    if not summary:
        return None, None

    match = _SCORE_RE.search(summary)

    if not match:
        return None, None

    return int(match.group(1)), int(match.group(2))


def remove_score_from_summary(summary: str | None) -> str:
    if not summary:
        return ""

    cleaned = _SCORE_RE.sub("", summary).strip()

    # Strip any other trailing parenthetical (replay/AET/etc.) that
    # isn't a score, so it doesn't end up glued onto the away team
    # name. Repeat in case of more than one, e.g. "(Replay) (AET)".
    while True:
        stripped = _TRAILING_ANNOTATION_RE.sub("", cleaned).strip()
        if stripped == cleaned:
            break
        cleaned = stripped

    return cleaned


def parse_match_summary(
    summary: str | None,
) -> tuple[str | None, str | None, int | None, int | None, str | None]:
    """
    Parse a SUMMARY field like "Rangers - Celtic (2-1)" into
    (home, away, home_score, away_score, round_label), with team
    names normalised via normalisation.normalise_team_name.

    Tolerates a leading round/leg label ("Round 4: ...", "Replay:
    ..."), " - "/" v "/" vs " as the team separator, and trailing
    non-score parenthetical annotations ("(Replay)", "(AET)") --
    variations seen on cup fixtures but not on league or European
    ones. The round/leg label itself is captured as round_label
    (e.g. "Round 4", "Replay", "Quarter Final") rather than just
    discarded, so callers can use it (e.g. in a programme
    description) -- None if the summary had no such prefix. Real
    Fixtur.es data inspected so far (a full Scottish Cup season)
    never actually included one, so this may rarely populate in
    practice; captured defensively in case other competition feeds
    do include it.
    """

    if not summary:
        return None, None, None, None, None

    home_score, away_score = parse_score_from_summary(summary)
    clean_summary = remove_score_from_summary(summary)

    round_match = _ROUND_PREFIX_RE.match(clean_summary)
    round_label = round_match.group(0).strip().rstrip(":").strip() if round_match else None

    clean_summary = _ROUND_PREFIX_RE.sub("", clean_summary).strip()

    match = _SEPARATOR_RE.search(clean_summary)

    if not match:
        return None, None, home_score, away_score, None

    home = clean_summary[: match.start()]
    away = clean_summary[match.end() :]

    return (
        normalise_team_name(home),
        normalise_team_name(away),
        home_score,
        away_score,
        round_label,
    )
