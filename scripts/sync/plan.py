"""What a source hands over, and the one function that turns it into a tariff file.

Every source builds `Plan` objects and nothing else. `to_tariff` is the only code that writes the
stored shape, and it validates what it built, so no source can store a file the check would refuse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from lib.tariffstore.schema import validate_tariff

SIX = Decimal("0.000001")


def price(value: object) -> str:
    """A price as stored: a plain decimal string, at most six places, no trailing zeros."""
    text = format(Decimal(str(value)).quantize(SIX, ROUND_HALF_UP), "f").rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class Area:
    """One row of prices. `standing` is per day, and None for an export."""

    rates: dict[str, object]
    standing: object | None = None
    label: str | None = None
    region: str | None = None


@dataclass(frozen=True)
class Plan:
    country: str
    provider_id: str
    provider: str
    id: str
    name: str
    effective_from: str
    source_url: str
    bands: list[dict]  # the first is the base {"name"}; later ones add "hours" and may add days, months
    areas: dict[str, Area]
    effective_to: str | None = None
    direction: str = "import"
    prices_include_tax: bool = True
    timezone: str | None = None  # only when it differs from the country's
    # True when the source states the date the prices started. False when the date is only when we
    # looked, so a changed price is dated by the day of the run.
    dated: bool = True
    extra: dict = field(default_factory=dict)  # export, bill, inputs, checks, customer_class

    @property
    def key(self) -> tuple[str, str, str]:
        return self.country.lower(), self.provider_id, self.id


def unique(names: list[str]) -> list[str]:
    """Band names must be unique. A source that names two windows alike gets a number on the later one."""
    seen: dict[str, int] = {}
    out = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name} {seen[name]}")
    return out


def single(base: tuple[str, object], zones: list[tuple[str, str, object]], standing: object | None,
           ) -> tuple[list[dict], dict[str, Area]]:
    """Bands and the one area `all` for a plan with one price everywhere.

    `base` is (name, price) and each zone is (name, "HH:MM-HH:MM", price)."""
    names = unique([base[0]] + [z[0] for z in zones])
    bands = [{"name": names[0]}] + [{"name": n, "hours": z[1]} for n, z in zip(names[1:], zones)]
    rates = dict(zip(names, [base[1]] + [z[2] for z in zones]))
    return bands, {"all": Area(rates=rates, standing=standing)}


def to_tariff(plan: Plan, source_id: str) -> dict:
    """The tariff file for a plan. Raises ValueError naming the fields the format refuses."""
    areas = {}
    for key, area in plan.areas.items():
        row: dict = {"rates": {band: price(value) for band, value in area.rates.items()}}
        if area.standing is not None:
            row["standing"] = price(area.standing)
        if area.label:
            row["label"] = area.label
        if area.region:
            row["region"] = area.region
        areas[key] = row
    tariff = {"schema": 1, "name": plan.name, "provider": plan.provider,
              "effective_from": plan.effective_from,
              "source": {"id": source_id, "url": plan.source_url},
              "bands": plan.bands, "areas": areas, **plan.extra}
    if plan.effective_to:
        tariff["effective_to"] = plan.effective_to
    if plan.direction == "export":
        tariff["direction"] = "export"
    if not plan.prices_include_tax:
        tariff["prices_include_tax"] = False
    if plan.timezone:
        tariff["timezone"] = plan.timezone
    errors = validate_tariff(tariff)
    if errors:
        raise ValueError(f"{plan.id}: " + "; ".join(errors))
    return tariff
