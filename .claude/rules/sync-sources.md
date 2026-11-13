---
description: "The sync path, source modules, fetching and source notes"
paths:
  - "scripts/sync/**"
  - "scripts/tools/**"
  - "sources/**"
---

# Sync and sources

    source.read()  ->  Plan  ->  to_tariff (validates)  ->  apply (revision rules)  ->  build

## The path

- A source module only fetches and parses. It has `SOURCE_ID`, `COUNTRY` and
  `read(fetch, today, stored)`, and returns a `Result` of plans, skipped rows and notes. It never
  writes a file and never decides a revision.
- `to_tariff` in `plan.py` is the one place a plan becomes a tariff file. `apply.py` holds the
  revision rules. Do not copy either into a source.
- A run is deterministic: the same responses, stored files and run date give the same files.
  Take the date from `today`. Never read the clock, and never iterate a set or an unsorted
  directory into the output.
- A source is all or nothing. If it raises, its files are restored and the other sources still
  run. Raise on anything unexpected. Do not catch and carry on.
- A row the format cannot hold is added to `skipped` with the reason. Never round it into shape.
- A source that states no start date sets `dated=False`, and a changed price starts on the day of
  the run. A revision that differs only by the export a plan pays also starts on the day of the
  run, since the supplier dates a price and not a pairing.
- A stored tariff the source no longer lists is reported as missing and left alone. Withdrawing
  a tariff is a person's decision.
- A change `apply` cannot place is refused and listed. Do not loosen `apply` to make a source
  pass. Fix the source or handle the tariff by hand.
- No AI at run time, no secrets, no third-party packages. A workbook or PDF is read with the
  standard library.

## Fetching

- All requests go through `Fetcher` in `http.py`: one pause between requests, bounded retries,
  `--record` and `--replay`. Never call `urllib` from a source.
- Keep requests few. A scheduled run refetches what is stored and does not crawl for more.
- A parser checks the shape it reads (the columns, the count of regions) and raises when it
  differs. A site that changed must fail loudly, not produce a plausible wrong price.

## Adding or changing a source

1. Write or update `sources/<source-id>.md`: what it covers, the link, the format, units, tax,
   how often it changes, how it is read, what it skips.
2. Add `scripts/sync/sources/<name>.py` and its name to `NAMES` in `sources/__init__.py`.
3. Add tests that feed it saved or synthetic responses. No test fetches from the network.
4. Run it once by hand with `--record`, read every file it wrote, and say in the pull request
   what was checked against the published figures.

A hand-edited constant (a yearly link, a start date) is named in the source note with when to
change it.
