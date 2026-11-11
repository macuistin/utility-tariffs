# lib/

The store library, and a copy of the tariff and bill calculators the Home Assistant integration
uses. They use only the standard library, so any script, skill or integration can import them.

| Folder | What it holds |
| --- | --- |
| `tariff/` | The tariff definition reader, the bill engine, band assignment, half-hourly slots and repricing. `tariff/README.md` lists the public names |
| `tariffstore/` | The store's own code: validator, checksum, index build, compile step and the client (`Store`). Written here, tested here |
| `timeutil/` | Clock helpers that `tariff/` imports (`shift_real`, `elapsed_seconds`, `local_time_on`) |

## Provenance

`tariff/` and `timeutil/` are copied unchanged from `macuistin/givenergy_inverter_manager`, commit
`68ec1923ac68817032dfaa51cc3c82817d2ce115` on `main`, folders
`custom_components/givenergy_inverter_manager/lib/tariff` and `.../lib/timeutil`, on 2026-11-11.
Calculation code only. Nothing from the integration glue (config, coordinator, entities) is here.
Behaviour is identical to that commit. Do not edit these files here: change them in the source
repository and copy them again, updating the commit above.

The code uses Python 3.14 syntax (for example `except A, B:`), so it needs Python 3.14 or newer.

## Known gaps between our files and this library

Found by `tests/test_tariffs_through_lib.py`. Our tariff files are not what the library reads. The
compile step (`lib/tariffstore/compile.py`) builds the library's definition from a tariff file and its
country block, and closes most gaps itself. What remains is to fix on the library side, in the source
repository, not by editing the copy here.

1. The library accepts only ISO 3166-2 region codes. Our area `region` codes (`GSP-A`,
   `OFGEM-EASTERN`) are not, so compile leaves the region null. A customer's region is chosen by the
   area key.
2. Closed. The library prices an export by time of day (export
   `zones`), so Prime Outgoing's 16:00 to 19:00 rate is credited by band.
3. The library requires an `export` price in every definition. With no export file paired, compile
   supplies 0 and adds no export line, so an unpaired tariff credits nothing. The library cannot say
   "unknown".
4. The library has one bill period rule, `monthly`, and no volume tiers, demand charges or dynamic
   prices. `docs/design.md` lists what each would need.
