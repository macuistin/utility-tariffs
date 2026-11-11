# Tariff prices

Open, versioned electricity tariff definitions, an index to find them by country, provider and
tariff, and a small library that fetches one, checks it and hands it to a bill engine. Each tariff
is a JSON document. No tariff contains code or formulas.

## Layout

| Path | Role |
| --- | --- |
| `tariffs/electricity/index.json` | The countries index: each country's index path, checksum and counts. Generated |
| `tariffs/electricity/<cc>/index.json` | One country: its shared values at the top (currency, time zone, VAT, standard bill), edited by hand, then `providers`, the tariff collection, generated. Holds no prices |
| `tariffs/electricity/<cc>/<provider>/<tariff>/<n>.json` | One revision of one tariff: name, provider, dates, source, bands, one row of rates per area |
| `lib/tariffstore/` | The format in code: validator, checksum, index build, compile step and the client. Standard library only. Scripts and clients share it |
| `lib/tariff/` | The bill engine, copied from the Home Assistant integration. See `lib/README.md` |
| `scripts/` | `build` (write or check the indexes) and `sync` (read the sources). See `scripts/README.md` |
| `sources/` | One note per upstream source: what it covers, how it is read, how often |
| `.github/workflows/` | `ci.yml` checks every change. `sync.yml` runs the sources on a schedule and opens a pull request |
| `docs/` | `format.md` (the files), `design.md` (why it is this way, what runs where, what is not built) |
| `tests/` | Tests for the library, the scripts and every stored tariff |
| `CONTRIBUTING.md`, `CLAUDE.md`, `.claude/rules/` | How to change the store, how things are named, and the rules for AI assistants (`AGENTS.md` is the same file) |

## Rules

1. **Definitions are data.** Unknown or malformed fields are refused, not repaired.
2. **Money is exact.** Prices are decimal strings, never floats.
3. **Revisions are permanent.** A price change is a new numbered file. A published file is never
   edited, except to add `effective_to` when a tariff is withdrawn. CI enforces this.
4. **Every tariff names its source.** Each file carries the source id and the link it was read from.
5. **The indexes are built** from the files and nothing else, so the same files always give the
   same bytes. CI fails if a committed index differs from a fresh build.
6. **Changes arrive as pull requests** that pass CI. A synced change is never merged without review.

## Using it from a library

```python
from datetime import date
from lib.tariffstore import Store, url_reader

store = Store(url_reader("https://raw.githubusercontent.com/<owner>/<repo>/main/tariffs/electricity"))
store.countries()                                   # {"GB": {"availability": "available", ...}, ...}
store.providers("GB")                               # {"octopus-energy": "Octopus Energy", ...}
store.tariffs("GB", "octopus-energy")               # {"octopus-var-22-11-01": "Flexible Octopus", ...}
store.areas("GB", "octopus-energy", "octopus-var-22-11-01", date.today())   # {"a": "Eastern England (A)", ...}
definition = store.definition("GB", "octopus-energy", "octopus-var-22-11-01", date.today(), area="c")
```

`definition` is the document `lib.tariff.load_definition` reads, so the next line prices a bill
(`price_bill`) or the half-hourly history (`price_period`). Every file is checked against the
checksum in the level above it before it is used. `docs/design.md` has the details.

Keep what is fetched on disk, so a tariff is downloaded once and still works with no network:

```python
store = Store.cached("https://raw.githubusercontent.com/<owner>/<repo>/main/tariffs/electricity",
                     "/path/to/cache")
store.fetch_country("IE", on=date.today())          # every tariff on offer, to compare bills
```

Price a tariff the store does not hold. It is written like a tariff file, and the country's
currency, time zone, tax and standard bill come from the store:

```python
mine = {"name": "My tariff", "effective_from": "2026-01-01",
        "bands": [{"name": "Day"}, {"name": "Night", "hours": "23:00-08:00"}],
        "areas": {"all": {"standing": "0.90", "rates": {"Day": "0.31", "Night": "0.14"}}}}
definition = store.custom_definition("IE", mine, date.today())
```

## Working on it

    python3 -m scripts.build             # rewrite the indexes after editing a tariff or a country block
    python3 -m scripts.build --check     # what CI runs
    python3 -m scripts.sync all          # read every scheduled source and write new revisions
    python3 -m unittest discover tests   # Python 3.14 runs everything; older skips the engine tests

## Licence

To be decided before any data is published. See `docs/licence.md`.
