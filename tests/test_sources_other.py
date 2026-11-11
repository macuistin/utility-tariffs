"""Australia, France and South Africa sources, and the Australian discovery tool."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zlib
from decimal import Decimal
from pathlib import Path
from unittest import mock

from lib.tariffstore import index as idx
from scripts import build
from scripts.paths import TARIFFS
from scripts.sync.apply import apply, stored_for
from scripts.sync.http import Blocked
from scripts.sync.plan import to_tariff
from scripts.sync.sources import au_cdr, fr_cre, za_eskom
from scripts.tools import au_discover
from tests.fixtures import country, write_store

EVERY_DAY = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def contract(**period) -> dict:
    base = {"startDate": "01-01", "endDate": "12-31", "dailySupplyCharge": "1.0793",
            "rateBlockUType": "singleRate", "singleRate": {"rates": [{"unitPrice": "0.3088"}]}}
    base.update(period)
    return {"tariffPeriod": [base]}


def time_of_use(*windows) -> dict:
    return contract(rateBlockUType="timeOfUseRates", timeOfUseRates=[
        {"displayName": name, "type": "PEAK", "rates": [{"unitPrice": unit}],
         "timeOfUse": [{"days": days, "startTime": start, "endTime": end}]}
        for name, unit, start, end, days in windows])


def detail(electricity: dict | None = None, distributors=("Ausgrid",), **more) -> dict:
    return {"data": {"brandName": "Example Power", "displayName": "Saver",
                     "effectiveFrom": "2026-11-09T00:00:00Z", "geography": {"distributors": list(distributors)},
                     "electricityContract": electricity or contract(), **more}}


class Fetch:
    def __init__(self, answers: dict) -> None:
        self.answers, self.asked = answers, []

    def get(self, url, headers=None):
        self.asked.append((url, headers))
        answer = self.answers.get(url, Blocked(f"{url}: HTTP 404"))
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, bytes) else json.dumps(answer).encode()


class AustraliaExpress(unittest.TestCase):
    def test_a_single_rate_plan(self) -> None:
        self.assertEqual(au_cdr.express(contract()),
                         ({"standing_per_day": "1.0793", "zones": [], "base_price": "0.3088"}, None))

    def test_time_of_use_takes_the_longest_window_as_the_base(self) -> None:
        priced, why = au_cdr.express(time_of_use(
            ("Peak", "0.45", "15:00", "20:59", EVERY_DAY), ("Off-Peak", "0.25", "21:00", "14:59", EVERY_DAY)))
        self.assertIsNone(why)
        self.assertEqual((priced["base_name"], priced["base_price"]), ("Off-Peak", "0.25"))
        self.assertEqual(priced["zones"], [("Peak", "15:00-21:00", "0.45")])

    def test_a_rate_with_no_window_runs_all_day(self) -> None:
        plan = contract(rateBlockUType="timeOfUseRates", timeOfUseRates=[
            {"type": "PEAK", "rates": [{"unitPrice": "0.3"}]}])
        self.assertEqual(au_cdr.express(plan)[0]["base_name"], "PEAK")

    def test_what_the_format_cannot_hold_is_named(self) -> None:
        cases = {
            "seasonal or multiple tariff periods": {"tariffPeriod": contract()["tariffPeriod"] * 2},
            "seasonal or multiple tariff periods ": contract(startDate="01-01", endDate="06-30"),
            "seasonal or multiple tariff periods  ": contract(startDate=None),
            "banded or missing daily supply charge": contract(dailySupplyChargeType="BAND"),
            "demand charges": {**contract(), "demandCharges": [{}]},
            "volume tiers (step pricing)": contract(singleRate={"rates": [{}, {}]}),
            "rate block demandCharges": contract(rateBlockUType="demandCharges", singleRate=None)
            if False else contract(rateBlockUType="flexible"),
            "windows not every day (weekday/weekend split)": time_of_use(
                ("Peak", "0.4", "00:00", "00:00", ["MON"])),
            "time windows overlap or leave gaps": time_of_use(("Peak", "0.4", "07:00", "21:00", EVERY_DAY)),
            "volume tiers inside time of use": contract(rateBlockUType="timeOfUseRates", timeOfUseRates=[
                {"type": "PEAK", "rates": [{}, {}]}]),
            "SOLAR rate inside time of use": contract(rateBlockUType="timeOfUseRates", timeOfUseRates=[
                {"type": "SOLAR", "rates": [{"unitPrice": "0.1"}]}]),
        }
        for why, plan in cases.items():
            self.assertEqual(au_cdr.express(plan), (None, why.strip().replace("rate block demandCharges",
                                                                               "rate block flexible")))
        self.assertEqual(au_cdr.express(contract(rateBlockUType="demandCharges"))[1], "demand charges")

    def test_a_year_can_start_on_any_day(self) -> None:
        self.assertTrue(au_cdr.full_year("07-01", "06-30"))
        self.assertFalse(au_cdr.full_year("07-01", "12-31"))
        self.assertEqual(au_cdr.minutes("20:59", end=True), 21 * 60)
        self.assertEqual(au_cdr.minutes("23:59", end=True), 0)
        self.assertEqual(au_cdr.clock(905), "15:05")


class AustraliaPlans(unittest.TestCase):
    def test_a_plan_is_priced_without_tax_and_named_with_its_network(self) -> None:
        plan, why = au_cdr.plan_from_detail("example", "EX123@EME", detail()["data"])
        self.assertIsNone(why)
        tariff = to_tariff(plan, au_cdr.SOURCE_ID)
        self.assertEqual((plan.provider_id, plan.id), ("example", "example-ex123-eme"))
        self.assertEqual(tariff["name"], "Saver (Ausgrid)")
        self.assertFalse(tariff["prices_include_tax"])
        self.assertEqual(tariff["areas"]["all"], {"rates": {"Base": "0.3088"}, "standing": "1.0793"})
        self.assertEqual(tariff["source"]["url"],
                         "https://cdr.energymadeeasy.gov.au/example/cds-au/v1/energy/plans/EX123@EME")
        self.assertNotIn("timezone", tariff)

    def test_a_plan_in_another_time_zone_carries_it(self) -> None:
        plan, _ = au_cdr.plan_from_detail("example", "Q1", detail(distributors=["Energex"],
                                                                 effectiveTo="2027-06-30T00:00:00Z")["data"])
        self.assertEqual((plan.timezone, plan.effective_to), ("Australia/Brisbane", "2027-06-30"))
        melbourne, _ = au_cdr.plan_from_detail("example", "V1", detail(distributors=["Powercor"])["data"])
        self.assertIsNone(melbourne.timezone)  # same clock rules as the country block

    def test_an_unknown_or_mixed_network_is_refused(self) -> None:
        self.assertIn("unknown timezone", au_cdr.plan_from_detail("e", "x", detail(distributors=["Nobody"])["data"])[1])
        self.assertIn("unknown timezone",
                      au_cdr.plan_from_detail("e", "x", detail(distributors=["Ausgrid", "Energex"])["data"])[1])
        self.assertEqual(au_cdr.plan_from_detail("e", "x", detail(contract(startDate=None))["data"])[1],
                         "seasonal or multiple tariff periods")

    def test_the_country_block_has_the_time_zone_the_source_assumes(self) -> None:
        block = json.loads((TARIFFS / "au/index.json").read_text())
        self.assertEqual(block["timezone"], au_cdr.COUNTRY_ZONE)


class AustraliaRead(unittest.TestCase):
    def test_a_scheduled_run_refetches_only_what_is_stored(self) -> None:
        url = au_cdr.detail_url("example", "EX1")
        stored = {
            ("au", "example", "example-ex1"): {"source": {"url": url}},
            ("au", "example", "example-gone"): {"source": {"url": au_cdr.detail_url("example", "GONE")}},
            ("au", "example", "example-ended"): {"source": {"url": "x"}, "effective_to": "2026-01-01"},
            ("au", "example", "example-odd"): {"source": {"url": "https://elsewhere.test/plan"}},
            ("au", "example", "example-over"): {"source": {"url": au_cdr.detail_url("example", "OVER")}},
        }
        fetch = Fetch({url: detail(), au_cdr.detail_url("example", "OVER"):
                       detail(effectiveTo="2026-11-01T00:00:00Z")})
        result = au_cdr.read(fetch, "2026-11-11", stored)
        self.assertEqual([p.id for p in result.plans], ["example-ex1"])
        self.assertEqual(len(fetch.asked), 3)
        self.assertEqual(fetch.asked[0][1]["x-v"], "3")
        reasons = " | ".join(result.skipped)
        self.assertIn("example-gone: detail failed", reasons)
        self.assertIn("example-odd: not a plan detail link", reasons)
        self.assertIn("example-over: the retailer ended it on 2026-11-01", reasons)


def listing(*plans, pages=1) -> dict:
    return {"data": {"plans": list(plans)}, "meta": {"totalPages": pages}}


def listed(plan_id: str, distributor="Ausgrid", customer="RESIDENTIAL") -> dict:
    return {"planId": plan_id, "displayName": f"Plan {plan_id}", "customerType": customer,
            "geography": {"distributors": [distributor]}}


class AustraliaDiscover(unittest.TestCase):
    def list_url(self, page: int) -> str:
        return (f"{au_cdr.HOST}/example/cds-au/v1/energy/plans?fuelType=ELECTRICITY&type=MARKET"
                f"&effective=CURRENT&page={page}&page-size=1000")

    def test_the_pick_spans_networks_in_a_fixed_order(self) -> None:
        plans = [listed("B2"), listed("A1"), listed("C3", "Energex"), listed("D4")]
        self.assertEqual([p["planId"] for p in au_discover.pick(plans, 3)], ["A1", "C3", "B2"])
        self.assertEqual(au_discover.pick(list(reversed(plans)), 3), au_discover.pick(plans, 3))
        self.assertEqual(len(au_discover.pick(plans, 10)), 4)

    def test_new_plans_are_stored_and_known_ones_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tariffs = write_store(Path(tmp), {})
            (tariffs / "ie").rename(tariffs / "au")
            (tariffs / "au/index.json").write_text(json.dumps(
                {**country(code="AU"), "timezone": "Australia/Sydney"}))
            fetch = Fetch({
                self.list_url(1): listing(listed("A1"), listed("B2", customer="BUSINESS"), pages=2),
                self.list_url(2): listing(listed("C3"), listed("D4")),
                au_cdr.detail_url("example", "A1"): detail(),
                au_cdr.detail_url("example", "C3"): detail(contract(startDate=None)),
                au_cdr.detail_url("example", "D4"): detail(),
            })
            lines = au_discover.discover(fetch, ["example"], 5, "2026-11-11", tariffs)
            self.assertEqual(sorted(lines), ["added au/example/example-a1", "added au/example/example-d4",
                                             "skipped example: Plan C3: seasonal or multiple tariff periods"])
            self.assertEqual(sorted(stored_for(au_cdr.SOURCE_ID, "AU", tariffs)),
                             [("au", "example", "example-a1"), ("au", "example", "example-d4")])
            block, files = build.read_country(tariffs / "au")
            self.assertEqual(idx.problems("AU", block, files), [])
            self.assertEqual(au_discover.discover(fetch, ["example"], 5, "2026-11-11", tariffs),
                             ["skipped example: Plan C3: seasonal or multiple tariff periods"])

    def test_the_command_runs_discover_then_builds(self) -> None:
        out = io.StringIO()
        with mock.patch.object(au_discover, "discover", return_value=["added x"]) as discover, \
                mock.patch.object(au_discover.build, "main", return_value=0) as built, \
                contextlib.redirect_stdout(out):
            self.assertEqual(au_discover.main(["agl", "--per-brand", "2", "--date", "2026-11-11"]), 0)
        self.assertEqual(discover.call_args.args[1:], (["agl"], 2, "2026-11-11"))
        self.assertEqual(built.call_count, 2)
        self.assertEqual(out.getvalue(), "added x\n")


CSV = ("﻿DATE_DEBUT;DATE_FIN;P_SOUSCRITE;PART_FIXE_HT;PART_FIXE_TTC;PART_VARIABLE_HT;PART_VARIABLE_TTC\n"
       "01/02/2026;31/07/2026;6;150,00;180,00;0,1500;0,1952\n"
       "01/08/2026;;3;120,00;146,00;0,1600;0,2001\n"
       "01/08/2026;;6;160,00;190,81;0,1600;0,2001\n")


class France(unittest.TestCase):
    def test_current_rows_become_one_tariff_per_subscribed_power(self) -> None:
        plans = fr_cre.plans(CSV)
        self.assertEqual([p.id for p in plans], ["edf-tarif-bleu-base-3kva", "edf-tarif-bleu-base-6kva"])
        tariff = to_tariff(plans[1], fr_cre.SOURCE_ID)
        self.assertEqual(tariff["areas"]["all"], {"rates": {"Base": "0.2001"}, "standing": "0.522767"})
        self.assertEqual((tariff["effective_from"], tariff["name"]), ("2026-08-01", "Tarif Bleu, option Base, 6 kVA"))
        self.assertTrue(plans[0].dated)

    def test_a_file_that_changed_shape_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected columns"):
            fr_cre.plans("DATE;PRIX\n01/01/2026;1\n")
        with self.assertRaisesRegex(ValueError, "no current row"):
            fr_cre.plans("\n".join(CSV.splitlines()[:2]))

    def test_read_fetches_the_one_file(self) -> None:
        result = fr_cre.read(Fetch({fr_cre.URL: CSV.encode()}), "2026-11-11", {})
        self.assertEqual(len(result.plans), 2)
        self.assertEqual(len(result.skipped), 2)


def booklet(rows: dict[str, list[str]]) -> bytes:
    """A PDF-shaped file: text operators inside Flate streams, as the booklet has."""
    parts = [b"%PDF-1.7\n1 0 obj\nstream\nnot compressed\nendstream\n"]
    for label, values in rows.items():
        text = f"({label}) Tj " + " ".join(f"[({v[:2]}) 5 ({v[2:]})] TJ" for v in values)
        parts.append(b"2 0 obj\nstream\n" + zlib.compress(text.encode("latin1")) + b"\nendstream\n")
    return b"".join(parts)


def pairs(*excl: str) -> list[str]:
    out = []
    for value in excl:
        out += [value, f"{Decimal(value) * Decimal('1.15'):.2f}"]
    return out


BOOKLET = {"Homelight 20A": pairs("235.04"), "Homelight 60A": pairs("266.00"),
           **{f"Homepower {n}": pairs("230.00", "0.50", "20.00", "5.00", "3.00", "1.50") for n in range(1, 5)}}


class SouthAfrica(unittest.TestCase):
    def test_rows_are_read_by_label_from_the_pdf_text(self) -> None:
        plans = za_eskom.plans(za_eskom.pdf_text(booklet(BOOKLET)))
        self.assertEqual([p.id for p in plans], ["eskom-homelight-20a", "eskom-homelight-60a",
                                                 "eskom-homepower-1", "eskom-homepower-2",
                                                 "eskom-homepower-3", "eskom-homepower-4"])
        light = to_tariff(plans[0], za_eskom.SOURCE_ID)
        self.assertEqual(light["areas"]["all"], {"rates": {"Energy": "2.3504"}, "standing": "0"})
        self.assertFalse(light["prices_include_tax"])
        power = to_tariff(plans[2], za_eskom.SOURCE_ID)
        self.assertEqual(power["areas"]["all"], {"rates": {"Energy": "2.505"}, "standing": "9.5"})
        self.assertEqual(power["effective_from"], za_eskom.EFFECTIVE_FROM)

    def test_a_missing_row_or_disagreeing_vat_columns_stop_the_run(self) -> None:
        with self.assertRaisesRegex(ValueError, "row 'Homelight 60A' not found"):
            za_eskom.plans(za_eskom.pdf_text(booklet({"Homelight 20A": pairs("235.04")})))
        wrong = {**BOOKLET, "Homelight 20A": ["235.04", "999.00"]}
        with self.assertRaisesRegex(ValueError, "VAT columns disagree"):
            za_eskom.plans(za_eskom.pdf_text(booklet(wrong)))

    def test_read_fetches_the_booklet(self) -> None:
        result = za_eskom.read(Fetch({za_eskom.URL: booklet(BOOKLET)}), "2026-11-11", {})
        self.assertEqual(len(result.plans), 6)
        self.assertTrue(result.notes and result.skipped)


class Apply(unittest.TestCase):
    def test_every_source_s_plans_survive_apply_and_the_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tariffs = write_store(Path(tmp), {})
            (tariffs / "ie").rename(tariffs / "fr")
            (tariffs / "fr/index.json").write_text(json.dumps(country(code="FR")))
            outcome = apply(fr_cre.plans(CSV), fr_cre.SOURCE_ID, "2026-11-11", tariffs)
            self.assertEqual(len(outcome.added), 2)
            self.assertEqual(build.main([], tariffs), 0)
            self.assertEqual(build.main(["--check"], tariffs), 0)


if __name__ == "__main__":
    unittest.main()
