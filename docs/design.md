# Design

Why the store is shaped this way, what runs where, and what is designed but not built.
`format.md` describes the files themselves.

## Aims

1. A tariff file a person can read and write by hand, with as few fields as possible.
2. One way in. Every tariff, typed or synced, passes the same validator and the same build.
3. Reproducible. The same files give the same indexes, byte for byte. The same source responses
   on the same date give the same files.
4. No AI and no private machine in the update path.
5. A library can find a country, a provider and a tariff, fetch only what it needs, prove it got
   the right file, and price a bill with it.

## The model

Three levels, each small enough to fetch on its own.

| Level | File | Holds | Written by |
| --- | --- | --- | --- |
| Countries | `tariffs/electricity/index.json` | Each country's path, checksum and counts | Build |
| Country | `tariffs/electricity/<cc>/index.json` | Country values on top: `currency`, `timezone`, `vat_percent` (or dated `vat`), standard `bill` and `inputs`. Then `providers`, the tariff collection | Top by hand, `providers` by build |
| Tariff | `tariffs/electricity/<cc>/<provider>/<tariff>/<n>.json` | One revision: names, dates, source, bands, one row of prices per area | Hand or sync |

Decisions and the reason for each:

- **Country values live once, at the top of the country file.** VAT is an input the bill tree
  takes by name (`$country.vat_percent`). A tariff never repeats it.
- **The index is derived from the tariff files and nothing else.** Provider names and source
  links sit in the tariff file, so the index holds no state of its own and cannot drift.
- **No timestamps.** "Generated at" and "last checked" made every run change bytes. Git history
  and the workflow log already hold both.
- **A revision is permanent.** A price change is a new numbered file. A revision ends on its own
  `effective_to` or on the day the next one starts, and the index shows the result. The only edit
  allowed to a published file is adding `effective_to`. `scripts.build --check --base <ref>`
  enforces it.
- **Checksums chain upward.** A tariff file's checksum is in its country index, the country
  index's in the countries index. One request shows what changed. The checksum is the SHA-256 of
  the canonical JSON, the same function the bill engine uses.
- **Money is a decimal string**, six places at most, no trailing zeros, so a price has one
  spelling.
- **Defaults are not written.** Electricity, residential, import, the country's time zone and
  tax-inclusive prices are assumed. A field appears only when it says something else.
- **Unknown is refused.** An unknown field, node kind or name fails validation. A source row the
  format cannot express is skipped and reported, never approximated.

The bill period is part of the country's `bill` today and a tariff may replace the bill. Whether
the period belongs to the country or the tariff is still an open decision.

## What runs where

| What | Where | When | Needs |
| --- | --- | --- | --- |
| `ci.yml`: validate every file, rebuild and compare the indexes, refuse an edited revision, run the tests with a 98% coverage floor | GitHub Actions runner | Every pull request, every push to `main` | Nothing |
| `sync.yml`: read every source, each in its own job, write new revisions, open one pull request | GitHub Actions runner | Mondays 05:17 UTC, or by hand | The repository setting "Allow GitHub Actions to create and approve pull requests" |
| Review and merge | A person | When a sync pull request is open | A few minutes |
| Client library | Wherever the caller runs, for example a Home Assistant integration | On demand | HTTPS to the raw files |

The sync is plain Python, standard library only. It uses no model, no secret and no machine of
ours. A public repository gets Actions minutes free. A weekly run takes a few minutes.

### One sync path

    source.read()  ->  Plan  ->  to_tariff (validates)  ->  apply (revision rules)  ->  build

- A source module only fetches and parses. It returns `Plan` values and a list of what it skipped.
- `to_tariff` is the single place a plan becomes a file, and it validates before anything is
  written.
- `apply` decides: new tariff, new revision, unchanged, or refused. A stored tariff the source no
  longer lists is reported as missing and left alone. Withdrawing a tariff is a person's call.
- Each source is all or nothing. If it fails, its files are restored and the other sources still
  run. In the workflow each source is its own job. The last job takes the tariff files of the
  sources that finished, builds the indexes once and opens the pull request.
- A source that failed gets its own `sync-failed` issue with its report and a link to the run.
  If that source already has an open issue, the new failure is added to it as a comment. The
  run is marked failed so it is noticed, and the other sources' changes still reach the pull
  request.
- A run that finds no price change writes nothing, so there is no pull request and no noise.

### The pull request

- Each run starts from `main` and reads everything again, so a new sync pull request replaces an
  older open one. The workflow closes the older one with a link.
- The body is the run report: added, revised, unchanged counts, refusals, missing and skipped.
- A pull request opened with the built-in token does not start workflows. The sync starts CI on
  its branch itself. A fine-grained token in the `SYNC_TOKEN` secret removes that step and is
  optional.
- Nothing is merged automatically. Branch protection on `main` should require the CI check.

### Things to know

- GitHub disables a scheduled workflow after 60 days without repository activity. A merged sync
  pull request counts as activity. If prices are quiet for two months, re-enable it from the
  Actions tab.
- `--record DIR` saves every response and `--replay DIR` runs from saved ones. Use them to debug
  a source without fetching again.
- Two values are edited by hand once a year: the booklet link and start date in
  `scripts/sync/sources/za_eskom.py`.

## How a library uses the store

    Store(url_reader(base))
      countries()                      one request: tariffs/electricity/index.json
      providers(cc), tariffs(cc, p)    one request: tariffs/electricity/<cc>/index.json, checked
      revision(cc, p, t, on)           no request: picks the revision in force on a date
      definition(cc, p, t, on, area)   one request: the tariff file, checked, then compiled

`definition` returns the document `lib.tariff.load_definition` reads. The caller then prices a
bill with `price_bill` or a half-hourly history with `price_period`. A file that does not match
its checksum is refused.

### The local cache

`Store.cached(base, folder)` keeps everything it reads in a folder, at the same paths as the
store. A tariff in use is downloaded once.

- **No list of what is held.** The cached countries index and country index are that list: they
  carry the checksum of every file below them. A cached file is used when it is the file its
  index describes, and fetched again when it is not, for example after a tariff gained an end
  date. A damaged or deleted cache file is simply fetched again.
- **One age.** Only the countries index goes stale. It is read again after `max_age` (a day by
  default) or on `refresh()`. That one small request shows which countries changed, and an
  unchanged country costs nothing more.
- **The country file is cached with the tariff**, so a cached tariff can always be priced.
- **No network.** When the store cannot be reached, or answers with something that is not the
  index, the cache is used and `store.offline` is true. A tariff never fetched is reported as
  not readable.
- **A whole country on request.** `fetch_country(cc)` brings in every revision, and
  `fetch_country(cc, on=day)` only what is on offer that day. Use it before comparing bills
  across tariffs. A second call downloads nothing.
- A path taken from an index is refused unless it stays inside the store, so a bad index cannot
  write outside the cache folder.

### A tariff the store does not hold

`custom_definition(cc, doc, on)` takes a tariff written like a tariff file and returns the same
definition a stored tariff gives. The caller types names, dates, bands and prices. `provider` and
`source` may be left out. The country's currency, time zone, tax and standard bill come from the
store, and a custom `bill` may replace the standard one. The export may be a stored export tariff
or a custom one. For a country the store does not hold, the caller passes the country values too
(`block`), and then nothing is read from the store.

A custom tariff passes the same validator as a stored one, so anything a custom tariff can say,
a stored tariff can say. Keeping the custom tariff is the caller's job: an integration saves it
with its own settings. A custom tariff that is right for other people is a pull request away
from the store, because it is already in the store's format.

`lib/tariffstore` uses only the standard library and has no Home Assistant import, so it can be
copied into an integration's `lib/` beside `lib/tariff`, or published as a package later.

## Other services, and combined tariffs

Each service is a folder under `tariffs/` and a complete store of its own:
`tariffs/electricity/` today, `tariffs/gas/` or `tariffs/water/` later. A client is pointed at
one service. The reasons:

- Tax, units, bands and the standard bill differ by service, so each service has its own country
  values. Only the currency and time zone would be repeated.
- A client that wants electricity never downloads a gas index.
- Adding a service changes no existing path, so no client breaks.

A combined tariff, such as a dual fuel discount, is not a third kind of tariff. It is a bundle:
a small file that names one tariff in each service and the discount for holding both. Bundles
would live in `tariffs/bundles/<cc>/<provider>/<bundle>/<n>.json`. They are not built, and no
tariff held today needs one.

## Billing structures

The format is open at one point only: the bill tree. A new structure is a new node kind or band
field, not a new file shape.

What the store and the engine both handle today:

| Structure | How it is written |
| --- | --- |
| Flat rate | One band |
| Day and night, peak windows | Bands with `hours` |
| Weekday, weekend, seasonal and public-holiday rates | Bands with `days`, `months`, `holidays` |
| Daily standing charge | `per_day` |
| Monthly or bill-period charges and levies | `per_period`, with a `share` for part periods |
| Percentage discounts and surcharges | `adjust` |
| Tax added or included, at any level, on any base | `tax`, nested |
| VAT that changes on a date | Dated `vat` list in the country block |
| Prices by region | `areas` |
| Export payment, flat or by time of day | An export tariff with one band or several, paired by `export` |
| Hours in another time zone than the country's | `timezone` on the tariff |

What is not handled, and where the work is:

| Structure | Store | Engine (`lib/tariff`, in the integration repository) |
| --- | --- | --- |
| Bill periods other than monthly (quarterly, every N days, meter-read dates) | Needs a period rule | Needs the rule |
| Volume tiers (first N kWh at one price) | Needs a `tiers` field on a rate | Needs tiered pricing |
| Demand charges (per kW of peak) | Needs a node kind | Needs peak tracking |

| Dynamic half-hourly prices | See below | Needs a price series input |
| Prepayment, block credits, minimum bills | Not designed | Not designed |

The rule for adding one: the engine supports it first, then the format gains the field, then a
real bill is added as a `checks` entry. Until then a tariff that needs it is refused or skipped,
never priced wrongly.

## Dynamic prices (designed, not built)

A dynamic tariff changes every half hour, so its prices cannot live in a revision file reviewed
weekly. The design keeps the two apart.

- **The tariff** stays a normal reviewed file. In place of `rates`, an area names a feed:
  `"prices": "octopus-agile"`. Standing charge, tax and the bill tree are unchanged.
- **The prices** are one file per feed, area and day:
  `prices/<cc>/<feed>/<area>/<yyyy>/<mm>/<dd>.json`, holding the interval length and the list of
  prices from local midnight. A published day is never changed.
- **A feed index** per feed and area lists the latest day and each month's checksum, so a client
  asks once and fetches only the days it lacks.
- **Updates** run from a second workflow, hourly or a few times a day depending on when the feed
  publishes. Prices are machine-checked (full day, right interval count, within a sane range,
  no gap from the day before) and committed straight to a separate `prices` branch. No pull
  request, because nobody can review 48 numbers a day per region. `main` stays reviewed.
- **The client** gains `prices(cc, feed, area, day)`, read from the `prices` branch.
- **The engine** needs a way to price energy against a price series. That is work in the
  integration repository and comes first.

Two kinds of feed exist. A supplier feed gives the price the customer pays (Octopus Agile in
Great Britain is the open example). A wholesale feed gives the market price, and the retail price
is then a formula on top (uplift, cap, tax), which the tariff must state. Start with a supplier
feed. Size is small: 48 values a day per area is about 1 MB a year per feed for fourteen regions.

A GitHub schedule can run late by several minutes and is not guaranteed. That is fine for
day-ahead prices published hours before they apply. It is not good enough for prices published
minutes ahead.

## Finding new sources (a scheduled AI task)

Looking for a new country's rates or a new feed is research, so it suits an AI task. It stays
outside the data path.

- `skills/find-sources/SKILL.md` holds the steps.
- It runs on a schedule, monthly by default, in a hosted session. It needs no private machine.
- It reads `sources/`, `tariffs/electricity/unavailable.json` and the open issues, searches for official
  fixed-tariff and dynamic-price sources not yet covered, and checks that each one can be read.
- Its output is a pull request that adds or updates source notes under `sources/`, and at most
  one issue per source worth building. It never writes under `tariffs/` or `prices/`, and it never
  merges.
- A person decides which source gets a sync module. The module is ordinary code with tests, and
  from then on the scheduled sync reads that source with no AI.

## Tests

- The library and scripts: every validator rule, the compile step, the index build, the client,
  each sync rule and each source parser on saved or synthetic responses. Branch coverage is 99%
  and CI fails under 98%.
- Every stored tariff: valid, compiles for every area, indexed as built, checksums match, prices
  within a sane range, and each `checks` entry reproduced.
- End to end: a tariff typed by hand is built, fetched through the client and priced by the
  engine to a figure worked out by hand.
- The engine tests need Python 3.14 and skip on an older one. CI runs 3.14.

Not covered by tests: the live sources. A parser test proves the code reads the saved shape, not
that the site still has that shape. The scheduled run is the check, and a source that changes
shape fails loudly and opens an issue.
