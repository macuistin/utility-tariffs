"""From the store to a priced bill, the way the Home Assistant integration would do it.

The client finds and checks a tariff and compiles it, the bill engine (lib/tariff) reads the
result and prices energy with it. Expected totals are worked by hand here.
The engine uses Python 3.14 syntax, so these are skipped on an older Python.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from lib.tariffstore import Store, folder_reader
from scripts import build
from scripts.paths import TARIFFS
from tests.fixtures import country, export, flat, holidays, tariff, write_store

try:
    from lib.tariff import BillInputs, SlotDay, load_definition, price_bill
    from lib.tariff.bands import import_by_band
    LIB_OK = True
except SyntaxError:  # Python older than 3.14
    LIB_OK = False

DAY = date(2026, 11, 10)


def priced(definition: dict, days: int, kwh: dict[str, str], export_kwh: str = "0") -> Decimal:
    inputs = BillInputs(days, days, {band: Decimal(v) for band, v in kwh.items()}, Decimal(export_kwh))
    return price_bill(load_definition(json.dumps(definition)), inputs).total


@unittest.skipUnless(LIB_OK, "needs Python 3.14 for lib/tariff")
class MadeUpStore(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        weekend = tariff(name="Weekender", bands=[
            {"name": "Day"}, {"name": "Night", "hours": "23:00-08:00"},
            {"name": "Weekend", "hours": "08:00-23:00", "days": ["sat", "sun"],
             "holidays": "weekend"}])
        for row in weekend["areas"].values():
            row["rates"]["Weekend"] = "0.2"
        levy = flat(name="With levy", bill={"total": {
            "kind": "tax", "name": "VAT", "mode": "added", "percent": "$country.vat_percent",
            "of": {"kind": "sum", "of": {
                "energy": {"kind": "adjust", "name": "Loyalty discount", "percent": "-10",
                           "of": {"kind": "energy_by_band", "round_bands": True}},
                "standing": {"kind": "per_day"},
                "levy": {"kind": "per_period", "amount": "$country.pso_levy", "share": "whole"}}}}})
        self.tariffs = write_store(Path(tmp.name), {
            "p/plan/1.json": tariff(export="p/out"), "p/out/1.json": export(),
            "p/flat/1.json": flat(), "p/flat/2.json": flat("0.3", "2026-06-01"),
            "p/weekender/1.json": weekend, "p/levy/1.json": levy},
            block={**country(), "pso_levy": "3.23", "holidays": holidays()})
        self.assertEqual(build.main([], self.tariffs), 0)
        self.store = Store(folder_reader(self.tariffs))

    def test_a_custom_tariff_with_a_custom_export_by_time_of_day_is_priced(self) -> None:
        mine = {"name": "My tariff", "effective_from": "2026-01-01",
                "bands": [{"name": "Day"}, {"name": "Night", "hours": "23:00-08:00"}],
                "areas": {"all": {"standing": "0.9", "rates": {"Day": "0.31", "Night": "0.14"}}}}
        paid = {"name": "My export", "effective_from": "2026-01-01", "direction": "export",
                "bands": [{"name": "Export"}, {"name": "Peak", "hours": "16:00-19:00"}],
                "areas": {"all": {"rates": {"Export": "0.1", "Peak": "0.2"}}}}
        definition = load_definition(json.dumps(
            self.store.custom_definition("IE", mine, DAY, export=paid)))
        exported = {"Export": Decimal(4), "Peak": Decimal(2)}
        bill = price_bill(definition, BillInputs(1, 1, {"Day": Decimal(10), "Night": Decimal(5)}, exported))
        # 10 x 0.31 + 5 x 0.14 + 0.90 standing, less 4 x 0.10 + 2 x 0.20 exported
        self.assertEqual(bill.total, Decimal("3.90"))

    def test_a_day_and_night_bill_with_an_export_credit(self) -> None:
        definition = self.store.definition("IE", "p", "plan", DAY, area="rural")
        # 300 kWh day at 0.32, 200 kWh night at 0.16, 30 days at 1.10, less 50 kWh exported at 0.12
        expected = Decimal("96.00") + Decimal("32.00") + Decimal("33.00") - Decimal("6.00")
        self.assertEqual(priced(definition, 30, {"Day": "300", "Night": "200"}, "50"), expected)

    def test_the_price_follows_the_revision_in_force(self) -> None:
        before = self.store.definition("IE", "p", "flat", date(2026, 5, 31))
        after = self.store.definition("IE", "p", "flat", date(2026, 6, 1))
        self.assertEqual(priced(before, 10, {"All day": "100"}), Decimal("30.00"))  # 25.00 + 5.00
        self.assertEqual(priced(after, 10, {"All day": "100"}), Decimal("35.00"))   # 30.00 + 5.00

    def test_a_tariff_with_its_own_bill_levy_discount_and_added_tax(self) -> None:
        definition = self.store.definition("IE", "p", "levy", DAY)
        # energy 100 x 0.25 = 25.00 less 10% = 22.50, standing 30 x 0.5 = 15.00, levy 3.23
        # net 40.73, plus 9% VAT 3.67 (3.6657 to the cent)
        self.assertEqual(priced(definition, 30, {"All day": "100"}), Decimal("44.40"))

    def test_half_hourly_energy_lands_in_weekday_and_weekend_bands(self) -> None:
        definition = load_definition(json.dumps(self.store.definition("IE", "p", "weekender", DAY, area="urban")))
        zone = ZoneInfo("Europe/Dublin")
        tuesday, saturday = SlotDay(date(2026, 11, 10), zone), SlotDay(date(2026, 11, 14), zone)
        for day in (tuesday, saturday):
            day.flows["import"][:] = [0.5] * 48
        self.assertEqual(import_by_band([tuesday], definition), {"Night": Decimal("9.0"), "Day": Decimal("15.0")})
        self.assertEqual(import_by_band([saturday], definition),
                         {"Night": Decimal("9.0"), "Weekend": Decimal("15.0")})

    def test_a_public_holiday_on_a_monday_is_priced_as_a_weekend_day(self) -> None:
        definition = load_definition(json.dumps(self.store.definition("IE", "p", "weekender", DAY, area="urban")))
        zone = ZoneInfo("Europe/Dublin")
        holiday, working = SlotDay(date(2026, 10, 26), zone), SlotDay(date(2026, 10, 19), zone)
        for day in (holiday, working):
            day.flows["import"][:] = [0.5] * 48
        is_holiday = self.store.is_holiday("IE")
        # 08:00 to 23:00 is 30 half hours of 0.5 kWh. On the holiday it is the Weekend band.
        self.assertEqual(import_by_band([holiday], definition, is_holiday),
                         {"Night": Decimal("9.0"), "Weekend": Decimal("15.0")})
        self.assertEqual(import_by_band([working], definition, is_holiday),
                         {"Night": Decimal("9.0"), "Day": Decimal("15.0")})
        # Without the store's holidays the same Monday is priced as a working day.
        self.assertEqual(import_by_band([holiday], definition),
                         {"Night": Decimal("9.0"), "Day": Decimal("15.0")})
        # 15 kWh at the 0.20 weekend rate in place of the 0.30 day rate: 1.50 less on the day.
        bill = {band: str(kwh) for band, kwh in import_by_band([holiday], definition, is_holiday).items()}
        self.assertEqual(priced(self.store.definition("IE", "p", "weekender", DAY, area="urban"), 1, bill),
                         Decimal("9.0") * Decimal("0.15") + Decimal("15.0") * Decimal("0.2") + 1)


@unittest.skipUnless(LIB_OK, "needs Python 3.14 for lib/tariff")
class RealStore(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store(folder_reader(TARIFFS))

    def test_flexible_octopus_in_london_for_a_month(self) -> None:
        day = date(2026, 11, 10)
        number, doc = self.store.tariff("GB", "octopus-energy", "octopus-var-22-11-01", day)
        row = doc["areas"]["c"]
        definition = self.store.definition("GB", "octopus-energy", "octopus-var-22-11-01", day, area="c")
        expected = ((Decimal(250) * Decimal(row["rates"]["Single rate"])).quantize(Decimal("0.01"), "ROUND_HALF_UP")
                    + (Decimal(30) * Decimal(row["standing"])).quantize(Decimal("0.01"), "ROUND_HALF_UP"))
        self.assertEqual(priced(definition, 30, {"Single rate": "250"}), expected)
        self.assertEqual((definition["currency"], definition["name"]), ("GBP", "Flexible Octopus (London (C))"))

    def test_an_australian_plan_adds_gst_on_top(self) -> None:
        provider = sorted(self.store.providers("AU"))[0]
        tariff_id = sorted(self.store.tariffs("AU", provider))[0]
        index = self.store.country("AU")["providers"][provider]["tariffs"][tariff_id]
        day = date.fromisoformat(index["revisions"][max(index["revisions"], key=int)]["effective_from"])
        definition = self.store.definition("AU", provider, tariff_id, day)
        standing = Decimal(definition["bill"]["total"]["of"]["of"]["standing"]["amount"])
        net = (standing * 10).quantize(Decimal("0.01"), "ROUND_HALF_UP")
        gst = (net * Decimal("0.10")).quantize(Decimal("0.01"), "ROUND_HALF_UP")
        self.assertEqual(priced(definition, 10, {}), net + gst)


if __name__ == "__main__":
    unittest.main()
