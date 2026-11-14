# lib/

The store library and the bill engine. This repository is where both are written and tested, and
it is the source of truth for all tariff and billing code and calculations. They use only the
standard library, so any script, skill or integration can import or copy them.

| Folder | What it holds |
| --- | --- |
| `tariff/` | The tariff definition reader, the bill engine, band assignment, half-hourly slots and repricing. `tariff/README.md` lists the public names |
| `tariffstore/` | The store's own code: validator, checksum, index build, compile step and the client (`Store`) |
| `tariffranking/` | Prices every plan over the same measured usage and ranks them, with the current plan's rank. Imports `tariff/` only |
| `timeutil/` | Clock helpers that `tariff/` imports (`shift_real`, `elapsed_seconds`, `local_time_on`) |

## Using it from another project

Copy the folders as they stand and do not edit the copy. Record the commit copied, so a
later copy can be compared. The Home Assistant integration `macuistin/givenergy_inverter_manager`
does this with a script, a weekly workflow that opens a pull request, and a release check. Change
the code here, with its tests, and let the copy follow.

`tariff/` and `timeutil/` began in that integration and moved here on 2026-11-11, unchanged from
its commit `68ec1923ac68817032dfaa51cc3c82817d2ce115`.

The code uses Python 3.14 syntax (for example `except A, B:`), so it needs Python 3.14 or newer.

## Known gaps between the tariff files and the engine

Found by `tests/test_tariffs_through_lib.py`. A tariff file is not what the engine reads. The
compile step (`lib/tariffstore/compile.py`) builds the library's definition from a tariff file and its
country block, and closes most gaps itself. What remains is work in `lib/tariff`.

1. The library accepts only ISO 3166-2 region codes. Our area `region` codes (`GSP-A`,
   `OFGEM-EASTERN`) are not, so compile leaves the region null. A customer's region is chosen by the
   area key.
2. Closed. The library prices an export by time of day (export
   `zones`), so Prime Outgoing's 16:00 to 19:00 rate is credited by band.
3. The library requires an `export` price in every definition. With no export file paired, compile
   supplies 0 and adds no export line, so an unpaired tariff credits nothing. The library cannot say
   "unknown".
4. A bill period is a whole number of calendar months. The library has no period of a fixed
   number of days, and no volume tiers, demand charges or dynamic prices. `docs/design.md` lists what each would need.
