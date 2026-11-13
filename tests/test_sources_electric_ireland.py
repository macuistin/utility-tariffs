"""Electric Ireland source, on made-up pages in the supplier's markup."""
from __future__ import annotations

import unittest
from decimal import Decimal

from lib.tariff import BillInputs, parse_definition, price_bill
from lib.tariffstore.compile import compile_area
from scripts.sync.plan import to_tariff
from scripts.sync.sources import electric_ireland as sync
from tests.fixtures import country

D = Decimal


def _card(plan_id: str, name: str, hours: dict[str, str]) -> str:
    rows = "".join(f"<tr>\n<td>{band}: {span}</td>\n<td>30.00c per kWh</td>\n</tr>"
                   for band, span in hours.items())
    return (f'<div class="plan-card"><h2>{name}</h2><table role="presentation" class="prices">'
            f"<tbody><tr><td>Electricity unit price</td><td>30.00c per kWh</td></tr>{rows}"
            "<tr><td>First year cost</td><td>€1,500</td></tr></tbody></table>"
            '<button class="btn-price-info" data-bs-toggle="modal" '
            f"onclick=\"showPricePlanCharges('{plan_id}')\" "
            f"aria-label='Full pricing information, {name}'>Full pricing information</button></div>")


def _table(rows: list[tuple[str, str]]) -> str:
    return "<table><tbody>" + "".join(
        f"<tr>\n<td>{label} <sup>1</sup></td>\n<td>{value}</td>\n<td></td>\n</tr>"
        for label, value in rows) + "</tbody></table>"


def _pricing(rates: list[tuple[str, str]], *, discount: str = "5.5",
             valid: str = "1st October 2026", levy: str = "€6.12") -> str:
    """A full pricing page. `rates` is the rows excluding VAT, before the discount."""
    effective = [(f"Effective {label[9:]} with {discount}% direct debit and online billing "
                  "discount", "1.00 c/kWh") for label, _ in rates] if discount else []
    without = _table(rates + effective + [
        ("Electricity standing charges per year", ""),
        ("Standing charge 24 hour urban per year", "€365.00"),
        ("Standing charge 24 hour rural per year", "€1,095.00"),
        ("Standing charge night storage heating per year", "€11.61"),
        ("Public Service Obligation levy per year", levy),
        ("Urban smart meter", "€1,463")])
    with_vat = _table([("Standard Day unit price", "99.00 c/kWh")])
    return (f'<h3>Plan</h3><div id="includeVAT_Contant">{with_vat}</div>'
            f'<div id="excludeVAT_Contant" style="display:none">{without}</div>'
            f"<div>Prices valid as of {valid}, prices are subject to change.</div>")


MICROGEN = ("<h1>Microgeneration</h1><p>Electric Ireland is supporting customers with a current "
            "Microgen export rate of 19.5c per kWh.</p><p>This rate is variable.</p>")
BOOST = [("Standard Day unit price", "36.50 c/kWh"),
         ("Standard Night unit / Night storage heating unit price", "18.00 c/kWh"),
         ("Standard Night Boost unit price", "10.56 c/kWh")]
FLAT = [("Standard unit price", "30.00 c/kWh"),
        ("Standard unit price for Night Storage Heating", "15.00 c/kWh")]
BOOST_HOURS = {"Day": "08.00 - 23.00", "Night": "23.00 - 08.00", "Night Boost": "02.00 - 04.00"}
PAGE = (_card("FLAT1", "Flat Plan", {}) + _card("BOOST1", "Home Plan+ Night Boost", BOOST_HOURS)
        + _card("FREE1", "Free Day Plan", {}) + _card("BOOST2", "Home Plan Night Boost", BOOST_HOURS)
        + _card("GONE1", "Changed Plan", {}))


class Parse(unittest.TestCase):
    def test_the_plans_page_gives_each_plan_once_and_its_band_hours(self) -> None:
        self.assertEqual(sync.plan_ids(PAGE + _card("FLAT1", "Flat Plan", {})), [
            ("FLAT1", "Flat Plan"), ("BOOST1", "Home Plan+ Night Boost"), ("FREE1", "Free Day Plan"),
            ("BOOST2", "Home Plan Night Boost"), ("GONE1", "Changed Plan")])
        self.assertEqual(sync.card_hours(PAGE, "BOOST1"), {
            "Day": "08:00-23:00", "Night": "23:00-08:00", "Night Boost": "02:00-04:00"})
        self.assertEqual(sync.card_hours(PAGE, "FLAT1"), {})

    def test_full_pricing_is_read_without_vat_and_before_the_discount(self) -> None:
        charges = sync.parse_charges(_pricing(BOOST))
        self.assertEqual(charges.rates, {"Day": D("0.365"), "Night": D("0.18"),
                                         "Night Boost": D("0.1056")})
        self.assertEqual((charges.discount, charges.levy), (D("5.5"), D("6.12")))
        self.assertEqual(charges.standing, {"urban": D("365.00"), "rural": D("1095.00")})
        self.assertEqual(charges.valid_from, "2026-10-01")

    def test_the_date_is_read_in_either_spelling(self) -> None:
        charges = sync.parse_charges(_pricing(FLAT, valid="14th of October 2026"))
        self.assertEqual(charges.valid_from, "2026-10-14")

    def test_storage_heating_is_a_second_meter_and_not_the_plan_price(self) -> None:
        self.assertEqual(sync.parse_charges(_pricing(FLAT)).rates, {"24 Hour": D("0.3")})

    def test_a_plan_with_no_discount_has_none(self) -> None:
        self.assertEqual(sync.parse_charges(_pricing(FLAT, discount="")).discount, 0)

    def test_a_page_that_changed_is_refused(self) -> None:
        for page, why in (
                (_pricing(BOOST).replace("excludeVAT_Contant", "other"), "excluding VAT"),
                (_pricing(BOOST).replace("Prices valid as of", "Prices from"), "valid as of"),
                (_pricing(BOOST).replace("rural per year", "country per year"), "missing"),
                (_pricing(BOOST).replace("Public Service", "Public"), "missing"),
                (_pricing(BOOST, levy="6.12 euro"), "no figure"),
                (_pricing(BOOST).replace("36.50 c/kWh", "36.50"), "no figure"),
                (_pricing([]), "missing")):
            with self.subTest(why), self.assertRaisesRegex(ValueError, why):
                sync.parse_charges(page)
        two = _pricing(BOOST).replace("Night unit / Night storage heating unit price with 5.5%",
                                      "Night unit price with 6.0%")
        with self.assertRaisesRegex(ValueError, "missing"):
            sync.parse_charges(two)


class Plans(unittest.TestCase):
    def plan(self, rates=BOOST, hours=None, **kw) -> sync.Plan:
        hours = sync.card_hours(PAGE, "BOOST1") if hours is None else hours
        return sync.plan_for("BOOST1", "Home Plan+ Night Boost", hours,
                             sync.parse_charges(_pricing(rates, **kw)))

    def test_a_plan_is_stored_as_the_supplier_bills_it(self) -> None:
        plan = self.plan()
        tariff = to_tariff(plan, sync.SOURCE_ID)
        self.assertEqual(plan.id, "electric-ireland-home-plan-night-boost")
        self.assertTrue(plan.dated)
        self.assertEqual((tariff["effective_from"], tariff["prices_include_tax"]),
                         ("2026-10-01", False))
        self.assertEqual(tariff["source"]["url"], "https://www.electricireland.ie/switch/"
                         "new-customer/priceplan-charges?pricePlanId=BOOST1")
        self.assertEqual(tariff["bands"], [
            {"name": "Day"}, {"name": "Night", "hours": "23:00-08:00"},
            {"name": "Night Boost", "hours": "02:00-04:00"}])
        self.assertEqual(tariff["areas"]["urban"], {
            "rates": {"Day": "0.365", "Night": "0.18", "Night Boost": "0.1056"},
            "standing": "1", "label": "Urban"})
        self.assertEqual(tariff["areas"]["rural"]["standing"], "3")
        charges = tariff["bill"]["total"]["of"]["charges"]
        self.assertEqual((charges["kind"], charges["mode"]), ("tax", "added"))
        self.assertEqual(charges["of"]["of"]["energy"]["percent"], "-5.5")
        self.assertEqual(charges["of"]["of"]["levy"], {
            "kind": "per_period", "amount": "0.51", "share": "days_in_period", "per": "month"})

    def test_the_bill_is_the_suppliers_arithmetic(self) -> None:
        # SOURCE: the rates, discount and levy in BOOST. ASSUMPTION: 30 days and these kWh.
        # Energy 67 x 0.365 = 24.46 (24.455 rounds up), 619 x 0.18 = 111.42, 257 x 0.1056 = 27.14,
        # together 163.02. Discount 5.5% = 8.97, leaving 154.05. Standing 30 x 1 = 30. Levy 0.51.
        # 184.56 plus 9% VAT of 16.61 = 201.17.
        doc = compile_area(to_tariff(self.plan(), sync.SOURCE_ID), "urban", block=country(),
                           meta={"country": "IE", "provider": "p", "tariff": "t", "revision": 1},
                           on="2026-10-15")
        kwh = {"Day": D(67), "Night": D(619), "Night Boost": D(257)}
        bill = price_bill(parse_definition(doc), BillInputs(30, 30, kwh, D(0)))
        lines = bill.root.children["charges"].children["of"].children
        self.assertEqual((lines["energy"].amount, lines["standing"].amount, lines["levy"].amount),
                         (D("154.05"), D("30.00"), D("0.51")))
        self.assertEqual(bill.total, D("201.17"))

    def test_a_plan_with_no_discount_has_a_plain_energy_line(self) -> None:
        plan = sync.plan_for("FLAT1", "Flat Plan", {}, sync.parse_charges(_pricing(FLAT, discount="")))
        energy = plan.extra["bill"]["total"]["of"]["charges"]["of"]["of"]["energy"]
        self.assertEqual(energy["kind"], "energy_by_band")
        self.assertEqual(plan.bands, [{"name": "24 Hour"}])

    def test_what_cannot_be_held_is_refused_with_the_reason(self) -> None:
        free = [*BOOST[:2], ("Standard Free Saturday or Sunday unit price", "0.00 c/kWh")]
        for rates, hours, why in (
                (free, None, "Free Saturday or Sunday not mapped"),
                (BOOST, {"Night": "23:00-08:00"}, "hours not stated for Night Boost"),
                (BOOST[1:], None, "no Day rate"),
                ([*FLAT, BOOST[0]], None, "flat rate beside banded")):
            with self.subTest(why), self.assertRaisesRegex(ValueError, why):
                self.plan(rates, hours)


class Export(unittest.TestCase):
    def test_the_export_rate_is_read_in_euro_and_stored_as_a_flat_export_tariff(self) -> None:
        rate = sync.export_rate(MICROGEN)
        self.assertEqual(rate, D("0.195"))
        plan = sync.export_plan(rate, "2026-11-13")
        tariff = to_tariff(plan, sync.SOURCE_ID)
        self.assertFalse(plan.dated)
        self.assertEqual((tariff["direction"], tariff["effective_from"], tariff["bands"]),
                         ("export", "2026-11-13", [{"name": "Export"}]))
        self.assertEqual(tariff["areas"], {"all": {"rates": {"Export": "0.195"}}})
        self.assertEqual(tariff["source"]["url"], sync.MICROGEN_URL)

    def test_the_credit_is_added_outside_the_vat(self) -> None:
        # SOURCE: 19.5c export, the BOOST rates and levy. ASSUMPTION: 30 days, the kWh below.
        # Imports as in the bill test give 184.56 and 16.61 VAT. 47 kWh x 0.195 = 9.165 = 9.17
        # credit, with no VAT on it: 201.17 - 9.17 = 192.00.
        plan = Plans().plan()
        export = to_tariff(sync.export_plan(D("0.195"), "2026-11-13"), sync.SOURCE_ID)
        doc = compile_area(to_tariff(plan, sync.SOURCE_ID), "urban", block=country(),
                           meta={"country": "IE", "provider": "p", "tariff": "t", "revision": 1},
                           on="2026-10-15", export_file=export)
        kwh = {"Day": D(67), "Night": D(619), "Night Boost": D(257)}
        bill = price_bill(parse_definition(doc), BillInputs(30, 30, kwh, D(47)))
        self.assertEqual(bill.total, D("192.00"))


class Read(unittest.TestCase):
    def fetch(self, page: str = PAGE):
        free = [*BOOST[:2], ("Standard Free Saturday or Sunday unit price", "0.00 c/kWh")]
        answers = {sync.PLANS_URL: page, sync.MICROGEN_URL: MICROGEN,
                   f"{sync.BASE}/priceplan-charges?pricePlanId=FLAT1": _pricing(FLAT),
                   f"{sync.BASE}/priceplan-charges?pricePlanId=BOOST1": _pricing(BOOST),
                   f"{sync.BASE}/priceplan-charges?pricePlanId=BOOST2": _pricing(BOOST),
                   f"{sync.BASE}/priceplan-charges?pricePlanId=FREE1": _pricing(free),
                   f"{sync.BASE}/priceplan-charges?pricePlanId=GONE1": "<p>Sorry</p>"}

        class Fetch:
            def get(self, url, headers=None):
                return answers[url].encode()
        return Fetch()

    def test_read_takes_each_plan_and_lists_what_it_skipped(self) -> None:
        result = sync.read(self.fetch(), "2026-11-13", {})
        self.assertEqual([p.id for p in result.plans], [
            "electric-ireland-microgen-export", "electric-ireland-flat-plan",
            "electric-ireland-home-plan-night-boost"])
        self.assertEqual(result.skipped, [
            "Free Day Plan: rate rows Free Saturday or Sunday not mapped",
            "Home Plan Night Boost: a second plan with the id "
            "electric-ireland-home-plan-night-boost",
            "Changed Plan: no prices excluding VAT"])
        self.assertEqual(len(result.notes), 3)
        self.assertEqual({p.extra["export"] for p in result.plans[1:]},
                         {"electric-ireland/electric-ireland-microgen-export"})

    def test_a_microgeneration_page_with_no_rate_stops_the_source(self) -> None:
        for page in ("<p>Microgeneration is here</p>", "<p>Microgen export rate of 19.5 per kWh</p>"):
            with self.subTest(page), self.assertRaisesRegex(ValueError, "no 'Microgen export"):
                sync.export_rate(page)

    def test_a_page_with_no_plans_stops_the_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "no price plans"):
            sync.read(self.fetch("<h1>Maintenance</h1>"), "2026-11-13", {})


if __name__ == "__main__":
    unittest.main()
