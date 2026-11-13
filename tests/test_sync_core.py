"""The sync core: a plan becomes a file one way, and apply writes revisions by fixed rules."""
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path

from lib.tariffstore.schema import validate_tariff
from scripts.sync import apply as apply_module
from scripts.sync.apply import apply, same_pricing, stored_for
from scripts.sync.http import Blocked, Fetcher, file_name
from scripts.sync.plan import Area, Plan, price, single, to_tariff, unique
from tests.fixtures import write_store

SOURCE = "example-source"


def plan(rate="0.25", start="2026-01-01", **changes) -> Plan:
    fields = dict(country="IE", provider_id="p", provider="P Energy", id="flat", name="Flat",
                  effective_from=start, source_url="https://example.test/prices",
                  bands=[{"name": "All day"}],
                  areas={"all": Area(rates={"All day": rate}, standing="0.5")})
    fields.update(changes)
    return Plan(**fields)


class PlanToTariff(unittest.TestCase):
    def test_prices_are_plain_decimals_of_at_most_six_places(self) -> None:
        self.assertEqual(price("0.308800"), "0.3088")
        self.assertEqual(price(Decimal("166.72") / 365), "0.456767")
        self.assertEqual(price(0), "0")
        self.assertEqual(price(Decimal("100")), "100")
        self.assertEqual(price("0.0000005"), "0.000001")
        self.assertEqual(price(Decimal("1E+2")), "100")

    def test_a_plan_becomes_a_valid_file(self) -> None:
        doc = to_tariff(plan(prices_include_tax=False, timezone="Australia/Brisbane",
                             effective_to="2027-01-01"), SOURCE)
        self.assertEqual(validate_tariff(doc), [])
        self.assertEqual(doc["source"], {"id": SOURCE, "url": "https://example.test/prices"})
        self.assertEqual(doc["areas"], {"all": {"rates": {"All day": "0.25"}, "standing": "0.5"}})
        self.assertEqual((doc["prices_include_tax"], doc["timezone"], doc["effective_to"]),
                         (False, "Australia/Brisbane", "2027-01-01"))
        for key in ("currency", "country", "id"):
            self.assertNotIn(key, doc)

    def test_areas_carry_labels_and_regions_and_an_export_has_no_standing(self) -> None:
        doc = to_tariff(plan(direction="export", areas={
            "a": Area(rates={"All day": 1}, label="East", region="GSP-A")}), SOURCE)
        self.assertEqual(doc["areas"]["a"], {"rates": {"All day": "1"}, "label": "East", "region": "GSP-A"})
        self.assertEqual(doc["direction"], "export")

    def test_a_refusal_is_raised_not_written(self) -> None:
        with self.assertRaisesRegex(ValueError, r"flat: .*bands\[1\]"):
            to_tariff(plan(bands=[{"name": "All day"}, {"name": "Night", "hours": "25:00-07:00"}]), SOURCE)

    def test_alike_band_names_are_numbered(self) -> None:
        self.assertEqual(unique(["A", "B", "A", "A"]), ["A", "B", "A 2", "A 3"])
        bands, areas = single(("Peak", "0.45"), [("Off-Peak", "00:00-07:00", "0.25"),
                                                  ("Off-Peak", "22:00-00:00", "0.25")], 1.1)
        self.assertEqual([b["name"] for b in bands], ["Peak", "Off-Peak", "Off-Peak 2"])
        self.assertEqual(areas["all"].rates, {"Peak": "0.45", "Off-Peak": "0.25", "Off-Peak 2": "0.25"})


class Apply(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tariffs = write_store(Path(tmp.name), {})
        self.folder = self.tariffs / "ie/p/flat"

    def apply(self, plans, today="2026-11-11"):
        return apply(plans, SOURCE, today, self.tariffs)

    def stored(self) -> dict[int, dict]:
        return apply_module.stored_revisions(self.folder)

    def test_a_new_tariff_is_revision_one(self) -> None:
        outcome = self.apply([plan()])
        self.assertEqual((outcome.added, outcome.changed), (["ie/p/flat"], True))
        self.assertEqual(sorted(self.stored()), [1])

    def test_the_same_prices_write_nothing_even_with_a_new_date_or_link(self) -> None:
        self.apply([plan()])
        before = (self.folder / "1.json").read_bytes()
        outcome = self.apply([plan(start="2026-09-01", name="Flat v2",
                                   source_url="https://example.test/moved")])
        self.assertEqual((outcome.unchanged, outcome.changed), (["ie/p/flat"], False))
        self.assertEqual(before, (self.folder / "1.json").read_bytes())

    def test_a_changed_price_is_a_new_revision_and_the_old_file_is_untouched(self) -> None:
        self.apply([plan()])
        before = (self.folder / "1.json").read_bytes()
        outcome = self.apply([plan("0.3", "2026-06-01")])
        self.assertEqual(outcome.revised, ["ie/p/flat revision 2 from 2026-06-01"])
        self.assertEqual(before, (self.folder / "1.json").read_bytes())
        self.assertEqual(self.stored()[2]["areas"]["all"]["rates"], {"All day": "0.3"})

    def test_a_source_without_dates_is_dated_by_the_run(self) -> None:
        self.apply([plan(dated=False)])
        self.apply([plan("0.3", dated=False)], today="2026-11-11")
        self.assertEqual(self.stored()[2]["effective_from"], "2026-11-11")
        outcome = self.apply([plan("0.31", "2026-12-01", dated=False)], today="2026-12-05")
        self.assertEqual(self.stored()[3]["effective_from"], "2026-12-01")  # a later source date is kept
        self.assertEqual(len(outcome.revised), 1)

    def test_a_new_pairing_is_dated_by_the_run_even_from_a_dated_source(self) -> None:
        self.apply([plan(start="2026-10-01")])
        outcome = self.apply([plan(start="2026-10-01", extra={"export": "p/out"})],
                             today="2026-11-13")
        self.assertEqual(outcome.revised, ["ie/p/flat revision 2 from 2026-11-13"])
        self.assertEqual(self.stored()[2]["export"], "p/out")
        again = self.apply([plan(start="2026-10-01", extra={"export": "p/out"})],
                           today="2026-11-14")
        self.assertEqual(again.unchanged, ["ie/p/flat"])
        # a price change at the same stated start is still refused
        refused = self.apply([plan("0.3", "2026-10-01", extra={"export": "p/out"})],
                             today="2026-11-15")
        self.assertEqual(len(refused.refused), 1)

    def test_a_dated_source_that_goes_backwards_is_refused(self) -> None:
        self.apply([plan(start="2026-06-01")])
        outcome = self.apply([plan("0.3", "2026-03-01")])
        self.assertEqual(sorted(self.stored()), [1])
        self.assertIn("check by hand", outcome.refused[0])
        self.assertFalse(outcome.changed)
        again = self.apply([plan("0.3", "2026-06-01", dated=False)], today="2026-06-01")
        self.assertEqual(len(again.refused), 1)  # the run date is not after revision 1 either

    def test_an_ended_revision_is_followed_even_at_the_same_price(self) -> None:
        self.apply([plan(effective_to="2026-04-01")])
        self.assertEqual(self.apply([plan(effective_to="2026-04-01")]).unchanged, ["ie/p/flat"])
        outcome = self.apply([plan(start="2026-04-01", effective_to="2026-07-01")])
        self.assertEqual(len(outcome.revised), 1)
        early = self.apply([plan("0.4", "2026-06-01", effective_to="2026-10-01")])
        self.assertIn("is not after it", early.refused[0])

    def test_a_first_sight_history_becomes_numbered_revisions(self) -> None:
        history = [plan("0.12", "2026-03-01"), plan("0.15", "2025-01-01", effective_to="2026-03-01")]
        self.assertEqual(self.apply(history).added, ["ie/p/flat"])
        stored = self.stored()
        self.assertEqual([stored[n]["effective_from"] for n in (1, 2)], ["2025-01-01", "2026-03-01"])
        self.assertEqual(self.apply(history).unchanged, ["ie/p/flat"])  # only the newest is compared

    def test_a_plan_the_format_refuses_is_reported_and_the_rest_carry_on(self) -> None:
        bad = plan(id="bad", bands=[{"name": "All day", "hours": "01:00-02:00"}])
        outcome = self.apply([bad, plan()])
        self.assertEqual(outcome.added, ["ie/p/flat"])
        self.assertIn("bad:", outcome.refused[0])
        self.assertFalse((self.tariffs / "ie/p/bad").exists())

    def test_a_stored_tariff_the_source_dropped_is_reported_not_closed(self) -> None:
        self.apply([plan(), plan(id="other"), plan(id="ended", effective_to="2026-06-01")])
        outcome = self.apply([plan()])
        self.assertEqual(outcome.missing, ["ie/p/other"])
        self.assertEqual(sorted(apply_module.stored_revisions(self.tariffs / "ie/p/other")), [1])

    def test_only_this_source_s_tariffs_count_as_stored(self) -> None:
        self.apply([plan()])
        apply([plan(id="theirs")], "another-source", "2026-11-11", self.tariffs)
        self.assertEqual(sorted(stored_for(SOURCE, "IE", self.tariffs)), [("ie", "p", "flat")])
        self.assertEqual(self.apply([plan()]).missing, [])

    def test_what_counts_as_the_same_pricing(self) -> None:
        a = to_tariff(plan(), SOURCE)
        self.assertTrue(same_pricing(a, {**a, "effective_from": "2030-01-01", "name": "x",
                                         "provider": "y", "source": {}, "effective_to": "2031-01-01"}))
        self.assertFalse(same_pricing(a, {**a, "prices_include_tax": False}))
        self.assertFalse(same_pricing(a, to_tariff(plan("0.250001"), SOURCE)))


class Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self) -> bytes:
        return self.body


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x.test", code, "nope", {}, None)


class Fetching(unittest.TestCase):
    def fetcher(self, answers: dict, **kw) -> Fetcher:
        self.calls, self.sleeps = [], []

        def opener(request, timeout):
            self.calls.append((request.full_url, dict(request.header_items())))
            answer = answers[request.full_url]
            answer = answer.pop(0) if isinstance(answer, list) else answer
            if isinstance(answer, Exception):
                raise answer
            return Response(answer)
        return Fetcher(opener=opener, sleep=self.sleeps.append, **kw)

    def test_it_fetches_with_our_user_agent_and_a_pause(self) -> None:
        fetch = self.fetcher({"https://x.test/a": b"A", "https://x.test/b": b"B"})
        self.assertEqual(fetch.get("https://x.test/a", {"x-v": "1"}), b"A")
        self.assertEqual(fetch.get("https://x.test/b"), b"B")
        self.assertEqual([c[0] for c in self.calls], ["https://x.test/a", "https://x.test/b"])
        self.assertIn("tariff-prices-sync", self.calls[0][1]["User-agent"])
        self.assertEqual(self.calls[0][1]["X-v"], "1")
        self.assertEqual(self.sleeps, [2, 2])
        self.assertEqual(fetch.requests, 2)

    def test_a_busy_server_is_tried_three_times_with_longer_waits(self) -> None:
        fetch = self.fetcher({"https://x.test/a": [http_error(503), TimeoutError("slow"), b"A"]})
        self.assertEqual(fetch.get("https://x.test/a"), b"A")
        self.assertEqual(self.sleeps, [2, 5, 2, 20, 2])
        fetch = self.fetcher({"https://x.test/a": [urllib.error.URLError("down")] * 3})
        with self.assertRaisesRegex(Blocked, "down"):
            fetch.get("https://x.test/a")

    def test_a_refusal_is_not_retried(self) -> None:
        fetch = self.fetcher({"https://x.test/a": http_error(403)})
        with self.assertRaisesRegex(Blocked, "HTTP 403"):
            fetch.get("https://x.test/a")
        self.assertEqual(len(self.calls), 1)

    def test_record_then_replay_needs_no_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "saved"
            fetch = self.fetcher({    "https://x.test/a?page=1": b"A"}, record=saved)
            fetch.get("https://x.test/a?page=1")
            self.assertEqual([p.name for p in saved.iterdir()], [file_name("https://x.test/a?page=1")])
            replay = self.fetcher({}, replay=saved)
            self.assertEqual(replay.get("https://x.test/a?page=1"), b"A")
            with self.assertRaisesRegex(Blocked, "not in the saved responses"):
                replay.get("https://x.test/other")
            self.assertEqual(self.calls, [])

    def test_file_names_are_readable_and_distinct(self) -> None:
        a, b = file_name("https://x.test/a?page=1"), file_name("https://x.test/a?page=2")
        self.assertTrue(a.startswith("x.test_a_page_1."))
        self.assertNotEqual(a, b)
        self.assertNotEqual(file_name("https://x.test/" + "y" * 200), file_name("https://x.test/" + "y" * 201))


if __name__ == "__main__":
    unittest.main()
