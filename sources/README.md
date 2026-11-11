# sources/

One file per upstream source, named `<source-id>.md`. Each says:

- what it covers (country, supplier, tariff kinds)
- the official URL, and whether it is a feed, a published sheet or a page
- its terms of use, quoted and linked, and whether we may redistribute the figures
- how often to check it
- how a sync reads it, and which script or skill does so

Official sources come first (regulator publications, supplier tariff sheets, supplier APIs).
Scraping a comparison site is a last resort and needs its terms read first.

The file name (without `.md`) is the `source.id` in every tariff file read from it.

A source with a sync module is read by the scheduled workflow (`scripts/README.md`). A source
without one is a note for later. `skills/find-sources/` describes how new ones are looked for.
