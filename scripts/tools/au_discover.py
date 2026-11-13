"""Add Australian plans to the store. Run by a person, never by the schedule.

    python3 -m scripts.tools.au_discover <brand> [<brand> ...] [--per-brand N] [--date YYYY-MM-DD]

For each retailer brand (the path segment on cdr.energymadeeasy.gov.au, such as `agl`), lists its
current residential market electricity plans, takes up to N not yet stored, spread across
distributors and in plan id order, and stores the ones the format can hold. After this the
scheduled sync keeps them up to date.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

from scripts import build
from scripts.paths import TARIFFS
from scripts.sync.apply import apply
from scripts.sync.http import Fetcher
from scripts.sync.sources import au_cdr


def list_plans(fetch, brand: str) -> list[dict]:
    plans, page = [], 1
    while True:
        url = (f"{au_cdr.HOST}/{brand}/cds-au/v1/energy/plans?fuelType=ELECTRICITY&type=MARKET"
               f"&effective=CURRENT&page={page}&page-size=1000")
        data = json.loads(fetch.get(url, {"Accept": "application/json", "x-v": "1"}))
        plans += [p for p in data["data"]["plans"] if p.get("customerType") == "RESIDENTIAL"]
        if page >= data["meta"]["totalPages"]:
            return plans
        page += 1


def pick(plans: list[dict], limit: int) -> list[dict]:
    """Round-robin across distributors, in plan id order, so a small pick spans the regions and
    the same listing always gives the same pick."""
    queues = defaultdict(list)
    for plan in sorted(plans, key=lambda p: p["planId"]):
        queues[tuple(plan["geography"]["distributors"])].append(plan)
    chosen: list[dict] = []
    while len(chosen) < limit and any(queues.values()):
        for key in sorted(queues):
            if queues[key] and len(chosen) < limit:
                chosen.append(queues[key].pop(0))
    return chosen


def discover(fetch, brands: list[str], per_brand: int, today: str, tariffs=TARIFFS) -> list[str]:
    """Store new plans and return the report lines."""
    lines, plans = [], []
    for brand in brands:
        fresh = [p for p in list_plans(fetch, brand)
                 if not (tariffs / "au" / au_cdr.slugify(brand)
                         / au_cdr.slugify(f"{brand}-{p['planId']}")).exists()]
        for item in pick(fresh, per_brand):
            found, reasons = au_cdr.fetch_plan(fetch, au_cdr.detail_url(brand, item["planId"]))
            plans += found
            lines += [f"skipped {brand}: {item['displayName']}: {why}" for why in reasons]
    outcome = apply(plans, au_cdr.SOURCE_ID, today, tariffs)
    return lines + [f"added {key}" for key in outcome.added] + \
        [f"refused {why}" for why in outcome.refused]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add Australian plans to the store.")
    parser.add_argument("brands", nargs="+")
    parser.add_argument("--per-brand", type=int, default=12)
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    today = args.date or datetime.now(timezone.utc).date().isoformat()
    print("\n".join(discover(Fetcher(), args.brands, args.per_brand, today)))
    return build.main([]) or build.main(["--check"])


if __name__ == "__main__":
    sys.exit(main())
