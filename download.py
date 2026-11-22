"""Phase 1: download everything a company has reported to the SEC and save it as a dated snapshot."""
import datetime as dt
from pathlib import Path

import requests

CIK = "0001032975"  # Logitech's SEC company ID (always 10 digits, padded with zeros)
URL = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"

contact = Path("sec_contact.txt").read_text(encoding="utf-8").strip()
response = requests.get(URL, headers={"User-Agent": contact}, timeout=30)
response.raise_for_status()  # stop here with an error if the SEC refused the request

data = response.json()
folder = Path("data/raw") / dt.date.today().isoformat()  # e.g. data/raw/2026-11-23
folder.mkdir(parents=True, exist_ok=True)
(folder / "companyfacts.json").write_bytes(response.content)  # save exactly what the SEC sent

print(f"Company: {data['entityName']}")
print(f"Line items (us-gaap tags): {len(data['facts']['us-gaap'])}")
print(f"Saved: {folder / 'companyfacts.json'} ({len(response.content) / 1e6:.1f} MB)")