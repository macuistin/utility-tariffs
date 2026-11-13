---
description: "Tariff files, country blocks, revisions and the generated indexes"
paths:
  - "tariffs/**"
---

# Tariff data

`docs/format.md` describes every field. This file says how to change the data safely.

## Tariff files

- Never edit a revision that is on `main`. A price change is the next numbered file in the same
  folder, with a later `effective_from`. CI compares against the base branch and refuses an edit.
- The one allowed edit to a published revision is adding `effective_to`, when a tariff is
  withdrawn with no successor. A revision that is followed by another needs no `effective_to`:
  the index derives its end.
- Prices are decimal strings in the currency's major unit, at most six decimal places, with no
  trailing zeros. Never a JSON number.
- Write only what differs from the default. Electricity, residential, import, the country's time
  zone and tax-inclusive prices are assumed. `service` is refused.
- Every file names its `source`: the id of a note in `sources/` and the link the figures were
  read from. Write the source note first if there is none.
- A tariff typed by hand from a source no sync reads is allowed, and goes stale in silence. Its
  source note must say `**How it is read:** by hand.` (a test checks it), and an issue asks for
  the sync module.
- The first band is the base rate and has only a name. A later band wins over the ones before
  it, so the order is the priority.
- A tariff with one price has one area, `all`. Add areas only where the price differs by place.
- `checks` entries come from real bills with every personal detail removed. Never invent one to
  make a tariff "complete".
- Provider and tariff ids are slugs and never change once published, because clients store them.

## Country blocks and indexes

- The top of `<cc>/index.json` is edited by hand: `currency`, `timezone`, `vat_percent` (or a
  dated `vat` list), the standard `bill` and its `inputs`. A tariff never repeats these.
- `providers` in a country index and the whole of `index.json` are generated. Never edit them.
  Run `python3 -m scripts.build`, then commit the result with the change that caused it.
- A change to a country's tax rate is a new dated entry in `vat`, never an edit of a past rate.
- A country with no rates goes in `unavailable.json` with a reason and the date checked.
- `holidays` in a country block holds the public holidays by year, with the https `source` they
  were read from. Take the dates from that page, never from memory or a rule of thumb. Add a
  year only when it is published. A year that is not listed is refused, not read as no holidays.

## What never goes in

- No timestamps of when something was generated or checked.
- No price that was estimated, converted from another currency or copied from a forum.
- No personal data: no account numbers, addresses, meter numbers or names from a bill.
- No tariff the format cannot express exactly. Skip it and open an issue that says what is
  missing.
