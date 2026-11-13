"""South Africa: Eskom Direct residential tariffs from the Tariffs and Charges Booklet PDF.

Held: Homelight 20A/60A (one energy rate, no fixed charge) and Homepower 1-4 (one all-in energy
rate plus a daily charge made of network capacity, service and administration, generation
capacity). Eskom publishes ex-VAT and incl-VAT columns; we take ex-VAT and let the 15% VAT be added,
after checking the two columns agree. Homeflex (seasonal, weekday time of use) and Homepower Bulk
are skipped and listed. Eskom direct customers only; municipal tariffs are out of scope.
Standard library only: the PDF text is read from its Flate streams.

The booklet is yearly and its address and start date change with it, so URL and EFFECTIVE_FROM
below are edited by hand each April. This source is not in the schedule (see sources/).
"""
from __future__ import annotations

import re
import zlib
from decimal import Decimal

from scripts.sync.plan import Plan, single
from scripts.sync.sources import Result

SOURCE_ID = "za-eskom-tariff-book"
COUNTRY = "ZA"
URL = "https://www.eskom.co.za/distribution/wp-content/uploads/2026/07/Eskom-Tariff-booklet_Final.pdf"
EFFECTIVE_FROM = "2026-04-01"
NUM = r"R?(\d+[.,]\d+)"


def pdf_text(pdf: bytes) -> str:
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            data = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        for tj, t in re.findall(rb"\[([^\]]*)\]\s*TJ|\(((?:\\.|[^\\)])*)\)\s*Tj", data):
            out.append(t or b"".join(re.findall(rb"\(((?:\\.|[^\\)])*)\)", tj)))
    return " | ".join(s.decode("latin1") for s in out)


def numbers(text: str, label: str, count: int) -> list[Decimal]:
    m = re.search(re.escape(label) + r"\s*\|((?:\s*" + NUM + r"\s*\|?){" + str(count) + "})", text)
    if not m:
        raise ValueError(f"row {label!r} not found in the booklet text")
    return [Decimal(n.replace(",", ".")) for n in re.findall(NUM, m.group(1))]


def excl_incl(pairs: list[Decimal], label: str) -> list[Decimal]:
    """Values come as (excl, incl) pairs; refuse the row if incl is not excl x 1.15."""
    ex = pairs[0::2]
    for e, i in zip(ex, pairs[1::2]):
        if abs(e * Decimal("1.15") - i) > Decimal("0.02"):
            raise ValueError(f"{label}: VAT columns disagree ({e} vs {i})")
    return ex


def plan(pid: str, name: str, base_cents: Decimal, daily: Decimal) -> Plan:
    bands, areas = single(("Energy", base_cents / 100), [], daily)
    return Plan(country=COUNTRY, provider_id="eskom", provider="Eskom", id=pid, name=name,
                effective_from=EFFECTIVE_FROM, source_url=URL, prices_include_tax=False,
                bands=bands, areas=areas)


def plans(text: str) -> list[Plan]:
    out = []
    for tier in ("20A", "60A"):
        (energy,) = excl_incl(numbers(text, f"Homelight {tier}", 2), f"Homelight {tier}")
        out.append(plan(f"eskom-homelight-{tier.lower()}", f"Homelight {tier}", energy, Decimal(0)))
    for n in range(1, 5):
        # energy, ancillary, network demand (c/kWh), then network capacity, service/admin, generation (R/day)
        v = excl_incl(numbers(text, f"Homepower {n}", 12), f"Homepower {n}")
        out.append(plan(f"eskom-homepower-{n}", f"Homepower {n}", v[0] + v[1] + v[2],
                        v[3] + v[4] + v[5]))
    return out


def read(fetch, today: str, stored: dict) -> Result:
    return Result(
        plans=plans(pdf_text(fetch.get(URL))),
        skipped=["Homeflex: seasonal and time-of-use with weekday/weekend and public-holiday rules",
                 "Homepower Bulk: sectional-title bulk supply, not a household tariff",
                 "Gen-offset: a net-billing credit by time-of-use period on Homeflex and Ruraflex rates, so it "
                 "goes with the skipped Homeflex tariff",
                 "Municipal tariffs: about 160 municipal PDFs, not attempted"],
        notes=["Homepower: energy + ancillary + network demand as the unit rate; network capacity + "
               "service/admin + generation capacity as the daily charge"])
