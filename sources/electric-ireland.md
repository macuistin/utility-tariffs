# electric-ireland

- **Covers:** Electric Ireland's household electricity plans for new customers: unit rates by
  band, band hours, the discount, the standing charge and the PSO levy. Official, the supplier's
  own pages.
- **Pages read:** the price plans page,
  https://www.electricireland.ie/switch/new-customer/price-plans?priceType=E, for the list of
  plans and the hours of each band. Then each plan's "Full pricing information",
  `/switch/new-customer/priceplan-charges?pricePlanId=<id>`, an HTML fragment the page loads.
- **Prices as shown:** the pricing page has one set of tables including VAT and one excluding it.
  The sync reads the set excluding VAT: unit rates in c/kWh before the discount, the discount as
  a percentage for paying by direct debit with online billing, standing charges for urban and
  rural in euro a year, and the PSO levy in euro a year. The page says "Prices valid as of" a
  date, which is the revision's start.
- **How it is stored:** rates without VAT and before the discount, the standing charge per day
  (the year's figure divided by 365) and a bill of the supplier's own shape: the discount on
  energy only, the levy for each month, then VAT on every charge. The pricing page says the bill
  shows the rate before discounts and the discount as one line.
- **Terms:** not read. The page links its residential pricing terms in the footer.
- **How it is read:** `scripts/sync/sources/electric_ireland.py`, one request for the plans page
  and one for each plan.
- **Frequency:** weekly at most.
- **Known gaps:** the plan with free weekend hours is skipped, because the customer picks the
  free day. Night storage heating prices are not held, since they need a second meter. Two plans
  on the page share a name apart from a plus sign, and the second is skipped. Plans for existing
  customers are not on the page. `selectra-ie` still lists two of this supplier's plans from the
  comparison page, with prices after the discount. No tariff from this source has a `checks`
  entry yet.
