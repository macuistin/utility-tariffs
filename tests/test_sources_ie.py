"""Selectra Ireland source, on made-up pages in the layout the parser expects."""
from __future__ import annotations

import json
import unittest
from datetime import date

from scripts.sync.plan import to_tariff
from scripts.sync.sources import selectra_ie as sync

PAGE = """<html><head><style>.x{}</style><script>var a = 1;</script></head><body><h2>Electricity Rates</h2>
<div><h3>Plan One 24hr</h3><div>24-Hour 30.00c/kWh 31.00c/kWh</div>
<div>Standing €365.00/yr €730.00/yr</div><ul><li>- 12-month contract</li></ul></div>
<div><h3>Plan Two NightSaver</h3><div>Night 15.00c/kWh 15.00c/kWh</div><div>Day 32.00c/kWh 32.00c/kWh</div>
<div>Standing €400.00/yr €400.00/yr</div></div>
<div><h3>Plan Three Smart</h3><div>Night 10.00c/kWh 10.00c/kWh</div><div>Day 30.00c/kWh 30.00c/kWh</div>
<div>Peak 40.00c/kWh 40.00c/kWh</div><div>Standing €300.00/yr €300.00/yr</div></div>
<p>Unit rates excl. VAT, incl. discounts. Standing charges incl. 9% VAT. Last updated 9 November 2026.</p>
<h2>Gas Rates</h2><div>24-Hour 99.00c/kWh 99.00c/kWh</div></body></html>"""


def _card(name, badges, rows, standing):
    cells = "".join(
        f'<div>\n<span class="l">{label}</span>\n<span x-show="area === \'urban\'">{u}c/kWh</span>\n'
        f'<span x-show="area === \'rural\'">{r}c/kWh</span>\n</div>' for label, u, r in rows)
    return (f'<div class="offer-card"><div><span>{name}</span>\n'
            + "".join(f"<span>{b}</span>\n" for b in badges)
            + '<img alt="Score B"></div><div><div class="grid">' + cells
            + f'<div><span>Standing</span>\n<span>&euro;{standing[0]}/yr</span>\n'
            f'<span>&euro;{standing[1]}/yr</span></div></div></div>'
            '<div><button>Details</button><a>Call to Compare</a><a>Request a Callback</a></div>'
            '<div><ul><li><p>12-month contract</p></li></ul></div></div>')


SPAN_PAGE = ("<h3>Electricity Rates</h3>"
             + _card("Plan One", ["Standard", "Green"], [("24-Hour", "30.00", "31.00")],
                     ("365.00", "730.00"))
             + _card("Plan Two NightSaver", ["Standard"], [("Night", "15.00", "15.00"), ("Day", "32.00", "32.00")],
                     ("400.00", "400.00"))
             + '<p class="rate-legend">Unit rates excl. VAT, incl. discounts. Standing charges incl. '
               '9% VAT &amp; all charges. Last updated 9 November 2026.</p><h3>Gas Rates</h3>')
DIRECTORY = ('<a href="/energy/providers/example-energy">x</a><a href="/energy/providers/broken/">y</a>'
             '<a href="/energy/providers/example-energy">again</a><a href="/energy/guides/x">no</a><a>none</a>')


class Parse(unittest.TestCase):
    def test_parses_plans_and_skips_unmapped(self) -> None:
        parsed = sync.parse_provider(PAGE)
        self.assertEqual(parsed["updated"], date(2026, 11, 9))
        self.assertEqual([p["header"] for p in parsed["plans"]], ["Plan One 24hr", "Plan Two NightSaver"])
        self.assertEqual(parsed["skipped"][0][0], "Plan Three Smart")

    def test_one_span_per_line_markup(self) -> None:
        parsed = sync.parse_provider(SPAN_PAGE)
        self.assertEqual([p["header"] for p in parsed["plans"]],
                         ["Plan One Standard Green", "Plan Two NightSaver Standard"])
        self.assertEqual(parsed["plans"][0]["rates"], [("24-Hour", "30.00", "31.00")])
        self.assertEqual(parsed["plans"][0]["standing"], ("365.00", "730.00"))
        self.assertEqual(parsed["plans"][1]["rates"][0][0], "Night")

    def test_night_day_plan_without_stated_hours_is_skipped(self) -> None:
        parsed = sync.parse_provider(SPAN_PAGE.replace("Plan Two NightSaver", "Plan Two Boost"))
        self.assertEqual([p["header"] for p in parsed["plans"]], ["Plan One Standard Green"])
        self.assertEqual(parsed["skipped"], [("Plan Two Boost Standard", "night hours not stated on the page")])

    def test_an_unknown_rate_label_is_a_rate_row_not_a_plan_name(self) -> None:
        parsed = sync.parse_provider(SPAN_PAGE.replace("Night</span>", "Night Boost</span>", 1))
        self.assertIn("Plan Two NightSaver Standard", [h for h, _ in parsed["skipped"]])
        self.assertTrue(all("Night Boost" not in p["header"] for p in parsed["plans"]))

    def test_gas_section_ignored(self) -> None:
        self.assertNotIn("99.00", json.dumps(sync.parse_provider(PAGE)["plans"]))

    def test_a_page_that_changed_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "VAT notes"):
            sync.parse_provider(PAGE.replace("excl. VAT", ""))
        with self.assertRaisesRegex(ValueError, "no 'Electricity Rates'"):
            sync.parse_provider("<h2>Broadband</h2>")

    def test_the_directory_lists_each_supplier_once(self) -> None:
        self.assertEqual(sync.provider_slugs(DIRECTORY), ["broken", "example-energy"])


def _guide(rows: list[tuple[str, str]], header: str = "Supplier</th><th>Microgeneration Rate</th>"
           "<th>Payment") -> str:
    body = "".join(f"<tr><td>{name}</td><td>{rate}</td><td>Quarterly credit</td></tr>"
                   for name, rate in rows)
    return ("<h1>Best rates</h1><p>By A Writer | Updated 1 November 2026 | 14 min read</p>"
            f"<table><tr><th>Technology</th><th>Description</th></tr></table>"
            f"<table><tr><th>{header}</th></tr>{body}</table>")


GUIDE = _guide([("Example Energy", "€0.185 per kWh"), ("Bord Gáis Energy", "€0.185 per kWh"),
                ("PrepayPower", "€0.1589 per kWh"), ("Electric Ireland", "€0.195 per kWh"),
                ("Elsewhere Power", "€0.2 per kWh")])


class ExportGuide(unittest.TestCase):
    def test_the_table_gives_a_rate_in_euro_for_each_supplier_slug(self) -> None:
        updated, rates = sync.parse_export_guide(GUIDE)
        self.assertEqual(updated, "2026-11-01")
        self.assertEqual(rates, {"example-energy": sync.Decimal("0.185"),
                                 "bord-gais-energy": sync.Decimal("0.185"),
                                 "prepaypower": sync.Decimal("0.1589"),
                                 "electric-ireland": sync.Decimal("0.195"),
                                 "elsewhere-power": sync.Decimal("0.2")})

    def test_a_guide_that_changed_is_refused(self) -> None:
        for page, why in ((GUIDE.replace("Microgeneration Rate", "Rate"), "no table headed"),
                          (GUIDE.replace("€0.185 per kWh", "18.5c", 1), "no export rate"),
                          ("<p>Updated 1 November 2026</p>", "no table headed")):
            with self.subTest(why), self.assertRaisesRegex(ValueError, why):
                sync.parse_export_guide(page)

    def test_an_export_is_a_flat_export_tariff_dated_by_the_guide(self) -> None:
        plan = sync.export_plan("example-energy", sync.Decimal("0.185"), "2026-11-01")
        tariff = to_tariff(plan, sync.SOURCE_ID)
        self.assertEqual((tariff["direction"], tariff["effective_from"], tariff["name"]),
                         ("export", "2026-11-01", "Example Energy Microgen Export"))
        self.assertEqual(tariff["areas"], {"all": {"rates": {"Export": "0.185"}}})
        self.assertEqual(tariff["source"]["url"], sync.GUIDE)
        self.assertFalse(plan.dated)


class Plans(unittest.TestCase):
    def test_prices_include_vat_and_each_column_is_an_area(self) -> None:
        plans, skipped = sync.plans_for("example-energy", PAGE, "2026-11-11")
        self.assertEqual([p.id for p in plans], ["example-energy-plan-one-24hr",
                                                 "example-energy-plan-two-nightsaver"])
        tariff = to_tariff(plans[0], sync.SOURCE_ID)
        self.assertEqual(tariff["areas"]["urban"], {"rates": {"24-Hour": "0.327"}, "standing": "1",
                                                    "label": "Urban"})
        self.assertEqual(tariff["areas"]["rural"]["rates"], {"24-Hour": "0.3379"})
        self.assertEqual(tariff["areas"]["rural"]["standing"], "2")
        self.assertEqual((tariff["provider"], tariff["effective_from"]), ("Example Energy", "2026-11-09"))
        self.assertEqual(tariff["source"], {"id": "selectra-ie",
                                            "url": "https://selectra.ie/energy/providers/example-energy"})
        self.assertNotIn("bill", tariff)  # the standard bill comes from the country
        night = to_tariff(plans[1], sync.SOURCE_ID)
        self.assertEqual(night["bands"], [{"name": "Day"}, {"name": "Night", "hours": "23:00-08:00"}])
        self.assertEqual(night["areas"]["urban"]["rates"], {"Day": "0.3488", "Night": "0.1635"})
        self.assertFalse(plans[0].dated)
        self.assertEqual(len(skipped), 1)

    def test_a_page_without_a_date_is_dated_by_the_run(self) -> None:
        plans, _ = sync.plans_for("example", PAGE.replace("Last updated 9 November 2026.", ""), "2026-11-11")
        self.assertEqual(plans[0].effective_from, "2026-11-11")

    def test_a_night_rate_not_below_the_day_rate_drops_that_area(self) -> None:
        plans, skipped = sync.plans_for("example", SPAN_PAGE.replace(">15.00c/kWh<", ">40.00c/kWh<"), "2026-11-11")
        self.assertEqual([p.id for p in plans], ["example-plan-one-standard-green"])
        self.assertEqual(len([s for s in skipped if "likely a source error" in s]), 2)
        one_bad = SPAN_PAGE.replace("area === 'rural'\">15.00c/kWh", "area === 'rural'\">40.00c/kWh")
        plans, _ = sync.plans_for("example", one_bad, "2026-11-11")
        self.assertEqual(sorted(plans[1].areas), ["urban"])

    def test_read_walks_the_directory_and_carries_on_past_a_refused_page(self) -> None:
        answers = {"https://selectra.ie/energy/providers": DIRECTORY, sync.GUIDE: GUIDE,
                   "https://selectra.ie/energy/providers/example-energy": PAGE,
                   "https://selectra.ie/energy/providers/broken": "<h2>Broadband</h2>"}

        class Fetch:
            def get(self, url, headers=None):
                return answers[url].encode()
        result = sync.read(Fetch(), "2026-11-11", {})
        imports = [p for p in result.plans if p.direction == "import"]
        self.assertEqual(len(imports), 2)
        self.assertEqual({p.extra["export"] for p in imports},
                         {"example-energy/example-energy-microgen-export"})
        exports = [p for p in result.plans if p.direction == "export"]
        self.assertEqual([(p.id, p.areas["all"].rates["Export"]) for p in exports],
                         [("example-energy-microgen-export", sync.Decimal("0.185"))])
        self.assertTrue(any(s.startswith("broken: page refused") for s in result.skipped))
        self.assertIn("elsewhere-power: an export rate on the guide for a supplier not in the "
                      "directory", result.skipped)
        self.assertFalse(any("electric-ireland" in s for s in result.skipped))
        self.assertTrue(any("assumed" in n for n in result.notes))

    def test_a_supplier_whose_paid_figure_is_unclear_gets_no_export(self) -> None:
        directory = '<a href="/energy/providers/prepaypower">x</a>'
        answers = {"https://selectra.ie/energy/providers": directory, sync.GUIDE: GUIDE,
                   "https://selectra.ie/energy/providers/prepaypower": PAGE}

        class Fetch:
            def get(self, url, headers=None):
                return answers[url].encode()
        result = sync.read(Fetch(), "2026-11-11", {})
        self.assertEqual({p.direction for p in result.plans}, {"import"})
        self.assertTrue(all("export" not in p.extra for p in result.plans))
        self.assertIn("prepaypower: export rate not paired, the supplier states 14c and 15.89c "
                      "with VAT and not which it pays", result.skipped)


if __name__ == "__main__":
    unittest.main()
