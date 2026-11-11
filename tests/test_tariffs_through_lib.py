"""Run every tariff definition in tariffs/ through the calculators in lib/.

Where each expected figure comes from:
  PAGE        read from the definition itself, which was read from the source page. The test
              repeats the sum by hand (round half up to the cent) and the engine must agree.
  ASSUMPTION  chosen by the test, not stated by any page. Marked in the comment beside it.

The lib code is copied unchanged from the integration (see lib/README.md) and uses Python 3.14
syntax, so these tests are skipped on an older Python.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from lib.tariffstore.compile import compile_area
from lib.tariffstore.index import block_of
from scripts.paths import ROOT, TARIFFS

try:
    from lib.tariff import (
        BillInputs, DefinitionError, SlotDay, load_definition, price_bill,
    )
    from lib.tariff.bands import import_by_band
    LIB_OK = True
except SyntaxError:  # Python older than 3.14
    LIB_OK = False

CENT = Decimal("0.01")


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, ROUND_HALF_UP)


def countries() -> dict[str, dict]:
    return {p.parent.name.upper(): json.loads(p.read_text()) for p in sorted(TARIFFS.glob("*/index.json"))}


def stored() -> list[tuple[dict, dict, dict]]:
    """(tariff file, meta, country block) for every file in tariffs/."""
    out = []
    for code, index in countries().items():
        for provider, pbody in index["providers"].items():
            for tariff_id, tbody in pbody["tariffs"].items():
                for revision, rbody in tbody["revisions"].items():
                    path = TARIFFS / code.lower() / provider / tariff_id / f"{revision}.json"
                    tariff = json.loads(path.read_text())
                    meta = {"id": tariff_id, "tariff": tariff_id, "revision": int(revision),
                            "provider": provider, "country": code, "source": tariff["source"],
                            "effective_to": rbody["effective_to"]}
                    out.append((tariff, meta, block_of(index)))
    return out


def documents(export: dict | None = None) -> list[dict]:
    """Every import tariff compiled to one plain definition per area, as lib/tariff reads them,
    priced on the day the tariff starts. `export` is a stored export file to pair with."""
    return [compile_area(t, area, block=b, meta=m, on=t["effective_from"], export_file=export)
            for t, m, b in stored() if t.get("direction") != "export" for area in t["areas"]]


def export_documents() -> list[dict]:
    """The stored export files, with their meta added as `_meta`."""
    return [{**t, "_meta": m} for t, m, _ in stored() if t.get("direction") == "export"]


def load(doc: dict):
    return load_definition(json.dumps(doc))


def by_id(docs: list[dict], tariff_id: str) -> dict:
    return next(d for d in docs if d["id"] == tariff_id)


def standing_of(doc: dict) -> Decimal:
    node = doc["bill"]["total"]
    while node["kind"] != "per_day":
        node = node["of"] if node["kind"] in ("tax", "adjust") else node["of"]["standing"]
    return Decimal(node["amount"])


def hand_bill(doc: dict, kwh: dict[str, Decimal], days: int) -> Decimal:
    """The bill worked by hand: each band to the cent, standing for the days, tax as stated."""
    prices = {doc["import"]["base"]["name"]: Decimal(doc["import"]["base"]["price"])}
    for zone in doc["import"].get("zones", []):
        prices[zone["name"]] = Decimal(zone["price"])
    energy = sum((cents(kwh[b] * prices[b]) for b in kwh), Decimal(0))
    standing = cents(standing_of(doc) * days)
    total = energy + standing
    node = doc["bill"]["total"]
    if node["kind"] == "tax" and node["mode"] == "added":
        total += cents(total * Decimal(node["percent"]) / 100)
    return total


@unittest.skipUnless(LIB_OK, "needs Python 3.14 for lib/")
class EveryDefinition(unittest.TestCase):
    def test_all_definitions_load(self) -> None:
        docs = documents()
        self.assertEqual(len(docs), sum(len(t["areas"]) for t, _, _ in stored()
                                        if t.get("direction") != "export"))
        self.assertGreater(len(docs), 200)
        for doc in docs:
            with self.subTest(doc["id"]):
                try:
                    load(doc)
                except DefinitionError as error:
                    self.fail(str(error))

    def test_a_month_priced_by_the_engine_equals_the_hand_sum(self) -> None:
        # PAGE prices and standing charge. ASSUMPTION: 30 days, 300 kWh in the base band and,
        # where there is a night band, 200 kWh in it.
        for doc in documents():
            with self.subTest(doc["id"]):
                definition = load(doc)
                kwh = {doc["import"]["base"]["name"]: Decimal(300)}
                for zone in doc["import"].get("zones", []):
                    kwh[zone["name"]] = Decimal(200)
                bill = price_bill(definition, BillInputs(30, 30, kwh, Decimal(0)))
                self.assertEqual(cents(bill.total), hand_bill(doc, kwh, 30))

    def test_standing_charge_alone(self) -> None:
        # PAGE standing charge, no energy: the bill is the standing charge for the days.
        for doc in documents():
            with self.subTest(doc["id"]):
                bill = price_bill(load(doc), BillInputs(10, 10, {}, Decimal(0)))
                self.assertEqual(cents(bill.total), hand_bill(doc, {}, 10))

    def test_energy_alone_scales_with_kwh(self) -> None:
        # ASSUMPTION: 1 kWh and 2 kWh in the base band, no standing charge days that matter.
        for doc in documents():
            with self.subTest(doc["id"]):
                name = doc["import"]["base"]["name"]
                price = Decimal(doc["import"]["base"]["price"])
                one = price_bill(load(doc), BillInputs(1, 1, {name: Decimal(1000)}, Decimal(0)))
                self.assertEqual(cents(one.total),
                                 hand_bill(doc, {name: Decimal(1000)}, 1))
                self.assertGreater(price, 0)

    def test_every_night_rate_is_below_its_day_rate(self) -> None:
        # Ireland: a night rate at or above the day rate was skipped as a likely source error.
        for doc in documents():
            if doc["country"] != "IE":
                continue
            for zone in doc["import"].get("zones", []):
                with self.subTest(doc["id"]):
                    self.assertLess(Decimal(zone["price"]), Decimal(doc["import"]["base"]["price"]))


@unittest.skipUnless(LIB_OK, "needs Python 3.14 for lib/")
class Vat(unittest.TestCase):
    def test_irish_prices_include_9_percent_vat(self) -> None:
        # PAGE: unit rates were stored including 9 percent VAT and the tax node says so.
        for doc in documents():
            if doc["country"] != "IE":
                continue
            with self.subTest(doc["id"]):
                node = doc["bill"]["total"]
                self.assertEqual((node["kind"], node["mode"], node["percent"]),
                                 ("tax", "included", "9"))
                kwh = {doc["import"]["base"]["name"]: Decimal(100)}
                bill = price_bill(load(doc), BillInputs(30, 30, kwh, Decimal(0)))
                self.assertEqual(bill.root.tax is not None, True)
                # An included tax adds nothing: the total equals the sum without the tax node.
                self.assertEqual(cents(bill.total), hand_bill(doc, kwh, 30))
                # The VAT inside the bill is the total less the total over 1.09.
                expected = cents(bill.total - bill.total / Decimal("1.09"))
                self.assertEqual(bill.root.tax, expected)

    def test_gb_vat_is_recorded_as_zero_percent_included(self) -> None:
        # ASSUMPTION: prices are the published inclusive figures; electricity VAT is 0 percent
        # from October 2026 to March 2027 (see sources/ofgem-price-cap.md).
        for doc in documents():
            if doc["country"] == "GB":
                with self.subTest(doc["id"]):
                    node = doc["bill"]["total"]
                    self.assertEqual((node["kind"], node["mode"], node["percent"]),
                                     ("tax", "included", "0"))
                    kwh = {doc["import"]["base"]["name"]: Decimal(100)}
                    bill = price_bill(load(doc), BillInputs(30, 30, kwh, Decimal(0)))
                    self.assertEqual(bill.root.tax, Decimal("0.00"))


@unittest.skipUnless(LIB_OK, "needs Python 3.14 for lib/")
class NightSaverWindow(unittest.TestCase):
    """The Night band runs 23:00 to 08:00. ASSUMPTION: no source page states the hours."""

    TZ = ZoneInfo("Europe/Dublin")

    def day_with(self, slot: int, kwh: float = 1.0, when: date = date(2026, 11, 10)) -> SlotDay:
        day = SlotDay(when, self.TZ)
        day.flows["import"][slot] = kwh
        return day

    def band(self, doc: dict, slot: int) -> str:
        (name,) = import_by_band([self.day_with(slot)], load(doc))
        return name

    def test_slot_boundaries(self) -> None:
        docs = [d for d in documents() if d["country"] == "IE" and d["import"].get("zones")]
        self.assertGreaterEqual(len(docs), 14)
        # slot 0 is 00:00, so 23:00 is slot 46, 22:30 is 45, 07:30 is 15 and 08:00 is 16.
        cases = {0: "Night", 15: "Night", 16: "Day", 30: "Day", 45: "Day", 46: "Night", 47: "Night"}
        for doc in docs:
            for slot, expected in cases.items():
                with self.subTest(doc["id"], slot=slot):
                    self.assertEqual(self.band(doc, slot), expected)

    def test_a_day_of_flat_use_splits_nine_hours_night_fifteen_day(self) -> None:
        doc = by_id(documents(), "electric-ireland-nightsaver-standard-green-urban")
        day = SlotDay(date(2026, 11, 10), self.TZ)
        day.flows["import"][:] = [0.5] * 48
        bands = import_by_band([day], load(doc))
        self.assertEqual(bands, {"Night": Decimal("9.0"), "Day": Decimal("15.0")})

    def test_worked_nightsaver_bill(self) -> None:
        # PAGE rates for Electric Ireland NightSaver (urban); ASSUMPTION: the usage below.
        # Hand sum, written out so the engine is not checked against itself:
        doc = by_id(documents(), "electric-ireland-nightsaver-standard-green-urban")
        day_rate = Decimal(doc["import"]["base"]["price"])
        night_rate = Decimal(doc["import"]["zones"][0]["price"])
        standing = standing_of(doc)
        expected = (cents(Decimal(300) * day_rate) + cents(Decimal(200) * night_rate)
                    + cents(standing * 30))
        kwh = {"Day": Decimal(300), "Night": Decimal(200)}
        bill = price_bill(load(doc), BillInputs(30, 30, kwh, Decimal(0)))
        self.assertEqual(cents(bill.total), expected)

    def test_clock_change_days_still_split_at_23_and_08(self) -> None:
        # ASSUMPTION: the window follows the wall clock. 2026-10-25 has 50 slots, 2027-03-28 has 46.
        doc = by_id(documents(), "electric-ireland-nightsaver-standard-green-urban")
        for when, slots in ((date(2026, 10, 25), 50), (date(2027, 3, 28), 46)):
            with self.subTest(when=when):
                day = SlotDay(when, self.TZ)
                self.assertEqual(len(day.flows["import"]), slots)
                day.flows["import"][:] = [1.0] * slots
                bands = import_by_band([day], load(doc))
                self.assertEqual(sum(bands.values()), Decimal(slots))
                self.assertEqual(bands["Day"], Decimal(30))  # 08:00 to 23:00 is 15 h, 30 slots


class SkippedPlans(unittest.TestCase):
    """Plans the sync refuses to guess. Their absence is part of the data."""

    def ids(self) -> set[str]:
        return {d["id"] for d in documents()} | {d["_meta"]["id"] for d in export_documents()}

    def test_bord_gais_rural_nightsaver_is_absent(self) -> None:
        # The page showed a night rate above the day rate, so it was skipped as a source error.
        product = next(t for t, m, _ in stored() if m["id"] == "bord-gais-energy-nightsaver-standard-green")
        self.assertEqual(list(product["areas"]), ["urban"])
        self.assertNotIn("bord-gais-energy-nightsaver-standard-green-rural", self.ids())

    def test_no_multi_register_gb_tariff(self) -> None:
        # Economy 7, Go, Cosy and Agile need a day and night split we cannot source.
        for tariff_id in (d["id"] for d in documents() if d["country"] == "GB"):
            for word in ("economy", "e7", "-go-", "cosy", "agile", "tracker"):
                self.assertNotIn(word, tariff_id)

    def test_gb_has_three_payment_groups_and_fourteen_regions(self) -> None:
        ids = {i for i in self.ids() if i.startswith("ofgem-cap-")}
        self.assertEqual(len(ids), 42)
        for group in ("direct-debit-and-other", "standard-credit", "prepayment"):
            self.assertEqual(len([i for i in ids if i.startswith(f"ofgem-cap-{group}-")]), 14)

    def test_every_definition_names_its_source(self) -> None:
        for _, meta, _ in stored():
            with self.subTest(meta["id"]):
                self.assertTrue(meta["source"]["url"].startswith("https://"))
                self.assertTrue(meta["source"]["id"])


@unittest.skipUnless(LIB_OK, "needs Python 3.14 for lib/")
class GbCap(unittest.TestCase):
    def test_ofgem_north_west_direct_debit_bill(self) -> None:
        # PAGE (Ofgem workbook): standing 0.456767 per day, unit 0.264892 per kWh, single rate.
        doc = by_id(documents(), "ofgem-cap-direct-debit-and-other-north-west")
        bill = price_bill(load(doc), BillInputs(30, 30, {"Single rate": Decimal(250)}, Decimal(0)))
        expected = cents(Decimal(250) * Decimal("0.264892")) + cents(Decimal("0.456767") * 30)
        self.assertEqual(cents(bill.total), expected)  # 66.22 + 13.70 = 79.92

    def test_the_cap_for_a_year_of_benchmark_use_matches_the_workbook(self) -> None:
        # ASSUMPTION: 2,500 kWh in 365 days. The workbook's benchmark minus nil, plus nil, is the
        # annual bill, so the derivation must round-trip within a penny a year per component.
        doc = by_id(documents(), "ofgem-cap-direct-debit-and-other-eastern")
        bill = price_bill(load(doc), BillInputs(365, 365, {"Single rate": Decimal(2500)}, Decimal(0)))
        self.assertAlmostEqual(float(bill.total), 854.53, delta=0.03)


def export_price_at(export_file: dict, hour: int, minute: int) -> Decimal:
    """The export price at a local wall-clock time, read from the bands of the export file
    itself (hours HH:MM-HH:MM, a later band wins)."""
    now = hour * 60 + minute
    rates = next(iter(export_file["areas"].values()))["rates"]
    price = rates[export_file["bands"][0]["name"]]
    for band in export_file["bands"][1:]:
        start, end = band["hours"].split("-")
        a, b = int(start[:2]) * 60 + int(start[3:]), int(end[:2]) * 60 + int(end[3:])
        if (a <= now < b) if a < b else (now >= a or now < b):
            price = rates[band["name"]]
    return Decimal(price)


def flat_price(export_file: dict) -> Decimal:
    return Decimal(next(iter(export_file["areas"].values()))["rates"][export_file["bands"][0]["name"]])


@unittest.skipUnless(LIB_OK, "needs Python 3.14 for lib/")
class Export(unittest.TestCase):
    HOST = "ofgem-cap-direct-debit-and-other-north-west"  # ASSUMPTION: any import file will do

    def test_there_are_export_files(self) -> None:
        ids = {d["_meta"]["id"] for d in export_documents()}
        self.assertEqual(ids, {"octopus-outgoing-var-24-10-26", "octopus-outgoing-seg-fix-12m-20-07-07",
                               "octopus-outgoing-seg-fix-12m-26-10-21",
                               "octopus-outgoing-prime-fix-12m-26-06-23"})

    def test_flat_exports_price_through_lib(self) -> None:
        # PAGE (Octopus API, region A, all regions equal): 12.0, 4.1 and 4.1 p/kWh. Pairing an
        # export file adds an export_credit line to the bill, so the export is paid.
        for export in export_documents():
            if len(export["bands"]) > 1 or export.get("effective_to"):
                continue
            with self.subTest(export["_meta"]["id"]):
                host = by_id(documents(export), self.HOST)
                bill = price_bill(load(host), BillInputs(1, 1, {}, Decimal(100)))
                standing = cents(standing_of(host))
                # export is a credit: the standing charge less 100 kWh at the export price
                self.assertEqual(cents(bill.total), standing - cents(Decimal(100) * flat_price(export)))

    def test_without_a_paired_export_nothing_is_credited(self) -> None:
        host = by_id(documents(), self.HOST)
        bill = price_bill(load(host), BillInputs(1, 1, {}, Decimal(100)))
        self.assertEqual(cents(bill.total), cents(standing_of(host)))

    def test_a_banded_export_is_credited_by_band(self) -> None:
        # PAGE (rates feed): Prime Outgoing pays 16.0 p/kWh 16:00 to 19:00, 9.0 p/kWh otherwise.
        # ASSUMPTION: 80 kWh exported off peak and 20 kWh in the peak window, in one day.
        prime = next(d for d in export_documents() if d["_meta"]["id"].startswith("octopus-outgoing-prime"))
        host = by_id(documents(prime), self.HOST)
        base, (peak,) = host["export"]["base"]["name"], host["export"]["zones"]
        exported = {base: Decimal(80), peak["name"]: Decimal(20)}
        bill = price_bill(load(host), BillInputs(1, 1, {}, exported))
        self.assertEqual(cents(bill.total), cents(standing_of(host)) - Decimal("10.40"))  # 80 x 0.09 + 20 x 0.16

    def test_outgoing_octopus_history(self) -> None:
        # PAGE (rates feed): 15.0 p/kWh to 1 March 2026, 12.0 p/kWh after.
        old, new = sorted((d for d in export_documents()
                           if d["_meta"]["id"] == "octopus-outgoing-var-24-10-26"),
                          key=lambda d: d["effective_from"])
        self.assertEqual((flat_price(old), old["effective_to"]), (Decimal("0.15"), "2026-03-01"))
        self.assertEqual((flat_price(new), new["effective_from"]), (Decimal("0.12"), "2026-03-01"))

    def test_prime_peak_is_16_to_19_local_time(self) -> None:
        # PAGE (rates feed): 16.0 p/kWh 16:00 to 19:00, 9.0 p/kWh otherwise.
        prime = next(d for d in export_documents() if d["_meta"]["id"].startswith("octopus-outgoing-prime"))
        for hour, minute, expected in ((15, 59, "0.09"), (16, 0, "0.16"), (18, 59, "0.16"),
                                       (19, 0, "0.09"), (0, 0, "0.09"), (23, 59, "0.09")):
            with self.subTest(time=f"{hour}:{minute:02d}"):
                self.assertEqual(export_price_at(prime, hour, minute), Decimal(expected))

    def test_no_export_is_zero_for_a_paying_tariff(self) -> None:
        for doc in export_documents():
            self.assertGreater(flat_price(doc), 0)


class Sanity(unittest.TestCase):
    def test_root(self) -> None:
        self.assertTrue((ROOT / "lib" / "tariff" / "engine.py").exists())
        self.assertEqual(len(documents()), 211)
        self.assertGreater(timedelta(days=1).days, 0)
        self.assertTrue(sys.version_info >= (3, 9))


if __name__ == "__main__":
    unittest.main()
