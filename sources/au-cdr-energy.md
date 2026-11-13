# au-cdr-energy

- Publisher: each Australian electricity retailer (Consumer Data Right product reference data); the AER
  hosts the endpoints at `https://cdr.energymadeeasy.gov.au/<brand>/cds-au/v1/energy/`.
- Spec: ConsumerDataStandardsAustralia/standards on GitHub, `swagger-gen/cds_energy.md`
  (Get Generic Plans `GET /energy/plans`, Get Generic Plan Detail `GET /energy/plans/{planId}`).
- Headers: `x-v` is mandatory (list `1`, detail `3` work); `x-min-v` optional. Query: `page`, `page-size`
  (max 1000), `fuelType`, `type`, `effective`.
- Auth: none for these public endpoints. Format: JSON. Prices: dollars per kWh and per day, exclusive of GST.
- Brand base URIs: not published in one place we could reach (aer.gov.au timed out), so
  `scripts/tools/au_discover.py` (run by hand) probes candidate brand slugs; an unknown slug returns 200 with zero plans.
- Terms: not reviewed.
- How it is read: `scripts/sync/sources/au_cdr.py` fetches the detail of each plan already stored,
  from the link in its file. New plans are chosen by hand with the discover tool.
- Frequency: plans change daily; weekly is plenty for a sample.
- Export: the plan detail lists the retailer's solar feed-in tariff. A flat rate, or rates by time
  of day that cover 24 hours once, is stored as an export tariff `<plan id>-export` that the plan
  names. Rates are per kWh and a year (or no period) and exclude GST, and the credit carries no GST,
  so the country bill adds GST to the charges only. Not read: government scheme rates (old
  installations), rates per day, tiers, windows that miss a day or leave gaps. A plan with such a
  rate is stored without an export and listed as skipped. On 2026-11-13, 47 of 58 plans read were
  paired.
