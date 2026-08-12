# Restaurant Operations Analytics Dashboard

**Live app:** https://restaurant-ops-dashboard-n9kgly3fxs25f5n57sceve.streamlit.app/

An interactive dashboard analysing restaurant trading patterns — peak hours,
revenue by day-part, and menu performance — built on **real, anonymised
Square POS exports** from an independent restaurant where I manage
day-to-day operations. The business's name is intentionally left out of this
project; everything shown here is real trading data with only the name
withheld.

The app also works for **any other Square POS user**: switch "Data source"
to "Upload your own" in the sidebar and drop in your own Item Sales /
Transactions / Timecards exports — same charts, same anonymisation, your
numbers. A Timecards upload drives a **real** Staffing tab (labour cost,
hours by day-part/role, labour cost as % of revenue), not the demo's
synthetic model. Nothing uploaded is saved anywhere; it's parsed in memory
for that browser session only, and employee identity is dropped entirely —
shifts are only ever shown in aggregate.

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

- **KPI cards with sparklines** — the top-line Revenue/Transactions/Avg
  transaction value cards each carry a small inline trend of the daily
  values behind the headline number, so the shape of the period is visible
  at a glance, not just the total.
- **Auto-generated insights** — each tab computes a plain-English "Reading
  it" callout from whatever's currently in view (busiest slot, dominant
  day-part, best seller), so it updates live as filters change rather than
  being a static caption.
- **Peak Trading Hours** — transactions by hour, one small bar-chart panel
  per day of week (deliberately not a heatmap — a grid of bars reads more
  precisely than colour intensity), plus totals by hour and busiest tables.
  A "Focus on a day" filter drills into a single day of week.
- **Revenue by Day-part** — share of revenue by Breakfast/Lunch/Afternoon/
  Dinner, split by day of week, and a daily revenue trend. A "Focus on a
  day-part" filter isolates one part across all three charts.
- **Menu Performance** — a **Best sellers / Worst sellers** toggle over
  units sold (the worst-sellers view is the "candidates to cut" list), a
  menu-engineering quadrant (popularity vs. estimated margin — Stars/
  Plowhorses/Puzzles/Dogs) with live-adjustable cost-of-sales sliders, a
  searchable item lookup, and a **clickable performance table** — click any
  row for the same detail card the lookup gives you. (Streamlit's native
  dataframe row-selection, not a Plotly chart click — the two use different
  underlying mechanisms, and only the former proved reliable here.)
- **Staffing** — on the demo dataset, clearly flagged as a modelled
  placeholder (no real Timecards export exists for it yet), showing the
  staffing-lag analysis method on a synthetic year. On an upload with a
  Timecards file, this becomes real: total hours and labour cost, hours by
  day-part/day-of-week/role, and — if a Transactions export was uploaded
  too — labour cost as a % of revenue over time. Works from just hours if
  the export has no pay/rate column, degrading gracefully rather than
  hiding the tab entirely.
- Sidebar filters (date range with quick presets, day of week, day-part)
  apply across every data-driven tab.

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
│   ├── square_parser.py     # shared Square CSV parsing/cleaning/anonymising —
│   │                        # used by both load_square_data.py and app.py uploads
│   ├── load_square_data.py  # demo dataset loader (reads data/raw/, applies
│   │                        # square_parser.py + this project's own name redaction)
│   ├── generate_data.py     # synthetic staffing/demand model (illustrative tab only)
│   ├── export_bi.py         # star-schema export for Power BI / Tableau
│   ├── theme.py             # shared chart color palette
│   └── app.py                # Streamlit dashboard (demo data + upload-your-own)
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
- **Item-name aggregation, Menu Performance** — Square's Item Sales export
  has one row per item *variation* ("Cappuccino / Regular", "Cappuccino /
  Large"), but every chart, the table, and the lookup all key on item name
  alone. Building the click-to-detail feature surfaced this: two rows both
  labelled "Cappuccino" with different numbers, and whichever sorted first
  silently won. Fixed by aggregating to one row per item name before
  anything else touches it, rather than patching each display point
  separately — the ambiguity doesn't exist anywhere downstream instead of
  being fixed once and re-introduced by the next chart.
- **Estimated margin** — Food 30% / Drink 22% / Dessert 24% cost-of-sales,
  typical UK hospitality benchmarks, used only because Square doesn't export
  COGS. Always labelled "estimated" in the app, never presented as actual.
- **Synthetic staffing model** — scheduled off a trailing 4-occurrence
  average for each (weekday, day-part), which is what produces the
  understaffed-ramp / overstaffed-drop-off pattern the tab highlights. See
  `src/generate_data.py` for the full demand + staffing model.
- **Upload-your-own robustness** (`src/square_parser.py`) — Square exports
  vary: this project's own files are UTF-16 tab-delimited with a BOM, but
  other accounts/regions export UTF-8 comma-delimited. The loader checks for
  a UTF-16 BOM explicitly rather than guessing by trial-and-error (blindly
  trying `.decode("utf-16")` on arbitrary bytes rarely raises an error — it
  just silently produces garbage — so encoding detection order matters).
  Missing/malformed files raise a specific, readable error in the app
  instead of a stack trace. Category names Square doesn't ship in this
  project's own data fall back to a keyword heuristic (wine/beer/coffee →
  Drink, cake/gelato → Dessert, else Food) rather than defaulting everything
  uploaded to one bucket.
- **Timecards parsing** (`src/square_parser.py: clean_timecards`) — Square's
  Timecards/Labor export column names are less standardised than Sales or
  Transactions (naming has shifted over time and by account), so fields are
  matched by a list of plausible candidate names case-insensitively rather
  than one fixed schema. Only a date column plus either hours-worked or a
  clock-in/clock-out pair are required; job title and pay/rate are optional
  and the tab degrades gracefully without them (hours-only view instead of
  £ cost). No employee-identifying column is ever read into the output — it
  simply isn't selected — and rows are renumbered to an anonymous
  `shift_id`, mirroring how Transactions handles the original Transaction ID.
