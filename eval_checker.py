"""Error injection: break real reviews on purpose and count how many the checker catches.

Takes the four real reviews Claude wrote from the same facts pack while this project was built
(frozen in tests/fixtures/; each passes the checker), breaks each one in ONE place at a time, in the
ways a real draft can go wrong, and runs the checker on every broken copy. It also makes harmless
edits that must still pass, to count false alarms. No AI involved, costs nothing:

    .venv\\Scripts\\python eval_checker.py            the table
    .venv\\Scripts\\python eval_checker.py --missed   also every broken copy that got through
"""
import json
import re
import sys
from pathlib import Path

import validate

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
PACK = json.loads((FIXTURES / "facts_pack.json").read_text(encoding="utf-8"))
REVIEWS = {name: (FIXTURES / name).read_text(encoding="utf-8")
           for name in ("draft_phase5.md", "review_phase6.md", "review.md", "review_published.md")}
FACTS = {f["id"]: f for f in PACK["facts"]}

# A cited number: the value written right before its [F:id], e.g. "USD 1,218.8m [F:cur.revenue]"
CITED = re.compile(r"((?:USD )?[+-]?\d[\d,.]*(?:%| pp| days|m|x)?)(\s*)\[F:([\w.]+)\]")
PERIOD_NAME = r"(?:Q[1-4]|\d{1,2}M) FY\d{4}"
# Words that say which way a number moved, and their opposites (used to break and to rephrase)
OPPOSITE = {"rose": "fell", "fell": "rose", "risen": "fallen", "fallen": "risen", "up": "down", "down": "up",
            "grew": "shrank", "increased": "decreased", "decreased": "increased", "improved": "worsened",
            "gain": "loss", "higher": "lower", "lower": "higher", "eased": "rose", "declined": "rose",
            "lengthened": "shortened", "shortened": "lengthened", "jump": "drop", "dropped": "rose"}
SAME_WAY = {"rose": "increased", "fell": "declined", "grew": "increased", "improved": "rose", "eased": "declined",
            "lengthened": "rose", "shortened": "fell", "gain": "rise", "fallen": "declined", "risen": "increased"}
# A direction word that is about a cited number: at most a few small words between them
ABOUT_A_NUMBER = r"(?=\s+(?:(?:to|from|by|only|of|just)\s+)*(?:USD\s+)?[+-]?\d[\d,.]*(?:%| pp| days|m|x)?\s*\[F:)"
REASONS = ["because demand in Europe weakened", "driven by higher promotional spending",
           "as retailers cut their orders", "due to a weaker US dollar"]
HTML = ["<b>slowed</b>", "<img src=x onerror=alert(document.domain)>", "<script>alert(document.cookie)</script>",
        '<a href="javascript:alert(document.domain)">see the filing</a>', '<iframe src="https://example.com"></iframe>']


def replace(text, start, end, new):
    return text[:start] + new + text[end:]


def keep_case(word, new):
    return new.capitalize() if word[0].isupper() else new


def earlier_period(period):
    """Q2 FY2027 -> Q1 FY2027, Q1 FY2027 -> Q4 FY2026, 6M FY2027 -> 6M FY2026."""
    q, fy = period.split()
    year = int(fy[2:])
    if q.endswith("M"):
        return f"{q} FY{year - 1}"
    n = int(q[1])
    return f"Q{n - 1} FY{year}" if n > 1 else f"Q4 FY{year - 1}"


def context(text, i):
    """About a line of text around position i, to show what was changed."""
    return "'..." + " ".join(text[max(0, i - 45):i + 35].split()) + "...'"


def sentence_ends(text):
    return [m.start() for m in re.finditer(r"[.!?](?=\s|$)|\n", text)]


# ---------- ways to break a review (each yields: what was changed, the broken text) ----------

def wrong_number(text):
    for m in CITED.finditer(text):
        i = m.start(1) + max(k for k, ch in enumerate(m.group(1)) if ch.isdigit())  # its last digit
        broken = replace(text, i, i + 1, str((int(text[i]) + 1) % 10))
        yield f"{m.group(3)}: {context(broken, i)}", broken


def wrong_direction(text):
    """A direction word next to a cited number turned into its opposite, or a minus sign dropped."""
    for m in re.finditer(r"\b(" + "|".join(OPPOSITE) + r")\b" + ABOUT_A_NUMBER, text, re.I):
        word = m.group(1)
        new = keep_case(word, OPPOSITE[word.lower()])
        broken = replace(text, m.start(1), m.end(1), new)
        yield f"'{word}' -> '{new}': {context(broken, m.start(1))}", broken
    for m in CITED.finditer(text):
        if "-" in m.group(1):
            i = m.start(1) + m.group(1).index("-")
            broken = replace(text, i, i + 1, "")
            yield f"minus sign dropped: {context(broken, i)}", broken


def swapped_pair(text):
    """Two figures of the same kind compared in one phrase ('X from Y', 'X against Y'): swap them."""
    cites = list(CITED.finditer(text))
    for a, b in zip(cites, cites[1:]):
        gap = text[a.end():b.start()]
        if not re.fullmatch(r",?\s+(?:[a-z]+\s+){0,4}?(?:from|against|compared with|versus)\s+", gap):
            continue
        fa, fb = FACTS[a.group(3)], FACTS[b.group(3)]
        if fa["unit"] != fb["unit"] or fa["value"] == fb["value"]:  # swapping 55 days with 55 days changes nothing
            continue
        broken = text[:a.start()] + b.group(0) + gap + a.group(0) + text[b.end():]
        yield f"{a.group(3)} <-> {b.group(3)}: {context(broken, b.start())}", broken


def wrong_period(text):
    """A period named next to a cited number, changed to the quarter before;
    'a year ago' after a number changed to the current quarter."""
    cites = list(CITED.finditer(text))
    ends = sentence_ends(text)
    for m in re.finditer(PERIOD_NAME, text):
        after_a_number = any(0 <= m.start() - c.end() <= 25 and not any(c.end() <= e < m.start() for e in ends)
                             for c in cites)
        before_a_number = any(0 <= c.start() - m.end() <= 50 and not any(m.end() <= e < c.start() for e in ends)
                              for c in cites)
        if after_a_number or before_a_number:
            new = earlier_period(m.group())
            broken = replace(text, m.start(), m.end(), new)
            yield f"'{m.group()}' -> '{new}': {context(broken, m.start())}", broken
    for c in cites:
        ago = re.match(r"\s+a year (?:ago|earlier)", text[c.end():])
        if ago:
            new = f" in {PACK['latest_period']}"
            broken = replace(text, c.end(), c.end() + ago.end(), new)
            yield f"{c.group(3)}: 'a year ago' -> '{new.strip()}': {context(broken, c.end())}", broken


def raw_html(text):
    start = text.index("## Growth and profitability\n\n") + len("## Growth and profitability\n\n")
    for snippet in HTML:
        yield f"inserted {snippet}", replace(text, start, start, snippet + " ")


def invented_cause(text):
    """A reason the filings do not give, added to sentences that cite a number."""
    body = text.split("## Growth and profitability", 1)[1].split("## What to watch", 1)[0]
    offset = text.index(body)
    n = 0
    for m in re.finditer(r"\[F:[\w.]+\]([^.\[\]\n]*)\.(?=\s)", body):  # the end of a sentence whose last number is cited
        pos = offset + m.end() - 1
        reason = REASONS[n % len(REASONS)]
        n += 1
        broken = replace(text, pos, pos, ", " + reason)
        yield f"added '{reason}': {context(broken, pos)}", broken


# ---------- harmless edits: the checker must still pass these ----------

def harmless(text):
    yield "unchanged", text
    for m in re.finditer(r"\b(" + "|".join(SAME_WAY) + r")\b" + ABOUT_A_NUMBER, text, re.I):
        word = m.group(1)
        new = keep_case(word, SAME_WAY[word.lower()])
        yield f"'{word}' -> '{new}'", replace(text, m.start(1), m.end(1), new)
    for m in CITED.finditer(text):
        fact = FACTS[m.group(3)]
        if text[m.end():m.end() + 1] not in (".", ","):
            continue
        yield f"{m.group(3)}: added 'in {fact['period']}'", replace(text, m.end(), m.end(), f" in {fact['period']}")
        if m.group(3).startswith("ly."):
            yield f"{m.group(3)}: added 'a year earlier'", replace(text, m.end(), m.end(), " a year earlier")


def problems(text):
    """The checker's verdict, without the length rule: adding a few words can push a 645-word review
    over the 650 limit, and that would be counted as a catch (or a false alarm) for the wrong reason."""
    return [e for e in validate.check(text, PACK) if not e.startswith("The review has")]


BREAKS = [("Wrong number", wrong_number),
          ("Wrong direction (word or minus sign)", wrong_direction),
          ("Current and earlier figure swapped", swapped_pair),
          ("Wrong period named", wrong_period),
          ("Raw HTML", raw_html),
          ("Cause the filings do not give", invented_cause)]


def run():
    """Return {error type: (broken copies, caught)}, (harmless edits, false alarms), and the details of both."""
    for name, text in REVIEWS.items():
        assert validate.check(text, PACK) == [], f"{name} must pass the checker before it is broken"
    results, missed = {}, []
    for label, make in BREAKS:
        total = caught = 0
        for name, text in REVIEWS.items():
            for what, broken in make(text):
                total += 1
                if problems(broken):
                    caught += 1
                else:
                    missed.append((label, name, what))
        results[label] = (total, caught)
    edits = alarms = 0
    false_alarms = []
    for name, text in REVIEWS.items():
        for what, edited in harmless(text):
            edits += 1
            found = problems(edited)
            if found:
                alarms += 1
                false_alarms.append((name, what, found[0]))
    return results, (edits, alarms), missed, false_alarms


if __name__ == "__main__":
    results, (edits, alarms), missed, false_alarms = run()
    print(f"Error injection: {len(REVIEWS)} real reviews, each broken in one place at a time\n")
    print(f"{'Error type':38}{'Broken copies':>15}{'Caught':>10}{'':>8}")
    for label, (total, caught) in results.items():
        print(f"{label:38}{total:>15}{caught:>10}{caught / total:>8.0%}")
    print(f"{'Harmless edits (must still pass)':38}{edits:>15}{'':>10}  false alarms: {alarms}")
    if "--missed" in sys.argv:
        print("\nGot through the checker:")
        for label, name, what in missed:
            print(f"  [{label}] {name}: {what}")
    for name, what, problem in false_alarms:
        print(f"\nFALSE ALARM in {name} ({what}): {problem}")
