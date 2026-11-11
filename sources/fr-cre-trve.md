# fr-cre-trve

- Publisher: CRE (Commission de régulation de l'énergie), on data.gouv.fr: "Historique des tarifs réglementés de
  vente d'électricité pour les consommateurs résidentiels" (licence field says "notspecified").
- Files: https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Base.csv (also Option_HPHC.csv, Option_Tempo.csv)
- Format: CSV, `;` separated, decimal comma, dates dd/mm/yyyy, empty DATE_FIN = current. HT and TTC columns.
- Fixed part is euros per year; variable is euros per kWh. Frequency: changes on 1 February and 1 August.
- Terms: not reviewed.
- How it is read: `scripts/sync/sources/fr_cre.py`.
