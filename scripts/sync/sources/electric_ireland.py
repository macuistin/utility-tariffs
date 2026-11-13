"""Ireland: Electric Ireland's household electricity plans, from the supplier's own pages.

The price plans page lists each plan with the hours of its bands. Each plan's "Full pricing
information" is a second page with the unit rates before the discount, the discount, the standing
charge, the PSO levy and the date the prices started, all without VAT. A bill is built the way the
supplier bills it: energy at the rates before the discount, the discount on energy, the standing
charge and the levy, then VAT on all of it.

Stop rather than guess: a plan with a rate row this module does not know, or a band with no
stated hours, is skipped and listed.
"""
from __future__ import annotations

import html as entities
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from scripts.sync.plan import Area, Plan, price
from scripts.sync.sources import Result

SOURCE_ID = "electric-ireland"
COUNTRY = "IE"
PROVIDER_ID = "electric-ireland"
PROVIDER = "Electric Ireland"
BASE = "https://www.electricireland.ie/switch/new-customer"
PLANS_URL = f"{BASE}/price-plans?priceType=E"
REGIONS = ("urban", "rural")
# The order is the priority: a later band wins where two overlap, as Night Boost does over Night.
BANDS = ("Day", "Night", "Peak", "Night Boost")
FLAT = "24 Hour"

PLAN = re.compile(r"showPricePlanCharges\('([A-Za-z0-9]+)'\)\"\s+aria-label='Full pricing "
                  r"information,\s*([^']+)'")
ROW = re.compile(r"<tr>\s*<t[dh][^>]*>(.*?)</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>", re.S)
HOURS = re.compile(r"<td>\s*([A-Za-z ]+?):\s*(\d\d)\.(\d\d)\s*-\s*(\d\d)\.(\d\d)\s*</td>")
RATE = re.compile(r"^Standard ([A-Za-z ]*?) ?unit\b")
DISCOUNT = re.compile(r"^Effective .* with ([\d.]+)% ")
STANDING = re.compile(r"^Standing charge (?:24 hour|NightSaver) (urban|rural) per year")
VALID = re.compile(r"Prices valid as of (\d{1,2})(?:st|nd|rd|th)?(?: of)? ([A-Za-z]+) (\d{4})")
CENTS = re.compile(r"^([\d.]+) c/kWh$")
EURO = re.compile(r"^€([\d,]+\.\d\d)$")


@dataclass(frozen=True)
class Charges:
    """One plan's full pricing, without VAT."""

    rates: dict[str, Decimal]  # band name -> euro per kWh before the discount
    discount: Decimal  # percent off the energy cost, 0 when none
    standing: dict[str, Decimal]  # urban, rural -> euro per year
    levy: Decimal  # the PSO levy, euro per year
    valid_from: str  # ISO date the prices started


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", entities.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def plan_ids(page: str) -> list[tuple[str, str]]:
    """Each plan on the price plans page: the id its pricing page takes, and its name."""
    found = {plan_id: _text(name) for plan_id, name in PLAN.findall(page)}
    return list(found.items())


def card_hours(page: str, plan_id: str) -> dict[str, str]:
    """The hours of each band, from the plan's own price table on the price plans page."""
    end = page.find(f"showPricePlanCharges('{plan_id}')")
    start = page.rfind("<table", 0, end)
    return {name: f"{h1}:{m1}-{h2}:{m2}"
            for name, h1, m1, h2, m2 in HOURS.findall(page[start:end])}


def _amount(pattern: re.Pattern[str], value: str, label: str) -> Decimal:
    match = pattern.match(value)
    if not match:
        raise ValueError(f"{label!r} has no figure in {value!r}")
    return Decimal(match.group(1).replace(",", ""))


def _rate_band(label: str) -> str | None:
    """The band a "Standard ... unit price" row prices. None for a row that prices no band here."""
    match = RATE.match(label)
    # Night storage heating on a 24 hour plan is a second meter with its own price.
    if not match or "for Night Storage Heating" in label:
        return None
    return match.group(1) or FLAT


def _valid_from(page: str) -> str:
    match = VALID.search(_text(page))
    if not match:
        raise ValueError("no 'Prices valid as of' date")
    day, month, year = match.groups()
    return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()


def parse_charges(page: str) -> Charges:
    """A plan's full pricing page. Raises ValueError when a figure it needs is not there."""
    marker = page.find('id="excludeVAT_Contant"')
    if marker < 0:
        raise ValueError("no prices excluding VAT")
    rates: dict[str, Decimal] = {}
    discounts: set[Decimal] = set()
    standing: dict[str, Decimal] = {}
    levy = None
    for label, value in ((_text(a), _text(b)) for a, b in ROW.findall(page[marker:])):
        if (band := _rate_band(label)):
            rates[band] = _amount(CENTS, value, label) / 100
        elif (found := DISCOUNT.match(label)):
            discounts.add(Decimal(found.group(1)))
        elif (found := STANDING.match(label)):
            standing[found.group(1)] = _amount(EURO, value, label)
        elif label.startswith("Public Service Obligation levy per year"):
            levy = _amount(EURO, value, label)
    if not rates or sorted(standing) != ["rural", "urban"] or levy is None or len(discounts) > 1:
        raise ValueError("unit rates, one discount, both standing charges or the levy are missing")
    return Charges(rates, discounts.pop() if discounts else Decimal(0), standing, levy,
                   _valid_from(page))


def bill(discount: Decimal, levy: Decimal) -> dict:
    """The supplier's bill: the discount is on energy only, and VAT is added to every charge."""
    energy: dict = {"kind": "energy_by_band", "round_bands": True}
    if discount:
        energy = {"kind": "adjust", "name": "Discount", "percent": price(-discount), "of": energy}
    charges = {"energy": energy, "standing": {"kind": "per_day"},
               "levy": {"kind": "per_period", "amount": price(levy / 12),
                        "share": "days_in_period", "per": "month"}}
    # The outer sum is where a paired export credit is added, so the credit carries no VAT.
    return {"total": {"kind": "sum", "of": {"charges": {
        "kind": "tax", "name": "VAT", "mode": "added", "percent": "$country.vat_percent",
        "of": {"kind": "sum", "of": charges}}}}}


def _bands(rates: dict[str, Decimal], hours: dict[str, str]) -> list[dict]:
    unknown = sorted(set(rates) - {FLAT, *BANDS})
    if unknown:
        raise ValueError("rate rows " + ", ".join(unknown) + " not mapped")
    if FLAT in rates:
        if len(rates) > 1:
            raise ValueError("a flat rate beside banded rates")
        return [{"name": FLAT}]
    names = [name for name in BANDS if name in rates]
    if names[0] != "Day":
        raise ValueError("no Day rate to be the base")
    missing = [name for name in names[1:] if name not in hours]
    if missing:
        raise ValueError("hours not stated for " + ", ".join(missing))
    return [{"name": "Day"}] + [{"name": name, "hours": hours[name]} for name in names[1:]]


def plan_for(plan_id: str, name: str, hours: dict[str, str], charges: Charges) -> Plan:
    """The plan as the store holds it, an area for each of urban and rural."""
    bands = _bands(charges.rates, hours)
    rates = {band["name"]: charges.rates[band["name"]] for band in bands}
    areas = {region: Area(rates=rates, standing=charges.standing[region] / 365,
                          label=region.capitalize()) for region in REGIONS}
    return Plan(country=COUNTRY, provider_id=PROVIDER_ID, provider=PROVIDER,
                id=f"{PROVIDER_ID}-{slugify(name)}", name=name,
                effective_from=charges.valid_from,
                source_url=f"{BASE}/priceplan-charges?pricePlanId={plan_id}", bands=bands,
                areas=areas, prices_include_tax=False,
                extra={"bill": bill(charges.discount, charges.levy)})


def read(fetch, today: str, stored: dict) -> Result:
    result = Result(notes=["a plan's discount is for paying by direct debit with online billing",
                           "night storage heating prices are not held: they need a second meter"])
    page = fetch.get(PLANS_URL).decode("utf-8", "replace")
    listed = plan_ids(page)
    if not listed:
        raise ValueError("no price plans on the page")
    seen: set[str] = set()
    for plan_id, name in listed:
        pricing = fetch.get(f"{BASE}/priceplan-charges?pricePlanId={plan_id}")
        try:
            plan = plan_for(plan_id, name, card_hours(page, plan_id),
                            parse_charges(pricing.decode("utf-8", "replace")))
        except ValueError as error:
            result.skipped.append(f"{name}: {error}")
            continue
        if plan.id in seen:
            result.skipped.append(f"{name}: a second plan with the id {plan.id}")
            continue
        seen.add(plan.id)
        result.plans.append(plan)
    return result
