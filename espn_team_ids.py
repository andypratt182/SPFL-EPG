"""
espn_team_ids.py

Maps each SPFL_TEAMS name to its ESPN team ID, used to build the
per-team fixtures URL:
    https://africa.espn.com/football/team/fixtures/_/id/{ID}/{slug}

The {slug} part of the URL doesn't actually matter for the request to
work - ESPN redirects/serves the same page regardless of what text is
there - so we always pass the team name lower-cased with spaces
replaced by hyphens; it doesn't need to be exact.

HOW TO FIND A MISSING ID:
  1. Go to espn.com (or espn.co.uk)
  2. Search for the club
  3. Open the club's "Fixtures" tab
  4. The ID is in the URL: .../football/team/fixtures/_/id/XXX/club-name
  5. Copy that number in below.

Match the keys here to the "name" field used in your SPFL_TEAMS dict
in teams.py (minus any trailing " TV").
"""

ESPN_TEAM_IDS = {
    "Aberdeen": 263,
    "Celtic": 256,
    "Dundee": 261,
    "Dundee United": 264,
    "Falkirk": 254,
    "Heart of Midlothian": 262,
    "Hibernian": 258,
    "Kilmarnock": 260,
    "Motherwell": 266,
    "Rangers": 257,
    "St Johnstone": 267,
    "St Mirren": 250,
}
