"""scripts.build: writes the indexes, checks them, and guards published revisions."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import build
from tests.fixtures import country, flat, tariff, write_store


def run(args: list[str], tariffs: Path) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = build.main(args, tariffs)
    return code, out.getvalue()


class Build(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.tariffs = write_store(self.root, {"p/flat/1.json": flat(), "p/plan/1.json": tariff()})

    def test_build_then_check_is_clean_and_a_second_build_changes_nothing(self) -> None:
        self.assertEqual(run(["--check"], self.tariffs)[0], 1)  # not built yet
        self.assertEqual(run([], self.tariffs), (0, ""))
        before = {p: p.read_bytes() for p in self.tariffs.rglob("*.json")}
        self.assertEqual(run(["--check"], self.tariffs), (0, ""))
        self.assertEqual(run([], self.tariffs), (0, ""))
        self.assertEqual(before, {p: p.read_bytes() for p in self.tariffs.rglob("*.json")})
        index = json.loads((self.tariffs / "ie/index.json").read_text())
        self.assertEqual(sorted(index["providers"]["p"]["tariffs"]), ["flat", "plan"])
        self.assertEqual(sorted(json.loads((self.tariffs / "index.json").read_text())["countries"]), ["IE", "XX"])

    def test_a_hand_edit_to_an_index_or_a_reformatted_file_fails_the_check(self) -> None:
        run([], self.tariffs)
        path = self.tariffs / "ie/p/flat/1.json"
        path.write_text(json.dumps(json.loads(path.read_text())))
        code, out = run(["--check"], self.tariffs)
        self.assertEqual(code, 1)
        self.assertIn("ie/p/flat/1.json: not as built", out)
        run([], self.tariffs)
        index = self.tariffs / "ie/index.json"
        index.write_text(index.read_text().replace('"Flat"', '"Renamed"'))
        self.assertIn("ie/index.json: not as built", run(["--check"], self.tariffs)[1])

    def test_an_invalid_file_stops_the_build_and_nothing_is_written(self) -> None:
        (self.tariffs / "ie/p/flat/1.json").write_text(json.dumps(flat(schema=2)))
        before = (self.tariffs / "ie/index.json").read_bytes()
        code, out = run([], self.tariffs)
        self.assertEqual(code, 1)
        self.assertIn("ie/p/flat/1.json: schema: must be 1", out)
        self.assertEqual(before, (self.tariffs / "ie/index.json").read_bytes())

    def test_a_country_folder_needs_its_block_and_the_unavailable_list(self) -> None:
        (self.tariffs / "fr").mkdir()
        self.assertIn("fr: no index.json", run([], self.tariffs)[1])
        (self.tariffs / "fr").rmdir()
        (self.tariffs / "unavailable.json").unlink()
        self.assertEqual(run([], self.tariffs)[0], 1)

    def test_a_changed_country_value_reaches_the_root_checksum(self) -> None:
        run([], self.tariffs)
        before = json.loads((self.tariffs / "index.json").read_text())["countries"]["IE"]["checksum"]
        (self.tariffs / "ie/index.json").write_text(json.dumps(
            {**json.loads((self.tariffs / "ie/index.json").read_text()), "vat_percent": "13.5"}))
        run([], self.tariffs)
        after = json.loads((self.tariffs / "index.json").read_text())["countries"]["IE"]["checksum"]
        self.assertNotEqual(before, after)


class PublishedRevisions(unittest.TestCase):
    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
                       cwd=self.root, check=True, capture_output=True)

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.tariffs = write_store(self.root, {"p/flat/1.json": flat()})
        run([], self.tariffs)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "first")
        self.file = self.tariffs / "ie/p/flat/1.json"

    def check(self) -> tuple[int, str]:
        run([], self.tariffs)
        return run(["--check", "--base", "HEAD"], self.tariffs)

    def test_a_new_revision_and_a_closing_date_are_allowed(self) -> None:
        self.assertEqual(self.check(), (0, ""))
        (self.tariffs / "ie/p/flat/2.json").write_text(json.dumps(flat("0.3", "2026-06-01")))
        self.assertEqual(self.check(), (0, ""))
        self.file.write_text(json.dumps(flat(effective_to="2026-06-01")))
        self.assertEqual(self.check(), (0, ""))

    def test_a_changed_price_in_a_published_revision_is_refused(self) -> None:
        self.file.write_text(json.dumps(flat("0.26")))
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("tariffs/ie/p/flat/1.json: a published revision was changed", out)

    def test_a_closing_date_cannot_be_moved_once_published(self) -> None:
        self.file.write_text(json.dumps(flat(effective_to="2026-06-01")))
        run([], self.tariffs)
        self.git("commit", "-qam", "closed")
        self.file.write_text(json.dumps(flat(effective_to="2026-07-01")))
        self.assertEqual(self.check()[0], 1)

    def test_a_deleted_revision_is_refused(self) -> None:
        self.file.unlink()
        self.assertIn("a published revision was deleted", self.check()[1])


if __name__ == "__main__":
    unittest.main()
