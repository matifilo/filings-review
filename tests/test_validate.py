"""Tests for the checker: it must pass a correct review and catch every kind of mistake.

Run from the project folder:  .venv\\Scripts\\python -m pytest
The fixtures are frozen copies of a real facts pack and of the four reviews Claude wrote from it,
so these tests do not change when new quarterly data arrives.
"""
import json
from pathlib import Path

import pytest

import eval_checker
import validate

FIXTURES = Path(__file__).parent / "fixtures"
PACK = json.loads((FIXTURES / "facts_pack.json").read_text(encoding="utf-8"))
GOOD = (FIXTURES / "review.md").read_text(encoding="utf-8")
SENTENCE = "The pack does not show why growth slowed."  # a sentence with no numbers, used for edits


def errors_after(old, new):
    """Make one change to the approved review and return what the checker says about it."""
    assert old in GOOD, f"the fixture no longer contains {old!r}"
    return validate.check(GOOD.replace(old, new, 1), PACK)


def test_approved_review_passes():
    assert validate.check(GOOD, PACK) == []


def test_wrong_number_is_caught():
    errors = errors_after("44.9% [F:cur.gross_margin]", "45.9% [F:cur.gross_margin]")
    assert any("[F:cur.gross_margin] must come right after its value 44.9%" in e for e in errors)


def test_number_that_only_ends_the_same_is_caught():
    # "15.5%" ends with "5.5%", but it is a different number
    errors = errors_after("rose 5.5% [F:cur.net_income_yoy]", "rose 15.5% [F:cur.net_income_yoy]")
    assert any("[F:cur.net_income_yoy] must come right after" in e for e in errors)


def test_unknown_fact_id_is_caught():
    errors = errors_after("[F:ly.cash]", "[F:ly.cash_balance]")
    assert any("[F:ly.cash_balance] does not exist" in e for e in errors)


def test_number_without_a_source_is_caught():
    errors = errors_after(SENTENCE, "Growth slowed for 3 quarters.")
    assert any("The number '3' has no [F:id] source" in e for e in errors)


def test_period_names_are_not_numbers():
    # Q4, 6M FY2027 and FY2026 contain digits but are names of periods (a false alarm fixed in Phase 6)
    assert errors_after(SENTENCE, "Q4 and 6M FY2027 differ from FY2026.") == []


def test_sign_may_be_dropped_when_the_words_say_it_fell():
    # the fact is -0.5%: "fallen 0.5%" and "-0.5%" are both accepted
    assert "fallen 0.5% [F:ly.inventory_yoy]" in GOOD
    assert errors_after("fallen 0.5%", "fallen -0.5%") == []


@pytest.mark.parametrize("placeholder", ["{{revenue}}", "TBD", "TODO"])
def test_placeholders_are_caught(placeholder):
    errors = errors_after(SENTENCE, f"Growth was {placeholder}.")
    assert any("placeholder" in e for e in errors)


def test_sections_must_be_complete_and_in_order():
    errors = errors_after("## What to watch next quarter", "## Outlook")
    assert any("The sections must be exactly" in e for e in errors)


def test_flagged_figure_must_be_reported():
    caveats = GOOD.split("## Data caveats", 1)[1]
    errors = validate.check(GOOD.replace(caveats, "\n\n- None.\n"), PACK)
    assert any("Data caveats must report the flagged figure" in e for e in errors)


def test_too_short_a_review_is_caught():
    headline_only = GOOD.split("## Growth and profitability")[0]
    errors = validate.check(headline_only, PACK)
    assert any("words; it must have 450 to 650" in e for e in errors)
    assert any("cited numbers; use at least 12" in e for e in errors)


# ---------- the words next to a correct number (direction, comparisons, periods) and HTML ----------

@pytest.mark.parametrize("name", ["draft_phase5.md", "review_phase6.md", "review.md", "review_published.md"])
def test_every_real_review_passes(name):
    # the four reviews Claude actually wrote: a new rule that rejects one of them is a false alarm
    assert validate.check((FIXTURES / name).read_text(encoding="utf-8"), PACK) == []


def test_reversed_direction_is_caught():
    # the outside review's example: net income grew 5.5%, the text says it fell
    errors = errors_after("net income rose 5.5% [F:cur.net_income_yoy]", "net income fell 5.5% [F:cur.net_income_yoy]")
    assert any("the word says it went down, but the fact is 5.5%" in e for e in errors)


def test_minus_sign_dropped_without_a_word_that_says_so_is_caught():
    errors = errors_after("at -0.1% [F:q4_fy2025.revenue_yoy]", "at 0.1% [F:q4_fy2025.revenue_yoy]")
    assert any("is -0.1%. Keep the minus sign" in e for e in errors)


def test_direction_against_last_year_is_caught():
    errors = errors_after("Selling and marketing rose to 18.0%", "Selling and marketing fell to 18.0%")
    assert any("'fell' does not fit the numbers: 18.0% [F:cur.selling_pct] is higher than 16.8%" in e for e in errors)


def test_current_and_earlier_figures_swapped_are_caught():
    errors = errors_after("fell to USD 163.6m [F:cur.operating_cash_flow] from USD 228.8m [F:ly.operating_cash_flow]",
                          "fell to USD 228.8m [F:ly.operating_cash_flow] from USD 163.6m [F:cur.operating_cash_flow]")
    assert any("are the wrong way round: 'from' must introduce the earlier figure" in e for e in errors)


def test_wrong_period_is_caught():
    # the outside review's other example: the current revenue figure said to be another quarter's
    errors = errors_after("[F:cur.revenue] in Q2 FY2027", "[F:cur.revenue] in Q1 FY2027")
    assert any("is the Q2 FY2027 figure (Revenue), but the text names Q1 FY2027" in e for e in errors)


def test_current_figure_called_a_year_ago_is_caught():
    errors = errors_after(SENTENCE, "Revenue was USD 1,218.8m [F:cur.revenue] a year ago.")
    assert any("but the text says it is from a year ago" in e for e in errors)


def test_html_is_caught():
    errors = errors_after(SENTENCE, "Growth <b>slowed</b>.")
    assert any("Remove the HTML '<b>'" in e for e in errors)


@pytest.mark.parametrize("sentence", [
    "The cash conversion cycle improved to 44 days [F:cur.cash_conversion_cycle_days] "
    "from 46 days [F:ly.cash_conversion_cycle_days].",                       # 'improved' is not 'up'
    "Operating cash flow fell from USD 228.8m [F:ly.operating_cash_flow] to USD 163.6m [F:cur.operating_cash_flow].",
    "A year earlier, net margin was 14.4% [F:ly.net_margin], against 14.8% [F:cur.net_margin] now.",
    "Gross margin fell back to 44.9% [F:cur.gross_margin] from 49.5% [F:q1_fy2027.gross_margin] in Q1 FY2027.",
    "That was a decline of 0.1% [F:q4_fy2025.revenue_yoy].",
    "The 0.1% [F:q4_fy2025.revenue_yoy] fall in Q4 FY2025 was the only one.",
    "For 6M FY2027, net income rose 31.3% [F:ytd.net_income_yoy] to USD 415.7m [F:ytd.net_income].",
    "Compared with Q2 FY2026, revenue rose to USD 1,218.8m [F:cur.revenue].",
    "Q1 FY2027 and Q2 FY2027 gross margins were 49.5% [F:q1_fy2027.gross_margin] and 44.9% [F:cur.gross_margin].",
])
def test_correct_wording_is_not_flagged(sentence):
    assert errors_after(SENTENCE, sentence) == []


def test_error_injection_catch_rates():
    # the table in the README: if a change to the checker makes it miss more, or flag correct text, this fails
    results, (edits, false_alarms), _, _ = eval_checker.run()
    rate = {label: caught / total for label, (total, caught) in results.items()}
    assert rate["Wrong number"] == 1
    assert rate["Current and earlier figure swapped"] == 1
    assert rate["Raw HTML"] == 1
    assert rate["Wrong direction (word or minus sign)"] >= 0.9
    assert rate["Wrong period named"] >= 0.9
    assert false_alarms == 0
