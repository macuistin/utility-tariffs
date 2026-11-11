"""Every file in tariffs/ is valid, indexed as built, and reachable through the client.

These run on every pull request, so a tariff that does not validate, compile or match its index
cannot be merged.
"""
from __future__ import annotations

import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from lib.tariffstore import Store, folder_reader
from lib.tariffstore import index as idx
from lib.tariffstore.schema import validate_country, validate_tariff
from scripts import build
from scripts.paths import ROOT, TARIFFS
from scripts.sync import sources
from scripts.sync.plan import price

FAR = date(9999, 1, 1)


def files() -> list[tuple[Path, dict]]:
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(TARIFFS.glob("*/*/*/*.json"))]


class Stored(unittest.TestCase):
    def test_the_whole_store_checks_clean(self) -> None:
        out, problems = build.render()
        self.assertEqual(problems, [])
        stale = [str(p.relative_to(TARIFFS)) for p, text in out.items()
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        self.assertEqual(stale, [], "run python3 -m scripts.build")

    def test_every_tariff_file_is_valid_on_its_own(self) -> None:
        self.assertGreater(len(files()), 100)
        for path, doc in files():
            with self.subTest(path.relative_to(TARIFFS).as_posix()):
                self.assertEqual(validate_tariff(doc), [])

    def test_every_country_block_is_valid_and_has_no_problems(self) -> None:
        for folder in sorted(p for p in TARIFFS.iterdir() if p.is_dir()):
            with self.subTest(folder.name):
                block, docs = build.read_country(folder)
                self.assertEqual(validate_country(block), [])
                self.assertEqual(idx.problems(folder.name.upper(), block, docs), [])

    def test_prices_are_in_the_one_stored_form_and_not_negative(self) -> None:
        for path, doc in files():
            for key, row in doc["areas"].items():
                for value in [*row["rates"].values(), *([row["standing"]] if "standing" in row else [])]:
                    with self.subTest(path.relative_to(TARIFFS).as_posix(), area=key):
                        self.assertEqual(value, price(value))
                        self.assertGreaterEqual(Decimal(value), 0)

    def test_every_source_has_its_note_and_a_reader_or_none(self) -> None:
        readers = {sources.load(name).SOURCE_ID for name in sources.NAMES}
        used = {doc["source"]["id"] for _, doc in files()}
        self.assertEqual(used - readers, set())
        for source_id in used:
            self.assertTrue((ROOT / "sources" / f"{source_id}.md").exists(), source_id)

    def test_the_layout_puts_values_first_and_the_collection_last(self) -> None:
        for path in sorted(TARIFFS.glob("*/index.json")):
            keys = list(json.loads(path.read_text()))
            self.assertEqual(keys[:4], ["schema", "country", "currency", "timezone"])
            self.assertEqual(keys[-1], "providers")
        for path, doc in files():
            self.assertEqual(list(doc)[:3], ["schema", "name", "provider"])
            self.assertEqual(list(doc)[-2:], ["bands", "areas"])


class ThroughTheClient(unittest.TestCase):
    """What a library does: list, choose, fetch, check, compile."""

    def setUp(self) -> None:
        self.store = Store(folder_reader(TARIFFS))

    def test_every_country_provider_and_tariff_can_be_found_and_fetched(self) -> None:
        held = {c: e for c, e in self.store.countries().items() if e["availability"] != "unavailable"}
        self.assertEqual(sorted(held), ["AU", "FR", "GB", "IE", "ZA"])
        fetched = 0
        for code, entry in held.items():
            providers = self.store.providers(code)
            self.assertEqual(len(providers), entry["providers"])
            for provider in providers:
                for direction in ("import", "export"):
                    for tariff, name in self.store.tariffs(code, provider, direction=direction).items():
                        index_entry = self.store.country(code)["providers"][provider]["tariffs"][tariff]
                        for number, revision in index_entry["revisions"].items():
                            day = date.fromisoformat(revision["effective_from"])
                            found, doc = self.store.tariff(code, provider, tariff, day)
                            self.assertEqual((found, doc.get("direction", "import")), (int(number), direction))
                            fetched += 1
                        self.assertEqual(name, doc["name"])
        self.assertEqual(fetched, len(files()))

    def test_every_area_of_every_import_tariff_compiles_on_its_first_day(self) -> None:
        compiled = 0
        for code, entry in self.store.countries().items():
            if entry["availability"] == "unavailable":
                continue
            for provider in self.store.providers(code):
                for tariff in self.store.tariffs(code, provider):
                    revisions = self.store.country(code)["providers"][provider]["tariffs"][tariff]["revisions"]
                    day = date.fromisoformat(revisions[max(revisions, key=int)]["effective_from"])
                    for area in self.store.areas(code, provider, tariff, day):
                        definition = self.store.definition(code, provider, tariff, day, area=area)
                        self.assertEqual(definition["country"], code)
                        self.assertEqual(definition["currency"], self.store.country(code)["currency"])
                        compiled += 1
        latest = {}
        for path, doc in files():
            if doc.get("direction") != "export":
                latest[path.parent] = len(doc["areas"])  # files are sorted, so the last revision wins
        self.assertEqual(compiled, sum(latest.values()))

    def test_an_unavailable_country_says_why(self) -> None:
        gone = {c: e for c, e in self.store.countries().items() if e["availability"] == "unavailable"}
        self.assertTrue(gone)
        for entry in gone.values():
            self.assertTrue(entry["reason"].strip())
            self.assertNotIn("path", entry)


if __name__ == "__main__":
    unittest.main()
