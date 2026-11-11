---
name: sync-tariff
description: Add or refresh one tariff by hand from its published source. Use when asked to add a tariff no sync module reads, or to correct one.
---

The scheduled sync (`scripts/sync`) handles every source that has a module, with no AI. Use this
skill only for a tariff typed by hand.

1. Read `docs/format.md` and the source's note in `sources/`. Write the note first if there is none.
2. Find the tariff's newest revision under `tariffs/electricity/<cc>/<provider>/<tariff>/`.
3. If the published prices match it, stop. Change nothing.
4. If they differ, write the next numbered file with the new `effective_from`. Do not edit the old
   file. Add `effective_to` to the old file only when the tariff is withdrawn with no successor.
5. Add a `checks` entry from a real bill where one exists.
6. Run `python3 -m scripts.build`, then `python3 -m scripts.build --check --base origin/main` and
   `python3 -m unittest discover tests`.
7. Open a pull request that names the source and what changed.

Stop and report instead of guessing when the source shows something the format cannot express.
