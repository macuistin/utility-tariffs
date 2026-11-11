# za-eskom-tariff-book

- Publisher: Eskom Distribution. "Tariffs and Charges Booklet 2026/2027" (PDF, about 4 MB), approved by NERSA
  (MYPD6), effective 1 April 2026 for Eskom direct customers, 1 July 2026 for municipalities.
- URL: https://www.eskom.co.za/distribution/wp-content/uploads/2026/07/Eskom-Tariff-booklet_Final.pdf
  (found from https://www.eskom.co.za/distribution/tariffs-and-charges/).
- Format: PDF with embedded text. The sync uses the standard library only, so it reads
  the Flate streams with the standard library and takes the table rows by label.
- Prices: c/kWh and R/day, shown excluding and including 15% VAT; the script checks incl = excl x 1.15.
- Terms: not reviewed.
- How it is read: `scripts/sync/sources/za_eskom.py`. The booklet link and start date are constants in
  that file. Edit both each April when the new booklet is published.
- Frequency: yearly (April), mid-year corrections possible.
- Not covered: Homeflex (seasonal TOU, weekday split), Homepower Bulk (sectional title developments),
  municipal tariffs (about 160 municipalities, each its own PDF; NERSA approves them annually).
