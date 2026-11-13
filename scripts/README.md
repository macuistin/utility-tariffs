# scripts/

Run every script from the repository root as a module. Standard library only.

| Path | Job |
| --- | --- |
| `build.py` | Write the indexes from the tariff files. `--check` validates everything and compares the committed indexes with a fresh build. `--base REF` also refuses a change to a revision published at `REF` |
| `sync/__main__.py` | `python3 -m scripts.sync <source>... \| all`. Runs each source, writes new revisions, rebuilds, prints a report |
| `sync/plan.py` | `Plan`, what a source returns, and `to_tariff`, the one place a plan becomes a validated file |
| `sync/apply.py` | The revision rules: add, revise, leave unchanged, refuse, report missing |
| `sync/http.py` | The fetcher: a pause between requests, retries, `--record` and `--replay` |
| `sync/sources/` | One module per source. Each only fetches and parses |
| `tools/au_discover.py` | Run by hand to choose which Australian plans to hold. The scheduled sync refreshes only the plans already stored |
| `paths.py` | The repository folders |

## A sync run

    python3 -m scripts.sync all --report report.md
    python3 -m scripts.sync octopus_gb --record raw/      # keep the responses
    python3 -m scripts.sync octopus_gb --replay raw/      # run again without fetching
    python3 -m scripts.sync all --date 2026-11-09         # fix the run date

1. Each source returns plans and a list of what it skipped, with the reason.
2. A plan becomes a tariff file and is validated. A failure stops that source.
3. A new tariff is added with its history. A stored tariff gets a new revision only when its
   pricing changed. A change the rules cannot place is refused and listed.
4. A source that fails has its files restored. The others still run and the exit code is 1.
5. The indexes are rebuilt once at the end.

A run with no price change writes nothing. `.github/workflows/sync.yml` runs this weekly, one job
for each source from `python3 -m scripts.sync all --list`, and opens a pull request. A source that
fails there gets its own issue. `docs/design.md` has the reasons.

## Sources

| Module | Source note | Reads |
| --- | --- | --- |
| `octopus_gb` | `sources/octopus-energy-gb.md` | Octopus Energy's product API: import and export |
| `ofgem_gb` | `sources/ofgem-price-cap.md` | The price cap workbook linked from Ofgem's page |
| `selectra_ie` | `sources/selectra-ie.md` | Irish supplier pages and their export rates |
| `electric_ireland` | `sources/electric-ireland.md` | Electric Ireland's price plans page, each plan's full pricing and the microgeneration export rate |
| `au_cdr` | `sources/au-cdr-energy.md` | Australian plan detail, and each plan's feed-in tariff, for the plans already stored |
| `fr_cre` | `sources/fr-cre-trve.md` | The French regulated tariff file |
| `za_eskom` | `sources/za-eskom-tariff-book.md` | Eskom's yearly booklet. Its link and start date are constants edited by hand each year |

## Adding a source

1. Write `sources/<source-id>.md`.
2. Add `sync/sources/<name>.py` with `SOURCE_ID`, `COUNTRY` and `read(fetch, today, stored)`
   returning a `Result`. Add the name to `NAMES` in `sync/sources/__init__.py`.
3. Add tests under `tests/` that feed it saved or synthetic responses. CI holds coverage at 98%.
