import json
import re
import unicodedata
from pathlib import Path


# ============================================================
# VENUE DATA
# ============================================================

VENUES_FILE = Path(__file__).resolve().parent / "venues.json"


# Fixtur.es names that cannot be resolved by normal text
# normalisation alone.
TEAM_ALIASES = {
    "fk shkendija 79": "kf shkendija",
    "shkendija": "kf shkendija",
    "shkëndija": "kf shkendija",
    "fk shkëndija": "kf shkendija",
}


def _normalise_name(name):
    """
    Create a forgiving lookup key for team names.

    Handles:
        - accents
        - punctuation
        - FC / F.C.
        - Football Club
        - Fixtur.es competition suffixes
        - whitespace differences
    """

    if not name:
        return ""

    value = str(name).strip()

    # Remove Fixtur.es competition suffixes.
    value = re.sub(
        r"\s+\[(?:EL|CL|Conf)\]\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Remove accents for matching.
    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower()

    # Normalise Football Club / FC / F.C.
    value = re.sub(
        r"\bfootball\s+club\b",
        "",
        value,
    )

    value = re.sub(
        r"\bf\.?c\.?\b",
        "",
        value,
    )

    # Remove punctuation.
    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(value.split())


def _load_venues():
    """
    Load venues.json and build a normalised lookup table.
    """

    if not VENUES_FILE.exists():
        raise FileNotFoundError(
            f"Venue data file not found: {VENUES_FILE}"
        )

    with VENUES_FILE.open(
        "r",
        encoding="utf-8",
    ) as handle:
        records = json.load(handle)

    venues = {}

    for record in records:

        if not isinstance(record, dict):
            continue

        team = record.get("team")
        stadium = record.get("stadium")

        if not team or not stadium:
            continue

        venues[
            _normalise_name(team)
        ] = stadium

    return venues


VENUES = _load_venues()


# ============================================================
# ALIASES
# ============================================================

for alias, canonical in TEAM_ALIASES.items():

    venue = VENUES.get(
        _normalise_name(canonical)
    )

    if venue:
        VENUES[
            _normalise_name(alias)
        ] = venue


# ============================================================
# PUBLIC API
# ============================================================

def get_venue(team_name):
    """
    Return the stadium for a team.

    Returns None when the team isn't present in venues.json.
    """

    if not team_name:
        return None

    return VENUES.get(
        _normalise_name(team_name)
    )


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    tests = (
        "Rangers",
        "Rangers FC",
        "Hibernian",
        "Hibernian F.C.",
        "FK Shkendija 79",
        "KF Shkëndija",
        "Jagiellonia Białystok",
    )

    for team in tests:

        venue = get_venue(team)

        print(
            f"{team}: "
            f"{venue or 'Venue TBC'}"
        )
