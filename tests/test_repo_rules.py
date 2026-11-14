"""The rules in CLAUDE.md that a machine can hold: the file itself, and what may import what."""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

from scripts.paths import ROOT

LOCAL = {"lib", "scripts", "tests"}


def imports(path: Path) -> set[str]:
    """The absolute modules a file imports, as dotted names."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def lib_packages(path: Path) -> set[str]:
    """The packages under lib/ a file reaches, by a relative or an absolute import."""
    own = path.relative_to(ROOT / "lib").parts
    found = {name.split(".")[1] for name in imports(path) if name.startswith("lib.")}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = own[:len(own) - node.level]
            target = [*base, *(node.module.split(".") if node.module else [])]
            found.update(target[:1] or [alias.name for alias in node.names])
    return found


def third_party(names: set[str]) -> set[str]:
    tops = {name.split(".")[0] for name in names}
    return tops - LOCAL - set(sys.stdlib_module_names)


class Instructions(unittest.TestCase):
    def test_claude_md_stays_short(self) -> None:
        lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
        self.assertLess(len(lines), 150)

    def test_agents_md_is_the_same_file(self) -> None:
        agents = ROOT / "AGENTS.md"
        self.assertTrue(agents.is_symlink())
        self.assertEqual(agents.resolve(), (ROOT / "CLAUDE.md").resolve())

    def test_every_rule_file_is_listed_and_every_listed_file_exists(self) -> None:
        listed = set(re.findall(r"`\.claude/rules/([a-z-]+\.md)`", (ROOT / "CLAUDE.md").read_text("utf-8")))
        present = {path.name for path in (ROOT / ".claude/rules").glob("*.md")}
        self.assertEqual(listed, present)


class Naming(unittest.TestCase):
    TITLE = re.compile(r'^title: "(feat|fix|docs|test|refactor|ci|chore|type)\((\w+)\): ')

    def scopes(self) -> set[str]:
        text = (ROOT / ".claude/rules/docs-and-style.md").read_text("utf-8")
        line = text[text.index("- **Scope**"):text.index("- **Summary:**")]
        return set(re.findall(r"`([a-z]+)`", line))

    def test_issue_templates_start_a_conventional_title_with_a_known_scope(self) -> None:
        templates = sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.md"))
        self.assertTrue(templates)
        for path in templates:
            with self.subTest(path.name):
                match = next(filter(None, map(self.TITLE.match, path.read_text("utf-8").splitlines())), None)
                self.assertIsNotNone(match)
                self.assertIn(match.group(2), self.scopes() | {"scope"})

    def test_contributing_names_the_same_scopes_as_the_rules(self) -> None:
        text = (ROOT / "CONTRIBUTING.md").read_text("utf-8")
        line = text[text.index("Scopes:"):text.index("For example")]
        self.assertEqual(set(re.findall(r"`([a-z]+)`", line)), self.scopes())


class Imports(unittest.TestCase):
    def test_the_store_library_and_the_scripts_use_the_standard_library_only(self) -> None:
        for folder in ("lib", "scripts"):
            for path in sorted((ROOT / folder).rglob("*.py")):
                with self.subTest(path.relative_to(ROOT).as_posix()):
                    self.assertEqual(third_party(imports(path)), set())

    def test_the_store_library_does_not_import_the_engine_or_the_scripts(self) -> None:
        for path in sorted((ROOT / "lib/tariffstore").rglob("*.py")):
            for name in imports(path):
                with self.subTest(path.name, module=name):
                    self.assertFalse(name.startswith(("lib.tariff.", "lib.timeutil", "scripts"))
                                     or name == "lib.tariff")

    def test_each_library_reaches_only_the_packages_it_is_allowed(self) -> None:
        allowed = {"tariff": {"tariff", "timeutil"}, "timeutil": {"timeutil"},
                   "tariffstore": {"tariffstore"}, "tariffranking": {"tariffranking", "tariff"}}
        for package, may in allowed.items():
            for path in sorted((ROOT / "lib" / package).rglob("*.py")):
                with self.subTest(path.relative_to(ROOT).as_posix()):
                    self.assertLessEqual(lib_packages(path), may)

    def test_the_scripts_do_not_import_the_engine(self) -> None:
        for path in sorted((ROOT / "scripts").rglob("*.py")):
            for name in imports(path):
                with self.subTest(path.relative_to(ROOT).as_posix(), module=name):
                    self.assertFalse(name == "lib.tariff" or name.startswith(("lib.tariff.", "lib.timeutil")))


if __name__ == "__main__":
    unittest.main()
