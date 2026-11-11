# Format

Three kinds of file. Each holds the facts of its own level once.

| File | Holds |
| --- | --- |
| `tariffs/electricity/index.json` | The countries, each with the checksum of its index |
| `tariffs/electricity/<cc>/index.json` | The country's shared values, then its providers, tariffs and revisions |
| `tariffs/electricity/<cc>/<provider>/<tariff>/<n>.json` | One revision of one tariff |

The country, provider id, tariff id and revision number are the path. A file never repeats them.
`lib/tariffstore/schema.py` is the format in code, and it is the only validator.

## The country index

```json
{
  "schema": 1,
  "country": "IE",
  "currency": "EUR",
  "timezone": "Europe/Dublin",
  "vat_percent": "9",
  "inputs": { "bill_start_day": { "type": "integer", "min": 1, "max": 28, "default": 1 } },
  "bill": {
    "period": { "rule": "monthly", "start_day": "$input.bill_start_day" },
    "total": {
      "kind": "tax", "name": "VAT", "mode": "included", "percent": "$country.vat_percent",
      "of": { "kind": "sum", "of": {
        "energy":   { "kind": "energy_by_band", "round_bands": true },
        "standing": { "kind": "per_day" } } }
    }
  },
  "providers": {
    "bord-gais-energy": { "name": "Bord Gais Energy", "tariffs": {
      "bord-gais-energy-nightsaver-standard-green": {
        "name": "NightSaver Standard Green",
        "revisions": { "1": {
          "effective_from": "2026-11-09", "effective_to": null, "checksum": "sha256:..." } } } } }
  }
}
```

**Everything above `providers` is the country block**, edited by hand. It holds what every tariff
in the country shares.

| Key | Meaning |
| --- | --- |
| `country` | ISO 3166-1 alpha-2, the same as the folder |
| `currency` | ISO 4217 |
| `timezone` | IANA zone the band hours are read in |
| `vat_percent` | A decimal string, or a list where later entries win. An entry with no dates is the fallback and a dated entry after it is a temporary rate. A date no entry covers has no rate, and compiling stops rather than price at zero |
| `bill` | The country's standard bill: a period and a tree of nodes (below) |
| `inputs` | What the customer supplies, with type and range. Today only the bill start day |
| `availability`, `reason` | `partial` needs a `reason` saying what is missing. Left out means `available` |
| any other key | A decimal string a bill can use as `$country.<name>`, a levy say |

**`providers` is the tariff collection**, built from the tariff files and from nothing else. A
provider's name and a tariff's name come from its newest file. Each revision has its dates and the
checksum of its file. A tariff that pays for export has `"direction": "export"`. The file of
revision `n` is at `<provider-id>/<tariff-id>/<n>.json`, so no path is stored.

## A tariff file

```json
{
  "schema": 1,
  "name": "NightSaver Standard Green",
  "provider": "Bord Gais Energy",
  "effective_from": "2026-11-09",
  "source": { "id": "selectra-ie", "url": "https://selectra.ie/energy/providers/bord-gais-energy" },
  "bands": [ { "name": "Day" }, { "name": "Night", "hours": "23:00-08:00" } ],
  "areas": {
    "urban": { "label": "Urban", "standing": "0.94526",
               "rates": { "Day": "0.351307", "Night": "0.173964" } }
  }
}
```

Required:

| Key | Meaning |
| --- | --- |
| `schema` | 1 |
| `name`, `provider` | Display names |
| `effective_from` | First day the prices apply |
| `source` | `id` names a file in `sources/`. `url` is where the figures were read |
| `bands` | The first is the base rate and has only a name. Each later band has `hours` in local clock time and wins over the bands before it, so the order is the priority. A later band may also have `days` (`mon` to `sun`), `months` (1 to 12) and `"holidays": "weekend"` (a public holiday counts as a weekend day) |
| `areas` | One row per place that is priced differently. A tariff with one price has one area, `all`. A row has `rates` (a price for every band), `standing` (per day) and, unless it is `all`, a `label`. `region` is an optional supplier region code |

Optional, written only when they say something:

| Key | Meaning |
| --- | --- |
| `effective_to` | The day the prices stop, when the source states one or the tariff is withdrawn |
| `direction` | `"export"`: the file prices exported energy. It has no standing charge and no bill. Its `bands` work like an import tariff's, so one band is a flat export price and later bands with `hours` pay a different price by time of day |
| `export` | `provider-id/tariff-id` of the export tariff this tariff pays. Only where the source states the pairing |
| `prices_include_tax` | `false` when the source quotes prices without tax |
| `timezone` | When the tariff's hours are in another zone than the country's |
| `customer_class` | `"commercial"`. Residential is the default |
| `bill`, `inputs` | A bill that replaces the country's standard one, with the same node kinds |
| `checks` | Worked bills the tariff must reproduce. A tariff with one is complete |

Prices are decimal strings in the currency's major unit, with at most six decimal places and no
trailing zeros.

## The bill tree

Node kinds: `sum` (named children), `tax` (`included` or `added`), `adjust` (a named percentage
added to what it wraps, negative for a discount), `energy_by_band`, `export_credit`, `per_day`,
`per_period` (with a `share`). Nesting sets the order and the tax base. `$country.<name>` takes a
value from the country block. `$input.<name>` is a customer input. An unknown kind, field or name
is refused.

## Revisions

- Revisions of a tariff are numbered 1, 2, 3 with none missing, each starting after the one before.
- A revision ends on its own `effective_to`, or else on the day the next revision starts. The index
  shows the result, so a reader never works it out.
- A published revision is never changed. The one allowed edit is adding `effective_to`.
  `python3 -m scripts.build --check --base <ref>` refuses anything else, and CI runs it.

## Checksums

`sha256:` plus the SHA-256 of the file's content in canonical form: keys sorted, no spaces, UTF-8.
It is the same function the bill engine uses (`lib.tariff.checksum_of`). A file's checksum is in the
level above it: a tariff file's in its country index, a country index's in the countries index. So
one small request shows which countries changed, and a client refuses a file that is not the one
the index describes.

## The countries index

```json
{ "schema": 1, "countries": {
    "GB": { "availability": "available", "path": "gb/index.json", "checksum": "sha256:...",
            "providers": 2, "tariffs": 10 },
    "ES": { "availability": "unavailable", "reason": "...", "checked": "2026-11-10" } } }
```

Countries with no rates are listed by hand in `tariffs/electricity/unavailable.json`
(`{"schema":1,"countries":{"XX":{"reason":"...","checked":"YYYY-MM-DD"}}}`) and merged in by the build.

## What is not in the files

No timestamps of when something was generated or checked. Git history has the first, the sync
workflow's run log has the second, and leaving them out means an unchanged tariff never changes a
byte.
