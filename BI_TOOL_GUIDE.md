# Building the Power BI / Tableau version

The Streamlit app is the primary deliverable. This guide gets you a **second,
equally real artifact** — a Power BI or Tableau Public workbook built on the
same real Square data — which is worth doing because a lot of Data Analyst
job postings name one of these tools specifically, and a working dashboard in
it is a much stronger CV line than "familiar with."

Power BI Desktop doesn't run on macOS, so pick based on your machine:

- **On Windows:** use Power BI Desktop (free).
- **On Mac:** use [Tableau Public](https://public.tableau.com/) (free) — steps
  below are written for Tableau but the same model/measures carry over almost
  1:1 to Power BI if you later get access to Windows.

## 1. Data model

Files are in `data/bi_export/` (generate with `python src/export_bi.py` after
`python src/load_square_data.py` — both read from the real, anonymised Square
exports, never the raw files):

| File | Grain | Role |
|---|---|---|
| `fact_transactions.csv` | one row per POS transaction | main fact table |
| `dim_item_sales.csv` | one row per menu item, period totals | menu dimension + measures |
| `dim_date.csv` | one row per calendar date in range | date dimension |

`dim_item_sales` is period-level (Square's Item Sales report doesn't break
items out per transaction), so it doesn't join to `fact_transactions` on a
shared key — treat it as its own table for the Menu Performance page, and
`fact_transactions` for everything else (Peak Hours, Revenue by Day-part).
Relate `fact_transactions.date` → `dim_date.date` (many-to-one).

## 2. Calculated fields / measures to add

| Name | Formula | Purpose |
|---|---|---|
| Revenue | `SUM([gross_sales])` on `fact_transactions` | base measure |
| Avg Transaction Value | `SUM([gross_sales]) / COUNTD([order_id])` | KPI (no covers field in the export, so this is per-transaction, not per-cover) |
| Estimated Margin % | `[est_margin] / [avg_unit_price]` on `dim_item_sales` | menu engineering — labelled "estimated", not real COGS |

## 3. Sheets/pages to build (mirrors the Streamlit tabs)

1. **Peak Trading Hours** — a heatmap: rows = day of week, columns = hour
   (both from `fact_transactions`), color = `COUNTD([order_id])`. Use a
   single-hue sequential palette (light → dark blue), not a rainbow. Add a
   bar of busiest tables (`table_number`, top 10 by transaction count).
2. **Revenue by Day-part** — a donut of revenue share by `day_part`, a
   stacked bar of revenue by day-of-week colored by `day_part`, and a daily
   revenue line (only 15 days currently — don't overreach into "seasonality"
   claims until more exports are added).
3. **Menu Performance** — from `dim_item_sales`: a horizontal bar of top
   items by `units_sold`, plus a scatter of `units_sold` (x) vs `Estimated
   Margin %` (y) sized by `revenue`, colored by `category_group` — the
   "menu engineering" quadrant chart (Stars / Plowhorses / Puzzles / Dogs).
   Label the margin axis "estimated" on the chart itself.
4. **Filters** — date range, day-of-week, and day-part as dashboard-level
   filters on the transaction-driven pages.

Labour/staffing isn't included here — there's no real Timecards export yet
(see the main README). Skip that page until one exists; the same model in
`src/generate_data.py` would translate directly once it does.

## 4. Color

Keep it consistent with the Streamlit build: categorical colors are assigned
**by entity identity, not by rank** (e.g. Dinner is always the same color
across every chart) — see `src/theme.py` for the exact hex values used. Avoid
a rainbow/default palette; pick 3–4 colors and reuse them everywhere.

## 5. Publish

- **Tableau Public:** File → Save to Tableau Public. You get a shareable URL
  — link it directly from your CV/portfolio.
- **Power BI:** File → Publish to Power BI Service (needs a free account), or
  export a `.pbix` and note in your portfolio that it's available on request
  (some employers won't have a way to open a live published report without a
  license).
