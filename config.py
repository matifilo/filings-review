"""Which company, and which line items we take from its filings.
To point the pipeline at another company, this is the file you change."""

COMPANY = {
    "name": "Logitech International",
    "ticker": "LOGI",
    "cik": "0001032975",
    "currency": "USD",
}

# our name -> (statement, [us-gaap tags, preferred first])
# Companies sometimes switch tags (Logitech's revenue tag changed in 2017-18),
# so one line item can list several. The first one wins when two cover the same period.
LINE_ITEMS = {
    "revenue":             ("income",   ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]),
    "gross_profit":        ("income",   ["GrossProfit"]),
    "rnd_expense":         ("income",   ["ResearchAndDevelopmentExpense"]),
    "selling_expense":     ("income",   ["SellingAndMarketingExpense"]),
    "admin_expense":       ("income",   ["GeneralAndAdministrativeExpense"]),
    "operating_income":    ("income",   ["OperatingIncomeLoss"]),
    "income_tax":          ("income",   ["IncomeTaxExpenseBenefit"]),
    "net_income":          ("income",   ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]),
    "operating_cash_flow": ("cashflow", ["NetCashProvidedByUsedInOperatingActivities",
                                         "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),  # used 2010-2015
    "capex":               ("cashflow", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    "buybacks":            ("cashflow", ["PaymentsForRepurchaseOfCommonStock"]),
    "cash":                ("balance",  ["CashAndCashEquivalentsAtCarryingValue"]),
    "receivables":         ("balance",  ["AccountsReceivableNetCurrent"]),
    "inventory":           ("balance",  ["InventoryNet"]),
    "payables":            ("balance",  ["AccountsPayableCurrent"]),
    "total_assets":        ("balance",  ["Assets"]),
    "equity":              ("balance",  ["StockholdersEquity"]),
}

MODEL = "claude-opus-5-5"  # which Claude model writes the review