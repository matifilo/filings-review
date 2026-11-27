"""Tests for the SQL KPI view: a trailing-twelve-month (TTM) figure must be built from four full quarters.

Run from the project folder:  .venv\\Scripts\\python -m pytest
Each test builds a small database in memory from sql/schema.sql and sql/views.sql,
with made-up numbers for four quarters, so it needs no SEC data and no saved database.
"""
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
QUARTERS = ["2014-09-30", "2014-12-31", "2015-03-31", "2015-06-30"]  # four back-to-back quarters
LAST = QUARTERS[-1]
M = 1e6


def kpis(net_income=(50, 50, 50, 50), cash_flow=(60, 60, 60, 60), gross_profit=(400, 400, 400, 400)):
    """Build the views over four quarters of made-up numbers (USD m; None = not reported).
    Returns the kpi_quarterly row of the last quarter."""
    con = sqlite3.connect(":memory:")
    con.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
    con.executescript((ROOT / "sql/views.sql").read_text(encoding="utf-8"))
    rows = []
    for i, end in enumerate(QUARTERS):
        d = date.fromisoformat(end)
        start = date(d.year, d.month - 2, 1).isoformat()  # 2015-06-30 -> 2015-04-01
        values = {("income", "revenue"): 1000, ("income", "gross_profit"): gross_profit[i],
                  ("income", "net_income"): net_income[i], ("cashflow", "operating_cash_flow"): cash_flow[i]}
        for (statement, line_item), value in values.items():
            if value is not None:
                rows.append((statement, line_item, start, end, 3, value * M))
        rows.append(("balance", "inventory", None, end, 0, 300 * M))
    con.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?, 'test-tag', '10-Q', '2016-01-01')", rows)
    con.row_factory = sqlite3.Row
    return dict(con.execute("SELECT * FROM kpi_quarterly WHERE period_end = ?", (LAST,)).fetchone())


def test_cash_conversion_from_four_full_quarters():
    assert kpis()["cash_conversion_ttm"] == 240 / 200


def test_cash_conversion_is_empty_when_a_quarter_has_no_cash_flow():
    # The June 2015 bug: three quarters had no cash flow, and SUM added up the one that did,
    # so a single quarter of cash was divided by a full year of earnings (8.66x in the old export)
    assert kpis(cash_flow=(None, None, None, -25.6))["cash_conversion_ttm"] is None


def test_cash_conversion_is_empty_over_a_loss():
    # June 2015 after the cash-flow tag was fixed: four quarters of cash, but a net loss of USD 3m over the year
    row = kpis(net_income=(36.1, 62.8, -109.3, 7.4), cash_flow=(32.9, 76.4, 41.6, -25.6))
    assert row["cash_conversion_ttm"] is None


def test_inventory_days_are_empty_when_a_quarter_has_no_gross_profit():
    assert kpis()["dio_days"] is not None
    assert kpis(gross_profit=(400, None, 400, 400))["dio_days"] is None
