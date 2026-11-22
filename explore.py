"""Look inside the snapshot: save every reported value of one line item to a CSV you can open in Excel."""
import json
import sys
from pathlib import Path

import pandas as pd

TAG = sys.argv[1] if len(sys.argv) > 1 else "RevenueFromContractWithCustomerExcludingAssessedTax"

snapshot = sorted(Path("data/raw").iterdir())[-1]  # the newest dated folder
data = json.loads((snapshot / "companyfacts.json").read_text(encoding="utf-8"))

item = data["facts"]["us-gaap"][TAG]
rows = pd.DataFrame(item["units"]["USD"])
rows = rows.reindex(columns=["start", "end", "val", "fy", "fp", "form", "filed"])

out = Path("data/explore") / f"{TAG}.csv"
out.parent.mkdir(parents=True, exist_ok=True)
rows.to_csv(out, index=False)

print(item["label"])
print(rows.tail(14).to_string())
print(f"\n{len(rows)} values saved to {out}")