---
name: find-sources
description: Look for official electricity tariff and dynamic price sources this repository does not read yet, and record what was found. Use on a schedule or when asked to find sources for a country.
---

The aim is a short, checked list of sources worth building. It is research only.

Limits:

- Write only under `sources/`. Never write under `tariffs/`, `prices/`, `lib/` or `scripts/`.
- Never merge. Open one pull request for the notes and stop.
- Record what a page said, with its link and the date read. Mark anything not read as unverified.
- Do not sign up for a key, accept terms or log in on anyone's behalf.

Steps:

1. Read `sources/README.md`, every note in `sources/`, `tariffs/electricity/unavailable.json` and
   `tariffs/electricity/index.json`. List the countries with no source and the sources marked not built.
2. Read the open issues labelled `source` so nothing is proposed twice.
3. Pick at most three targets for this run. Prefer, in order: a country people have asked for, a
   dynamic price feed for a country already held, a country marked unavailable longest ago.
4. For each target look for, in order: a regulator's published rates or comparison data, a
   supplier's public API or tariff sheet, a market operator's day-ahead price feed. A comparison
   site is a last resort.
5. For each source found, check and record:
   - what it covers (country, suppliers, fixed or dynamic, import or export)
   - the exact link, the format (JSON, CSV, workbook, PDF, page) and whether a sign-in or key is needed
   - the units, whether tax is included, and the time zone of any times
   - for a dynamic feed: the interval, when the next day is published, and how far back it goes
   - how often it changes
   - whether the format can hold it today (`docs/format.md`, `docs/design.md`), and what is missing
6. Write or update `sources/<source-id>.md` in the shape `sources/README.md` gives. Update the
   `checked` date of a country in `tariffs/electricity/unavailable.json` only through a note in the pull
   request text, not by editing the file.
7. Open a pull request titled `docs(sources): <what was found>`. In the body, list each source
   with one line on whether it is worth building and why.
8. For a source worth building, open one issue labelled `source` with the link to its note. One
   issue per source, and none if one is already open.

Stop and say so when nothing new was found. An empty run is a good result.
