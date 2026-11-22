-- One row per reported number, after duplicates are removed.
CREATE TABLE facts (
    statement    TEXT    NOT NULL CHECK (statement IN ('income', 'balance', 'cashflow')),
    line_item    TEXT    NOT NULL,   -- our name, e.g. revenue
    period_start TEXT,               -- empty for balance-sheet items (a photo, not a video)
    period_end   TEXT    NOT NULL,   -- e.g. 2026-09-30
    months       INTEGER NOT NULL,   -- 0 = balance sheet; 3, 6, 9 or 12 = length of the period
    value        REAL    NOT NULL,   -- in USD
    tag          TEXT    NOT NULL,   -- the us-gaap tag it came from
    form         TEXT    NOT NULL,   -- 10-Q or 10-K
    filed        TEXT    NOT NULL,   -- date of the filing we took it from
    PRIMARY KEY (line_item, period_end, months)   -- the database refuses a second copy of the same number
);

-- One row per run: what went in, what came out.
CREATE TABLE load_log (
    loaded_at     TEXT    NOT NULL,
    snapshot      TEXT    NOT NULL,
    rows_before   INTEGER NOT NULL,
    rows_after    INTEGER NOT NULL
);