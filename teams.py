"""
teams.py

The 12 SPFL clubs this EPG generates channels for, keyed by their
IPTV channel ID.
"""

from models import Team

SPFL_TEAMS: dict[str, Team] = {
    "rangerstv": {
        "name": "Rangers TV",
        "urn": "urn:bbc:sportsdata:football:team:rangers",
        "stadium": "Ibrox Stadium",
    },
    "celtictv": {
        "name": "Celtic TV",
        "urn": "urn:bbc:sportsdata:football:team:celtic",
        "stadium": "Celtic Park",
    },
    "aberdeentv": {
        "name": "Aberdeen TV",
        "urn": "urn:bbc:sportsdata:football:team:aberdeen",
        "stadium": "Pittodrie Stadium",
    },
    "dundeetv": {
        "name": "Dundee TV",
        "urn": "urn:bbc:sportsdata:football:team:dundee",
        "stadium": "Dens Park",
    },
    "dundeeunitedtv": {
        "name": "Dundee United TV",
        "urn": "urn:bbc:sportsdata:football:team:dundee-united",
        "stadium": "Tannadice Park",
    },
    "heartstv": {
        "name": "Hearts TV",
        "urn": "urn:bbc:sportsdata:football:team:heart-of-midlothian",
        "stadium": "Tynecastle Park",
    },
    "hibstv": {
        "name": "Hibernian TV",
        "urn": "urn:bbc:sportsdata:football:team:hibernian",
        "stadium": "Easter Road",
    },
    "kilmarnocktv": {
        "name": "Kilmarnock TV",
        "urn": "urn:bbc:sportsdata:football:team:kilmarnock",
        "stadium": "Rugby Park",
    },
    "motherwelltv": {
        "name": "Motherwell TV",
        "urn": "urn:bbc:sportsdata:football:team:motherwell",
        "stadium": "Fir Park",
    },
    "falkirktv": {
        "name": "Falkirk TV",
        "urn": "urn:bbc:sportsdata:football:team:falkirk",
        "stadium": "Falkirk Stadium",
    },
    "stjohnstonetv": {
        "name": "St Johnstone TV",
        "urn": "urn:bbc:sportsdata:football:team:st-johnstone",
        "stadium": "McDiarmid Park",
    },
    "stmirrentv": {
        "name": "St Mirren TV",
        "urn": "urn:bbc:sportsdata:football:team:st-mirren",
        "stadium": "The SMiSA Stadium",
    },
}
