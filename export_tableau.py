"""Export the KPI table for the Tableau Public dashboard.

Reads the kpi_quarterly view and the data flags from the facts pack, adds labels Tableau
can show as they are, and writes output/kpi_quarterly.csv (one row per quarter).
Ratios stay decimals (0.449 = 44.9%): Tableau formats them as percentages.
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

# column -> field name in Tableau, in the order the CSV keeps. "(USD m)" columns are divided by a million.
FIELDS = {
    "period_end":                  "Quarter end",
    "fiscal_year":                 "Fiscal year",
    "fiscal_quarter":              "Fiscal quarter",
    "quarter_label":               "Quarter",          # added below, e.g. 'Q2 FY27'
    "period_label":                "Months",           # added below, e.g. 'Jul–Sep 2026'
    "revenue":                     "Revenue (USD m)",
    "revenue_yoy":                 "Revenue growth YoY",
    "revenue_ttm":                 "Revenue TTM (USD m)",
    "gross_margin":                "Gross margin",
    "gross_margin_change_yoy":     "Gross margin change YoY",
    "rnd_pct":                     "R&D / revenue",
    "selling_pct":                 "Selling / revenue",
    "admin_pct":                   "G&A / revenue",
    "operating_margin":            "Operating margin",
    "operating_margin_change_yoy": "Operating margin change YoY",
    "net_income":                  "Net income (USD m)",
    "net_income_yoy":              "Net income growth YoY",
    "net_margin":                  "Net margin",
    "operating_cash_flow":         "Operating cash flow (USD m)",
    "free_cash_flow":              "Free cash flow (USD m)",
    "buybacks":                    "Buybacks (USD m)",
    "cash":                        "Cash (USD m)",
    "cash_conversion_ttm":         "Cash conversion TTM (x)",
    "inventory":                   "Inventory (USD m)",
    "inventory_yoy":               "Inventory growth YoY",
    "dso_days":                    "DSO (days)",
    "dio_days":                    "DIO (days)",
    "dpo_days":                    "DPO (days)",
    "cash_conversion_cycle_days":  "Cash conversion cycle (days)",
    "ccc_change_yoy":              "Cash conversion cycle change YoY (days)",  # added below
    "flag_note":                   "Data flag",                                # added below
}
MONEY = [column for column, name in FIELDS.items() if "(USD m)" in name]

con = sqlite3.connect("data/filings.db")
df = pd.read_sql_query("SELECT * FROM kpi_quarterly ORDER BY period_end", con)
end = pd.to_datetime(df["period_end"])

# 1) Labels Tableau can show as they are (Logitech's fiscal year ends in March)
df["quarter_label"] = "Q" + df["fiscal_quarter"].astype(str) + " FY" + (df["fiscal_year"] % 100).astype(str).str.zfill(2)
df["period_label"] = (end - pd.DateOffset(months=2)).dt.strftime("%b") + "\N{EN DASH}" + end.dt.strftime("%b %Y")

# 2) Cash conversion cycle vs the same quarter a year earlier (for the KPI header)
ccc = dict(zip(df["period_end"], df["cash_conversion_cycle_days"]))
year_earlier = (end - pd.DateOffset(years=1)).dt.strftime("%Y-%m-%d")
df["ccc_change_yoy"] = df["cash_conversion_cycle_days"] - year_earlier.map(ccc)

# 3) Data flags: the same unusual quarters the report flags, taken from the facts pack
pack = json.loads(Path("output/facts_pack.json").read_text(encoding="utf-8"))
if pack["latest_period_end"] != df["period_end"].iloc[-1]:
    raise SystemExit("The facts pack does not match the database: run facts.py first.")
notes = {}
for f in pack["data_flags"]:
    notes.setdefault(f["period"], []).append(f"{f['metric']} {f['value']} ({f['compared_with']})")
pack_label = "Q" + df["fiscal_quarter"].astype(str) + " FY" + df["fiscal_year"].astype(str)  # 'Q1 FY2027', as in facts.py
if not set(notes) <= set(pack_label):
    raise SystemExit(f"A data flag names a quarter that is not in the table: {set(notes) - set(pack_label)}")
df["flag_note"] = pack_label.map({period: "; ".join(texts) for period, texts in notes.items()})

# 4) Money in USD millions, Tableau names, and save
df[MONEY] = df[MONEY] / 1e6
out = df[list(FIELDS)].rename(columns=FIELDS).round(6)
if out["Quarter end"].duplicated().any():
    raise SystemExit("Two rows for the same quarter: check kpi_quarterly.")
path = Path("output/kpi_quarterly.csv")
out.to_csv(path, index=False, encoding="utf-8-sig")  # utf-8-sig: Tableau and Excel read the en dash correctly

# 5) Excel copy for Tableau: numbers and dates are stored as numbers and dates there,
#    so Tableau does not have to guess them from text (that guess depends on Windows' language settings)
excel = out.copy()
excel["Quarter end"] = pd.to_datetime(excel["Quarter end"]).dt.date
excel.to_excel("output/kpi_quarterly.xlsx", index=False, sheet_name="kpi_quarterly")

latest = out.iloc[-1]
print(f"Quarters: {len(out)}, {out['Quarter'].iloc[0]} to {latest['Quarter']}")
print(f"Latest: {latest['Quarter']} ({latest['Months']}): revenue USD {latest['Revenue (USD m)']:,.1f}m, "
      f"gross margin {latest['Gross margin']:.1%}, cash conversion cycle {latest['Cash conversion cycle (days)']:.0f} days "
      f"({latest['Cash conversion cycle change YoY (days)']:+.0f} vs a year earlier)")
for _, row in out[out["Data flag"].notna()].iterrows():
    print(f"  flag: {row['Quarter']}: {row['Data flag']}")

# 6) Count what is empty, not only what fails. facts.py checks only the figures the review uses; this checks every quarter.
#    Growth needs a year of history and TTM figures need four quarters, so the first quarters are empty by design.
print("Empty cells (blank on the dashboard):")
for name in out.columns.drop("Data flag"):
    empty = out.index[out[name].isna()].tolist()
    if not empty:
        continue
    spans, start = [], empty[0]
    for i, following in zip(empty, empty[1:] + [None]):
        if following != i + 1:  # the end of a run of back-to-back quarters
            first, last = out["Quarter"][start], out["Quarter"][i]
            spans.append(first if start == i else f"{first} to {last}")
            start = following
    print(f"  {name}: {len(empty)}  ({', '.join(spans)})")
print("Saved: output\\kpi_quarterly.csv and output\\kpi_quarterly.xlsx")