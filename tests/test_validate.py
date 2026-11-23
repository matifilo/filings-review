"""Tests for the checker: it must pass a correct review and catch every kind of mistake.

Run from the project folder:  .venv\\Scripts\\python -m pytest
The fixtures are frozen copies of a real facts pack and an approved review,
so these tests do not change when new quarterly data arrives.
"""
import json
from pathlib import Path

import pytest

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