# Restaurant Operations Analytics Dashboard

**Live app:** https://restaurant-ops-dashboard-n9kgly3fxs25f5n57sceve.streamlit.app/

An interactive dashboard analysing restaurant trading patterns — peak hours,
revenue by day-part, and menu performance — built on **real, anonymised
Square POS exports** from an independent restaurant where I manage
day-to-day operations. The business's name is intentionally left out of this
project; everything shown here is real trading data with only the name
withheld.

## Data

Two Square Dashboard exports cover 17–31 Jul 2026 (15 trading days):

- **Item Sales report** — units sold, revenue, and category per menu item.
- **Transactions export** — 1,256 payments with timestamp, amount, table,
  and channel.

`src/load_square_data.py` reads both, strips everything that isn't needed
for operations analytics (staff names, staff IDs, customer names/IDs, card
brand + PAN suffix, device names/IDs, and every transaction/payment/deposit
ID), and writes clean, anonymised CSVs to `data/real/`. Only that cleaned
output is tracked in this repo — the raw exports live in `data/raw/`, which
is gitignored, so nothing identifying ever gets published alongside the
dashboard.

**What the real data can't tell you:** Square's export has no covers/party-
size field, so the dashboard reports per-transaction metrics (transaction
count, avg transaction value) rather than per-cover ones — an honest
adaptation to what POS data actually contains, not an oversight. There's
also no COGS, so the menu "margin" used in the Stars/Plowhorses/Puzzles/Dogs
chart is an **estimated** figure from category-level cost-of-sales
benchmarks, clearly labelled as such in the app.

**Staffing/labour** isn't wired to real data — there's no Timecards export
available yet. That tab runs on a modelled synthetic year
(`src/generate_data.py`) instead, with an explicit on-screen warning that
it's illustrative. It demonstrates a real finding worth watching for once
labour data is connected: a rota scheduled off trailing averages structurally
lags fast demand ramps (e.g. a festive December) and overshoots once demand
drops. Swapping in a real Timecards export doesn't change the logic, just the
inputs.

**Window length:** only 15 real trading days are in yet, so the dashboard
can't speak to seasonality — the daily revenue trend tab says as much rather
than implying more than the data supports. More Square exports (a full
quarter or year) would extend this directly; the loader doesn't need to
change, just the files in `data/raw/`.

## Why this project

A lot of Data Analyst job postings name a specific BI tool (Power BI or
Tableau) that doesn't show up elsewhere on my CV. This project is two things
built on one real dataset: a Python/Streamlit dashboard (fast to build, fully
interactive, easy to deploy and link), and a guide + star-schema export to
reproduce it in Power BI or Tableau (see
[`BI_TOOL_GUIDE.md`](BI_TOOL_GUIDE.md)). Both are grounded in the same
interview story: I run this floor, so I know exactly what a Tuesday lunch
shift looks like versus a Saturday dinner — this dashboard is that knowledge
turned into a measurable, filterable tool.

## What's in the dashboard

- **Peak Trading Hours** — an hour × day-of-week heatmap of transaction
  volume, plus totals by hour and by busiest table, from the real 15-day
  window.
- **Revenue by Day-part** — share of revenue by Breakfast/Lunch/Afternoon/
  Dinner, split by day of week, and a daily revenue trend.
- **Menu Performance** — top sellers by units (from the real Item Sales
  report), and a menu-engineering quadrant (popularity vs. estimated margin)
  splitting items into Stars, Plowhorses, Puzzles, and Dogs.
- **Staffing (illustrative)** — clearly flagged as a modelled placeholder
  until real Timecards data is available; shows the staffing-lag analysis
  method on a synthetic year.
- Sidebar filters (date range, day of week, day-part) apply across the real-
  data tabs.

## Tech stack

Python · Pandas · NumPy · Streamlit · Plotly

Chart colors follow a fixed, colorblind-validated categorical palette
(`src/theme.py`) — each entity (a day-part, a menu category) keeps the same
color everywhere rather than colors being reassigned per chart.

## Running it

```bash
cd restaurant-ops-dashboard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Put your own Square exports in data/raw/, named like:
#   item-sales-summary-<start>-<end>.csv
#   transactions-<start>-<end>.csv
python src/load_square_data.py    # cleans + anonymises -> data/real/
python src/generate_data.py       # (optional) regenerates the synthetic staffing model
streamlit run src/app.py
```

Opens at `http://localhost:8501`.

## Project structure

```
restaurant-ops-dashboard/
├── src/
│   ├── load_square_data.py  # real Square export loader + anonymiser
│   ├── generate_data.py     # synthetic staffing/demand model (illustrative tab only)
│   ├── export_bi.py         # star-schema export for Power BI / Tableau
│   ├── theme.py             # shared chart color palette
│   └── app.py                # Streamlit dashboard
├── data/
│   ├── raw/                 # original Square exports — gitignored, local only
│   ├── real/                # cleaned, anonymised real data (tracked)
│   ├── synthetic/           # modelled year, used only by the Staffing tab
│   └── bi_export/           # real-data star schema for Power BI / Tableau
├── BI_TOOL_GUIDE.md          # how to rebuild this in Power BI / Tableau
└── requirements.txt
```

## Methodology notes (for the interview)

- **Anonymisation** (`src/load_square_data.py`) — drops every PII/identifier
  column from the Square exports at load time: staff name/ID, customer
  name/ID/reference, card brand, PAN suffix, device name/nickname, and all
  transaction/payment/deposit IDs. Only operationally relevant fields
  (timestamp, amounts, table number, item, category) survive into `data/real/`.
  A few menu items/categories are named after the restaurant itself (e.g. a
  signature dish) — those are rewritten to a generic "Signature" at the same
  load step, so the business's real name never appears anywhere in this repo.
- **Day-parts** — Breakfast (8–11), Lunch (11–15), Afternoon (15–17), Dinner
  (17–23) — set from the actual hourly transaction distribution in the real
  data, not assumed.
- **Category grouping** — Square's 47 raw menu categories are mapped to
  Food / Drink / Dessert for consistent chart coloring, with the original
  category kept as a filterable detail field.
- **Estimated margin** — Food 30% / Drink 22% / Dessert 24% cost-of-sales,
  typical UK hospitality benchmarks, used only because Square doesn't export
  COGS. Always labelled "estimated" in the app, never presented as actual.
- **Synthetic staffing model** — scheduled off a trailing 4-occurrence
  average for each (weekday, day-part), which is what produces the
  understaffed-ramp / overstaffed-drop-off pattern the tab highlights. See
  `src/generate_data.py` for the full demand + staffing model.
