# ofgem-price-cap

- **Covers:** the Great Britain energy price cap: the maximum unit rate and standing charge for
  default tariffs, by region, payment method and meter type, reset every three months.
- **Pages:** https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges
  (national summary table in the page; the regional tables are JavaScript embeds from
  app.everviz.com) and
  https://www.ofgem.gov.uk/energy-regulation/domestic-and-non-domestic/energy-pricing-rules/energy-price-cap/energy-price-cap-default-tariff-levels
  (cap workbooks back to 2019).
- **Terms:** the copyright page (https://www.ofgem.gov.uk/c-ofgem-2026) says material is Crown
  copyright and "You may use Crown copyright information (not including logos) free of charge in any
  format or medium, under the terms of the Open Government Licence", except material identified as
  third-party copyright. Reuse is allowed. Attribution wording is not given on the page; the Open
  Government Licence asks for an acknowledgement of the source and a link to the licence.
- **robots.txt:** disallows only admin and system paths. The pages above are allowed.
- **Format:** HTML, embedded tables, XLSX workbooks. The Annex 9 workbook ("1a Levelised DTC")
  holds annual benchmark values per region, not unit rates and standing charges. The per-unit
  figures are expected in the pre-levelised workbook or the embedded tables, not yet confirmed.
- **VAT:** electricity has no VAT from 1 October 2026 to 31 March 2027, and gas carries 5%. Prices
  are as stated on the page.
- **How it is read:** `scripts/sync/sources/ofgem_gb.py` finds the first Annex 9 workbook link on the
  default tariff levels page and reads the workbook. It refuses a workbook without all 14 regions.
- **Frequency:** quarterly.
