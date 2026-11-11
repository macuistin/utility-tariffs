"""The one definition of the stored format: validate a tariff file and a country block, and
compute the checksum. Standard library only. docs/format.md describes the format in words.

The sync scripts, the index build, the check and a client all call these functions, so nothing
can be written, indexed or priced that this module refuses.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
HOURS = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
REF = re.compile(r"^\$(country|input)\.([a-z][a-z0-9_]*)$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")
EXPORT_REF = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*/[a-z0-9]+(-[a-z0-9]+)*$")

TARIFF_REQUIRED = {"schema", "name", "provider", "effective_from", "source", "bands", "areas"}
TARIFF_OPTIONAL = {"effective_to", "service", "customer_class", "timezone", "direction", "export",
                   "prices_include_tax", "bill", "inputs", "checks"}
COUNTRY_RESERVED = {"schema", "country", "currency", "timezone", "vat_percent", "bill", "inputs",
                    "availability", "reason", "providers"}
BAND_FIELDS = {"name", "hours", "days", "months", "holidays"}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# How much of a country's rates the repository holds. A country with tariff files is available or
# partial (partial says why in `reason`). A country with none is unavailable, with the reason.
AVAILABILITY = ("available", "partial", "unavailable")
NODE_FIELDS = {
    "energy_by_band": {"kind", "round_bands", "round"},
    "export_credit": {"kind", "round"},
    "per_day": {"kind", "amount", "round"},
    "per_period": {"kind", "amount", "share", "round"},
    "adjust": {"kind", "name", "percent", "of", "round"},
    "tax": {"kind", "name", "percent", "mode", "of", "round"},
    "sum": {"kind", "of", "round"},
}
MAX_DEPTH = 8


def canonical(doc: object) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def checksum(doc: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(doc)).hexdigest()


def stamp_ok(value: object) -> bool:
    """A date, or a UTC date and time such as 2026-11-10T08:15:00Z."""
    if not isinstance(value, str) or not STAMP.match(value):
        return False
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def _price(value: object, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not DECIMAL.match(value):
        errors.append(f"{field}: must be a decimal string")


def _number(value: object, field: str, errors: list[str]) -> None:
    """A decimal string, or a $country.name / $input.name reference."""
    if isinstance(value, str) and REF.match(value):
        return
    _price(value, field, errors)


def _date(value: object, field: str, errors: list[str]) -> None:
    try:
        date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{field}: not an ISO date")


def _node(node: object, path: str, depth: int, errors: list[str]) -> None:
    if depth > MAX_DEPTH:
        errors.append(f"{path}: tree too deep")
        return
    if not isinstance(node, dict) or node.get("kind") not in NODE_FIELDS:
        errors.append(f"{path}: unknown node kind")
        return
    kind = node["kind"]
    for key in node:
        if key not in NODE_FIELDS[kind]:
            errors.append(f"{path}.{key}: not allowed on {kind}")
    for key in ("amount", "percent"):
        if key in node:
            _number(node[key], f"{path}.{key}", errors)
    if kind == "tax" and node.get("mode") not in ("added", "included"):
        errors.append(f"{path}.mode: must be added or included")
    if kind in ("adjust", "tax"):
        _node(node.get("of"), f"{path}.of", depth + 1, errors)
    if kind == "sum":
        children = node.get("of")
        if not isinstance(children, dict) or not children:
            errors.append(f"{path}.of: sum needs one or more named children")
        else:
            for name, child in children.items():
                _node(child, f"{path}.of.{name}", depth + 1, errors)


def _band_window(band: dict, where: str, errors: list[str]) -> None:
    """When a band after the first applies: hours every time, and optionally days and months."""
    hours = str(band.get("hours"))
    if not HOURS.match(hours) or hours[:5] == hours[6:]:
        errors.append(f"{where}.hours: must be HH:MM-HH:MM with different ends")
    days = band.get("days", ["mon"])
    if not isinstance(days, list) or not days or len(set(days)) != len(days) \
            or any(d not in WEEKDAYS for d in days):
        errors.append(f"{where}.days: distinct values from {', '.join(WEEKDAYS)}")
    months = band.get("months", [1])
    if not isinstance(months, list) or not months or len(set(months)) != len(months) \
            or any(type(m) is not int or not 1 <= m <= 12 for m in months):
        errors.append(f"{where}.months: distinct month numbers from 1 to 12")
    if band.get("holidays", "weekend") != "weekend":
        errors.append(f"{where}.holidays: write it only as weekend")


def _source(source: object, errors: list[str]) -> None:
    if not isinstance(source, dict) or set(source) != {"id", "url"} \
            or not SLUG.match(str(source["id"])) or not str(source["url"]).startswith("https://"):
        errors.append("source: needs id (the name of a file in sources/) and an https url")


def _timezone(value: object, field: str, errors: list[str]) -> None:
    try:
        ZoneInfo(str(value))
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(f"{field}: not an IANA time zone")


def _bill(bill: object, errors: list[str]) -> None:
    if not isinstance(bill, dict) or "total" not in bill or set(bill) - {"period", "total"}:
        errors.append("bill: needs total and optional period")
        return
    period = bill.get("period")
    if period is not None:
        if not isinstance(period, dict) or period.get("rule") != "monthly":
            errors.append("bill.period: rule must be monthly")
        else:
            start = period.get("start_day")
            if not (isinstance(start, int) or (isinstance(start, str) and REF.match(start))):
                errors.append("bill.period.start_day: must be a day number or a reference")
    _node(bill["total"], "bill.total", 0, errors)


def _inputs(inputs: object, errors: list[str]) -> None:
    if not isinstance(inputs, dict):
        errors.append("inputs: must be an object")
        return
    for name, spec in inputs.items():
        if not NAME.match(name) or not isinstance(spec, dict) or set(spec) != {
                "type", "min", "max", "default"} or spec.get("type") != "integer":
            errors.append(f"inputs.{name}: needs type integer, min, max and default")


def validate_tariff(doc: object) -> list[str]:
    """Refusals for a tariff file, each naming the field. Empty means valid."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["document: must be an object"]
    for key in TARIFF_REQUIRED - doc.keys():
        errors.append(f"{key}: missing")
    for key in doc.keys() - TARIFF_REQUIRED - TARIFF_OPTIONAL:
        errors.append(f"{key}: not allowed")
    if errors:
        return sorted(errors)
    if doc["schema"] != 1:
        errors.append("schema: must be 1")
    for key in ("name", "provider"):
        if not doc[key] or not isinstance(doc[key], str):
            errors.append(f"{key}: must be text")
    _source(doc["source"], errors)
    if "service" in doc:
        errors.append("service: electricity is the default and no other service is priced yet")
    if "customer_class" in doc and doc["customer_class"] != "commercial":
        errors.append("customer_class: write it only when commercial")
    if "timezone" in doc:
        _timezone(doc["timezone"], "timezone", errors)
    _date(doc["effective_from"], "effective_from", errors)
    if doc.get("effective_to") is not None:
        _date(doc["effective_to"], "effective_to", errors)
        if str(doc["effective_to"]) <= str(doc["effective_from"]):
            errors.append("effective_to: must be after effective_from")
    if doc.get("direction", "import") not in ("import", "export"):
        errors.append("direction: must be export when present")
    if doc.get("prices_include_tax", False) is not False:
        errors.append("prices_include_tax: write it only when false")
    bands = doc["bands"]
    names: list[str] = []
    if not isinstance(bands, list) or not bands:
        errors.append("bands: needs at least one band")
    else:
        for i, band in enumerate(bands):
            if not isinstance(band, dict) or not band.get("name") or set(band) - BAND_FIELDS:
                errors.append(f"bands[{i}]: needs name and, after the first, hours")
                continue
            names.append(band["name"])
            if i == 0 and len(band) > 1:
                errors.append("bands[0]: the first band is the base and has only a name")
            if i > 0:
                _band_window(band, f"bands[{i}]", errors)
        if len(set(names)) != len(names):
            errors.append("bands: names must be unique")
    is_export = doc.get("direction") == "export"
    areas = doc["areas"]
    if not isinstance(areas, dict) or not areas:
        errors.append("areas: needs at least one area")
    else:
        for key, row in areas.items():
            where = f"areas.{key}"
            if not SLUG.match(str(key)) or not isinstance(row, dict):
                errors.append(f"{where}: key must be a slug and the row an object")
                continue
            if set(row) - {"label", "region", "standing", "rates"}:
                errors.append(f"{where}: only label, region, standing and rates are allowed")
            if key != "all" and not row.get("label"):
                errors.append(f"{where}.label: missing")
            if is_export and "standing" in row:
                errors.append(f"{where}.standing: an export has no standing charge")
            if not is_export:
                _price(row.get("standing"), f"{where}.standing", errors)
            rates = row.get("rates")
            if not isinstance(rates, dict) or set(rates) != set(names):
                errors.append(f"{where}.rates: must price exactly the bands {names}")
            else:
                for band, price in rates.items():
                    _price(price, f"{where}.rates.{band}", errors)
    if "bill" in doc:
        _bill(doc["bill"], errors)
        if is_export:
            errors.append("bill: an export file has no bill of its own")
    if "inputs" in doc:
        _inputs(doc["inputs"], errors)
    if "checks" in doc and not isinstance(doc["checks"], dict):
        errors.append("checks: must be an object")
    if "export" in doc:
        if is_export or not EXPORT_REF.match(str(doc["export"])):
            errors.append("export: an import file may name one export file as provider-id/tariff-id")
    return sorted(errors)


def validate_country(block: object) -> list[str]:
    """Refusals for the hand-maintained top block of a country index."""
    errors: list[str] = []
    if not isinstance(block, dict):
        return ["country block: must be an object"]
    for key in ("country", "currency", "timezone", "vat_percent", "bill"):
        if key not in block:
            errors.append(f"{key}: missing")
    if errors:
        return errors
    if not re.match(r"^[A-Z]{2}$", str(block["country"])):
        errors.append("country: must be an ISO 3166-1 alpha-2 code")
    if not re.match(r"^[A-Z]{3}$", str(block["currency"])):
        errors.append("currency: must be an ISO 4217 code")
    _timezone(block["timezone"], "timezone", errors)
    vat = block["vat_percent"]
    if isinstance(vat, list):
        for i, entry in enumerate(vat):
            _price(entry.get("percent") if isinstance(entry, dict) else None,
                   f"vat_percent[{i}].percent", errors)
            for key in ("effective_from", "effective_to"):
                if isinstance(entry, dict) and key in entry:
                    _date(entry[key], f"vat_percent[{i}].{key}", errors)
    else:
        _price(vat, "vat_percent", errors)
    for key in block.keys() - COUNTRY_RESERVED:
        _price(block[key], key, errors)
    _bill(block["bill"], errors)
    if "inputs" in block:
        _inputs(block["inputs"], errors)
    availability = block.get("availability", "available")
    if availability not in ("available", "partial"):
        errors.append("availability: a country with tariff files is available or partial")
    if availability == "partial" and not (isinstance(block.get("reason"), str) and block["reason"].strip()):
        errors.append("reason: a partial country says what is missing")
    return errors


def validate_unavailable(doc: object) -> list[str]:
    """Refusals for tariffs/unavailable.json: countries we looked at and cannot hold rates for."""
    errors: list[str] = []
    if not isinstance(doc, dict) or set(doc) != {"schema", "countries"} or doc.get("schema") != 1:
        return ["unavailable: needs schema 1 and countries"]
    for code, entry in doc["countries"].items():
        where = f"unavailable.{code}"
        if not re.match(r"^[A-Z]{2}$", str(code)):
            errors.append(f"{where}: key must be an ISO 3166-1 alpha-2 code")
        if not isinstance(entry, dict) or set(entry) != {"reason", "checked"}:
            errors.append(f"{where}: needs reason and checked")
            continue
        if not (isinstance(entry["reason"], str) and entry["reason"].strip()):
            errors.append(f"{where}.reason: say why")
        if not stamp_ok(entry["checked"]):
            errors.append(f"{where}.checked: not a date")
    return errors


def vat_on(block: dict, on: str) -> str | None:
    """The VAT rate in force on an ISO date, or None when no entry covers it.

    Later entries win, so an undated first entry is the fallback and a dated entry after it is a
    temporary change that ends and hands back to the fallback."""
    vat = block["vat_percent"]
    if not isinstance(vat, list):
        return vat
    found = None
    for entry in vat:
        if entry.get("effective_from", "0000-01-01") <= on < entry.get("effective_to", "9999-12-31"):
            found = entry["percent"]
    return found
