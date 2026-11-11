# selectra-ie

- **Covers:** Irish household electricity plans by supplier (unit rates, standing charge) as
  listed on https://selectra.ie/energy/providers/<supplier>.
- **Pages read:** the provider directory (`/energy/providers`) and each supplier page.
- **Prices as shown:** unit rates in c/kWh excluding VAT, standing charge in euro a year including
  9% VAT, both after discounts that apply to new customers. The definitions store everything
  including VAT.
- **Terms:** the site's legal notice (https://selectra.ie/legal) says its content belongs to
  Selectra SAS and that reproduction requires written consent. It does not mention automated
  access.
- **How it is read:** `scripts/sync/sources/selectra_ie.py`, with a delay between requests. Each
  tariff file links the page it came from. The page shows no start date, so a changed price is
  dated the day the sync saw it.
- **Frequency:** weekly at most.
- **Known gaps:** plans with a Peak rate are skipped. NightSaver night hours are assumed to be
  23:00-08:00 and need checking against the supplier's sheet. No tariff from this source has a
  `checks` entry yet.
