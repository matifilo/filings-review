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
PERIOD_NAME = r"(?:Q[1-4]|\d{1,2}M) FY\d{4}"            # a full period name, as the pack writes it
HTML_TAG = re.compile(r"<[A-Za-z/!?][^>\n]{0,60}>?")    # <b>, </p>, <img ...>, <!-- ...

# Words that say which way a number moved. Not 'improved' or 'weakened': they say better or worse,
# and a cash conversion cycle that "improved to 44 days from 46 days" went down.
UP = {"rose", "risen", "rise", "rises", "rising", "up", "grew", "grown", "increased", "increase", "increases",
      "higher", "gain", "gained", "gains", "climbed", "jumped", "jump", "lengthened", "widened", "expanded",
      "accelerated"}
DOWN = {"fell", "fallen", "fall", "falls", "falling", "down", "declined", "decline", "declines", "decreased",
        "decrease", "decreases", "lower", "dropped", "drop", "shrank", "contracted", "eased", "slowed",
        "shortened", "narrowed", "slipped", "loss"}
NOUNS = {"rise", "increase", "gain", "jump", "decline", "decrease", "fall", "drop", "loss"}  # 'a 0.5% decline'
NEGATIVE = re.compile(r"\b(?:negative|outflows?|loss(?:es)?|deficit|shortfall|minus)\b", re.I)  # 'an outflow of USD 40.9m'
# One of those words (any case), longest first so 'rises' is not read as 'rise'
DIRECTION = r"\b(?i:(" + "|".join(sorted(UP | DOWN, key=len, reverse=True)) + r"))\b"
COMPARING = re.compile(r"\b(?:than|below|above|against|from|with|versus|vs|since|over)\b")


def way(word):
    """+1 for a word that says up, -1 for down, 0 for any other word."""
    word = word.lower()
    return 1 if word in UP else -1 if word in DOWN else 0


def check_words(draft, matched, facts):
    """The number is right (step 3 checked it); do the words next to it say the same thing?

    a) Direction of a change: 'rose 5.5%' needs a positive fact, 'fell 5.5%' a negative one.
       Only for growth and change facts (ids ending in _yoy): '44.9%' has no direction of its own.
       A minus sign may only be dropped when the words say so ('fell 0.1%', 'an outflow of USD 40.9m').
    b) Two figures of the same kind: 'fell to X from Y' needs X below Y ('rose to', ', up from',
       'fell from Y to X' alike). 'Buybacks rose to X' with no 'from' is read as against last year.
       For the same measure in two quarters, 'from' and 'against' must introduce the earlier quarter.
    c) Period: 'X in Q1 FY2027' needs X to be a Q1 FY2027 fact (also 'For 6M FY2027, revenue was X'
       and '- **Q1 FY2027 gross margin:** X'), and 'X a year ago' must not be the current quarter's figure.
    """
    errors = []
    current = {f["period"] for f in facts.values() if f["id"].startswith(("cur.", "ytd."))}
    # For each cited number, the words before it: back to the previous number or the start of the sentence
    leads = [re.split(r"[.!?;:](?=[\s*])|\n|\]", draft[max(0, start - 300):start])[-1]
             for _, _, start, _ in matched]
    next_to = r"\s+(?:(?:by|of|only|just|about)\s+)*$"  # 'rose 5.5%', 'a gain of +1.5 pp', 'rose by only +0.3 pp'

    for (fact, written, start, end), lead in zip(matched, leads):
        cite = f"{written} [F:{fact['id']}]"
        after = draft[end:end + 60]
        word = re.search(DIRECTION + next_to, lead)
        if not word and re.search(r"\b(?i:a|an|the)\s+$", lead):  # 'the 0.5% [F:...] decline seen a year ago'
            word = re.match(r"\s+(" + "|".join(NOUNS) + r")\b", after)
        said = way(word.group(1)) if word else 0
        # a) direction of a change
        if fact["id"].endswith("_yoy") and fact["value"] != 0 and said and said != (1 if fact["value"] > 0 else -1):
            errors.append(f"'{word.group(1)} {cite}': the word says it went {'up' if said > 0 else 'down'}, but "
                          f"the fact is {fact['display']} ({fact['label']}, {fact['period']}). Use a word that fits.")
        if "-" in fact["display"] and "-" not in written and said != -1 and not NEGATIVE.search(lead):
            errors.append(f"{cite} is {fact['display']}. Keep the minus sign, or say that it is a fall or "
                          f"negative (e.g. 'fell {written}', 'an outflow of {written}').")
        # c) period named right after the number, earlier in its clause, or in its bullet's label
        named = re.match(r"\s+(?:[a-z]+\s+)?(?:in|of|for|during)\s+(" + PERIOD_NAME + ")", after)
        if not named:  # earlier in the same clause: 'For 6M FY2027, revenue was X', 'grew Q2 FY2027 revenue to X'
            in_lead = list(re.finditer("(" + PERIOD_NAME + ")", lead))
            named = in_lead[0] if len(in_lead) == 1 and "," not in lead[in_lead[0].end():].removeprefix(",") \
                else None  # two periods ('Q1 and Q2 FY2027 margins were X and Y'): too ambiguous to check
            if named:
                word_before = (lead[:named.start()].split() or [""])[-1]
                if (COMPARING.search(lead[named.end():]) or COMPARING.fullmatch(word_before)
                        or re.match(r"\s+(?:[a-z]+\s+)?(?:in|of|for|during)\s+" + PERIOD_NAME, lead)):
                    # 'In Q2 FY2027, margin was below the 49.5% ...', 'since Q4 FY2025', or the period
                    # belongs to the number before ('66 days [F:..] in Q1 FY2027 and 70 days'): not about this one
                    named = None
        if not named:  # '- **Gross margin, Q1 FY2027:** reported at 49.5%': the first number of a labelled bullet
            line = draft[draft.rfind("\n", 0, start) + 1:start]
            label = re.match(r"\s*[-*]\s+\*\*([^*]+)\*\*", line)
            in_label = re.findall(PERIOD_NAME, label.group(1)) if label else []
            if len(in_label) == 1 and "[F:" not in line:
                named = re.search("(" + PERIOD_NAME + ")", label.group(1))
        if named and named.group(1) != fact["period"]:
            errors.append(f"{cite} is the {fact['period']} figure ({fact['label']}), but the text names "
                          f"{named.group(1)} for it.")
        if re.match(r"\s+a year (?:ago|earlier|before)\b", after) and fact["period"] in current:
            errors.append(f"{cite} is the {fact['period']} figure, but the text says it is from a year ago.")

    # b) two figures of the same kind, compared with a direction word
    def against(word, new, old):
        if way(word) * (new["value"] - old["value"]) < 0:
            errors.append(f"'{word}' does not fit the numbers: {new['display']} [F:{new['id']}] is "
                          f"{'lower' if new['value'] < old['value'] else 'higher'} than {old['display']} "
                          f"[F:{old['id']}]. Check which figure is the current one and which way it moved.")

    def when(f):
        """(fiscal year, quarter) of a quarterly fact, for putting two of them in order; None otherwise."""
        m = re.fullmatch(r"Q([1-4]) FY(\d{4})", f["period"])
        return (int(m.group(2)), int(m.group(1))) if m else None

    paired = set()  # numbers already compared with the figure next to them
    for i, ((f1, w1, s1, e1), (f2, w2, s2, e2), lead) in enumerate(zip(matched, matched[1:], leads)):
        if f1["unit"] != f2["unit"]:
            continue
        gap = draft[e1:s2]
        # b1) the same measure for two quarters: 'from' and 'against' introduce the EARLIER one
        if f1["id"].partition(".")[2] == f2["id"].partition(".")[2] and when(f1) and when(f2):
            sentence = re.split(r"[.!?](?=\s)|\n", draft[max(0, s1 - 300):s1])[-1]
            about_last_year = re.search(r"year (?:ago|earlier|before)|(?:last|prior|previous) year", sentence, re.I)
            if re.fullmatch(r",?\s+(?:[a-z&]+\s+){0,4}?from\s+", gap):
                first_is_later, connector = True, "from"
            elif re.fullmatch(r"\s+to\s+", gap) and re.search(r"\bfrom\s+$", lead):
                first_is_later, connector = False, "from"
            elif re.fullmatch(r",?\s+(?:[a-z]+\s+){0,2}?(?:against|compared with|versus|vs)\s+", gap) \
                    and not about_last_year:
                first_is_later, connector = True, "against"
            else:
                first_is_later = None
            if first_is_later is not None and (when(f1) > when(f2)) != first_is_later:
                errors.append(f"{w1} [F:{f1['id']}] ({f1['period']}) and {w2} [F:{f2['id']}] ({f2['period']}) "
                              f"are the wrong way round: '{connector}' must introduce the earlier figure.")
                paired.update((i, i + 1))
                continue
        word, new, old = None, (i, f1), (i + 1, f2)
        m = re.search(DIRECTION + r"\s+(?:[a-z]+\s+)?to\s+$", lead)
        if m and re.fullmatch(r"\s+(?:[a-z&]+\s+){0,3}?from\s+", gap):     # 'rose to X of revenue from Y'
            word = m.group(1)
        elif m := re.fullmatch(r",?\s+(?:[a-z]+\s+){0,2}?" + DIRECTION + r"\s+from\s+", gap):  # 'X, up from Y'
            word = m.group(1)
        elif re.fullmatch(r"\s+to\s+", gap):                                 # 'fell from Y to X'
            m = re.search(DIRECTION + r"\s+(?:[a-z]+\s+)?from\s+$", lead)
            word, new, old = (m.group(1) if m else None), (i + 1, f2), (i, f1)
        if word:
            paired.add(new[0])
            against(word, new[1], old[1])

    # b2) 'buybacks rose to USD 170.8m [F:cur.buybacks].' with no 'from': the only other figure the pack has
    #     for buybacks is last year's, so that is what it rose from. (Not for measures that also have
    #     trend quarters: 'gross margin fell to 44.9%' may mean from Q1 FY2027's 49.5%.)
    for i, ((fact, written, start, end), lead) in enumerate(zip(matched, leads)):
        prefix, _, measure = fact["id"].partition(".")
        m = re.search(DIRECTION + r"\s+(?:[a-z]+\s+)?to\s+$", lead)
        same_measure = {f for f in facts if f.partition(".")[2] == measure}
        if prefix == "cur" and m and i not in paired and same_measure == {fact["id"], "ly." + measure}:
            against(m.group(1), fact, facts["ly." + measure])
    return errors


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
    matched = []  # (fact, the value as written, where it starts, where its [F:id] ends), for step 3b
    for m in CITATION.finditer(draft):
        fact_id = m.group(1)
        fact = facts.get(fact_id)
        if fact is None:
            errors.append(f"[F:{fact_id}] does not exist in the facts pack. Use only ids from the pack.")
            cleared.append((m.start(), m.end()))
            continue
        before = draft[:m.start()].rstrip()
        shown = fact["display"]
        # the value as displayed, or without its sign when the words say "fell" / "rose".
        # The exact display is tried first, so "-0.1%" is read with its minus, not as "0.1%".
        allowed = [shown, shown.replace("-", "", 1), shown.replace("+", "", 1)]
        found = None
        for value in allowed:
            # (?<![\d.,]) stops "15.5%" from counting as "5.5%"
            hit = re.search(r"(?<![\d.,])" + re.escape(value) + r"$", before)
            if hit:
                found = hit
                break
        if found:
            cleared.append((found.start(), m.end()))
            matched.append((fact, found.group(), found.start(), m.end()))
        else:
            errors.append(f"[F:{fact_id}] must come right after its value {shown} "
                          f"({fact['label']}, {fact['period']}). The text before it is: '...{before[-30:]}'.")
            cleared.append((m.start(), m.end()))

    # 3b) The words around a correct number must agree with it: direction and period
    errors += check_words(draft, matched, facts)

    # 3c) Plain Markdown only: the report turns the review into HTML, so no HTML may come in with it
    for m in HTML_TAG.finditer(draft):
        errors.append(f"Remove the HTML '{m.group()}'. Write plain Markdown only.")

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