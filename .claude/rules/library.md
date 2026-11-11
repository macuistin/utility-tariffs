---
description: "lib/tariffstore, the copied bill engine, the client, its cache and format changes"
paths:
  - "lib/**"
  - "docs/format.md"
---

# Libraries

## lib/tariff and lib/timeutil are copies

- They are the bill engine of `macuistin/givenergy_inverter_manager`, copied unchanged.
  `lib/README.md` records the commit.
- Never edit them here. Change the engine in the integration repository, with its tests, then
  copy the folders again and update the commit in `lib/README.md`.
- They need Python 3.14. Nothing in `lib/tariffstore` or `scripts/` may import them.

## lib/tariffstore

- Standard library only. No import of `lib.tariff`, `scripts` or anything installed with pip. It
  is written to be copied into another project as it stands.
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
