"""Great Britain: the Ofgem price cap, from the levelised cap workbook (Annex 9).

The cap page lists one workbook per cap period, newest first. The sheet '1a Levelised DTC' gives,
per region and payment group, an annual cost at nil consumption ('Nil') and at benchmark
consumption. So:
    standing charge per day = nil / 365
    unit rate per kWh       = (benchmark - nil) / benchmark kWh
This reproduces Ofgem's published national figures (checked on the GB average row).
Single-rate electricity only: multi-register has one blended rate and no day/night split.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET

from scripts.sync.plan import Area, Plan
from scripts.sync.sources import Result

SOURCE_ID = "ofgem-price-cap"
COUNTRY = "GB"
SITE = "https://www.ofgem.gov.uk"
PAGE = (SITE + "/energy-regulation/domestic-and-non-domestic/energy-pricing-rules/energy-price-cap/"
        "energy-price-cap-default-tariff-levels")
WORKBOOK_LINK = re.compile(r'href="([^"]*/sites/default/files/[^"]*annex-9[^"]*\.xlsx)"', re.I)
SHEET = "1a Levelised DTC"
SINGLE_RATE_KWH = Decimal("2500")  # benchmark consumption, sheet '1c', May 2026 update
BLOCKS = {"Other Payment Method": "direct-debit-and-other", "Standard Credit": "standard-credit",
          "PPM": "prepayment"}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October November December"
    .split(), 1)}


def workbook_url(html: str) -> str:
    """The newest Annex 9 workbook the cap page links: the first such link on it."""
    match = WORKBOOK_LINK.search(html)
    if not match:
        raise ValueError("no Annex 9 workbook link on the Ofgem cap page; its layout has changed")
    link = match.group(1).replace("&amp;", "&")
    return link if link.startswith("http") else SITE + link


def read_sheet(workbook: bytes, sheet_name: str) -> dict[tuple[int, str], str]:
    """Return {(row, column letters): text} for one sheet, using only the standard library."""
    with zipfile.ZipFile(io.BytesIO(workbook)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
                      for si in root.findall("m:si", NS)]
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = next(s.get(f"{{{NS['r']}}}id") for s in wb.find("m:sheets", NS)
                   if s.get("name") == sheet_name)
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == rid)
        target = target.lstrip("/")
        sheet = ET.fromstring(z.read(target if target.startswith("xl/") else f"xl/{target}"))
    cells = {}
    for c in sheet.iter(f"{{{NS['m']}}}c"):
        v = c.find("m:v", NS)
        if v is None:
            continue
        col, row = re.match(r"([A-Z]+)(\d+)", c.get("r")).groups()
        cells[(int(row), col)] = shared[int(v.text)] if c.get("t") == "s" else v.text
    return cells


def period(text: str) -> tuple[date, date]:
    """'October 2026 - December 2026' -> (2026-10-01, 2027-01-01), end excluded."""
    m = re.match(r"(\w+) (\d{4}) - (\w+) (\d{4})", text.strip())
    if not m:
        raise ValueError(f"cannot read cap period from {text!r}")
    start = date(int(m.group(2)), MONTHS[m.group(1)], 1)
    end_month, end_year = MONTHS[m.group(3)], int(m.group(4))
    end = date(end_year + (end_month == 12), end_month % 12 + 1, 1)
    return start, end


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def rows_by_block(cells) -> tuple[str, dict[str, list[tuple[str, Decimal, Decimal]]], dict]:
    period_text = next(v for (r, c), v in cells.items() if c == "C" and r == 6)
    blocks, current, averages = {}, None, {}
    for row in sorted({r for r, _ in cells}):
        label = cells.get((row, "B"))
        if label in BLOCKS:
            current = BLOCKS[label]
            blocks[current] = []
            continue
        if current is None or label is None:
            continue
        if label.startswith("GB average") and "VAT" not in label:
            averages[current] = (cells[(row, "C")], cells[(row, "D")])
            current = None
            continue
        try:
            blocks[current].append((label, Decimal(cells[(row, "C")]), Decimal(cells[(row, "D")])))
        except (KeyError, ArithmeticError):
            continue
    return period_text, blocks, averages


def plans(cells, url: str) -> tuple[list[Plan], list[str]]:
    """One plan per payment group with an area per region, and the averages to check by eye."""
    period_text, blocks, averages = rows_by_block(cells)
    start, end = period(period_text)
    out, notes = [], []
    for group, rows in blocks.items():
        areas = {slug(region): Area(rates={"Single rate": (bench - nil) / SINGLE_RATE_KWH},
                                    standing=nil / 365, label=region,
                                    region=f"OFGEM-{slug(region).upper()}")
                 for region, nil, bench in rows}
        if len(areas) != 14:
            raise ValueError(f"{group}: expected 14 regions in the workbook, found {len(areas)}")
        out.append(Plan(country=COUNTRY, provider_id="ofgem-price-cap", provider="Ofgem price cap",
                        id=f"ofgem-cap-{group}",
                        name=f"Price cap, {group.replace('-', ' ')}, single rate",
                        effective_from=start.isoformat(), effective_to=end.isoformat(),
                        source_url=url, bands=[{"name": "Single rate"}], areas=areas))
    if len(out) != len(BLOCKS):
        raise ValueError(f"expected {len(BLOCKS)} payment groups in the workbook, found {len(out)}")
    for group, (nil, bench) in averages.items():
        n, b = Decimal(nil), Decimal(bench)
        notes.append(f"{group}: GB average works out at {(n / 365 * 100):.2f} p/day and "
                     f"{((b - n) / SINGLE_RATE_KWH * 100):.2f} p/kWh. Compare with Ofgem's "
                     f"published national figures.")
    return out, notes


def read(fetch, today: str, stored: dict) -> Result:
    url = workbook_url(fetch.get(PAGE).decode("utf-8", "replace"))
    found, notes = plans(read_sheet(fetch.get(url), SHEET), url)
    return Result(plans=found, notes=notes, skipped=[
        "multi-register electricity (one blended rate, no day and night split)"])
