"""Ireland: household electricity plans from the supplier pages on selectra.ie.

Stop rather than guess: a plan with a row we cannot map (for example a Peak rate with no stated
hours) is skipped and listed, and a page without the expected VAT notes is refused. The page gives
no date a price started, only when the page was updated, so a changed price is dated by the run.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser

from scripts.sync.plan import Area, Plan
from scripts.sync.sources import Result

SOURCE_ID = "selectra-ie"
COUNTRY = "IE"
BASE = "https://selectra.ie"
VAT = Decimal("1.09")
# NightSaver night hours, assumed, not read from the page. Only plans named NightSaver use them.
# Check against the supplier sheet.
NIGHT_HOURS = "23:00-08:00"
REGIONS = ("urban", "rural")  # the two price columns, in page order

RATE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 -]*?)\s+([\d.]+)\s*c/kWh\s+([\d.]+)\s*c/kWh$")
STANDING = re.compile(r"^Standing\s+€([\d,.]+)/yr\s+€([\d,.]+)/yr$")
UPDATED = re.compile(r"Last updated (\d{1,2} [A-Za-z]+ \d{4})")


class _Text(HTMLParser):
    BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "br", "section", "ul", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "a":
            self.links.extend(v for k, v in attrs if k == "href" and v)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            # Newlines inside a text node are source formatting, not line breaks.
            self.parts.append(data.replace("\n", " "))


def to_lines(html: str) -> tuple[list[str], list[str]]:
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.parts)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
    return [ln for ln in lines if ln], parser.links


def provider_slugs(html: str) -> list[str]:
    _, links = to_lines(html)
    found = {m.group(1) for ln in links
             if (m := re.search(r"/energy/providers/([a-z0-9-]+)/?$", ln))}
    return sorted(found)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_provider(html: str) -> dict:
    """Return {'updated': date|None, 'plans': [...], 'skipped': [...]} for the electricity section."""
    lines, _ = to_lines(html)
    start = next((i for i, ln in enumerate(lines) if ln.startswith(("Electricity Rates", "Pay-As-You-Go Rates"))), None)
    if start is None:
        raise ValueError("no 'Electricity Rates' or 'Pay-As-You-Go Rates' section")
    section = []
    for ln in lines[start + 1:]:
        if ln.startswith(("Gas Rates", "Dual Fuel Rates")):
            break
        section.append(ln)
    body = " ".join(section)
    if "excl. VAT" not in body or "incl. 9% VAT" not in body:
        raise ValueError("VAT notes missing or changed; refusing to guess which rates include VAT")
    m = UPDATED.search(body)
    updated = datetime.strptime(m.group(1), "%d %B %Y").date() if m else None
    plans, skipped = [], []
    header, rates = None, []
    for ln in section:
        if (r := RATE.match(ln)):
            rates.append((r.group(1), r.group(2), r.group(3)))
        elif (s := STANDING.match(ln)):
            if header and rates:
                plans.append({"header": header, "rates": rates,
                              "standing": (s.group(1).replace(",", ""), s.group(2).replace(",", ""))})
            header, rates = None, []
        elif not ln.startswith(("-", "Unit rates", "Score", "Details")) and not rates:
            header = re.sub(r"\s*Score [A-G][+-]?$", "", ln)
    ok = []
    for plan in plans:
        names = [r[0] for r in plan["rates"]]
        if names == ["24-Hour"]:
            ok.append(plan)
        elif sorted(names) == ["Day", "Night"] and "nightsaver" in plan["header"].lower():
            ok.append(plan)
        elif sorted(names) == ["Day", "Night"]:
            skipped.append((plan["header"], "night hours not stated on the page"))
        else:
            skipped.append((plan["header"], "rate rows " + ", ".join(names) + " not mapped"))
    return {"updated": updated, "plans": ok, "skipped": skipped}


def plans_for(slug: str, html: str, today: str) -> tuple[list[Plan], list[str]]:
    """The plans on one supplier page, an area for each of urban and rural, and what was skipped."""
    parsed = parse_provider(html)
    start = parsed["updated"].isoformat() if parsed["updated"] else today
    url = f"{BASE}/energy/providers/{slug}"
    plans, skipped = [], [f"{slug}: {header}: {why}" for header, why in parsed["skipped"]]
    for plan in parsed["plans"]:
        banded = len(plan["rates"]) > 1
        areas = {}
        for column, region in enumerate(REGIONS):
            cents = {name: Decimal(values[column]) for name, *values in plan["rates"]}
            if banded and cents["Night"] >= cents["Day"]:
                skipped.append(f"{slug}: {plan['header']} ({region}): night rate is not below the "
                               "day rate, likely a source error")
                continue
            areas[region] = Area(rates={name: value / 100 * VAT for name, value in cents.items()},
                                 standing=Decimal(plan["standing"][column]) / 365,
                                 label=region.capitalize())
        if not areas:
            continue
        bands = [{"name": "Day"}, {"name": "Night", "hours": NIGHT_HOURS}] if banded \
            else [{"name": "24-Hour"}]
        plans.append(Plan(country=COUNTRY, provider_id=slug, provider=slug.replace("-", " ").title(),
                          id=f"{slug}-{slugify(plan['header'])}", name=plan["header"],
                          effective_from=start, dated=False, source_url=url, bands=bands,
                          areas=areas))
    return plans, skipped


def read(fetch, today: str, stored: dict) -> Result:
    result = Result(notes=[f"NightSaver night hours are assumed to be {NIGHT_HOURS}",
                           "prices are the page's figures after new-customer discounts"])
    directory = fetch.get(f"{BASE}/energy/providers").decode("utf-8", "replace")
    for slug in provider_slugs(directory):
        html = fetch.get(f"{BASE}/energy/providers/{slug}").decode("utf-8", "replace")
        try:
            plans, skipped = plans_for(slug, html, today)
        except ValueError as error:
            result.skipped.append(f"{slug}: page refused: {error}")
            continue
        result.plans += plans
        result.skipped += skipped
    return result
