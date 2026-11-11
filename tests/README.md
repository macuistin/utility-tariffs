# tests/

Run from the repository root: `python3 -m unittest discover tests`. Python 3.14 runs everything.
An older Python skips the tests that need the bill engine. With coverage:
`python3 -m coverage run -m unittest discover tests && python3 -m coverage report`.

| File | Proves |
| --- | --- |
| `test_schema.py` | Every validator rule, for tariff files, country blocks and the unavailable list |
| `test_compile.py` | A tariff file and a country block become the definition the engine reads |
| `test_index.py`, `test_build.py` | The index build, its checks, and the rule that a published revision does not change |
| `test_client.py` | Finding countries, providers, tariffs and revisions, checksum refusal, the cache |
| `test_sync_core.py`, `test_sync_run.py` | Plans, the revision rules, the fetcher, a whole run and its rollback |
| `test_sources_*.py` | Each source parser on synthetic responses |
| `test_stored_tariffs.py` | Every file in `tariffs/`: valid, compiles for every area, indexed as built, sane prices |
| `test_tariffs_through_lib.py` | Every stored tariff priced by `lib/tariff`. Each expected figure is labelled PAGE (from the source) or ASSUMPTION (chosen by the test) |
| `test_repo_rules.py` | The rules a machine can hold: `CLAUDE.md` stays short, the libraries import only what they may, titles follow the naming rule |
| `test_end_to_end.py` | A hand-written tariff built, fetched through the client and priced to a hand-worked figure |

Every `checks` entry in a tariff file is also a test vector: an engine passes if it reproduces each
expected total. No test fetches from the network.
