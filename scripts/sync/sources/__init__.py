"""The sources. Each module has SOURCE_ID, COUNTRY and `read(fetch, today, stored) -> Result`.

`fetch` is a `Fetcher`, `today` an ISO date and `stored` the tariffs this source last wrote, as
`{(country, provider id, tariff id): latest file}`. A source only reads and parses: it never writes
a file and never reads the clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module

from scripts.sync.plan import Plan

NAMES = ("octopus_gb", "ofgem_gb", "selectra_ie", "au_cdr", "fr_cre", "za_eskom")


@dataclass
class Result:
    plans: list[Plan] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # what the source has and the format cannot hold
    notes: list[str] = field(default_factory=list)    # assumptions and figures to check by eye


def load(name: str):
    if name not in NAMES:
        raise SystemExit(f"unknown source {name}; choose from {', '.join(NAMES)}")
    return import_module(f"scripts.sync.sources.{name}")
