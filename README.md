# SPFL-EPG
Automatic SPFL XMLTV EPG generator for TiviMate

## Running

```
python generator.py
```

Writes `output/spfl.xml`. Runs automatically every 6 hours via
`.github/workflows/update_epg.yml` and deploys to GitHub Pages.

## Development

No third-party runtime dependencies -- everything uses the standard
library. For the test suite:

```
pip install -r requirements-dev.txt
pytest tests/
```

## Layout

- `generator.py` -- entry point
- `fixtures.py` -- per-team fixture windowing
- `sources/fixtur_es.py` -- live fixture source (ics.fixtur.es), including
  competition classification
- `xmltv.py` -- builds the XMLTV output
- `teams.py` / `venues.py` -- static team and stadium data
- `normalisation.py` / `ics.py` / `models.py` -- shared primitives used
  across the above (team-name normalisation, ICS parsing, shared types)
- `tools/inspect_fixtur_es.py` -- manual diagnostic audit tool (does not
  modify fixture data or the EPG); run via the "Inspect Fixtur.es"
  workflow
- `tests/` -- pytest suite
