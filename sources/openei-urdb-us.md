# openei-urdb-us

- **Covers:** United States utility tariffs (residential, commercial, industrial, lighting) with
  tiers, time-of-use schedules, demand charges and fuel adjustments. About 63,000 records. Maintained
  by the National Laboratory of the Rockies (formerly NREL).
- **URLs:** https://openei.org/wiki/Utility_Rate_Database ; bulk files
  https://openei.org/apps/USURDB/download/usurdb.json.gz and `.csv.gz` ; API
  `https://api.openei.org/utility_rates?version=8&api_key=...` (free key, `limit` up to 500, paged with
  `offset`).
- **Terms:** the wiki and apps footers say "Content is available under Creative Commons Zero"
  (apps page adds "unless otherwise noted"). The OpenEI Terms of Use
  (https://openei.org/wiki/OpenEI:General_disclaimer) disclaim any warranty of accuracy. Whether CC0
  covers the rate records themselves, as opposed to site content, is **unverified**. API rate limits
  are not stated.
- **robots.txt (openei.org):** disallows `/apps/USURDB/download/usurdb.csv` (a prefix, so it covers
  `usurdb.csv.gz`), `/services/api/`, `/datasets/files/` and some wiki special pages. The `.json.gz`
  path is not disallowed. robots.txt for `api.openei.org` and `apps.openei.org` is **unread**.
- **Format:** JSON or CSV, gzip. Field names include `energyratestructure`, `energyweekdayschedule`,
  `energyweekendschedule`, `demandratestructure`, `fixedchargefirstmeter` (API) or `fixedmonthlycharge`
  (query form), `sector`, `startdate`, `enddate`, `utility`. Names in bulk files are unverified.
- **Frequency:** about 150 large utilities are checked yearly. Other records may be stale.
- **Fit:** our schema has no tier, demand or fuel-adjustment nodes yet. A sync needs those first.
- **Sync status:** no script. Blocked by the schema, and by the unread `api.openei.org` robots.txt.
