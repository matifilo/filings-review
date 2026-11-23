"""Phase 7: turn the approved review into a report you can open in a browser or print to PDF.

It reads only output/review.md, output/facts_pack.json and output/validation_log.json,
so the report cannot show a number that is not in the facts pack.
"""
import html
import json
import re
from datetime import date
from pathlib import Path
from string import Template

import markdown

approved = Path("output/review.md")
if not approved.exists():
    raise SystemExit("No approved review. Run review.py first - only a draft that passes the checker is used.")
review = approved.read_text(encoding="utf-8")
pack = json.loads(Path("output/facts_pack.json").read_text(encoding="utf-8"))
log = json.loads(Path("output/validation_log.json").read_text(encoding="utf-8"))
facts = {f["id"]: f for f in pack["facts"]}

# 1) Commentary: Markdown -> HTML, then every "value [F:id]" becomes a number linked to its source
CITED_VALUE = re.compile(r"((?:USD )?[+-]?[\d,.]+(?:m|%|x| pp| days)?) \[F:([\w.]+)\]")
cited = []  # fact ids in the order they first appear


def link(m):
    value, fact = m.group(1), facts[m.group(2)]
    if fact["id"] not in cited:
        cited.append(fact["id"])
    tip = html.escape(f"{fact['label']}, {fact['period']} (fact {fact['id']})")
    return f'<a class="num" href="#f-{fact["id"]}" title="{tip}">{value}</a>'


# Markdown needs an empty line before a list, or the list is printed as part of the paragraph
review_md = re.sub(r"(?m)^(?!- )(.+)\n(?=- )", r"\1\n\n", review)
commentary = CITED_VALUE.sub(link, markdown.markdown(review_md))
numbers = len(re.findall(r"\[F:", review))

# 2) Headline tiles: this quarter, with the same quarter last year underneath
tiles = ""
for fact_id, sub_id in (("revenue", "revenue_yoy"), ("gross_margin", None),
                        ("operating_margin", None), ("free_cash_flow", None)):
    cur, ly = facts[f"cur.{fact_id}"], facts[f"ly.{fact_id}"]
    sub = (f"{facts['cur.' + sub_id]['display']} year on year" if sub_id
           else f"{ly['period']}: {ly['display']}")
    tiles += (f'<div class="tile"><div class="label">{cur["label"]}</div>'
              f'<div class="value">{cur["display"]}</div><div class="sub">{sub}</div></div>')

# 3) Trend charts: one small chart per measure, drawn as SVG (no chart library needed)
flagged = {(f["period"], f["metric"].lower()) for f in pack["data_flags"]}


def chart(metric):
    # the trend facts are the ones named after a quarter, e.g. q2_fy2027.gross_margin
    points = [f for f in pack["facts"] if re.fullmatch(r"q\d_fy\d{4}\." + metric, f["id"])]
    values = [p["value"] for p in points]
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.2 or 1
    lo, hi = lo - pad, hi + pad
    W, H, left, right, top, bottom = 360, 150, 10, 64, 14, 26
    def x(i): return left + i * (W - left - right) / (len(points) - 1)
    def y(v): return top + (hi - v) * (H - top - bottom) / (hi - lo)

    svg = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{points[0]["label"]}, last eight quarters">']
    svg.append(f'<line x1="{left}" x2="{W - right}" y1="{H - bottom}" y2="{H - bottom}" stroke="#e1e0d9"/>')
    if lo < 0 < hi:  # growth can be negative: show where zero is
        svg.append(f'<line x1="{left}" x2="{W - right}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="#c3c2b7"/>')
    line = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
    svg.append(f'<path d="{line}" fill="none" stroke="#2a78d6" stroke-width="2" '
               'stroke-linejoin="round" stroke-linecap="round"/>')
    for i, p in enumerate(points):
        is_flag = (p["period"], p["label"].lower()) in flagged
        color = "#d03b3b" if is_flag else "#2a78d6"
        svg.append(f'<circle cx="{x(i):.1f}" cy="{y(p["value"]):.1f}" r="4" fill="{color}" '
                   f'stroke="#fcfcfb" stroke-width="2"><title>{p["period"]}: {p["display"]}'
                   f'{" (flagged)" if is_flag else ""}</title></circle>')
        if is_flag:
            svg.append(f'<text x="{x(i):.1f}" y="{y(p["value"]) - 9:.1f}" font-size="10" '
                       f'text-anchor="middle" fill="#d03b3b">flagged</text>')
    last = points[-1]
    svg.append(f'<text x="{x(len(points) - 1) + 8:.1f}" y="{y(last["value"]) + 4:.1f}" font-size="12" '
               f'fill="#0b0b0b">{last["display"]}</text>')
    for i in (0, len(points) - 1):  # name the first and last quarter on the axis
        svg.append(f'<text x="{x(i):.1f}" y="{H - 8}" font-size="10" fill="#52514e" '
                   f'text-anchor="{"start" if i == 0 else "end"}">{points[i]["period"]}</text>')
    svg.append("</svg>")
    return f'<div class="chart"><div class="title">{points[0]["label"]}</div>{"".join(svg)}</div>'


charts = "".join(chart(m) for m in ("revenue_yoy", "gross_margin", "operating_margin", "dio_days"))

# 4) Key figures table and the sources appendix
kpi_rows = ""
for fact_id, fact in facts.items():
    if fact_id.startswith("cur.") and "ly." + fact_id[4:] in facts:
        kpi_rows += (f'<tr><td>{fact["label"]}</td><td class="n">{fact["display"]}</td>'
                     f'<td class="n">{facts["ly." + fact_id[4:]]["display"]}</td></tr>')
source_rows = "".join(
    f'<tr id="f-{i}"><td><code>{i}</code></td><td>{facts[i]["label"]}</td>'
    f'<td>{facts[i]["period"]}</td><td class="n">{facts[i]["display"]}</td></tr>' for i in cited)

# 5) Fill the template and save
final = log[-1]
check = (f"<strong>Checked:</strong> all {numbers} numbers in the commentary match their source facts "
         f"(passed in round {final['round']} of the write-check-revise loop, {final['time'].replace('T', ' ')}). "
         "Hover over a number to see its source; click it to jump to the source table.")
page = Template(Path("templates/report.html").read_text(encoding="utf-8")).substitute(
    company=pack["company"]["name"], ticker=pack["company"]["ticker"],
    period=pack["latest_period"], period_ly=facts["ly.revenue"]["period"],
    period_end=pack["latest_period_end"], snapshot=pack["snapshot"], generated=date.today().isoformat(),
    check=check, tiles=tiles, commentary=commentary, charts=charts,
    kpi_rows=kpi_rows, source_rows=source_rows, method=" ".join(pack["method_notes"]),
)
out = Path("output/report.html")
out.write_text(page, encoding="utf-8")
print(f"Report: {numbers} cited numbers linked to {len(cited)} facts -> {out}")