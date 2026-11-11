"""Great Britain sources (Octopus, Ofgem), on made-up responses."""
from __future__ import annotations

import io
import json
import unittest
import zipfile
from datetime import date
from decimal import Decimal

from scripts.sync.http import file_name
from scripts.sync.plan import to_tariff
from scripts.sync.sources import octopus_gb as octo
from scripts.sync.sources import ofgem_gb as ofgem

REGIONS = ("Eastern", "East Midlands", "London", "Midlands", "N Wales and Mersey", "North West",
           "Northern", "Northern Scotland", "South East", "South Wales", "Southern",
           "Southern Scotland", "Southern Western", "Yorkshire")


def xlsx(rows: dict[int, dict[str, str]], target: str = "worksheets/sheet1.xml") -> bytes:
    strings, cells = [], []
    for r, cols in rows.items():
        for col, text in cols.items():
            if text.replace(".", "").isdigit():
                cells.append(f'<c r="{col}{r}"><v>{text}</v></c>')
            else:
                strings.append(text)
                cells.append(f'<c r="{col}{r}" t="s"><v>{len(strings) - 1}</v></c>')
    cells.append('<c r="Z1"/>')  # an empty cell, as real sheets have
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'
                   '<sheet name="1a Levelised DTC" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Id="rId1" Target="{target}"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}">'
                   + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml",
                   f'<worksheet xmlns="{ns}"><sheetData><row>' + "".join(cells) + "</row></sheetData></worksheet>")
    return out.getvalue()


def cap_rows(groups=("Other Payment Method", "Standard Credit", "PPM"), regions=REGIONS) -> dict:
    rows = {6: {"C": "October 2026 - December 2026"}}
    line = 9
    for group in groups:
        rows[line] = {"B": group}
        rows[line + 1] = {"B": "Charge Restriction Region", "C": "Electricity: Single-Rate"}
        rows[line + 2] = {"C": "Nil kWh"}
        line += 3
        for region in regions:
            rows[line] = {"B": region, "C": "166.72", "D": "828.95"}
            line += 1
        rows[line] = {"B": "GB average", "C": "200.15", "D": "858.2"}
        rows[line + 1] = {"B": "GB average, inc VAT", "C": "200.15", "D": "858.2"}
        line += 4
    return rows


class Ofgem(unittest.TestCase):
    def test_period_end_is_excluded(self) -> None:
        self.assertEqual(ofgem.period("October 2026 - December 2026"), (date(2026, 10, 1), date(2027, 1, 1)))
        self.assertEqual(ofgem.period("April 2026 - June 2026"), (date(2026, 4, 1), date(2026, 7, 1)))
        with self.assertRaises(ValueError):
            ofgem.period("Winter 2026")

    def test_the_newest_workbook_is_the_first_annex_9_link(self) -> None:
        html = ('<a href="/sites/default/files/2026-08/Other-annex-2.xlsx">x</a>'
                '<a href="/sites/default/files/2026-08/Annex-9-Levelisation-v1.11.xlsx">new</a>'
                '<a href="https://www.ofgem.gov.uk/sites/default/files/2026-05/Annex-9-v1.10.xlsx">old</a>')
        self.assertEqual(ofgem.workbook_url(html),
                         "https://www.ofgem.gov.uk/sites/default/files/2026-08/Annex-9-Levelisation-v1.11.xlsx")
        self.assertEqual(ofgem.workbook_url(html[html.index("<a href=\"https"):]),
                         "https://www.ofgem.gov.uk/sites/default/files/2026-05/Annex-9-v1.10.xlsx")
        with self.assertRaisesRegex(ValueError, "layout has changed"):
            ofgem.workbook_url("<p>No links today</p>")

    def test_unit_rate_and_standing_charge_are_derived(self) -> None:
        cells = ofgem.read_sheet(xlsx(cap_rows()), ofgem.SHEET)
        plans, notes = ofgem.plans(cells, "https://example.test/cap.xlsx")
        self.assertEqual([p.id for p in plans], ["ofgem-cap-direct-debit-and-other",
                                                 "ofgem-cap-standard-credit", "ofgem-cap-prepayment"])
        tariff = to_tariff(plans[0], ofgem.SOURCE_ID)
        self.assertEqual(len(tariff["areas"]), 14)  # the average rows are not areas
        self.assertEqual(tariff["areas"]["north-west"], {
            "rates": {"Single rate": "0.264892"}, "standing": "0.456767", "label": "North West",
            "region": "OFGEM-NORTH-WEST"})
        self.assertEqual((tariff["effective_from"], tariff["effective_to"]), ("2026-10-01", "2027-01-01"))
        self.assertEqual(tariff["source"]["url"], "https://example.test/cap.xlsx")
        self.assertEqual(tariff["name"], "Price cap, direct debit and other, single rate")
        self.assertNotIn("bill", tariff)
        self.assertTrue(plans[0].dated)
        self.assertTrue(any("26.32 p/kWh" in n for n in notes))

    def test_a_workbook_with_a_region_or_group_missing_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 14 regions"):
            ofgem.plans(ofgem.read_sheet(xlsx(cap_rows(regions=REGIONS[:13])), ofgem.SHEET), "https://x.test")
        with self.assertRaisesRegex(ValueError, "expected 3 payment groups"):
            ofgem.plans(ofgem.read_sheet(xlsx(cap_rows(groups=("PPM",))), ofgem.SHEET), "https://x.test")

    def test_a_row_without_figures_is_passed_over(self) -> None:
        rows = cap_rows()
        rows[12]["C"] = "n/a"
        with self.assertRaisesRegex(ValueError, "expected 14 regions"):
            ofgem.plans(ofgem.read_sheet(xlsx(rows), ofgem.SHEET), "https://x.test")

    def test_read_follows_the_page_to_the_workbook(self) -> None:
        book = "https://www.ofgem.gov.uk/sites/default/files/2026-08/Annex-9-v1.11.xlsx"
        answers = {ofgem.PAGE: b'<a href="/sites/default/files/2026-08/Annex-9-v1.11.xlsx">cap</a>',
                   book: xlsx(cap_rows(), target="/xl/worksheets/sheet1.xml")}

        class Fetch:
            def get(self, url, headers=None):
                return answers[url]
        result = ofgem.read(Fetch(), "2026-11-11", {})
        self.assertEqual(len(result.plans), 3)
        self.assertEqual(result.plans[0].source_url, book)
        self.assertTrue(result.skipped)


def product(code="VAR-X", **changes) -> dict:
    doc = {"code": code, "full_name": "Flexible Test", "is_business": False, "is_prepay": False,
           "is_tracker": False, "is_restricted": False, "tariffs_active_at": "2026-11-09T05:54:02Z",
           "single_register_electricity_tariffs": {"_A": {"varying": {
               "standing_charge_inc_vat": 50.5464, "standard_unit_rate_inc_vat": 26.6132}}},
           "dual_register_electricity_tariffs": {"_A": {"varying": {}}}}
    doc.update(changes)
    return doc


def export_product(code="OUT-X", rate=None, **changes) -> dict:
    regions = {f"_{k}": {"direct_debit_monthly": {
        "standing_charge_inc_vat": 0.0,
        "standard_unit_rate_inc_vat": float(i) if rate is None else rate}}
        for i, k in enumerate("ABCDEFGHJKLMNP")}
    return product(code, full_name="Outgoing Test", single_register_electricity_tariffs=regions,
                   dual_register_electricity_tariffs={}, **changes)


def banded_rows() -> list[dict]:
    out = [{"value_inc_vat": 9.0, "valid_from": "2026-11-01T00:00:00Z", "valid_to": "2026-11-01T16:00:00Z"}]
    for day in range(1, 11):
        out.append({"value_inc_vat": 16.0, "valid_from": f"2026-11-{day:02d}T16:00:00Z",
                    "valid_to": f"2026-11-{day:02d}T19:00:00Z"})
        out.append({"value_inc_vat": 9.0, "valid_from": f"2026-11-{day:02d}T19:00:00Z",
                    "valid_to": f"2026-11-{day + 1:02d}T16:00:00Z"})
    return out


FLAT_ROWS = [{"value_inc_vat": 12.0, "valid_from": "2026-03-01T00:00:00Z", "valid_to": None},
             {"value_inc_vat": 15.0, "valid_from": "2025-01-01T00:00:00Z", "valid_to": "2026-03-01T00:00:00Z"},
             {"value_inc_vat": 15.0, "valid_from": "2024-10-26T00:00:00Z", "valid_to": "2025-01-01T00:00:00Z"}]


class OctopusImport(unittest.TestCase):
    def test_single_register_becomes_pounds_with_an_area_per_region(self) -> None:
        plan, skipped = octo.import_plan(product(), "2026-11-11")
        tariff = to_tariff(plan, octo.SOURCE_ID)
        self.assertEqual(tariff["areas"]["a"], {"rates": {"Single rate": "0.266132"}, "standing": "0.505464",
                                                "label": "Eastern England (A)", "region": "GSP-A"})
        self.assertEqual((plan.id, tariff["effective_from"]), ("octopus-var-x", "2026-11-09"))
        self.assertEqual(tariff["source"]["url"], "https://api.octopus.energy/v1/products/VAR-X/")
        self.assertNotIn("export", tariff)  # no export pairing is stated by the API
        self.assertFalse(plan.dated)
        self.assertTrue(any("dual register" in s for s in skipped))

    def test_the_run_date_stands_in_when_the_api_gives_none(self) -> None:
        plan, _ = octo.import_plan(product(tariffs_active_at=None), "2026-11-11")
        self.assertEqual(plan.effective_from, "2026-11-11")

    def test_restricted_or_empty_products_are_skipped(self) -> None:
        self.assertEqual(octo.import_plan(product(is_restricted=True), "2026-11-11"),
                         (None, ["VAR-X: business, prepay, tracker or restricted"]))
        plan, skipped = octo.import_plan(product(single_register_electricity_tariffs={}), "2026-11-11")
        self.assertIsNone(plan)
        self.assertIn("no single-register", skipped[-1])

    def test_pounds_never_uses_exponent_form(self) -> None:
        from scripts.sync.plan import price
        self.assertEqual(price(octo.pounds(10000)), "100")
        self.assertEqual(price(octo.pounds(0)), "0")


class OctopusExport(unittest.TestCase):
    def test_bands_ignore_the_odd_first_row(self) -> None:
        self.assertEqual(octo.bands_from_rows(banded_rows()),
                         [("16:00", "19:00", Decimal("0.16")), ("19:00", "16:00", Decimal("0.09"))])

    def test_summer_rows_give_the_same_local_bands(self) -> None:
        rows = []
        for day in range(1, 11):
            rows.append({"value_inc_vat": 16.0, "valid_from": f"2026-07-{day:02d}T15:00:00Z",
                         "valid_to": f"2026-07-{day:02d}T18:00:00Z"})
            rows.append({"value_inc_vat": 9.0, "valid_from": f"2026-07-{day:02d}T18:00:00Z",
                         "valid_to": f"2026-07-{day + 1:02d}T15:00:00Z"})
        self.assertEqual([b[:2] for b in octo.bands_from_rows(rows)], [("16:00", "19:00"), ("19:00", "16:00")])

    def test_flat_history_merges_equal_neighbours(self) -> None:
        self.assertEqual(octo.flat_history(FLAT_ROWS),
                         [(Decimal("0.15"), date(2024, 10, 26), date(2026, 3, 1)),
                          (Decimal("0.12"), date(2026, 3, 1), None)])

    def test_a_flat_export_gives_its_price_history(self) -> None:
        plans, skipped = octo.export_plans(export_product(rate=12.0), FLAT_ROWS)
        self.assertEqual(skipped, [])
        files = [to_tariff(p, octo.SOURCE_ID) for p in plans]
        self.assertEqual([(f["effective_from"], f.get("effective_to"), f["areas"]["all"]["rates"]["Flat"])
                          for f in files], [("2024-10-26", "2026-03-01", "0.15"), ("2026-03-01", None, "0.12")])
        self.assertEqual({f["direction"] for f in files}, {"export"})
        self.assertNotIn("standing", files[0]["areas"]["all"])

    def test_a_banded_export_has_an_off_peak_base_and_a_peak_band(self) -> None:
        (plan,), _ = octo.export_plans(export_product(rate=9.0), banded_rows())
        tariff = to_tariff(plan, octo.SOURCE_ID)
        self.assertEqual(tariff["bands"], [{"name": "Off-peak"}, {"name": "Peak", "hours": "16:00-19:00"}])
        self.assertEqual(tariff["areas"]["all"]["rates"], {"Off-peak": "0.09", "Peak": "0.16"})
        self.assertEqual(tariff["effective_from"], "2026-11-01")

    def test_exports_the_format_cannot_hold_are_skipped_with_the_reason(self) -> None:
        self.assertIn("differs by region", octo.export_plans(export_product(), [])[1][0])
        self.assertIn("restricted", octo.export_plans(export_product(is_restricted=True), [])[1][0])
        short = export_product(rate=9.0)
        short["single_register_electricity_tariffs"].pop("_A")
        self.assertIn("not a flat zero-standing-charge", octo.export_plans(short, [])[1][0])
        irregular = [{"value_inc_vat": float(i), "valid_from": f"2026-11-01T{i:02d}:00:00Z",
                      "valid_to": f"2026-11-01T{i + 1:02d}:00:00Z"} for i in range(23)]
        self.assertIn("no repeating daily pattern", octo.export_plans(export_product(rate=9.0), irregular)[1][0])


class OctopusRead(unittest.TestCase):
    def test_read_asks_for_every_product_and_pages_the_rate_feed(self) -> None:
        answers, asked = {}, []
        for code in octo.PRODUCTS:
            answers[f"{octo.API}/products/{code}/"] = product(code)
        for code in octo.EXPORT_PRODUCTS:
            answers[f"{octo.API}/products/{code}/"] = export_product(code, rate=12.0)
            feed = f"{octo.API}/products/{code}/electricity-tariffs/E-1R-{code}-A/standard-unit-rates/"
            answers[feed] = {"results": FLAT_ROWS[:1], "next": feed + "?page=2"}
            answers[feed + "?page=2"] = {"results": FLAT_ROWS[1:], "next": None}

        class Fetch:
            def get(self, url, headers=None):
                asked.append(file_name(url))
                return json.dumps(answers[url]).encode()
        result = octo.read(Fetch(), "2026-11-11", {})
        self.assertEqual(len(asked), len(octo.PRODUCTS) + 3 * len(octo.EXPORT_PRODUCTS))
        self.assertEqual(len([p for p in result.plans if p.direction == "import"]), len(octo.PRODUCTS))
        self.assertEqual(len([p for p in result.plans if p.direction == "export"]), 2 * len(octo.EXPORT_PRODUCTS))
        self.assertEqual(len(result.skipped), len(octo.PRODUCTS))  # each made-up product has a dual register


if __name__ == "__main__":
    unittest.main()
