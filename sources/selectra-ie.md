# selectra-ie

- **Covers:** Irish household electricity plans by supplier (unit rates, standing charge) as
  listed on https://selectra.ie/energy/providers/<supplier>.
- **Pages read:** the provider directory (`/energy/providers`), each supplier page and the
  microgeneration guide.
- **Prices as shown:** unit rates in c/kWh excluding VAT, standing charge in euro a year including
  9% VAT, both after discounts that apply to new customers. The definitions store everything
  including VAT.
- **Export:** the microgeneration guide,
  https://selectra.ie/energy/guides/prices/best-microgeneration-rates-ireland, has one table of
  each supplier's export rate in euro per kWh. Each supplier in the table gets an export tariff
  `<supplier>-microgen-export`, and its plans name it, so a bill pays for exported energy. The
  credit carries no VAT. The guide's "Updated" date is the start of the first revision, and a
  later change is dated by the run. A table that changed shape stops the source. Checked against
  the suppliers' own pages on 2026-11-13: Bord Gáis Energy and Energia 18.5c, Flogas 18.5c
  excluding VAT, Pinergy 18.5c excluding VAT, Yuno Energy 17.16c. SSE Airtricity's own page is
  not readable without a script, so its 19.5c is the guide's figure. Electric Ireland is left to
  its own source. PrepayPower is not paired: its page gives 14c and 15.89c with VAT and does not
  say which is paid (`NOT_PAIRED` in the module, edit when the supplier says). Suppliers not in
  the table (Community Power, Ecopower, Waterpower and others) have no export.
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
