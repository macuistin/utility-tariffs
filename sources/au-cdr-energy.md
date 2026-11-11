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
