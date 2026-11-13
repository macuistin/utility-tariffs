# octopus-energy-gb

- **Covers:** Octopus Energy household tariffs in Great Britain: unit rates and standing charges
  for each of the 14 regions, with VAT-exclusive and VAT-inclusive pence figures, and the periods
  they apply to.
- **Endpoint:** https://api.octopus.energy/v1/products/ (list) and each product's self link
  (detail), with per-tariff links for standing charges and unit rates. No sign-in was needed for
  the product list or a product detail. The developer portal is at
  https://developer.oegb-kraken.energy/rest/.
- **Terms:** none found. api.octopus.energy has no robots.txt (404), the REST portal page has no
  terms or licence link, and the responses carry no rate-limit or licence headers. Treat the terms
  as unknown, keep requests few, and record any wording found later.
- **Format:** JSON. The product list includes export, prepay and half-hourly (Agile) products, so a
  sync must filter on `direction`, `is_prepay`, `is_business` and `is_tracker`.
- **Units:** pence per kWh and pence per day, with `_exc_vat` and `_inc_vat` fields.
- **Not representable yet:** half-hourly dynamic prices (Agile) need a price source, not zones.
  Time-of-use products (Go, Cosy, Flux) need their cheap windows, which are in the description
  text and not in a structured field.
- **Frequency:** daily at most.

## Export products

Synced by `scripts/sync/sources/octopus_gb.py`, with the import products: Outgoing Octopus (variable, 12.0 p/kWh since
1 March 2026, 15.0 before), the two Smart Export Guarantee products (4.1 p/kWh) and Prime Outgoing
12M Fixed (9.0 p/kWh, 16.0 p/kWh from 16:00 to 19:00 local time, read from the rates feed because
the product page shows only 9.0). All 14 regions carry the same rate and no standing charge.
Skipped: Agile Outgoing (half-hourly), Flux Export (varies by region and time), Power Pack and the
three Zero export products (restricted to registered homes).

Pairing: the API does not say which export product goes with which import product. Checked on
2026-11-13: a product has a name, a description and a list of rates and nothing that names another
product. So no Octopus import file carries an `export` reference. The export products are open to
any customer, so a client offers the customer the choice (`Store.definition(..., export=...)`).
Add a reference only where Octopus states it. The July 2020
Smart Export Guarantee product has no rate history in the files because only its current rate was
read, so its `effective_from` is the date the rate was fetched.

## Import products

A product lists a price for each payment method it can be paid by. The sync holds the monthly
direct debit price (`direct_debit_monthly`). Where another method's price differs, the run report
lists it as not held. A product that lists one method only is held at that price. A region that
has several methods and no monthly direct debit price makes the sync skip the product and say so.
