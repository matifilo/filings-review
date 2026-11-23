"""Phase 7: lay the approved review out like a research note, then print it to PDF.

It reads only output/review.md, output/facts_pack.json and output/validation_log.json,
so the report cannot show a number that is not in the facts pack.
"""
import html
import json
import math
import re
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path
from string import Template

import markdown

import config

approved = Path("output/review.md")
if not approved.exists():
    raise SystemExit("No approved review. Run review.py first - only a draft that passes the checker is used.")
review = approved.read_text(encoding="utf-8")
pack = json.loads(Path("output/facts_pack.json").read_text(encoding="utf-8"))
log = json.loads(Path("output/validation_log.json").read_text(encoding="utf-8"))
facts = {f["id"]: f for f in pack["facts"]}
flagged = {(f["period"], f["metric"].lower()) for f in pack["data_flags"]}
NAVY, MIST, FLAG, SOFT, RULE = "#0f2a44", "#a9b7c4", "#b4461a", "#4d5b69", "#d9dfe5"


def short(fact):
    """The value without 'USD', 'm' or 'days', for tables whose heading already gives the unit."""
    return re.sub(r"^USD |m$| days$", "", fact["display"])


# 1) Commentary: every [F:id] becomes a small note number that links to its line in the notes list
notes = []  # fact ids, in the order they first appear


def cite(m):
    fact_id = m.group(1)
    if fact_id not in notes:
        notes.append(fact_id)
    n = notes.index(fact_id) + 1
    tip = html.escape(f"{facts[fact_id]['label']}, {facts[fact_id]['period']}")
    return f'<sup class="n"><a href="#n{n}" title="{tip}">{n}</a></sup>'


def to_html(md):
    md = re.sub(r"(?m)^(?!- )(.+)\n(?=- )", r"\1\n\n", md)  # Markdown needs a blank line before a list
    return re.sub(r"\s*\[F:([\w.]+)\]", cite, markdown.markdown(md))


parts = re.split(r"(?m)^## (.+)$", review)  # ["", "Headline", "text", "Growth and ...", "text", ...]
sections = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}

# The first sentence of the Headline becomes the title; the rest goes underneath it
first, rest = re.match(r"(.+?\.)\s+(.*)", sections["Headline"], re.S).groups()
title = to_html(first).removeprefix("<p>").removesuffix("</p>")
dek = to_html(rest)
main_text = "".join(f"<h2>{name}</h2>{to_html(sections[name])}"
                    for name in ("Growth and profitability", "Working capital and cash"))
lower_text = "".join(f'<section class="blk"><h2>{name}</h2>{to_html(sections[name])}</section>'
                     for name in ("What to watch next quarter", "Data caveats"))

# 2) Sidebar: key data, verification, data checks
KEY_DATA = [("Revenue, USD m", "revenue"), ("Revenue growth", "revenue_yoy"),
            ("Gross margin", "gross_margin"), ("Operating margin", "operating_margin"),
            ("Net income, USD m", "net_income"), ("Free cash flow, USD m", "free_cash_flow"),
            ("Cash, USD m", "cash"), ("Inventory days", "dio_days"),
            ("Cash cycle, days", "cash_conversion_cycle_days"), ("Cash conversion", "cash_conversion_ttm")]
key_rows = "".join(f"<tr><td>{label}</td><td>{short(facts['cur.' + k])}</td><td>{short(facts['ly.' + k])}</td></tr>"
                   for label, k in KEY_DATA)
numbers = len(re.findall(r"\[F:", review))
final = log[-1]
verification = (f"All {numbers} numbers in the text match the source data ({len(notes)} distinct facts). "
                f"Passed the automatic check on draft {final['round']}.")
flag_notes = "".join(f'<p class="flag"><em>a</em> {f["period"]} {f["metric"].lower()} of {f["value"]}: '
                     f'compared with the {f["compared_with"]}. Verify against the filing.</p>'
                     for f in pack["data_flags"]) or '<p class="flag">No unusual figures.</p>'


# 3) Exhibit 1: eight-quarter table; flagged cells get an "a"
def trend(metric):
    """The eight trend facts for one measure, oldest first (ids like q2_fy2027.gross_margin)."""
    return [f for f in pack["facts"] if re.fullmatch(r"q\d_fy\d{4}\." + metric, f["id"])]


def mark(f):
    return '<sup class="fl">a</sup>' if (f["period"], f["label"].lower()) in flagged else ""


quarters = [f["period"] for f in trend("gross_margin")]
quarter_heads = "".join(f"<th>{q.replace('FY20', 'FY')}</th>" for q in quarters)  # Q2 FY2027 -> Q2 FY27
summary_rows = "".join(
    f"<tr><td>{label}</td>" + "".join(f"<td>{short(f)}{mark(f)}</td>" for f in trend(metric)) + "</tr>"
    for label, metric in (("Revenue growth, year on year", "revenue_yoy"), ("Gross margin", "gross_margin"),
                          ("Operating margin", "operating_margin"), ("Inventory days (TTM)", "dio_days")))


# 4) Exhibits 2-4: charts drawn as SVG by hand (no chart library)
def ticks_for(lo, hi):
    """Four to six round numbers that cover lo..hi, e.g. 0, 10, 20, 30, 40, 50."""
    for step in (0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100):
        if (hi - lo) / step <= 5:
            break
    first, last = math.floor(lo / step) * step, math.ceil(hi / step) * step
    return [first + i * step for i in range(round((last - first) / step) + 1)]


def chart(series, bars=False):
    """series: list of (name, colour, facts). Bars for one series, lines otherwise."""
    W, H, left, right, top, bottom = 210, 128, 18, 42, 6, 24
    values = [f["value"] for _, _, pts in series for f in pts]
    ticks = ticks_for(min(values + [0]) if bars else min(values), max(values))
    lo, hi = ticks[0], ticks[-1]
    n = len(series[0][2])
    slot = (W - left - right) / n
    def x(i): return left + slot * (i + 0.5)
    def y(v): return top + (hi - v) * (H - top - bottom) / (hi - lo)

    s = [f'<svg viewBox="0 0 {W} {H}" font-family="Source Sans 3, Segoe UI, sans-serif" role="img">']
    for t in ticks:  # light horizontal gridlines with their values on the left
        s.append(f'<line x1="{left}" x2="{W - right}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{RULE}" stroke-width=".6"/>'
                 f'<text x="{left - 4}" y="{y(t) + 3:.1f}" font-size="8" fill="{SOFT}" text-anchor="end">{t:g}</text>')
    for i, f in enumerate(series[0][2]):  # two-line quarter labels: Q3 / FY25
        q, fy = f["period"].split()
        s.append(f'<text x="{x(i):.1f}" y="{H - 13}" font-size="7.5" fill="{SOFT}" text-anchor="middle">{q}</text>'
                 f'<text x="{x(i):.1f}" y="{H - 4}" font-size="7.5" fill="{SOFT}" text-anchor="middle">{fy.replace("FY20", "FY")}</text>')
    for name, colour, pts in series:
        if bars:  # muted bars, the quarter under review in navy
            for i, f in enumerate(pts):
                top_y, base_y = sorted((y(f["value"]), y(0)))
                c = NAVY if i == n - 1 else MIST
                s.append(f'<rect x="{x(i) - slot * .3:.1f}" y="{top_y:.1f}" width="{slot * .6:.1f}" '
                         f'height="{max(base_y - top_y, .8):.1f}" fill="{c}"><title>{f["period"]}: {f["display"]}</title></rect>')
        else:
            d = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(f['value']):.1f}" for i, f in enumerate(pts))
            s.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="1.5" stroke-linejoin="round"/>')
            for i, f in enumerate(pts):
                s.append(f'<circle cx="{x(i):.1f}" cy="{y(f["value"]):.1f}" r="5" fill="transparent">'
                         f'<title>{f["period"]}: {f["display"]}</title></circle>')
        for i, f in enumerate(pts):  # ring flagged quarters
            if mark(f):
                s.append(f'<circle cx="{x(i):.1f}" cy="{y(f["value"]):.1f}" r="3.2" fill="#fff" stroke="{FLAG}" stroke-width="1.2"/>'
                         f'<text x="{x(i) + 5:.1f}" y="{y(f["value"]) - 4:.1f}" font-size="8" font-style="italic" fill="{FLAG}">a</text>')
        last = pts[-1]  # label the latest value at the right-hand end, with the series name above it
        end_y = y(last["value"])
        if name:
            s.append(f'<text x="{W - right + 4}" y="{end_y - 3:.1f}" font-size="7.5" fill="{SOFT}">{name}</text>')
        s.append(f'<text x="{W - right + 4}" y="{end_y + (8 if name else 3):.1f}" font-size="8.5" font-weight="600" '
                 f'fill="{colour}">{short(last)}</text>')
    s.append("</svg>")
    return "".join(s)


chart_growth = chart([("", NAVY, trend("revenue_yoy"))], bars=True)
chart_margins = chart([("Gross", NAVY, trend("gross_margin")), ("Operating", SOFT, trend("operating_margin"))])
chart_inventory = chart([("", NAVY, trend("dio_days"))])

# 5) Notes: the source of every number, in order of first appearance
note_rows = "".join(f'<li id="n{n}"><span class="nn">{n}</span><span class="nl">{facts[i]["label"]}, '
                    f'{facts[i]["period"]}</span><span class="nv">{facts[i]["display"]}</span></li>'
                    for n, i in enumerate(notes, 1))
method = ("Figures come from the company's 10-Q and 10-K filings (SEC XBRL data), loaded into SQLite. "
          "Standalone quarters, margins, growth and working-capital days are calculated in SQL. "
          f"The commentary is written by {config.MODEL} from a pack of {len(facts)} approved facts: it may not "
          "calculate numbers and must cite a fact for each one. A program checks every number against the fact "
          "it cites and sends errors back until the draft passes. Unusual margins are flagged before writing.")

# 6) Fill the template, save the HTML, print the PDF
page = Template(Path("templates/report.html").read_text(encoding="utf-8")).substitute(
    company=pack["company"]["name"], ticker=pack["company"]["ticker"], period=pack["latest_period"],
    title=title, dek=dek, main_text=main_text, lower_text=lower_text, key_rows=key_rows,
    verification=verification, flag_notes=flag_notes, quarter_heads=quarter_heads, summary_rows=summary_rows,
    chart_growth=chart_growth, chart_margins=chart_margins, chart_inventory=chart_inventory,
    note_rows=note_rows, method=method, generated=date.today().strftime("%d %B %Y").lstrip("0"),
)
html_path, pdf_path = Path("output/report.html"), Path("output/report.pdf")
html_path.write_text(page, encoding="utf-8")

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
pdf_path.unlink(missing_ok=True)  # never leave an old PDF behind if printing fails
with tempfile.TemporaryDirectory() as profile:
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                    "--no-pdf-header-footer", "--virtual-time-budget=15000",
                    f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
                   capture_output=True, timeout=120)
    size = -1
    for _ in range(60):  # Edge can return before the file is fully written: wait until its size stops changing
        time.sleep(0.5)
        new = pdf_path.stat().st_size if pdf_path.exists() else -1
        if new > 0 and new == size:
            break
        size = new
if not pdf_path.exists():
    raise SystemExit("Edge did not produce the PDF. Is Microsoft Edge installed in the usual place?")
print(f"Report: {numbers} numbers linked to {len(notes)} notes -> {html_path} and {pdf_path}")