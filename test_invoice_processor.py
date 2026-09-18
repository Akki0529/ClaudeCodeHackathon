# test_invoice_processor.py
# Scenario A — regression tests for the invoice processor refactor.
#
# WHAT THIS IS
#   A small safety net that checks your refactored code still does what the
#   original did — the single most important thing when modernising legacy code.
#   Run it early and often. Green tests are not the goal; correct, readable code
#   that happens to stay green is the goal.
#
# THE CONTRACT
#   Your refactored module must expose ONE function:
#
#       summarize(path="transactions.csv") -> dict
#
#   returning a dict with these keys:
#       total            float   — sum of all valid amounts, after currency conversion
#       by_category      dict     — {normalised category: total amount}
#       by_employee      dict     — {employee_id: total amount}
#       by_month         dict     — {"YYYY-MM": total amount}
#       flagged          list     — rows over the high threshold OR meals over the meal threshold
#       needs_approval   list     — rows in the approval band (over approval threshold, not yet flagged)
#
#   How you structure everything else is yours to decide. Keep the thresholds
#   (500 / 2500 / 5000), the currency rates (EUR 1.08, GBP 1.26, USD 1.0) and the
#   category normalisation rules from the original.
#
# HOW TO RUN
#   pip install pytest    (once)
#   pytest test_invoice_processor.py -v
#
# NOTE ON TEST 7
#   One test encodes a fix, not the original behaviour. The legacy code has a
#   latent bug. Test 7 passes only when that bug is fixed. Finding and fixing it
#   is part of the exercise — we are not telling you where it is.

import csv
import os
import tempfile

import pytest

invoice_processor = pytest.importorskip(
    "invoice_processor",
    reason="Your refactored module must be importable as invoice_processor.py",
)

SAMPLE = os.path.join(os.path.dirname(__file__), "transactions.csv")


def _summarize(path=SAMPLE):
    assert hasattr(invoice_processor, "summarize"), (
        "Expected a summarize(path) function — see the contract at the top of this file."
    )
    return invoice_processor.summarize(path)


def _write_csv(rows):
    """Write a tiny CSV with the standard header and return its path."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "employee_id", "category", "description", "amount", "currency"])
        w.writerows(rows)
    return path


# 1 — Total spend is preserved (currency-converted sum across the sample data).
def test_total_is_preserved():
    result = _summarize()
    assert result["total"] == pytest.approx(46736.97, abs=0.05)


# 2 — Currency conversion is applied at the original rates.
def test_currency_conversion():
    path = _write_csv([
        ["2026-03-01", "E1", "Software", "x", "100.00", "USD"],
        ["2026-03-01", "E1", "Software", "x", "100.00", "EUR"],
        ["2026-03-01", "E1", "Software", "x", "100.00", "GBP"],
    ])
    try:
        result = _summarize(path)
        assert result["total"] == pytest.approx(100 + 108 + 126, abs=0.01)
    finally:
        os.remove(path)


# 3 — Unknown currencies are skipped, not crashed on.
def test_unknown_currency_skipped():
    path = _write_csv([
        ["2026-03-01", "E1", "Software", "x", "100.00", "USD"],
        ["2026-03-01", "E1", "Software", "x", "999.00", "JPY"],
    ])
    try:
        result = _summarize(path)
        assert result["total"] == pytest.approx(100.00, abs=0.01)
    finally:
        os.remove(path)


# 4 — Category aliases collapse to canonical names.
def test_category_normalisation():
    path = _write_csv([
        ["2026-03-01", "E1", "Travel-Air", "x", "10.00", "USD"],
        ["2026-03-01", "E1", "Travel-Ground", "x", "10.00", "USD"],
        ["2026-03-01", "E1", "Travel - Air", "x", "10.00", "USD"],
        ["2026-03-01", "E1", "T&E", "x", "10.00", "USD"],
        ["2026-03-01", "E1", "meals", "x", "10.00", "USD"],
        ["2026-03-01", "E1", "Meal", "x", "10.00", "USD"],
        ["2026-03-01", "E1", "client-meal", "x", "10.00", "USD"],
    ])
    try:
        cats = _summarize(path)["by_category"]
        assert cats.get("Travel") == pytest.approx(40.00, abs=0.01)
        assert cats.get("Meals") == pytest.approx(30.00, abs=0.01)
        assert "Travel-Air" not in cats and "meals" not in cats
    finally:
        os.remove(path)


# 5 — Category totals on the sample data are preserved.
def test_category_totals():
    cats = _summarize()["by_category"]
    assert cats["Travel"] == pytest.approx(26676.08, abs=0.05)
    assert cats["Meals"] == pytest.approx(5505.43, abs=0.05)
    assert cats["Software"] == pytest.approx(7499.99, abs=0.05)
    assert cats["Conference"] == pytest.approx(5100.00, abs=0.05)


# 6 — The approval band (over 2500, not yet flagged) holds the right count.
def test_needs_approval_band():
    result = _summarize()
    assert len(result["needs_approval"]) == 5


# 7 — A meal over the high threshold must be flagged ONCE, not twice.
#     This fails on the original code. Fixing it is the point.
def test_meals_not_double_flagged():
    path = _write_csv([
        ["2026-03-01", "E1", "Meals", "Very expensive client dinner", "6000.00", "USD"],
    ])
    try:
        flagged = _summarize(path)["flagged"]
        meal_hits = [r for r in flagged if "6000" in str(r) or 6000.0 in (
            [r.get("amount")] if isinstance(r, dict) else list(r)
        )]
        assert len(meal_hits) == 1, (
            "A single high-value meal should appear once in 'flagged', not twice."
        )
    finally:
        os.remove(path)
