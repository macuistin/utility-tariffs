"""Great Britain: Octopus Energy import and export tariffs from its public product API.

Import: single-register electricity only, one area per distribution region, at the monthly
direct debit price. Dual register, half-hourly, time of use and restricted products are skipped
and listed, and so is any other payment method whose price differs. Export: flat and
fixed-time-band products only. Prices are pence on the API and pounds in the files.
The API gives no start date for an import price, so a changed price is dated by the run.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from scripts.sync.plan import Area, Plan
from scripts.sync.sources import Result

SOURCE_ID = "octopus-energy-gb"
COUNTRY = "GB"
API = "https://api.octopus.energy/v1"
# Plain variable and fixed plans only. Add a code here after reading its description.
PRODUCTS = ("VAR-22-11-01", "OE-FIX-12M-26-11-09", "OE-FIX-18M-26-11-09")
EXPORT_PRODUCTS = ("OUTGOING-VAR-24-10-26", "OUTGOING-SEG-FIX-12M-20-07-07",
                   "OUTGOING-SEG-FIX-12M-26-10-21", "OUTGOING-PRIME-FIX-12M-26-06-23")
# The payment method held. A product lists a price for each method it can be paid by.
PAYMENT = "direct_debit_monthly"
LONDON = ZoneInfo("Europe/London")
MIN_SHARE = Decimal("0.05")  # a band seen on fewer than this share of rows is an edge row
MAX_RATE_PAGES = 5
ONE_DAY = timedelta(days=1)
# Octopus names the 14 distribution regions by letter. These are the usual region names.
GSP_NAMES = {
    "a": "Eastern England", "b": "East Midlands", "c": "London", "d": "Merseyside and North Wales",
    "e": "West Midlands", "f": "North East England", "g": "North West England",
    "h": "Southern England", "j": "South East England", "k": "South Wales",
    "l": "South Western England", "m": "Yorkshire", "n": "Southern Scotland",
    "p": "Northern Scotland",
}


def pounds(pence) -> Decimal:
    return Decimal(str(pence)) / 100


def _restricted(product: dict) -> bool:
    return bool(product["is_business"] or product["is_prepay"] or product["is_tracker"]
                or product["is_restricted"])


def _plan(product: dict, **fields) -> Plan:
    code = product["code"]
    return Plan(country=COUNTRY, provider_id="octopus-energy", provider="Octopus Energy",
                id=f"octopus-{code.lower()}", name=product["full_name"],
                source_url=f"{API}/products/{code}/", **fields)


def _held(methods: dict) -> dict | None:
    """The price held for a region: monthly direct debit, or the only method there is."""
    if PAYMENT in methods:
        return methods[PAYMENT]
    return next(iter(methods.values())) if len(methods) == 1 else None


def _prices(tariff: dict) -> tuple:
    return tariff["standard_unit_rate_inc_vat"], tariff["standing_charge_inc_vat"]


def import_plan(product: dict, today: str) -> tuple[Plan | None, list[str]]:
    """One plan with an area per region, and what was skipped."""
    code = product["code"]
    if _restricted(product):
        return None, [f"{code}: business, prepay, tracker or restricted"]
    skipped = []
    if product["dual_register_electricity_tariffs"]:
        skipped.append(f"{code}: dual register (Economy 7 hours are set by the meter, not the API)")
    areas = {}
    others: set[str] = set()
    for region_key, methods in sorted(product["single_register_electricity_tariffs"].items()):
        letter = region_key.strip("_").lower()
        tariff = _held(methods)
        if tariff is None:
            return None, skipped + [f"{code}: region {letter.upper()} has no {PAYMENT} price and "
                                    f"lists {', '.join(sorted(methods))}"]
        others |= {name for name, other in methods.items() if _prices(other) != _prices(tariff)}
        areas[letter] = Area(rates={"Single rate": pounds(tariff["standard_unit_rate_inc_vat"])},
                             standing=pounds(tariff["standing_charge_inc_vat"]),
                             label=f"{GSP_NAMES[letter]} ({letter.upper()})",
                             region=f"GSP-{letter.upper()}")
    if not areas:
        return None, skipped + [f"{code}: no single-register electricity tariff"]
    if others:
        skipped.append(f"{code}: prices for {', '.join(sorted(others))} differ and are not held")
    start = (product.get("tariffs_active_at") or "")[:10] or today
    return _plan(product, effective_from=start, dated=False, bands=[{"name": "Single rate"}],
                 areas=areas), skipped


def _local(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(LONDON)


def bands_from_rows(rows: list[dict]) -> list[tuple[str, str, Decimal]]:
    """The daily bands in local time as (start HH:MM, end HH:MM, price in pounds).

    Rows whose local start and end times and value repeat on at least 5 percent of rows are
    the pattern; a first-day or clock-change row that does not repeat is dropped. Refuses a
    feed with no repeating pattern, rather than guess.
    """
    closed = [r for r in rows if r.get("valid_to")]
    counts: Counter = Counter()
    for r in closed:
        counts[(_local(r["valid_from"]).strftime("%H:%M"), _local(r["valid_to"]).strftime("%H:%M"),
                pounds(r["value_inc_vat"]))] += 1
    keep = sorted(k for k, n in counts.items() if Decimal(n) / len(closed) >= MIN_SHARE)
    if not keep:
        raise ValueError("no repeating daily pattern in the rate rows")
    return keep


def flat_history(rows: list[dict]) -> list[tuple[Decimal, date, date | None]]:
    """(price in pounds, effective from, effective to) oldest first, for a flat product."""
    out: list[tuple[Decimal, date, date | None]] = []
    for r in sorted(rows, key=lambda r: r["valid_from"]):
        start = _local(r["valid_from"]).date()
        end = _local(r["valid_to"]).date() if r.get("valid_to") else None
        value = pounds(r["value_inc_vat"])
        if out and out[-1][0] == value:
            out[-1] = (value, out[-1][1], end)
        else:
            out.append((value, start, end))
    return out


def _minutes(band: tuple[str, str, Decimal]) -> int:
    start, end = (int(t[:2]) * 60 + int(t[3:]) for t in band[:2])
    return (end - start) % 1440


def export_plans(product: dict, rows: list[dict]) -> tuple[list[Plan], list[str]]:
    """The price history of a flat export product, or one plan for a banded one."""
    code = product["code"]
    if _restricted(product):
        return [], [f"{code}: business, prepay, tracker or restricted"]
    tariffs = product["single_register_electricity_tariffs"]
    rates = {m["standard_unit_rate_inc_vat"] for ms in tariffs.values() for m in ms.values()}
    standing = {m["standing_charge_inc_vat"] for ms in tariffs.values() for m in ms.values()}
    if product["dual_register_electricity_tariffs"] or standing != {0.0} or len(tariffs) != 14:
        return [], [f"{code}: not a flat zero-standing-charge export over all 14 regions"]
    if len(rates) != 1:
        return [], [f"{code}: the rate differs by region, which export files do not hold yet"]
    if any(r.get("valid_to") and _local(r["valid_to"]) - _local(r["valid_from"]) < ONE_DAY
           for r in rows):  # a price that lasts hours is a daily band, one that lasts days is a change
        try:
            bands = bands_from_rows(rows)
        except ValueError as error:
            return [], [f"{code}: {error}"]
        longest = max(bands, key=_minutes)
        peaks = [b for b in bands if b is not longest]
        names = ["Peak"] if len(peaks) == 1 else [f"Peak {i}" for i in range(1, len(peaks) + 1)]
        area = Area(rates={"Off-peak": longest[2], **{n: b[2] for n, b in zip(names, peaks)}})
        start = min(_local(r["valid_from"]).date() for r in rows).isoformat()
        return [_plan(product, direction="export", effective_from=start, areas={"all": area},
                      bands=[{"name": "Off-peak"}] + [{"name": n, "hours": f"{b[0]}-{b[1]}"}
                                                      for n, b in zip(names, peaks)])], []
    return [_plan(product, direction="export", effective_from=start.isoformat(),
                  effective_to=end.isoformat() if end else None, bands=[{"name": "Flat"}],
                  areas={"all": Area(rates={"Flat": value})})
            for value, start, end in flat_history(rows)], []


def _rate_rows(fetch, code: str) -> list[dict]:
    url = f"{API}/products/{code}/electricity-tariffs/E-1R-{code}-A/standard-unit-rates/"
    rows: list[dict] = []
    for _ in range(MAX_RATE_PAGES):
        page = json.loads(fetch.get(url, {"Accept": "application/json"}))
        rows += page["results"]
        url = page.get("next")
        if not url:
            break
    return rows


def read(fetch, today: str, stored: dict) -> Result:
    result = Result()
    for code in PRODUCTS:
        product = json.loads(fetch.get(f"{API}/products/{code}/", {"Accept": "application/json"}))
        plan, skipped = import_plan(product, today)
        result.plans += [plan] if plan else []
        result.skipped += skipped
    for code in EXPORT_PRODUCTS:
        product = json.loads(fetch.get(f"{API}/products/{code}/", {"Accept": "application/json"}))
        plans, skipped = export_plans(product, _rate_rows(fetch, code))
        result.plans += plans
        result.skipped += skipped
    return result
