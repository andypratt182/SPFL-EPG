"""
models.py

Shared type definitions.

Fixtures were previously passed around as untyped dicts everywhere,
with each consumer defensively checking several possible key names
for the same concept (xmltv.py checks "venue", then "stadium", then
"location" -- because different upstream sources have used all
three). A TypedDict doesn't stop that at runtime, but it does let a
type checker (mypy/pyright) catch typos and missing keys at the call
site, and it gives one place that documents what a "fixture" actually
contains.
"""

from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict


class Fixture(TypedDict):
    home: str
    away: str
    kickoff: datetime | str
    competition: str

    # Optional / source-dependent fields.
    venue: NotRequired[str]
    channel_id: NotRequired[str]
    competition_type: NotRequired[str]
    classification_status: NotRequired[str]
    home_score: NotRequired[int | None]
    away_score: NotRequired[int | None]


class Team(TypedDict):
    name: str
    urn: str
    stadium: str
