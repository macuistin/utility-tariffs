"""Write the indexes from the tariff files, or check them.

    python3 -m scripts.build                    rewrite every index and tariff file in house layout
    python3 -m scripts.build --check            fail if anything is invalid or not as built
    python3 -m scripts.build --check --base REF also fail if a revision that exists at the git
                                                ref REF was changed (only effective_to may be added)

This is the only code that writes an index. It reads the country block from the top of each
tariffs/electricity/<cc>/index.json and derives the rest from the tariff files, so it takes no clock and keeps
no state: the same files always give the same bytes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from lib.tariffstore import index as idx
from lib.tariffstore import layout
from scripts.paths import TARIFFS


def read_country(folder: Path) -> tuple[dict, dict[str, dict]]:
    """(country block, {provider/tariff/n.json: file}) for one country folder."""
    block = idx.block_of(json.loads((folder / "index.json").read_text(encoding="utf-8")))
    block.pop("schema", None)
    files = {p.relative_to(folder).as_posix(): json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(folder.rglob("*.json")) if p.name != "index.json"}
    return block, files


def render(tariffs: Path = TARIFFS) -> tuple[dict[Path, str], list[str]]:
    """({path: the text it should hold}, problems) for every index and tariff file."""
    out: dict[Path, str] = {}
    problems: list[str] = []
    countries = {}
    for folder in sorted(p for p in tariffs.iterdir() if p.is_dir()):
        code = folder.name.upper()
        if not (folder / "index.json").exists():
            problems.append(f"{folder.name}: no index.json with the country block")
            continue
        block, files = read_country(folder)
        found = idx.problems(code, block, files)
        problems += [f"{folder.name}/{p}" for p in found]
        if found:
            continue
        countries[code] = idx.country_index(block, files)
        out[folder / "index.json"] = layout.dumps_index(countries[code])
        out.update({folder / path: layout.dumps_tariff(doc) for path, doc in files.items()})
    try:
        unavailable = json.loads((tariffs / "unavailable.json").read_text(encoding="utf-8"))
        out[tariffs / "index.json"] = layout.dumps_root(idx.root_index(countries, unavailable))
    except (OSError, ValueError) as error:
        problems.append(str(error))
    return out, problems


def changed_revisions(base: str, tariffs: Path = TARIFFS) -> list[str]:
    """Revision files that exist at the git ref `base` and no longer say the same thing.

    A published revision is permanent. The one edit allowed is adding `effective_to`."""
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=tariffs, check=True,
                          capture_output=True, text=True).stdout.strip()
    prefix = tariffs.resolve().relative_to(Path(root).resolve()).as_posix()
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", base, "--", prefix], cwd=root,
                             check=True, capture_output=True, text=True).stdout.split()
    problems = []
    for name in listing:
        if not idx.PATH.match(name[len(prefix) + 1:].split("/", 1)[-1]):
            continue
        old = json.loads(subprocess.run(["git", "show", f"{base}:{name}"], cwd=root, check=True,
                                        capture_output=True, text=True).stdout)
        path = Path(root) / name
        if not path.exists():
            problems.append(f"{name}: a published revision was deleted")
            continue
        new = json.loads(path.read_text(encoding="utf-8"))
        if "effective_to" not in old:
            new.pop("effective_to", None)
        if new != old:
            problems.append(f"{name}: a published revision was changed; add a new revision instead")
    return problems


def main(argv: list[str] | None = None, tariffs: Path = TARIFFS) -> int:
    parser = argparse.ArgumentParser(description="Write or check the tariff indexes.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--base", help="git ref whose revisions must be unchanged (with --check)")
    args = parser.parse_args(argv)
    out, problems = render(tariffs)
    if args.check:
        problems += [f"{p.relative_to(tariffs)}: not as built; run python3 -m scripts.build"
                     for p, text in out.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if args.base:
            problems += changed_revisions(args.base, tariffs)
    for line in problems:
        print(line)
    if problems:
        return 1
    if not args.check:
        for path, text in out.items():
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
