"""Australia: retailer plans from the Consumer Data Right energy product reference API.

Retailers publish Get Generic Plans / Get Generic Plan Detail. The AER hosts them under
https://cdr.energymadeeasy.gov.au/<brand>/cds-au/v1/energy/ (see sources/au-cdr-energy.md). Requests
carry x-v. Prices are per kWh and per day, EXCLUSIVE of GST (CDS schema text), so tax is 'added'.

A scheduled run refreshes the plans already stored, one request each, found again by the link in
each file. It never picks new plans, so the set of tariffs only grows when a person asks for it
with scripts/tools/au_discover.py.

Plans the format can hold: a single flat rate, or time of use where the windows run every day and
cover 24 hours exactly once. Skipped and listed: seasonal periods, step blocks/volume tiers,
demand charges, banded supply charges, weekday-only windows, anything with an unknown time zone.
A plan outside the country block's time zone carries its own `timezone`.

The plan detail also lists the retailer's solar feed-in tariff. A flat rate, or rates by time of
day that cover 24 hours once, becomes an export tariff the plan names. A government scheme rate, a
rate that is not per kWh or not per year, tiers, and windows that miss a day or leave gaps are
skipped and listed, and the plan stays unpaired.
"""
from __future__ import annotations

import dataclasses
import json
import re
from datetime import date

from scripts.sync.http import Blocked
from scripts.sync.plan import Plan, single
from scripts.sync.sources import Result

HOST = "https://cdr.energymadeeasy.gov.au"
SOURCE_ID = "au-cdr-energy"
COUNTRY = "AU"
COUNTRY_ZONE = "Australia/Sydney"  # the time zone in the AU country block
# Sydney, Melbourne and Hobart change clocks on the same dates, so one block timezone fits all three.
SAME_RULES = {"Australia/Sydney", "Australia/Melbourne", "Australia/Hobart"}
TZ = {  # distributor -> IANA zone (ACT/NSW/VIC/TAS observe DST, QLD/NT/WA/SA as listed)
    "Ausgrid": "Australia/Sydney", "Endeavour": "Australia/Sydney", "Essential": "Australia/Sydney",
    "Evoenergy": "Australia/Sydney", "Jemena": "Australia/Melbourne",
    "CitiPower": "Australia/Melbourne", "Powercor": "Australia/Melbourne",
    "United Energy": "Australia/Melbourne", "AusNet": "Australia/Melbourne",
    "Energex": "Australia/Brisbane", "Ergon": "Australia/Brisbane",
    "SA Power Networks": "Australia/Adelaide", "TasNetworks": "Australia/Hobart",
    "Western Power": "Australia/Perth", "Horizon": "Australia/Perth",
    "Power and Water": "Australia/Darwin",
}
ALL_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fits_block(zone: str, block_zone: str) -> bool:
    return zone == block_zone or (zone in SAME_RULES and block_zone in SAME_RULES)


def tz_for(distributors: list[str]) -> str | None:
    zones = {z for d in distributors for k, z in TZ.items() if k.lower() in d.lower()}
    return zones.pop() if len(zones) == 1 else None


def minutes(hhmm: str, end: bool = False) -> int:
    """Minute of day. Retailers write inclusive ends ('20:59'), so an end at :59 means the next minute."""
    h, m = hhmm.split(":")[:2]
    total = int(h) * 60 + int(m)
    return (total + 1) % 1440 if end and int(m) == 59 else total


def clock(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def full_year(start: str | None, end: str | None) -> bool:
    """One period that spans the whole year, whichever day it starts (01-01..12-31, 07-01..06-30)."""
    if not start or not end:
        return False
    day = date.fromisoformat
    return (day(f"2025-{end}").toordinal() + 1 - day(f"2025-{start}").toordinal()) % 365 == 0


def express(contract: dict) -> tuple[dict | None, str | None]:
    """Return ({'base_price','zones','standing_per_day'}, None) or (None, reason)."""
    periods = contract.get("tariffPeriod") or []
    if len(periods) != 1 or not full_year(periods[0].get("startDate"), periods[0].get("endDate")):
        return None, "seasonal or multiple tariff periods"
    period = periods[0]
    if period.get("dailySupplyChargeType", "SINGLE") != "SINGLE" or not period.get("dailySupplyCharge"):
        return None, "banded or missing daily supply charge"
    if contract.get("demandCharges") or period.get("rateBlockUType") == "demandCharges":
        return None, "demand charges"
    out = {"standing_per_day": period["dailySupplyCharge"], "zones": []}
    kind = period.get("rateBlockUType")
    if kind == "singleRate":
        rates = period["singleRate"]["rates"]
        if len(rates) != 1:
            return None, "volume tiers (step pricing)"
        out["base_price"] = rates[0]["unitPrice"]
        return out, None
    if kind != "timeOfUseRates":
        return None, f"rate block {kind}"
    covered, windows = [0] * 1440, []
    for rate in period["timeOfUseRates"]:
        if len(rate["rates"]) != 1:
            return None, "volume tiers inside time of use"
        if rate.get("type") in ("CONTROLLED_LOAD", "SOLAR", "EXCESS"):
            return None, f"{rate['type']} rate inside time of use"
        for window in rate.get("timeOfUse") or [{"days": sorted(ALL_DAYS), "startTime": "00:00", "endTime": "00:00"}]:
            if set(window["days"]) != ALL_DAYS:
                return None, "windows not every day (weekday/weekend split)"
            s, e = minutes(window["startTime"]), minutes(window["endTime"], end=True)
            span = (range(1440) if e == s else range(s, e) if e > s
                    else list(range(s, 1440)) + list(range(0, e)))
            for minute in span:
                covered[minute] += 1
            windows.append((rate.get("displayName") or rate["type"], f"{clock(s)}-{clock(e)}",
                            rate["rates"][0]["unitPrice"], len(span)))
    if any(c != 1 for c in covered):
        return None, "time windows overlap or leave gaps"
    windows.sort(key=lambda w: -w[3])
    out["base_name"], _, out["base_price"], _ = windows[0]
    out["zones"] = [(n, h, p) for n, h, p, _ in windows[1:]]
    return out, None


def feed_in(contract: dict) -> tuple[dict | None, str | None]:
    """The retailer's feed-in rates as ({'base_name','base_price','zones'}, None). (None, None)
    when it publishes none, and (None, reason) when the format cannot hold what it publishes.
    Government scheme rates belong to old installations and are not read."""
    windows = []
    for entry in contract.get("solarFeedInTariff") or []:
        if entry.get("payerType") == "GOVERNMENT":
            continue
        kind = entry.get("tariffUType")
        if kind == "singleTariff":
            bodies = [(entry["singleTariff"], entry.get("displayName") or "Export")]
        elif kind == "timeVaryingTariffs":
            bodies = [(v, v.get("displayName") or v.get("type") or "Export")
                      for v in entry["timeVaryingTariffs"]]
        else:
            return None, f"feed-in {kind}"
        for body, name in bodies:
            rates = body.get("rates") or []
            if len(rates) != 1 or rates[0].get("measureUnit", "KWH") != "KWH":
                return None, "feed-in with tiers or a unit that is not kWh"
            if body.get("period") not in (None, "P1Y"):
                return None, f"feed-in rate for the period {body['period']}"
            for window in body.get("timeVariations") or [{"days": sorted(ALL_DAYS)}]:
                if set(window["days"]) != ALL_DAYS:
                    return None, "feed-in windows not every day"
                windows.append((name, window.get("startTime", "00:00"),
                                window.get("endTime", "00:00"), rates[0]["unitPrice"]))
    if not windows:
        return None, None
    return cover(windows)


def cover(windows: list[tuple[str, str, str, str]]) -> tuple[dict | None, str | None]:
    """Windows that cover 24 hours exactly once, as the longest one for the base and the rest as zones."""
    covered, spans = [0] * 1440, []
    for name, start, end, price in windows:
        s, e = minutes(start), minutes(end, end=True)
        span = list(range(1440)) if e == s else list(range(s, e)) if e > s \
            else list(range(s, 1440)) + list(range(0, e))
        for minute in span:
            covered[minute] += 1
        spans.append((name, f"{clock(s)}-{clock(e)}", price, len(span)))
    if any(c != 1 for c in covered):
        return None, "feed-in windows overlap or leave gaps"
    spans.sort(key=lambda w: -w[3])
    return {"base_name": spans[0][0], "base_price": spans[0][2],
            "zones": [(n, h, p) for n, h, p, _ in spans[1:]]}, None


def export_plan(plan: Plan, priced: dict) -> Plan:
    """The feed-in as an export tariff beside the plan, with the plan's dates and time zone."""
    bands, areas = single((priced["base_name"], priced["base_price"]), priced["zones"], None)
    return Plan(country=COUNTRY, provider_id=plan.provider_id, provider=plan.provider,
                id=f"{plan.id}-export", name=f"{plan.name} export",
                effective_from=plan.effective_from, effective_to=plan.effective_to, dated=False,
                source_url=plan.source_url, prices_include_tax=False, timezone=plan.timezone,
                bands=bands, areas=areas, direction="export")


def plan_from_detail(brand: str, plan_id: str, data: dict) -> tuple[Plan | None, str | None]:
    """(plan, None), or (None, why the format cannot hold it)."""
    priced, why = express(data.get("electricityContract") or {})
    distributors = data["geography"]["distributors"]
    zone = tz_for(distributors)
    if not why and not zone:
        why = f"unknown timezone for distributor {distributors}"
    if why:
        return None, why
    bands, areas = single((priced.get("base_name", "Base"), priced["base_price"]), priced["zones"],
                          priced["standing_per_day"])
    return Plan(country=COUNTRY, provider_id=slugify(brand), provider=data["brandName"],
                id=slugify(f"{brand}-{plan_id}"),
                name=f"{data['displayName']} ({' + '.join(distributors)})",
                effective_from=data["effectiveFrom"][:10],
                effective_to=data["effectiveTo"][:10] if data.get("effectiveTo") else None,
                dated=False, source_url=detail_url(brand, plan_id), prices_include_tax=False,
                timezone=None if fits_block(zone, COUNTRY_ZONE) else zone,
                bands=bands, areas=areas), None


def detail_url(brand: str, plan_id: str) -> str:
    return f"{HOST}/{brand}/cds-au/v1/energy/plans/{plan_id}"


def fetch_plan(fetch, url: str) -> tuple[list[Plan], list[str]]:
    """Read one plan by its detail link: the plan and the export it pays when the retailer
    publishes a feed-in tariff the format can hold, and the reasons for anything left out."""
    match = re.match(re.escape(HOST) + r"/([^/]+)/cds-au/v1/energy/plans/(.+)$", url)
    if not match:
        return [], ["not a plan detail link"]
    try:
        detail = json.loads(fetch.get(url, {"Accept": "application/json", "x-v": "3", "x-min-v": "1"}))
    except Blocked as error:
        return [], [f"detail failed: {error}"]
    plan, why = plan_from_detail(match.group(1), match.group(2), detail["data"])
    if plan is None:
        return [], [why or "not held"]
    priced, why = feed_in(detail["data"].get("electricityContract") or {})
    if priced is None:
        return [plan], [f"no export paired: {why}"] if why else []
    export = export_plan(plan, priced)
    paired = dataclasses.replace(plan, extra={**plan.extra, "export": f"{plan.provider_id}/{export.id}"})
    return [paired, export], []


def read(fetch, today: str, stored: dict) -> Result:
    result = Result()
    for key, latest in sorted(stored.items()):
        if latest.get("effective_to"):
            continue
        plans, reasons = fetch_plan(fetch, latest["source"]["url"])
        result.skipped += [f"{'/'.join(key)}: {why}" for why in reasons]
        if plans and plans[0].effective_to and plans[0].effective_to <= today:
            result.skipped.append(f"{'/'.join(key)}: the retailer ended it on {plans[0].effective_to}")
        else:
            result.plans += plans
    return result
