# electric-ireland

- **Covers:** Electric Ireland's household electricity plans for new customers, as listed on
  https://www.electricireland.ie/switch/new-customer/price-plans?priceType=E. A supplier page.
- **Pages read:** the price plans page, for each plan's name, bands, band hours and unit rates.
  The page shows no standing charge, so that is read from the same plan's row on
  https://selectra.ie/energy/providers/electric-ireland (see `selectra-ie.md`).
- **Prices as shown:** unit rates in c/kWh for each band with its hours, and a discount on unit
  rates beside them. The page does not say whether a rate includes VAT or the discount. The
  comparison page lists the same plans "excl. VAT, incl. discounts", and its figures match the
  supplier's once 9% VAT is added, so the supplier's rates are taken as including both. The
  standing charge is in euro a year including 9% VAT and is stored per day, divided by 365.
- **Terms:** not read. The page links its residential pricing terms in the footer.
- **How it is read:** by hand. There is no sync module, so a price change is not picked up until
  someone reads the page again.
- **Frequency:** when a plan is reported wrong or missing.
- **Known gaps:** the page states no start date, so a revision is dated the day it was read. It
  shows no PSO levy. Only the Night Boost plan is held from this page. The plan that gives free
  weekend hours and the plans with a Peak rate are not held. No tariff from this source has a
  `checks` entry yet.
