"""Build the full definition the bill engine (lib/tariff) reads, from a tariff file and its
country block. Standard library only.

The tariff file has bands and one row of rates per area. The country block has the currency, the
time zone, the VAT rate and the standard bill. `$country.name` takes a value from the country block
and `$input.name` becomes a reference to a customer input. Nothing here changes a price.
"""
from __future__ import annotations

import copy
import json
import re

from .schema import REF, vat_on


class CompileError(ValueError):
    pass


def _resolve(node, block: dict, on: str, path: str = ""):
    """Copy of a bill tree with `$country.x` replaced by its value."""
    if isinstance(node, dict):
        return {k: _resolve(v, block, on, f"{path}.{k}") for k, v in node.items()}
    if isinstance(node, str):
        match = REF.match(node)
        if match and match.group(1) == "country":
            name = match.group(2)
            value = vat_on(block, on) if name == "vat_percent" else block.get(name)
            if value is None or isinstance(value, (dict, list)):
                raise CompileError(f"{path}: country has no value for {name} on {on}")
            return value
        if match:
            raise CompileError(f"{path}: $input is only allowed as the bill start day")
    return node


def _nodes(node: dict):
    yield node
    child = node.get("of")
    if isinstance(child, dict):
        if "kind" in child:
            yield from _nodes(child)
        else:
            for sub in child.values():
                yield from _nodes(sub)


def _add_export_credit(total: dict) -> None:
    """Add an export_credit line to the outermost sum, so a paired export price is paid."""
    node = total
    while node["kind"] != "sum":
        if "of" not in node or "kind" not in node["of"]:
            raise CompileError("no sum in the bill to add an export credit to")
        node = node["of"]
    node["of"].setdefault("export", {"kind": "export_credit"})


def _zone(band: dict, priority: int, price: str) -> dict:
    zone = {"name": band["name"], "priority": priority, "hours": band["hours"], "price": price}
    zone.update({k: band[k] for k in ("days", "months", "holidays") if k in band})
    return zone


def _prices(bands: list, rates: dict) -> dict:
    """The engine's price table: the first band is the base, each later band a zone that wins
    over the ones before it."""
    base = {"name": bands[0]["name"], "price": rates[bands[0]["name"]]}
    zones = [_zone(band, i, rates[band["name"]]) for i, band in enumerate(bands[1:], 1)]
    return {"base": base, "zones": zones}


def export_prices(export_file: dict, area: str = "all") -> dict:
    """The export prices for `area`, flat or by time of day. An export file with no row for the
    area pays its first row, which is how a single national export price is written."""
    areas = export_file["areas"]
    row = areas.get(area) or next(iter(areas.values()))
    prices = _prices(export_file["bands"], row["rates"])
    return prices if prices["zones"] else {"base": prices["base"]}


def compile_area(tariff: dict, area: str, *, block: dict, meta: dict, on: str,
                 export_file: dict | None = None) -> dict:
    """The engine's definition for one area of a tariff, priced on the ISO date `on`.

    `meta` is what the path says: country, provider id, tariff id and revision number."""
    if area not in tariff["areas"]:
        raise CompileError(f"no area {area}; this tariff has {', '.join(tariff['areas'])}")
    row = tariff["areas"][area]
    bill = copy.deepcopy(tariff.get("bill") or block["bill"])
    period = bill.get("period") or copy.deepcopy(block["bill"]["period"])
    inputs = {**copy.deepcopy(block.get("inputs", {})), **tariff.get("inputs", {})}
    start = period["start_day"]
    if isinstance(start, str):
        match = REF.match(start)
        if not match or match.group(1) != "input" or match.group(2) not in inputs:
            raise CompileError(f"bill.period.start_day: {start} is not a declared input")
        period["start_day"] = {"input": match.group(2)}
    total = _resolve(bill["total"], block, on)
    for node in _nodes(total):
        if node.get("kind") == "per_day" and node.get("amount") is None:
            node["amount"] = row["standing"]
    if export_file is not None:
        _add_export_credit(total)
    export = {"base": {"name": "Export", "price": "0"}}
    if export_file is not None:
        export = export_prices(export_file, area)
    revision = int(meta["revision"])
    return {
        "schema": 1,
        "id": meta["tariff"] if area == "all" else f"{meta['tariff']}-{area}",
        "revision": revision, "supersedes": revision - 1 or None,
        "name": tariff["name"] if area == "all" else f"{tariff['name']} ({row['label']})",
        "service": tariff.get("service", "electricity"),
        "customer_class": tariff.get("customer_class", "residential"),
        "provider": {"id": meta["provider"], "name": tariff["provider"]},
        "country": meta["country"], "region": None,
        "currency": block["currency"], "timezone": tariff.get("timezone", block["timezone"]),
        "effective_from": tariff["effective_from"], "effective_to": meta.get("effective_to"),
        "source_url": tariff["source"]["url"], "last_verified": None,
        "completeness": "complete" if tariff.get("checks") else "partial",
        "inputs": inputs, "import": _prices(tariff["bands"], row["rates"]), "export": export,
        "bill": {"period": period, "total": total}, "checks": tariff.get("checks", {}),
    }


def check_references(tariff: dict, block: dict) -> list[str]:
    """Every `$country.x` the tariff or the country bill uses must exist in the country block."""
    problems = []
    for where, tree in (("tariff", tariff.get("bill")), ("country bill", block["bill"])):
        for ref in re.findall(r"\$country\.([a-z][a-z0-9_]*)", json.dumps(tree or {})):
            if ref not in block:
                problems.append(f"{where}: $country.{ref} is not in the country block")
    return problems
