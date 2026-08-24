"""
venues.py

Stadium lookup by team name, backed by data/venues.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from normalisation import normalise_team_name

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "venues.json"

UNKNOWN_VENUE = "Venue TBC"
UNKNOWN_COUNTRY = "Unknown"


def _load_venues() -> dict:
    """Load venue data from data/venues.json.

    Kept in a JSON file under data/ so venue information can be
    expanded without touching this module.
    """

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Venue data file not found: {DATA_FILE}")

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid venue JSON: {DATA_FILE}") from error

    if not isinstance(data, dict):
        raise RuntimeError(f"Venue data must be a JSON object: {DATA_FILE}")

    return data


VENUES = _load_venues()

# Pre-normalise the lookup table once at import time rather than
# re-normalising every key on every call to get_venue().
_NORMALISED_VENUES = {normalise_team_name(name): venue for name, venue in VENUES.items()}

# Names permanently exempt from the WARNING-level miss log below --
# either because no single stadium answer could ever be correct
# ("Vikingur"), or because the name isn't a real team at all
# ("Winnaar Groep D"). Both are settled, not new gaps, so warning
# about them every run would just bury genuinely new misses.
#
# "Vikingur": ambiguous between two different real clubs -- Víkingur
# Reykjavík (Iceland) and Víkingur Gøta (Faroe Islands) -- both
# entered in UEFA qualifying most seasons. Confirmed by real fixture
# data: "Vikingur" appears simultaneously alive in Champions League
# qualifying (7/21 Jul) AND playing a separate Conference League
# qualifier sandwiched between those dates (16 Jul) -- two different
# qualifying paths that can't belong to the same club at once. Any
# single alias here would be wrong for roughly half its fixtures.
#
# "Winnaar Groep D": Dutch for "Winner of Group D" -- a UEFA
# qualifying-round placeholder for a group draw that hasn't happened
# yet, not an actual club. Confirmed seen playing itself (home ==
# away == "Winnaar Groep D") in a real feed. Will keep recurring
# every run until the real draw replaces it -- nothing to fix here.
_KNOWN_UNRESOLVABLE_NAMES = {"Vikingur", "Winnaar Groep D"}

# Known cases where the team name as it appears in fixture data
# (Fixtur.es SUMMARY parsing) doesn't match the venues.json key --
# usually an extra club-type prefix ("FK ", "SK ") or city qualifier
# ("Linz") that normalise_team_name() doesn't strip generically.
# Generic prefix/suffix stripping isn't safe here: venues.json has
# 800+ entries including short, common words as keys ("Rangers",
# "United"), so a loose substring match risks matching the wrong
# club entirely (e.g. "Rangers" matching inside "Queens Park
# Rangers"). Confirmed mismatches are added here explicitly instead.
_FIXTURE_NAME_ALIASES = {
    "FK Jablonec 97": "Jablonec",
    "LASK Linz": "LASK",
    "SK Rapid Wien": "Rapid Wien",

    # The batch below was identified from a real generator run's
    # warnings.log (134 unresolved names) and verified individually
    # against venues.json -- each target confirmed to exist and to
    # be the correct club, not just the closest string match. Some
    # near-matches were deliberately rejected as false friends
    # despite being textually close: "Sporting Braga" is Braga, NOT
    # "Sporting CP" (a different Portuguese club); "Dinamo Tirana"/
    # "Dinamo City" are NOT "Tirana" (a different Albanian club);
    # "Železničar Pančevo" is NOT "Željezničar" (different clubs,
    # different countries). Those are left unmapped rather than
    # guessed.
    "AEK Athene": "AEK Athens",
    "AS Monaco": "Monaco",
    "Bate Borisov": "BATE Borisov",
    "Beer Sheva": "Hapoel Beer Sheva",
    "CFR 1907 Cluj": "CFR Cluj",
    "CS Petrocub": "Petrocub Hîncești",
    "CS Universitatea Craiova": "Universitatea Craiova",
    "DAC 1904": "DAC 1904 Dunajská Streda",
    "DAC Dunajska Streda": "DAC 1904 Dunajská Streda",
    "Debreceni VSC": "Debrecen",
    "Egnatia Rrogozhinë": "Egnatia",
    "FC Ararat-Armenia": "Ararat-Armenia",
    "FC Astana": "Astana",
    "FC Drita": "Drita",
    "FC Flora Tallinn": "Flora Tallinn",
    "FC Kopenhagen": "FC Copenhagen",
    "FC Lugano": "Lugano",
    "FC Midtjylland": "Midtjylland",
    "FC Nordsjealland": "Nordsjælland",
    "FC Porto": "Porto",
    "FC Pyunik": "Pyunik",
    "FC Santa Coloma": "Santa Coloma",
    "FC Sheriff Tiraspol": "Sheriff Tiraspol",
    "FC St Gallen": "St. Gallen",
    "FC Viktoria Plzen": "Viktoria Plzeň",
    "Ferencvarosi": "Ferencváros",
    "FK Austria Wien": "Austria Wien",
    "FK Kauno Zalgiris": "Kauno Žalgiris",
    "FK Liepaja": "FK Liepāja",
    "FK Partizan": "Partizan Belgrade",
    "FK Qarabag": "Qarabağ",
    "FK Sarajevo": "Sarajevo",
    "FK Vojvodina": "Vojvodina",
    "H. Tel Aviv": "Hapoel Tel Aviv",
    "Hamilton": "Hamilton Academical",
    "Hammarby IF": "Hammarby",
    "Hamrun Spartans": "Ħamrun Spartans",
    "HB Torshavn": "HB Tórshavn",
    "HSK Zrinjski Mostar": "Zrinjski Mostar",
    "Ilves Tampere": "Ilves",
    "Inter Club D'Escaldes": "Inter Escaldes",
    "Inverness CT": "Inverness Caledonian Thistle",
    "Jerusalem": "Hapoel Jerusalem",
    "KAA Gent": "Gent",
    "Klaksvik": "KÍ Klaksvík",
    "Lillestrom": "Lillestrøm",
    "M. Tel Aviv": "Maccabi Tel Aviv",
    "MSK Zilina": "Žilina",
    "N.E.C.": "NEC Nijmegen",
    "Neftchi Baku": "Neftçi",
    "NK Rijeka": "Rijeka",
    "Nomme Kalju": "Nõmme Kalju",
    "OFI": "OFI Crete",
    "Olympiakos Piraeus": "Olympiacos",
    "Olympique Lyonnais": "Lyon",
    "Omonia Nicosia": "Omonia",
    "PAOK Salonika": "PAOK",
    "Paphos": "Pafos",
    "PFC Levski Sofia": "Levski Sofia",
    "PFC Ludogorets Razgrad": "Ludogorets Razgrad",
    "Polissya": "Polissya Zhytomyr",
    "RB Salzburg": "Red Bull Salzburg",
    "Rigas FS": "RFS",
    "RSC Anderlecht": "Anderlecht",
    "SK Brann": "Brann",
    "SK Slovan Bratislava": "Slovan Bratislava",
    "SK Sturm Graz": "Sturm Graz",
    "Sint Truiden VV": "Sint-Truiden",
    "Sparta Praag": "Sparta Prague",
    "Sporting Braga": "Braga",
    "Sporting Portugal": "Sporting CP",
    "Steaua Boekarest": "Steaua Bucharest",
    "Sutjeska Niksic": "Sutjeska Nikšić",
    "The Spartans": "Spartans",
    "Tobol Kostanai": "Tobol",
    "Union Saint-Gilloise": "Union SG",
    "Valur Reykjavik": "Valur",
    "Viking FK": "Viking",
    "Vllaznia Shkodër": "Vllaznia",
    "Zalgiris Vilnius": "Žalgiris Vilnius",
    "Zimbru": "Zimbru Chișinău",
    "Zira FK": "Zira",
}


def _stadium_from(venue) -> str | None:
    if isinstance(venue, str) and venue.strip():
        return venue.strip()

    if isinstance(venue, dict):
        stadium = venue.get("stadium")
        if stadium:
            return str(stadium).strip()

    return None


def _country_from(venue) -> str | None:
    if isinstance(venue, dict):
        country = venue.get("country")
        if country:
            return str(country).strip()

    return None


def _resolve_entry(team_name: str):
    """
    Shared lookup chain for both get_venue() and get_venue_country():
    exact key match, then normalised-name match, then the known
    fixture-name alias table. Returns the raw venues.json value (a
    {stadium, country} dict, or a legacy plain string for any entry
    not yet migrated) or None if nothing matched.
    """

    if team_name in VENUES:
        return VENUES[team_name]

    venue = _NORMALISED_VENUES.get(normalise_team_name(team_name))

    if venue is None:
        alias = _FIXTURE_NAME_ALIASES.get(team_name)
        if alias:
            venue = VENUES.get(alias)

    return venue


def get_venue(team_name: str | None, *, context: str | None = None) -> str:
    """
    Return the stadium for a team, or "Venue TBC" if unknown.

    `context` is optional and purely for the miss-warning below --
    e.g. the opponent/competition/kickoff of the fixture that
    triggered the lookup, so an unresolved name can be traced back to
    an actual fixture in the log instead of just a bare team name.
    """

    if not team_name:
        return UNKNOWN_VENUE

    stadium = _stadium_from(_resolve_entry(team_name))

    if stadium:
        return stadium

    # Data-completeness gap rather than a code bug: this team just
    # isn't in venues.json under any name we tried. Logged so new
    # mismatches (an opponent's name spelled differently to how
    # venues.json has it) are visible in run logs instead of
    # silently producing "Venue TBC" forever.
    #
    # Exception: names in _KNOWN_UNRESOLVABLE_NAMES are a settled
    # case, not a new gap -- warning about them every run would just
    # bury genuinely new misses in repeat noise.
    if team_name in _KNOWN_UNRESOLVABLE_NAMES:
        logger.debug("No venue found for %r (known unresolvable name)", team_name)
        return UNKNOWN_VENUE

    suffix = f" ({context})" if context else ""
    logger.warning("No venue found for %r%s", team_name, suffix)

    return UNKNOWN_VENUE


def get_venue_country(team_name: str | None) -> str:
    """
    Return the country a team's venue is in, or "Unknown" if
    unavailable (either the team isn't in venues.json under any name
    we tried, or its entry predates the {stadium, country} migration
    and is still a bare stadium string).

    Doesn't log a miss warning -- get_venue() already does for the
    same lookup chain, and both are typically called for the same
    fixture, so a second warning here would just double up on the
    same underlying gap.
    """

    if not team_name:
        return UNKNOWN_COUNTRY

    return _country_from(_resolve_entry(team_name)) or UNKNOWN_COUNTRY


# Demonym for every country currently used in venues.json (verified
# 75/75 -- programmatically checked against the actual distinct
# country values in the file, not just written by hand and hoped
# complete). Used to describe an opponent's nationality in a more
# natural way than repeating the country noun, e.g. "Czech
# opposition" rather than "opposition from Czech Republic".
_DEMONYMS = {
    "Albania": "Albanian", "Andorra": "Andorran", "Argentina": "Argentine",
    "Armenia": "Armenian", "Australia": "Australian", "Austria": "Austrian",
    "Azerbaijan": "Azerbaijani", "Belarus": "Belarusian", "Belgium": "Belgian",
    "Bolivia": "Bolivian", "Bosnia and Herzegovina": "Bosnian", "Brazil": "Brazilian",
    "Bulgaria": "Bulgarian", "Canada": "Canadian", "Chile": "Chilean", "China": "Chinese",
    "Colombia": "Colombian", "Croatia": "Croatian", "Cyprus": "Cypriot",
    "Czech Republic": "Czech", "Denmark": "Danish", "Ecuador": "Ecuadorian",
    "Egypt": "Egyptian", "England": "English", "Estonia": "Estonian",
    "Faroe Islands": "Faroese", "Finland": "Finnish", "France": "French",
    "Georgia": "Georgian", "Germany": "German", "Gibraltar": "Gibraltarian",
    "Greece": "Greek", "Hungary": "Hungarian", "Iceland": "Icelandic", "India": "Indian",
    "Israel": "Israeli", "Italy": "Italian", "Japan": "Japanese", "Kazakhstan": "Kazakh",
    "Kosovo": "Kosovan", "Latvia": "Latvian", "Liechtenstein": "Liechtenstein",
    "Lithuania": "Lithuanian", "Luxembourg": "Luxembourgish", "Malta": "Maltese",
    "Mexico": "Mexican", "Moldova": "Moldovan", "Montenegro": "Montenegrin",
    "Morocco": "Moroccan", "Netherlands": "Dutch", "North Macedonia": "North Macedonian",
    "Northern Ireland": "Northern Irish", "Norway": "Norwegian", "Peru": "Peruvian",
    "Poland": "Polish", "Portugal": "Portuguese", "Republic of Ireland": "Irish",
    "Romania": "Romanian", "Russia": "Russian", "San Marino": "Sammarinese",
    "Saudi Arabia": "Saudi", "Scotland": "Scottish", "Serbia": "Serbian",
    "Slovakia": "Slovak", "Slovenia": "Slovenian", "South Africa": "South African",
    "South Korea": "South Korean", "Spain": "Spanish", "Sweden": "Swedish",
    "Switzerland": "Swiss", "Turkey": "Turkish", "Ukraine": "Ukrainian",
    "United States": "American", "Uruguay": "Uruguayan", "Wales": "Welsh",
}


def get_demonym(country: str | None) -> str | None:
    """
    Adjective form of a country name, e.g. "Czech" for "Czech
    Republic". Returns None (not UNKNOWN_COUNTRY or similar) for
    anything not in _DEMONYMS, so callers can use `if demonym:` to
    decide whether they have something usable rather than needing to
    special-case a placeholder string.
    """

    if not country:
        return None

    return _DEMONYMS.get(country)


def has_venue(team_name: str | None) -> bool:
    """Return True if a known venue exists for the team."""

    return get_venue(team_name) != UNKNOWN_VENUE


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

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

    print("=" * 60)
    print("VENUE DATABASE TEST")
    print("=" * 60)

    for team in test_teams:
        print(f"{team:30} -> {get_venue(team)}")
