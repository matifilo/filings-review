"""Phase 6: the checker. It reads a draft and lists every broken rule - it never fixes anything itself.

Run it alone to check output/draft.md (costs nothing, no AI involved):
    .venv\\Scripts\\python validate.py
"""
import json
import re
import sys
from pathlib import Path

SECTIONS = ["Headline", "Growth and profitability", "Working capital and cash",
            "What to watch next quarter", "Data caveats"]
MIN_WORDS, MAX_WORDS = 450, 650
MIN_CITED = 12  # a draft that avoids numbers would pass every other test

CITATION = re.compile(r"\[F:([^\]]*)\]")                 # [F:cur.revenue] -> cur.revenue
PERIOD = re.compile(r"\b(?:(?:Q[1-4]|\d{1,2}M)(?: FY\d{4})?|FY\d{4})\b")  # Q2 FY2027, 6M FY2027, FY2026, Q4
LIST_NUMBER = re.compile(r"^\s*\d+\.\s", re.MULTILINE)   # "1. " at the start of a list line
NUMBER = re.compile(r"\d[\d,.]*")


def check(draft, pack):
    """Return a list of problems. An empty list means the draft passed."""
    facts = {f["id"]: f for f in pack["facts"]}
    errors = []

    # 1) The five sections, in the right order
    headings = [line[3:].strip() for line in draft.splitlines() if line.startswith("## ")]
    if headings != SECTIONS:
        errors.append(f"The sections must be exactly {SECTIONS}, in that order. Found: {headings}.")

    # 2) No placeholders or template leftovers
    for bad in ("{", "}", "TBD", "TODO"):
        if bad in draft:
            errors.append(f"Remove the placeholder text '{bad}' and write a real sentence.")

    # 3) Every citation: the fact exists, and its exact value is written right before it
    cleared = []  # text spans that are correctly cited; step 4 ignores them
    for m in CITATION.finditer(draft):
        fact_id = m.group(1)
        fact = facts.get(fact_id)
        if fact is None:
            errors.append(f"[F:{fact_id}] does not exist in the facts pack. Use only ids from the pack.")
            cleared.append((m.start(), m.end()))
            continue
        before = draft[:m.start()].rstrip()
        shown = fact["display"]
        # the value as displayed, or without its sign when the words say "fell" / "rose"
        allowed = {shown, shown.replace("-", "", 1), shown.replace("+", "", 1)}
        found = None
        for value in allowed:
            # (?<![\d.,]) stops "15.5%" from counting as "5.5%"
            hit = re.search(r"(?<![\d.,])" + re.escape(value) + r"$", before)
            if hit:
                found = hit
                break
        if found:
            cleared.append((found.start(), m.end()))
        else:
            errors.append(f"[F:{fact_id}] must come right after its value {shown} "
                          f"({fact['label']}, {fact['period']}). The text before it is: '...{before[-30:]}'.")
            cleared.append((m.start(), m.end()))

    # 4) No number without a source: blank out cited values and period names, then look for digits
    rest = draft
    for start, end in cleared:
        rest = rest[:start] + " " * (end - start) + rest[end:]  # same length, so positions stay valid
    rest = PERIOD.sub(lambda m: " " * len(m.group()), rest)
    rest = LIST_NUMBER.sub(lambda m: " " * len(m.group()), rest)
    for m in NUMBER.finditer(rest):
        context = " ".join(draft[max(0, m.start() - 40):m.end() + 20].split())
        errors.append(f"The number '{m.group()}' has no [F:id] source: '...{context}...'. "
                      "Cite the fact it comes from, or remove it (write small counts in words).")

    # 5) Every data flag is reported in the Data caveats section
    caveats = draft.split("## Data caveats", 1)[1] if "## Data caveats" in draft else ""
    for flag in pack["data_flags"]:
        if not (flag["period"] in caveats and flag["metric"].lower() in caveats.lower()
                and flag["value"] in caveats):
            errors.append(f"Data caveats must report the flagged figure: {flag['period']} "
                          f"{flag['metric']} {flag['value']} ({flag['compared_with']}).")

    # 6) Every missing item is said to be missing
    for item in pack["missing"]:
        if item["label"].lower() not in draft.lower():
            errors.append(f"Say that '{item['label']}' for {item['period']} is not available.")

    # 7) Length (citations do not count as words) and enough real numbers
    words = len(CITATION.sub("", draft).split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        errors.append(f"The review has {words} words; it must have {MIN_WORDS} to {MAX_WORDS}.")
    cited = len(CITATION.findall(draft))
    if cited < MIN_CITED:
        errors.append(f"Only {cited} cited numbers; use at least {MIN_CITED} facts from the pack.")

    return errors


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/draft.md")
    draft = path.read_text(encoding="utf-8")
    pack = json.loads(Path("output/facts_pack.json").read_text(encoding="utf-8"))
    problems = check(draft, pack)
    print(f"Checked {path}: {len(CITATION.findall(draft))} cited numbers, "
          f"{len(CITATION.sub('', draft).split())} words")
    if problems:
        print(f"FAIL - {len(problems)} problem(s):")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("PASS - every number matches the fact it cites")