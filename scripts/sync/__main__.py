"""Run sources: fetch, parse, validate, write new revisions, rebuild and check the indexes.

    python3 -m scripts.sync <source> [<source> ...] [--date YYYY-MM-DD] [--report FILE]
                                                    [--record DIR | --replay DIR]
    python3 -m scripts.sync all

`all` is the scheduled sources. A source that is run by hand is only run when it is named.

Each source is all or nothing: if it cannot be read, or what it wrote does not pass the check,
tariffs/ is put back as it was before that source and the next source still runs. Exit 0 when
every source finished, changed or not, and 1 when any failed. The report is Markdown: what
changed, what was skipped and what to look at. It is the body of the pull request.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from scripts import build
from scripts.paths import TARIFFS
from scripts.sync import sources
from scripts.sync.apply import Outcome, apply, stored_for
from scripts.sync.http import Blocked, Fetcher


def report(name: str, today: str, result: sources.Result, outcome: Outcome) -> str:
    lines = [f"## Tariff sync: {name}, {today}", "",
             f"{len(outcome.added)} new, {len(outcome.revised)} revised, "
             f"{len(outcome.unchanged)} unchanged, {len(outcome.refused)} refused, "
             f"{len(outcome.missing)} no longer at the source.", ""]
    for title, items in (("New tariffs", outcome.added), ("New revisions", outcome.revised),
                         ("Refused, needs a person", outcome.refused),
                         ("Stored but no longer at the source", outcome.missing),
                         ("Skipped by the source reader", result.skipped),
                         ("Notes", result.notes)):
        if items:
            lines += [f"### {title}", "", *[f"- {item}" for item in items], ""]
    return "\n".join(lines)


def snapshot(tariffs: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in tariffs.rglob("*.json")}


def restore(tariffs: Path, before: dict[Path, bytes]) -> None:
    """Put tariffs/ back exactly as it was."""
    for path in sorted(tariffs.rglob("*.json")):
        if path not in before:
            path.unlink()
            folder = path.parent
            while folder != tariffs and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent
    for path, data in before.items():
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)


def run(name: str, today: str, fetch: Fetcher, tariffs: Path = TARIFFS) -> tuple[int, str]:
    """(exit code, report) for one source. On a failure tariffs/ is left as it was."""
    source = sources.load(name)
    try:
        result = source.read(fetch, today, stored_for(source.SOURCE_ID, source.COUNTRY, tariffs))
    except (Blocked, ValueError, KeyError, StopIteration) as error:
        return 1, f"## Tariff sync: {name}, {today}\n\nFailed to read the source: {error!r}\n"
    before = snapshot(tariffs)
    outcome = apply(result.plans, source.SOURCE_ID, today, tariffs)
    text = report(name, today, result, outcome)
    if build.main([], tariffs) or build.main(["--check"], tariffs):
        restore(tariffs, before)
        return 1, text + ("\nFailed: the result does not pass the check, so nothing from this "
                          "source was kept. See the lines above the report.\n")
    return 0, text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync tariff sources into tariffs/.")
    parser.add_argument("sources", nargs="+", choices=(*sources.NAMES, "all"), metavar="source",
                        help=f"all ({', '.join(sources.SCHEDULED)}), or any of those, or one run "
                             f"by hand: {', '.join(sources.BY_HAND)}")
    parser.add_argument("--date", help="the day of the run, default today in UTC")
    parser.add_argument("--report", type=Path, help="also write the report to this file")
    parser.add_argument("--record", type=Path, help="save every response in this folder")
    parser.add_argument("--replay", type=Path, help="answer from this folder, no network")
    args = parser.parse_args(argv)
    today = args.date or datetime.now(timezone.utc).date().isoformat()
    date.fromisoformat(today)
    named = [n for name in args.sources for n in (sources.SCHEDULED if name == "all" else (name,))]
    names = tuple(dict.fromkeys(named))
    fetch = Fetcher(record=args.record, replay=args.replay)
    results = [run(name, today, fetch) for name in names]
    failed = [name for name, (code, _) in zip(names, results) if code]
    text = "\n".join(text for _, text in results)
    if failed:
        text = f"**Failed: {', '.join(failed)}.** The other sources ran.\n\n" + text
    print(text)
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
