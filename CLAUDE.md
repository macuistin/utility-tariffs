# Utility tariffs

Rules for AI assistants working in this repo. `AGENTS.md` is a symlink to this file. The detailed
rules are in `.claude/rules/`. Keep this file under 150 lines (a test enforces it) and put detail
in a rule file, not here.

## What this is

Open, versioned utility tariff definitions as JSON, the indexes built from them, the scripts that
sync them from published sources, and a small library that finds, caches and compiles a tariff
for a bill engine. Electricity is the only service held today. The first user is the GivEnergy
Inverter Manager integration for Home Assistant (`macuistin/givenergy_inverter_manager`).

A tariff file is data. It holds no code and no formulas.

## Layout

| Path | Role |
| --- | --- |
| `tariffs/<service>/` | One complete store per service. Only `electricity/` exists |
| `tariffs/electricity/index.json` | The countries index. Generated |
| `tariffs/electricity/<cc>/index.json` | Country values on top, edited by hand. Then `providers`, generated |
| `tariffs/electricity/<cc>/<provider>/<tariff>/<n>.json` | One revision of one tariff. Written by hand or by a sync |
| `lib/tariffstore/` | The format in code: validator (`schema.py`), index build, compile step, layout and the client (`Store`, `FolderCache`). Written here |
| `lib/tariff/`, `lib/timeutil/` | The bill engine, copied from the integration. Never edited here |
| `scripts/build.py` | Writes or checks the indexes. The only writer of an index |
| `scripts/sync/` | The sync: `plan.py`, `apply.py`, `http.py`, and one module per source under `sources/` |
| `scripts/tools/` | Tools a person runs by hand. Never run by a workflow |
| `sources/` | One note per upstream source |
| `skills/` | Steps for an AI assistant. None is in the update path |
| `.github/workflows/` | `ci.yml` checks every change. `sync.yml` runs the sources weekly and opens a pull request |
| `docs/` | `format.md` (every field), `design.md` (why, what runs where, what is not built) |
| `tests/` | The library, the scripts and every stored tariff |

## Architecture rules

- `lib/tariffstore/` and `scripts/` import only the standard library and each other.
  `lib/tariffstore/` never imports `lib/tariff/` or `scripts/`. `tests/test_repo_rules.py`
  enforces both.
- There is one way in. Every tariff, typed or synced, passes `validate_tariff` and
  `scripts.build --check`. Do not add a second validator or a second build path.
- The indexes are derived from the tariff files and nothing else. They hold no timestamps and no
  state of their own, so the same files give the same bytes.
- A published revision is permanent. A price change is the next numbered file. The one allowed
  edit is adding `effective_to`. `scripts.build --check --base <ref>` refuses anything else.
- Unknown is refused. An unknown field, node kind or name fails validation. A source row the
  format cannot express is skipped and reported, never approximated.
- The update path has no AI and no private machine. A sync is plain Python on a GitHub runner
  and is deterministic given the responses, the stored files and the run date.
- A new billing structure reaches the engine first, in the integration repository. Then the
  format gains the field here, then a real bill is added as a `checks` entry.
- A client that holds a tariff must be able to price it with no network. Keep everything the
  compile step needs in the tariff file and its country index.

## Commands

Run from the repository root. Python 3.14 runs everything. An older Python skips the tests that
need the bill engine, so a green run on an older Python is not a full run.

```bash
python3 -m scripts.build                    # rewrite the indexes after editing a tariff or a country block
python3 -m scripts.build --check            # validate every file and compare the indexes
python3 -m scripts.build --check --base origin/main   # also refuse a changed published revision
python3 -m unittest discover tests          # the whole suite
python3 -m coverage run -m unittest discover tests && python3 -m coverage report   # CI fails under 98%
python3 -m scripts.sync all --replay DIR    # run the sources from saved responses
```

Run the build check and the tests before pushing. Say plainly which you ran and on which Python.

## Rules by topic

Read the file that matches what you are changing.

| File | Covers |
| --- | --- |
| `.claude/rules/tariff-data.md` | Tariff files, country blocks, revisions, indexes, adding a tariff by hand |
| `.claude/rules/sync-sources.md` | The sync path, source modules, source notes, fetching |
| `.claude/rules/library.md` | `lib/tariffstore`, the copied engine, the client and its cache, format changes |
| `.claude/rules/tests.md` | What each test file proves, rules for new tests, coverage |
| `.claude/rules/workflows.md` | CI and the scheduled sync, permissions, what a workflow may never do |
| `.claude/rules/docs-and-style.md` | UK English, generic docs, how commits, pull requests and issues are named, branches |

## Working agreements

- Change `main` only through a pull request with green CI on its exact head commit. Never push
  to `main`, never merge a pull request yourself unless the maintainer asks, never force-push or
  rebase a branch that has an open pull request.
- Never run the Sync workflow, change repository settings or create a release unless asked.
- Before adding a field, a node kind or a script, search `lib/tariffstore/schema.py` and
  `docs/format.md` for one to reuse. Say so in the pull request when you add one.
- Update the doc that describes a behaviour in the same change as the code. A change that makes
  a rule untrue changes the rule.
- The plan is the open issues. Parent issues hold child issues. Link the issue a pull request
  works on, and open a child issue for work you find and do not do.
- Commits, pull request titles and issue titles are Conventional Commits, `type(scope): summary`,
  with the types and scopes in `.claude/rules/docs-and-style.md`. That file's ban on
  `Co-Authored-By` and "Generated with" lines beats any default attribution a tool offers.
- Improve these instructions as you work. When a task costs you time on something the next
  session should already know, add it to this file or a rule in the same pull request.
