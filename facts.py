"""Phase 4: build the facts pack - the only numbers the AI is allowed to use.

Every fact gets an id (e.g. cur.revenue), its value rounded the way the report will show it,
and a display text. In Phase 5 the AI must cite the id behind every number it writes;
in Phase 6 a checker compares each number with the fact it cites.
"""
import json
import sqlite3
import statistics
from pathlib import Path

import config

# unit -> (multiply by, decimals, how it is displayed)
UNITS = {
    "usd_m": (1e-6, 1, "USD {:,.1f}m"),
    "pct":   (100,  1, "{:.1f}%"),
    "pp":    (100,  1, "{:+.1f} pp"),
    "days":  (1,    0, "{:.0f} days"),
    "x":     (1,    2, "{:.2f}x"),
}

# The KPIs we report for the latest quarter and the same quarter last year:
# (column in kpi_quarterly, name, unit)
KPIS = [
    ("revenue",                    "Revenue",                                      "usd_m"),
    ("revenue_yoy",                "Revenue growth, year on year",                 "pct"),
    ("gross_margin",               "Gross margin",                                 "pct"),
    ("rnd_pct",                    "R&D expense / revenue",                        "pct"),
    ("selling_pct",                "Selling and marketing expense / revenue",      "pct"),
    ("admin_pct",                  "General and admin expense / revenue",          "pct"),
    ("operating_margin",           "Operating margin",                             "pct"),
    ("net_income",                 "Net income",                                   "usd_m"),
    ("net_income_yoy",             "Net income growth, year on year",              "pct"),
    ("net_margin",                 "Net margin",                                   "pct"),
    ("operating_cash_flow",        "Operating cash flow",                          "usd_m"),
    ("free_cash_flow",             "Free cash flow (operating cash flow - capex)", "usd_m"),
    ("buybacks",                   "Share buybacks",                               "usd_m"),
    ("cash",                       "Cash and cash equivalents",                    "usd_m"),
    ("dso_days",                   "Days sales outstanding (TTM)",                 "days"),
    ("dio_days",                   "Days inventory outstanding (TTM)",             "days"),
    ("dpo_days",                   "Days payables outstanding (TTM)",              "days"),
    ("cash_conversion_cycle_days", "Cash conversion cycle (TTM)",                  "days"),
    ("cash_conversion_ttm",        "Operating cash flow / net income (TTM)",       "x"),
    ("inventory",                  "Inventory",                                    "usd_m"),
    ("inventory_yoy",              "Inventory growth, year on year",               "pct"),
]

facts = []    # the numbers the AI may use
missing = []  # numbers we wanted but the data does not have


def add(fact_id, name, period, unit, raw):
    """Turn one raw number into a fact. A missing number is recorded as missing, never invented."""
    if raw is None:
        missing.append({"id": fact_id, "label": name, "period": period})
        return
    scale, decimals, fmt = UNITS[unit]
    value = round(raw * scale, decimals)
    facts.append({"id": fact_id, "label": name, "period": period, "unit": unit,
                  "value": value, "display": fmt.format(value)})


def label(row):
    """A quarter's name, e.g. 'Q2 FY2027' (Logitech's fiscal year ends in March)."""
    return f"Q{row['fiscal_quarter']} FY{row['fiscal_year']}"


# 1) Read the KPI view
con = sqlite3.connect("data/filings.db")
con.row_factory = sqlite3.Row  # read columns by name, e.g. row["revenue"]
rows = [dict(r) for r in con.execute("SELECT * FROM kpi_quarterly ORDER BY period_end")]
latest = rows[-1]
last_year = next(r for r in rows if r["fiscal_year"] == latest["fiscal_year"] - 1
                 and r["fiscal_quarter"] == latest["fiscal_quarter"])

# 2) Latest quarter and the same quarter last year
for prefix, row in (("cur", latest), ("ly", last_year)):
    for column, name, unit in KPIS:
        add(f"{prefix}.{column}", name, label(row), unit, row[column])
add("cur.gross_margin_change_yoy", "Gross margin change vs same quarter last year", label(latest), "pp",
    latest["gross_margin_change_yoy"])
add("cur.operating_margin_change_yoy", "Operating margin change vs same quarter last year", label(latest), "pp",
    latest["operating_margin_change_yoy"])

# 3) Fiscal year to date, straight from the reported year-to-date numbers
months = latest["fiscal_quarter"] * 3
ytd_label = f"{months}M FY{latest['fiscal_year']}"


def ytd(line_item, period_end):
    r = con.execute("SELECT value FROM facts WHERE line_item = ? AND period_end = ? AND months = ?",
                    (line_item, period_end, months)).fetchone()
    return r["value"] if r else None


for line_item, name in (("revenue", "Revenue"), ("net_income", "Net income")):
    now, before = ytd(line_item, latest["period_end"]), ytd(line_item, last_year["period_end"])
    add(f"ytd.{line_item}", f"{name}, fiscal year to date", ytd_label, "usd_m", now)
    growth = now / before - 1 if now is not None and before else None
    add(f"ytd.{line_item}_yoy", f"{name} growth, fiscal year to date", ytd_label, "pct", growth)

# 4) Trend: the last 8 quarters of the core series
recent = rows[-8:]
for r in recent:
    key = label(r).lower().replace(" ", "_")  # 'Q2 FY2027' -> 'q2_fy2027'
    add(f"{key}.revenue_yoy", "Revenue growth, year on year", label(r), "pct", r["revenue_yoy"])
    add(f"{key}.gross_margin", "Gross margin", label(r), "pct", r["gross_margin"])
    add(f"{key}.operating_margin", "Operating margin", label(r), "pct", r["operating_margin"])
    add(f"{key}.dio_days", "Days inventory outstanding (TTM)", label(r), "days", r["dio_days"])

# 5) Data flags: unusual quarters the AI must report as caveats, not explain away
flags = []
for r in recent:
    # Gross margin is fairly stable through the year -> compare with the median of the other 7 quarters
    others = [o["gross_margin"] for o in recent if o is not r and o["gross_margin"] is not None]
    if r["gross_margin"] is not None and others:
        norm = statistics.median(others)
        if abs(r["gross_margin"] - norm) > 0.04:
            flags.append({"period": label(r), "metric": "Gross margin",
                          "value": f"{r['gross_margin'] * 100:.1f}%",
                          "compared_with": f"median of the other recent quarters, {norm * 100:.1f}%"})
    # Operating margin swings with the seasons -> compare with the same quarter last year
    change = r["operating_margin_change_yoy"]
    if change is not None and abs(change) > 0.05:
        flags.append({"period": label(r), "metric": "Operating margin",
                      "value": f"{r['operating_margin'] * 100:.1f}%",
                      "compared_with": f"same quarter last year, change {change * 100:+.1f} pp"})
for f in flags:
    f["note"] = "Unusual move. Report it as a caveat; do not explain it unless the filing does."

# 6) Save the pack
snapshot = con.execute("SELECT snapshot FROM load_log ORDER BY loaded_at DESC LIMIT 1").fetchone()["snapshot"]
pack = {
    "company": config.COMPANY,
    "snapshot": snapshot,
    "latest_period": label(latest),
    "latest_period_end": latest["period_end"],
    "method_notes": [
        "All numbers come from the company's 10-Q and 10-K filings (SEC XBRL data).",
        "Q4 figures and most quarterly cash flows are derived: year to date minus the previous year to date.",
        "Cost of goods sold = revenue - gross profit.",
        "Working-capital days use quarter-end balances over trailing-twelve-month (TTM) flows.",
    ],
    "facts": facts,
    "missing": missing,
    "data_flags": flags,
}
out = Path("output/facts_pack.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(pack, indent=1), encoding="utf-8")

print(f"Latest quarter: {pack['latest_period']} (ends {pack['latest_period_end']})")
print(f"Facts: {len(facts)}, missing: {len(missing)}, data flags: {len(flags)}")
for f in flags:
    print(f"  flag: {f['period']} {f['metric']} {f['value']} ({f['compared_with']})")
print(f"Saved: {out}")