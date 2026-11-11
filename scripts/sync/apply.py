"""Compare what a source gave with what is stored, and write the new revisions.

Three inputs decide the result: the plans, the files already in tariffs/ and the date of the run.
Nothing else is read, so a run can be repeated and tested from saved responses.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lib.tariffstore import layout
from scripts.sync.plan import Plan, to_tariff

NOT_PRICING = ("effective_from", "effective_to", "source", "provider", "name")


@dataclass
class Outcome:
    added: list[str] = field(default_factory=list)       # a tariff seen for the first time
    revised: list[str] = field(default_factory=list)     # a new revision of a stored tariff
    unchanged: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)     # not written, with the reason
    missing: list[str] = field(default_factory=list)     # stored and open, no longer at the source

    @property
    def changed(self) -> bool:
        return bool(self.added or self.revised)


def stored_revisions(folder: Path) -> dict[int, dict]:
    files = sorted(folder.glob("*.json"), key=lambda p: int(p.stem)) if folder.is_dir() else []
    return {int(p.stem): json.loads(p.read_text(encoding="utf-8")) for p in files}


def same_pricing(a: dict, b: dict) -> bool:
    """Equal in everything that prices a bill. Dates, names and the source link are not prices."""
    strip = lambda d: {k: v for k, v in d.items() if k not in NOT_PRICING}  # noqa: E731
    return strip(a) == strip(b)


def stored_for(source_id: str, country: str, tariffs: Path) -> dict[tuple[str, str, str], dict]:
    """{(country, provider id, tariff id): latest file} for the tariffs this source last wrote."""
    out = {}
    for folder in sorted(p for p in (tariffs / country.lower()).glob("*/*") if p.is_dir()):
        revisions = stored_revisions(folder)
        if revisions and revisions[max(revisions)]["source"]["id"] == source_id:
            out[(country.lower(), folder.parent.name, folder.name)] = revisions[max(revisions)]
    return out


def _write(folder: Path, number: int, tariff: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{number}.json").write_text(layout.dumps_tariff(tariff), encoding="utf-8")


def apply(plans: list[Plan], source_id: str, today: str, tariffs: Path) -> Outcome:
    """Write new revisions under `tariffs` and say what happened to every plan.

    A tariff seen for the first time gets every plan given for it, oldest first, as revisions 1, 2
    and so on (a source may hand over a price history). A stored tariff is compared with the newest
    plan only, and gets one new revision when its prices differ or the stored one has ended."""
    outcome = Outcome()
    by_key: dict[tuple, list[Plan]] = {}
    for plan in plans:
        by_key.setdefault(plan.key, []).append(plan)
    countries = {plan.country for plan in plans}
    for key in sorted(by_key):
        history = sorted(by_key[key], key=lambda p: p.effective_from)
        label = "/".join(key)
        folder = tariffs.joinpath(*key)
        try:
            files = [to_tariff(p, source_id) for p in history]
        except ValueError as error:
            outcome.refused.append(str(error))
            continue
        stored = stored_revisions(folder)
        if not stored:
            for number, tariff in enumerate(files, 1):
                _write(folder, number, tariff)
            outcome.added.append(label)
            continue
        number, latest = max(stored), stored[max(stored)]
        plan, tariff = history[-1], files[-1]
        ended = latest.get("effective_to")
        if same_pricing(latest, tariff) and (not ended or ended == tariff.get("effective_to")):
            outcome.unchanged.append(label)
            continue
        if tariff["effective_from"] <= latest["effective_from"] and not plan.dated:
            tariff["effective_from"] = today
        starts = tariff["effective_from"]
        if starts <= latest["effective_from"] or (ended and ended > starts):
            outcome.refused.append(
                f"{label}: prices differ from revision {number} but the new start {starts} is not "
                f"after it (it runs {latest['effective_from']} to {ended or 'open'}); check by hand")
            continue
        _write(folder, number + 1, tariff)
        outcome.revised.append(f"{label} revision {number + 1} from {starts}")
    seen = set(by_key)
    for country in sorted(countries):
        for key, latest in stored_for(source_id, country, tariffs).items():
            if key not in seen and not latest.get("effective_to"):
                outcome.missing.append("/".join(key))
    return outcome
