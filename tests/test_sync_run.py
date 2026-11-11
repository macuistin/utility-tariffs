"""The runner: one command from a source's saved responses to checked files and a report."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import build
from scripts.sync import __main__ as runner
from scripts.sync import sources
from scripts.sync.http import Fetcher, file_name
from scripts.sync.sources import fr_cre
from tests.fixtures import country, write_store
from tests.test_sources_other import CSV


class Run(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.tariffs = write_store(self.root, {})
        (self.tariffs / "ie").rename(self.tariffs / "fr")
        (self.tariffs / "fr/index.json").write_text(json.dumps(country(code="FR")))
        build.main([], self.tariffs)
        self.saved = self.root / "saved"
        self.saved.mkdir()
        self.save(CSV)

    def save(self, text: str) -> None:
        (self.saved / file_name(fr_cre.URL)).write_text(text, encoding="utf-8")

    def run_source(self, today="2026-11-11") -> tuple[int, str]:
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.run("fr_cre", today, Fetcher(replay=self.saved), self.tariffs)

    def snapshot(self) -> dict:
        return {p.relative_to(self.tariffs).as_posix(): p.read_bytes() for p in self.tariffs.rglob("*.json")}

    def test_a_first_run_adds_the_tariffs_and_leaves_the_store_checked(self) -> None:
        code, text = self.run_source()
        self.assertEqual(code, 0)
        self.assertIn("2 new, 0 revised, 0 unchanged", text)
        self.assertIn("- fr/edf/edf-tarif-bleu-base-6kva", text)
        self.assertIn("### Skipped by the source reader", text)
        self.assertEqual(build.main(["--check"], self.tariffs), 0)
        index = json.loads((self.tariffs / "fr/index.json").read_text())
        self.assertEqual(sorted(index["providers"]["edf"]["tariffs"]),
                         ["edf-tarif-bleu-base-3kva", "edf-tarif-bleu-base-6kva"])

    def test_a_second_run_on_the_same_responses_changes_no_byte(self) -> None:
        self.run_source()
        before = self.snapshot()
        code, text = self.run_source(today="2027-01-01")
        self.assertEqual(code, 0)
        self.assertIn("0 new, 0 revised, 2 unchanged", text)
        self.assertEqual(before, self.snapshot())

    def test_a_price_change_is_one_new_revision_and_the_index_follows(self) -> None:
        self.run_source()
        self.save(CSV.replace("01/08/2026;;6;160,00;190,81;0,1600;0,2001",
                              "01/08/2026;01/02/2027;6;160,00;190,81;0,1600;0,2001\n"
                              "01/02/2027;;6;160,00;190,81;0,1700;0,2100"))
        code, text = self.run_source(today="2027-02-03")
        self.assertEqual(code, 0)
        self.assertIn("- fr/edf/edf-tarif-bleu-base-6kva revision 2 from 2027-02-01", text)
        revisions = json.loads((self.tariffs / "fr/index.json").read_text())[
            "providers"]["edf"]["tariffs"]["edf-tarif-bleu-base-6kva"]["revisions"]
        self.assertEqual(revisions["1"]["effective_to"], "2027-02-01")
        self.assertEqual(revisions["2"]["effective_to"], None)

    def test_a_tariff_the_source_dropped_is_listed(self) -> None:
        self.run_source()
        self.save("\n".join(CSV.splitlines()[:3]) + "\n")
        self.assertIn("### Stored but no longer at the source\n\n- fr/edf/edf-tarif-bleu-base-6kva",
                      self.run_source()[1])

    def test_a_source_that_cannot_be_read_fails_and_writes_nothing(self) -> None:
        before = self.snapshot()
        self.save("DATE;PRIX\n1;2\n")
        code, text = self.run_source()
        self.assertEqual(code, 1)
        self.assertIn("Failed to read the source", text)
        (self.saved / file_name(fr_cre.URL)).unlink()
        self.assertEqual(self.run_source()[0], 1)
        self.assertEqual(before, self.snapshot())

    def test_a_result_that_fails_the_check_fails_the_run(self) -> None:
        (self.tariffs / "fr/index.json").write_text(json.dumps(
            country([{"percent": "20", "effective_from": "2030-01-01"}], code="FR")))
        before = self.snapshot()
        code, text = self.run_source()
        self.assertEqual(code, 1)
        self.assertIn("does not pass the check", text)
        self.assertEqual(before, self.snapshot())  # the new files and folders were taken out again
        self.assertFalse((self.tariffs / "fr/edf").exists())

    def test_restore_puts_back_changed_and_deleted_files(self) -> None:
        self.run_source()
        before = runner.snapshot(self.tariffs)
        (self.tariffs / "fr/index.json").write_text("{}")
        (self.tariffs / "fr/edf/edf-tarif-bleu-base-6kva/1.json").unlink()
        runner.restore(self.tariffs, before)
        self.assertEqual(before, runner.snapshot(self.tariffs))


class CommandLine(unittest.TestCase):
    def test_the_command_runs_each_source_and_writes_one_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(runner, "run", side_effect=[(0, "first"), (1, "second")]) as run, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            report = Path(tmp) / "report.md"
            code = runner.main(["fr_cre", "ofgem_gb", "fr_cre", "--date", "2026-11-11",
                                "--report", str(report), "--replay", tmp])
            self.assertEqual(code, 1)  # one source failed, the other still ran
            self.assertEqual(report.read_text(), "**Failed: ofgem_gb.** The other sources ran.\n\nfirst\nsecond")
            self.assertEqual(out.getvalue(), report.read_text() + "\n")
            self.assertEqual([c.args[0] for c in run.call_args_list], ["fr_cre", "ofgem_gb"])
            name, today, fetch = run.call_args.args
            self.assertEqual((today, fetch.replay), ("2026-11-11", Path(tmp)))

    def test_all_means_every_source_and_the_date_defaults_to_today(self) -> None:
        with mock.patch.object(runner, "run", return_value=(0, "x")) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(["all"]), 0)
            self.assertEqual(tuple(c.args[0] for c in run.call_args_list), sources.NAMES)
            self.assertRegex(run.call_args.args[1], r"^\d{4}-\d{2}-\d{2}$")
            with self.assertRaises(ValueError):
                runner.main(["fr_cre", "--date", "tomorrow"])

    def test_every_listed_source_loads_and_says_what_it_is(self) -> None:
        for name in sources.NAMES:
            module = sources.load(name)
            self.assertRegex(module.SOURCE_ID, r"^[a-z0-9-]+$")
            self.assertRegex(module.COUNTRY, r"^[A-Z]{2}$")
            self.assertTrue(callable(module.read))
            self.assertTrue((Path(runner.__file__).parents[2] / "sources" / f"{module.SOURCE_ID}.md").exists(),
                            f"sources/{module.SOURCE_ID}.md")
        with self.assertRaises(SystemExit):
            sources.load("nowhere")


if __name__ == "__main__":
    unittest.main()
