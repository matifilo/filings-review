-- Phase 3A: turn the clean facts into one row per quarter.

-- 1) Every income and cash-flow number for ONE quarter (3 months).
--    Part A: the company reported the 3-month number itself -> take it as it is.
--    Part B: it only reported year-to-date (cash flow; and Q4, which is only in the annual report)
--            -> this year-to-date minus the previous year-to-date of the same fiscal year.
--    If the previous year-to-date is missing, there is no row: a gap, never a guess.
CREATE VIEW quarterly_flows AS
SELECT line_item,
       period_end,
       value,
       'reported' AS source
FROM facts
WHERE statement IN ('income', 'cashflow')
  AND months = 3

UNION ALL

SELECT cur.line_item,
       cur.period_end,
       cur.value - prev.value AS value,
       'derived' AS source
FROM facts AS cur
JOIN facts AS prev
  ON prev.line_item    = cur.line_item
 AND prev.period_start = cur.period_start      -- same fiscal year (both start 1 April)
 AND prev.months       = cur.months - 3         -- the year-to-date one quarter earlier
WHERE cur.statement IN ('income', 'cashflow')
  AND cur.months IN (6, 9, 12)
  AND NOT EXISTS (                              -- skip it if a reported 3-month number exists
      SELECT 1 FROM facts AS r
      WHERE r.line_item  = cur.line_item
        AND r.period_end = cur.period_end
        AND r.months     = 3);

-- 2) One row per quarter, one column per line item (a pivot), with the balance sheet next to it.
CREATE VIEW quarterly AS
WITH flows AS (
    SELECT period_end,
           MAX(CASE WHEN line_item = 'revenue'             THEN value END) AS revenue,
           MAX(CASE WHEN line_item = 'gross_profit'        THEN value END) AS gross_profit,
           MAX(CASE WHEN line_item = 'rnd_expense'         THEN value END) AS rnd_expense,
           MAX(CASE WHEN line_item = 'selling_expense'     THEN value END) AS selling_expense,
           MAX(CASE WHEN line_item = 'admin_expense'       THEN value END) AS admin_expense,
           MAX(CASE WHEN line_item = 'operating_income'    THEN value END) AS operating_income,
           MAX(CASE WHEN line_item = 'net_income'          THEN value END) AS net_income,
           MAX(CASE WHEN line_item = 'operating_cash_flow' THEN value END) AS operating_cash_flow,
           MAX(CASE WHEN line_item = 'capex'               THEN value END) AS capex,
           MAX(CASE WHEN line_item = 'buybacks'            THEN value END) AS buybacks
    FROM quarterly_flows
    GROUP BY period_end
),
balances AS (
    SELECT period_end,
           MAX(CASE WHEN line_item = 'cash'         THEN value END) AS cash,
           MAX(CASE WHEN line_item = 'receivables'  THEN value END) AS receivables,
           MAX(CASE WHEN line_item = 'inventory'    THEN value END) AS inventory,
           MAX(CASE WHEN line_item = 'payables'     THEN value END) AS payables,
           MAX(CASE WHEN line_item = 'total_assets' THEN value END) AS total_assets,
           MAX(CASE WHEN line_item = 'equity'       THEN value END) AS equity
    FROM facts
    WHERE months = 0
    GROUP BY period_end
)
SELECT f.period_end,
       -- Logitech's fiscal year ends 31 March: Apr-Jun 2026 is Q1 of fiscal 2027
       CASE WHEN CAST(strftime('%m', f.period_end) AS INTEGER) > 3
            THEN CAST(strftime('%Y', f.period_end) AS INTEGER) + 1
            ELSE CAST(strftime('%Y', f.period_end) AS INTEGER)
       END AS fiscal_year,
       CASE strftime('%m', f.period_end)
            WHEN '06' THEN 1 WHEN '09' THEN 2 WHEN '12' THEN 3 WHEN '03' THEN 4
       END AS fiscal_quarter,
       f.revenue,
       f.revenue - f.gross_profit AS cogs,      -- not tagged since 2017, so we derive it
       f.gross_profit,
       f.rnd_expense,
       f.selling_expense,
       f.admin_expense,
       f.operating_income,
       f.net_income,
       f.operating_cash_flow,
       f.capex,
       f.buybacks,
       b.cash,
       b.receivables,
       b.inventory,
       b.payables,
       b.total_assets,
       b.equity
FROM flows AS f
LEFT JOIN balances AS b USING (period_end)
WHERE f.revenue IS NOT NULL
ORDER BY f.period_end;


-- ===================== Phase 3B: KPIs =====================

-- 3) Ratios, growth and trailing-twelve-month (TTM) metrics, one row per quarter.
CREATE VIEW kpi_quarterly AS
WITH ttm AS (
    -- Rolling sums of the last 4 quarters (like =SUM(B2:B5) dragged down in Excel)
    SELECT q.*,
           SUM(revenue)             OVER last4 AS revenue_ttm,
           SUM(cogs)                OVER last4 AS cogs_ttm,
           SUM(net_income)          OVER last4 AS net_income_ttm,
           SUM(operating_cash_flow) OVER last4 AS ocf_ttm,
           COUNT(*)                 OVER last4 AS n_quarters,
           MIN(period_end)          OVER last4 AS window_start
    FROM quarterly AS q
    WINDOW last4 AS (ORDER BY period_end ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
),
checked AS (
    -- A TTM figure only counts if the 4 rows really are 4 back-to-back quarters
    -- (e.g. for 2026-09-30 the window must start at 2025-12-31). Otherwise it is left empty.
    SELECT *,
           (n_quarters = 4
            AND window_start = date(period_end, 'start of month', '-8 months', '-1 day')) AS ttm_ok
    FROM ttm
)
SELECT c.period_end,
       c.fiscal_year,
       c.fiscal_quarter,

       -- Growth: this quarter vs the same quarter one year earlier (ly = "last year")
       c.revenue,
       c.revenue / ly.revenue - 1                                         AS revenue_yoy,

       -- Margins: each line as a share of revenue
       c.gross_profit / c.revenue                                         AS gross_margin,
       c.gross_profit / c.revenue - ly.gross_profit / ly.revenue          AS gross_margin_change_yoy,
       c.rnd_expense / c.revenue                                          AS rnd_pct,
       c.selling_expense / c.revenue                                      AS selling_pct,
       c.admin_expense / c.revenue                                        AS admin_pct,
       c.operating_income / c.revenue                                     AS operating_margin,
       c.operating_income / c.revenue - ly.operating_income / ly.revenue  AS operating_margin_change_yoy,
       c.net_income,
       c.net_income / ly.net_income - 1                                   AS net_income_yoy,
       c.net_income / c.revenue                                           AS net_margin,

       -- Cash
       c.operating_cash_flow,
       c.operating_cash_flow - c.capex                                    AS free_cash_flow,
       c.buybacks,
       c.cash,

       -- Working capital, in days (balance at quarter end vs the last 12 months of flows)
       CASE WHEN c.ttm_ok THEN c.revenue_ttm END                          AS revenue_ttm,
       CASE WHEN c.ttm_ok THEN c.receivables / c.revenue_ttm * 365 END    AS dso_days,
       CASE WHEN c.ttm_ok THEN c.inventory   / c.cogs_ttm    * 365 END    AS dio_days,
       CASE WHEN c.ttm_ok THEN c.payables    / c.cogs_ttm    * 365 END    AS dpo_days,
       CASE WHEN c.ttm_ok THEN (c.receivables / c.revenue_ttm
                                + (c.inventory - c.payables) / c.cogs_ttm) * 365 END
                                                                          AS cash_conversion_cycle_days,
       CASE WHEN c.ttm_ok THEN c.ocf_ttm / c.net_income_ttm END           AS cash_conversion_ttm,
       c.inventory,
       c.inventory / ly.inventory - 1                                     AS inventory_yoy
FROM checked AS c
LEFT JOIN quarterly AS ly ON ly.period_end = date(c.period_end, '-1 year')
ORDER BY c.period_end;