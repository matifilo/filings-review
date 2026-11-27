"""Tests for what a run leaves behind: when it stops early, and when the data has gaps.

Run from the project folder:  .venv\\Scripts\\python -m pytest
Each test runs the real script in a temporary folder with frozen inputs. Neither calls the AI
(the API key is set to empty) nor needs Microsoft Edge (the report is laid out as HTML only).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
OLD_FILES = ["review.md", "report.html", "report.pdf", "draft.md", "validation_log.json"]


def run(script, folder, *args):
    env = dict(os.environ, ANTHROPIC_API_KEY="")  # empty wins over .env, so no request is ever sent
    return subprocess.run([sys.executable, str(ROOT / script), *args], cwd=folder, env=env,
                          capture_output=True, text=True, timeout=60)


def test_a_run_that_stops_before_approval_leaves_no_old_review_or_report(tmp_path):
    # The outside review's case: the API call fails, and last run's review, HTML and PDF were still there
    out = tmp_path / "output"
    out.mkdir()
    for name in OLD_FILES:
        (out / name).write_text("from an earlier run", encoding="utf-8")
    shutil.copy(FIXTURES / "facts_pack.json", out / "facts_pack.json")
    shutil.copytree(ROOT / "prompts", tmp_path / "prompts")

    result = run("review.py", tmp_path)

    assert result.returncode != 0
    assert "No API key found" in result.stdout + result.stderr  # it stopped where we meant it to, no API call
    assert [name for name in OLD_FILES if (out / name).exists()] == []


def test_report_shows_missing_facts_as_na_and_keeps_every_value_under_its_quarter(tmp_path):
    # Cash for the current quarter and gross margin for Q2 FY2026 are missing from the data
    pack = json.loads((FIXTURES / "facts_pack.json").read_text(encoding="utf-8"))
    gone = {"cur.cash", "q2_fy2026.gross_margin"}
    pack["missing"] += [{"id": f["id"], "label": f["label"], "period": f["period"]}
                        for f in pack["facts"] if f["id"] in gone]
    pack["facts"] = [f for f in pack["facts"] if f["id"] not in gone]
    # ...and the review says so instead of citing the cash figure (it does not cite Q2 FY2026 gross margin)
    review = (FIXTURES / "review.md").read_text(encoding="utf-8")
    cash = "Cash and cash equivalents stood at USD 1,507.6m [F:cur.cash], up from USD 1,375.8m [F:ly.cash] a year earlier."
    assert cash in review
    review = review.replace(cash, "Cash and cash equivalents for Q2 FY2027 are not available in the filings data.")

    out = tmp_path / "output"
    out.mkdir()
    (out / "facts_pack.json").write_text(json.dumps(pack), encoding="utf-8")
    (out / "review.md").write_text(review, encoding="utf-8")
    (out / "validation_log.json").write_text(json.dumps([{"round": 1, "passed": True}]), encoding="utf-8")
    shutil.copytree(ROOT / "templates", tmp_path / "templates")

    result = run("report.py", tmp_path, "--html-only")

    assert result.returncode == 0, result.stdout + result.stderr  # it used to stop with KeyError: 'cur.cash'
    page = (out / "report.html").read_text(encoding="utf-8")
    assert "<tr><td>Cash, USD m</td><td>n/a</td><td>1,375.8</td></tr>" in page
    # Exhibit 1: still eight quarters, and the gap sits under Q2 FY26 instead of shifting the row left
    assert re.findall(r"<th>(Q\d FY\d\d)</th>", page) == ["Q3 FY25", "Q4 FY25", "Q1 FY26", "Q2 FY26",
                                                          "Q3 FY26", "Q4 FY26", "Q1 FY27", "Q2 FY27"]
    rows = [re.findall(r"<td>(.*?)</td>", r) for r in re.findall(r"<tr><td>Gross margin</td>(.*?)</tr>", page)]
    exhibit = [cells for cells in rows if len(cells) == 8]  # the key data box has a 'Gross margin' row too
    assert len(exhibit) == 1 and exhibit[0][3] == "n/a"
    assert not (out / "report.pdf").exists()
