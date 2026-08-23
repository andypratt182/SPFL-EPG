"""
normalisation.py

Single source of truth for team-name normalisation.

Previously this logic was reimplemented separately in fixtures.py,
sources/fixtur_es.py, venues.py, and tools/inspect_fixtur_es.py, each
with slightly different rules. That divergence is exactly how feeds
silently stop matching each other: add a team, or a new naming quirk
from a data source, and it's easy to update one copy and forget the
rest. Every module in this project should import from here instead of
rolling its own.
"""

from __future__ import annotations

import re

# ============================================================
# CANONICAL SPFL TEAM NAMES
# ============================================================

# The 12 clubs currently in the Scottish Premiership. This is the
# canonical spelling every data source's team name should normalise
# to.
SPFL_TEAMS = {
    "Aberdeen",
    "Celtic",
    "Dundee",
    "Dundee United",
    "Falkirk",
    "Hearts",
    "Hibernian",
    "Kilmarnock",
    "Motherwell",
    "Rangers",
    "St Johnstone",
    "St Mirren",
}

# Known aliases that don't reduce to the canonical name through the
# generic suffix-stripping rules below (e.g. "Heart of Midlothian" is
# an entirely different string to "Hearts", not just a suffix
# difference).
_ALIASES = {
    "heart of midlothian": "Hearts",
    "saint johnstone": "St Johnstone",
    "saint mirren": "St Mirren",
}

# UEFA competition-suffix tags that some feeds append to a team name,
# e.g. "Malmo [CL]" for a Champions League fixture.
_UEFA_SUFFIX_RE = re.compile(
    r"\s+\[(?:EL|CL|Conf)\]\s*$",
    re.IGNORECASE,
)

_CLUB_SUFFIX_RE = re.compile(
    r"\s+(football\s+club|f\.?c\.?)$",
    re.IGNORECASE,
)

_TV_SUFFIX_RE = re.compile(r"\s+tv$", re.IGNORECASE)

_ST_PREFIX_RE = re.compile(r"\bst\.?\s+", re.IGNORECASE)
_SAINT_PREFIX_RE = re.compile(r"\bsaint\s+", re.IGNORECASE)

# Match-status markers Fixtur.es prepends to a team name for that
# specific event, e.g. "⚠️ Suspended: Rangers" for an abandoned/
# suspended fixture. Left unstripped, these corrupt matching for
# BOTH venue lookups and competition classification -- "⚠️
# Suspended: Rangers" doesn't equal "Rangers" as far as either is
# concerned, even though it's the same club.
_STATUS_PREFIX_RE = re.compile(
    r"^[^\w]*(?:suspended|postponed|cancelled|canceled|abandoned)\s*:\s*",
    re.IGNORECASE,
)


def normalise_team_name(name: str | None) -> str:
    """
    Normalise a team name to a consistent, comparable form.

    Strips UEFA competition tags ("[CL]"), club suffixes ("FC",
    "Football Club"), a trailing "TV" (used by our own channel
    names), and unifies "St"/"St."/"Saint" prefixes. Known aliases
    (e.g. "Heart of Midlothian" -> "Hearts") are then applied.

    This does not guarantee the result is one of SPFL_TEAMS -- it
    normalises non-SPFL names too (e.g. European or lower-league
    opponents), just without an alias applied.
    """

    if not name:
        return ""

    value = str(name).strip()

    value = _STATUS_PREFIX_RE.sub("", value).strip()
    value = _UEFA_SUFFIX_RE.sub("", value)
    value = _CLUB_SUFFIX_RE.sub("", value)
    value = _TV_SUFFIX_RE.sub("", value)
    value = _ST_PREFIX_RE.sub("St ", value)
    value = _SAINT_PREFIX_RE.sub("St ", value)

    value = " ".join(value.split())

    alias = _ALIASES.get(value.lower())

    return alias if alias else value


def is_spfl_team(name: str | None) -> bool:
    """Return True if name normalises to one of the 12 top-flight clubs."""

    return normalise_team_name(name) in SPFL_TEAMS


if __name__ == "__main__":

    logging_examples = [
        "Rangers FC",
        "Rangers Football Club",
        "RANGERS TV",
        "Heart of Midlothian",
        "St. Johnstone",
        "Saint Mirren",
        "Malmo [CL]",
        "Buckie Thistle",
    ]

    for example in logging_examples:
        print(
            f"{example!r:30} -> "
            f"{normalise_team_name(example)!r:20} "
            f"(SPFL: {is_spfl_team(example)})"
        )
