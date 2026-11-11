"""France: the regulated residential tariff (TRVE, 'Tarif Bleu' Base option) from CRE open data.

CRE publishes the history of regulated tariffs as CSV (data.gouv.fr dataset 'Historique des tarifs
réglementés de vente d'électricité pour les consommateurs résidentiels'). Rows with an empty
DATE_FIN are current. One tariff per subscribed power (kVA). Prices are the TTC columns (all taxes
in), and the fixed part is euros per year so it is divided by 365. Heures Creuses and Tempo are
skipped: off-peak hours are set per meter by the network operator and are not in the file, and
Tempo has day colours.
"""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal

from scripts.sync.plan import Plan, single
from scripts.sync.sources import Result

SOURCE_ID = "fr-cre-trve"
COUNTRY = "FR"
URL = "https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Base.csv"
COLUMNS = {"DATE_DEBUT", "DATE_FIN", "P_SOUSCRITE", "PART_FIXE_TTC", "PART_VARIABLE_TTC"}


def num(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def plans(text: str) -> list[Plan]:
    rows = list(csv.DictReader(text.lstrip("\ufeff").splitlines(), delimiter=";"))
    if not rows or not COLUMNS <= set(rows[0]):
        raise ValueError("Option_Base.csv does not have the expected columns")
    out = []
    for row in rows:
        if row["DATE_FIN"]:
            continue
        kva = row["P_SOUSCRITE"]
        bands, areas = single(("Base", num(row["PART_VARIABLE_TTC"])), [],
                              num(row["PART_FIXE_TTC"]) / 365)
        out.append(Plan(country=COUNTRY, provider_id="edf", provider="EDF (tarif réglementé Bleu)",
                        id=f"edf-tarif-bleu-base-{kva}kva", name=f"Tarif Bleu, option Base, {kva} kVA",
                        effective_from=datetime.strptime(row["DATE_DEBUT"], "%d/%m/%Y").date().isoformat(),
                        source_url=URL, bands=bands, areas=areas))
    if not out:
        raise ValueError("Option_Base.csv has no current row (every DATE_FIN is set)")
    return out


def read(fetch, today: str, stored: dict) -> Result:
    return Result(
        plans=plans(fetch.get(URL).decode("utf-8")),
        skipped=["Option_HPHC (off-peak hours are per meter, not in the file)",
                 "Option_Tempo (day colours)"],
        notes=["TTC prices; the real VAT is 5.5% on the subscription and 20% on energy, so the "
               "country's single 20% included tax is an approximation of how the total is built"])
