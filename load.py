"""Phase 2: take the line items we need from the snapshot, remove duplicates, load them into SQLite."""
import datetime as dt
import json
import sqlite3
from pathlib import Path

import pandas as pd

import config

# 1) Open the newest snapshot
snapshot = sorted(Path("data/raw").iterdir())[-1]
data = json.loads((snapshot / "companyfacts.json").read_text(encoding="utf-8"))
gaap = data["facts"]["us-gaap"]

# 2) Collect every value of every tag we listed in config.py
pieces = []
for line_item, (statement, tags) in config.LINE_ITEMS.items():
    for priority, tag in enumerate(tags):          # priority 0 = preferred tag
        if tag not in gaap:
            print(f"  note: {tag} not found, skipped")
            continue
        rows = pd.DataFrame(gaap[tag]["units"]["USD"])
        rows = rows.reindex(columns=["start", "end", "val", "form", "filed"])
        rows["line_item"] = line_item
        rows["statement"] = statement
        rows["tag"] = tag
        rows["priority"] = priority
        pieces.append(rows)

facts = pd.concat(pieces, ignore_index=True)       # stack all pieces into one table
facts = facts[facts["form"].isin(["10-Q", "10-K", "10-Q/A", "10-K/A"])]

# 3) How many months each number covers (0 = balance sheet)
days = (pd.to_datetime(facts["end"]) - pd.to_datetime(facts["start"])).dt.days
facts["months"] = (days / 30.44).round().fillna(0).astype(int)

# 4) Remove duplicates: same line item + same period end + same length = the same number.
#    Keep the most recent filing first (it includes any corrections), then the preferred tag.
rows_before = len(facts)
facts = facts.sort_values(["filed", "priority"], ascending=[False, True])
facts = facts.drop_duplicates(subset=["line_item", "end", "months"], keep="first")

# 5) Rebuild the database from scratch and load the clean table
facts = facts.rename(columns={"start": "period_start", "end": "period_end", "val": "value"})
columns = ["statement", "line_item", "period_start", "period_end", "months", "value", "tag", "form", "filed"]
facts = facts[columns].sort_values(["line_item", "period_end", "months"])

db = Path("data/filings.db")
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
con.executescript(Path("sql/schema.sql").read_text(encoding="utf-8"))
facts.to_sql("facts", con, if_exists="append", index=False)
con.executescript(Path("sql/views.sql").read_text(encoding="utf-8"))
con.execute("INSERT INTO load_log VALUES (?, ?, ?, ?)",
            (dt.datetime.now().isoformat(timespec="seconds"), snapshot.name, rows_before, len(facts)))
con.commit()
con.close()

print(f"Snapshot: {snapshot.name}")
print(f"Rows before removing duplicates: {rows_before}")
print(f"Rows loaded into {db}: {len(facts)}")