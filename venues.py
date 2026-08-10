from pathlib import Path
import json


# ============================================================
# VENUE DATA
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "venues.json"


def _load_venues():
    """
    Load venue data from data/venues.json.

    The JSON file is deliberately kept under data/ so venue
    information can be expanded without changing this module.
    """

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Venue data file not found: {DATA_FILE}"
        )

    try:
        with DATA_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid venue JSON: {DATA_FILE}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Venue data must be a JSON object: {DATA_FILE}"
        )

    return data


VENUES = _load_venues()


# ============================================================
# NAME NORMALISATION
# ============================================================

def _normalise_name(name):
    """
    Normalise a team name sufficiently for venue lookup.
    """

    if not name:
        return ""

    value = str(name).strip()

    # Remove competition suffixes used by Fixtur.es.
    value = value.replace("[CL]", "")
    value = value.replace("[EL]", "")
    value = value.replace("[Conf]", "")

    # Remove common football-club suffixes.
    replacements = (
        (" Football Club", ""),
        (" F.C.", ""),
        (" FC", ""),
    )

    for suffix, replacement in replacements:
        if value.lower().endswith(suffix.lower()):
            value = value[: -len(suffix)] + replacement

    value = " ".join(value.split())

    return value.strip().lower()


# ============================================================
# VENUE LOOKUP
# ============================================================

def get_venue(team_name):
    """
    Return the stadium for a team.

    Returns:
        Stadium name
        or "Venue TBC" if no venue is known.
    """

    if not team_name:
        return "Venue TBC"

    # First try exact name.
    if team_name in VENUES:
        venue = VENUES[team_name]

        if isinstance(venue, str) and venue.strip():
            return venue.strip()

        if isinstance(venue, dict):
            stadium = venue.get("stadium")

            if stadium:
                return str(stadium).strip()

    # Then use normalised matching.
    wanted = _normalise_name(team_name)

    for name, venue in VENUES.items():

        if _normalise_name(name) != wanted:
            continue

        if isinstance(venue, str):
            if venue.strip():
                return venue.strip()

        elif isinstance(venue, dict):
            stadium = venue.get("stadium")

            if stadium:
                return str(stadium).strip()

    return "Venue TBC"


# ============================================================
# OPTIONAL HELPER
# ============================================================

def has_venue(team_name):
    """
    Return True if a known venue exists for the team.
    """

    return get_venue(team_name) != "Venue TBC"


# ============================================================
# OPTIONAL DIRECT TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("VENUE DATABASE TEST")
    print("=" * 60)

    test_teams = [
        "Rangers",
        "Celtic",
        "Aberdeen",
        "Dundee",
        "Dundee United",
        "Hearts",
        "Hibernian",
        "Kilmarnock",
        "Motherwell",
        "Falkirk",
        "St Johnstone",
        "St Mirren",
        "Jagiellonia Białystok",
        "LASK Linz",
        "Benfica",
        "FK Shkendija 79",
        "HJK Helsinki",
    ]

    for team in test_teams:
        print(
            f"{team:30} -> {get_venue(team)}"
        )
