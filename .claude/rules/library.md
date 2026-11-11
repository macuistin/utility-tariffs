---
description: "lib/tariffstore, the bill engine, the client, its cache and format changes"
paths:
  - "lib/**"
  - "docs/format.md"
---

# Libraries

## Everything under lib/ is written here

- This repository is the source of truth for all tariff and billing code and calculations.
  `macuistin/givenergy_inverter_manager` copies `lib/tariff`, `lib/timeutil` and
  `lib/tariffstore` with its `scripts/copy_tariffstore.py`, on a weekly workflow, and its release
  refuses a copy that is behind. It never edits a copy.
- A copy must work unchanged, so `lib/` uses relative imports inside a package and between
  packages (`from ..timeutil import`), names no project that uses it, and reads no option keys.
- All of `lib/` passes `ruff check lib`, `mypy` and `bandit -r lib -c .bandit.yaml` with the
  settings in `pyproject.toml`: strict types, lines to 100, a function to complexity 8 and four
  arguments. They are the limits of the integration that copies it. CI runs all three. A
  `# noqa` or `# nosec` needs a reason a reviewer would accept.
- The tests of a package are copied with it: `tests/tariff/`, `tests/timeutil/` and the four
  `tests/test_*.py` files of the store library. Write them so they run from a copy: import the
  package by `lib.<name>`, a helper by `tests.tariff.<file>`, and use nothing else of this
  repository.

## lib/tariff and lib/timeutil

- The bill engine: the tariff model, the definition reader, bill maths, bands, half-hourly
  slots and repricing. `lib/tariff/README.md` lists the public names.
- `lib/tariff` imports only the standard library and `lib/timeutil`. `lib/timeutil` imports only
  the standard library. Nothing in `lib/tariffstore` or `scripts/` may import either.
- They need Python 3.14.
- A change in behaviour arrives with a test that fails without it. A stored figure a client
  already holds (a slot day, a bill row) keeps its meaning, or the change says how old data is
  read.

## lib/tariffstore

- Standard library only. No import of `lib.tariff`, `scripts` or anything installed with pip. It
  is written to be copied into another project as it stands.
- The three public functions that take a country, provider, tariff and date carry a `# noqa`
  for their argument count.
- `schema.py` is the one definition of the format. The sync, the build, the client and the tests
  all call it. A rule that exists only in a script or a test is a bug.
- A validator returns a list of refusals, each naming the field. It never repairs a value.
- `compile.py` changes no price. It rearranges a tariff file and its country values into the
  document the engine reads. If the engine cannot price something, compile raises `CompileError`.
- `layout.py` fixes the key order and spacing of every written file. Write files only through it.

## The client

- `Store` checks every file against the checksum in the level above before it is used. Never add
  a path that skips the check.
- The cache mirrors the store's paths and has no list of its own: the cached indexes say what
  each file should be. Only the countries index has an age.
- A path taken from an index is refused unless it stays inside the store (`SAFE_PATH`). Keep that
  check in front of every read and write.
- With no network the client answers from the cache and sets `offline`. A change must keep a
  cached tariff priceable offline.
- A custom tariff passes the same validator as a stored one. Do not add a field that only a
  custom tariff may use.
- The client reads over https only and sends no detail about the caller.

## Changing the format

1. The engine supports it (see above).
2. `schema.py` accepts it, with a test for each refusal.
3. `compile.py` passes it to the engine, with a test.
4. `docs/format.md` describes it, and `docs/design.md` moves it out of "not handled".
5. A stored tariff uses it, with a `checks` entry from a real bill where one exists.

A change that existing clients cannot read needs a new `schema` number and a plan for clients
that still read the old one. Adding an optional field does not.
