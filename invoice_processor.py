"""
invoice_processor — Deloitte expense-report summariser.

Reads a CSV of expense transactions (columns: date, employee_id, category,
description, amount, currency), applies Deloitte expense-policy rules, and
returns a structured summary.  Designed to be imported as a library (via
``summarize()``) or run directly from the command line.

CSV format
----------
Header row is required.  Columns (in order):
    date          ISO-8601 date string, e.g. "2026-03-15"
    employee_id   Employee identifier, e.g. "E1042"
    category      Expense category; legacy aliases are normalised automatically
    description   Free-text description
    amount        Numeric amount in the given currency
    currency      ISO 4217 currency code; only USD, EUR, GBP are supported

Public API
----------
summarize(path) -> ExpenseSummary
    Process the CSV at *path* and return an ExpenseSummary dict.

CLI
---
    python invoice_processor.py [path]   # defaults to transactions.csv
"""

import csv
import datetime
import logging
import sys
from pathlib import Path
from typing import Iterator, NamedTuple, TypedDict

# Only summarize() is part of the public API; everything else is internal.
__all__ = ["summarize"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Policy thresholds — values set by ops; do not alter without sign-off.
# ---------------------------------------------------------------------------
MEAL_FLAG_THRESHOLD = 500    # meals above this amount trigger a review flag
HIGH_VALUE_THRESHOLD = 5000  # any expense above this is auto-flagged, regardless of category
APPROVAL_THRESHOLD = 2500    # expenses in (APPROVAL_THRESHOLD, HIGH_VALUE_THRESHOLD] need manager approval

DEFAULT_PATH = "transactions.csv"

# ---------------------------------------------------------------------------
# Reference data — extend here when new currencies or category aliases appear.
# ---------------------------------------------------------------------------

# Conversion rates to USD.  All output amounts are in USD.
CURRENCY_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.26,
}

# Legacy category names mapped to their current canonical equivalents.
# Categories not listed here are kept as-is.
CATEGORY_ALIASES: dict[str, str] = {
    "Travel-Air": "Travel",
    "Travel-Ground": "Travel",
    "Travel - Air": "Travel",
    "T&E": "Travel",
    "meals": "Meals",
    "Meal": "Meals",
    "client-meal": "Meals",
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Transaction(NamedTuple):
    """A single validated expense row after currency conversion and category normalisation."""

    date: str         # ISO-8601 date string from the source row, e.g. "2026-03-15"
    employee_id: str  # employee identifier, e.g. "E1042"
    category: str     # canonical category name, e.g. "Travel" or "Meals"
    description: str  # free-text description from the source row
    amount: float     # expense amount converted to USD


class ExpenseSummary(TypedDict):
    """Structured return value of ``summarize()``.  All monetary amounts are in USD."""

    total: float                      # sum of all valid, currency-converted amounts
    by_category: dict[str, float]     # canonical category → total spend
    by_employee: dict[str, float]     # employee_id → total spend
    by_month: dict[str, float]        # "YYYY-MM" → total spend
    flagged: list[Transaction]        # rows that exceed policy thresholds
    needs_approval: list[Transaction] # rows in the manager-approval band


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_currency(amount: float, currency: str) -> float | None:
    """Convert *amount* to USD using the policy rate for *currency*.

    Returns ``None`` for unsupported currencies so the caller can skip the row.
    """
    rate = CURRENCY_RATES.get(currency)
    if rate is None:
        return None
    return amount * rate


def normalize_category(category: str) -> str:
    """Return the canonical category name, collapsing any legacy aliases.

    Categories not found in ``CATEGORY_ALIASES`` are returned unchanged.
    """
    return CATEGORY_ALIASES.get(category, category)


def load_transactions(path: Path | str) -> Iterator[Transaction]:
    """Yield validated ``Transaction`` objects from the CSV at *path*.

    Rows that cannot be parsed (missing columns, non-numeric amount) are logged
    as warnings and skipped.  Rows with unsupported currencies are also skipped.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Transaction file not found: {path}")

    with path.open(newline="") as f:
        reader = csv.reader(f)
        next(reader)  # skip the header row
        for row in reader:
            try:
                date_str = row[0]
                employee_id = row[1]
                category = row[2]
                description = row[3]
                amount = float(row[4])
                currency = row[5]
            except (ValueError, IndexError):
                # Row is structurally broken or amount is non-numeric; skip it.
                logger.warning("Skipping malformed row: %s", row)
                continue

            converted = normalize_currency(amount, currency)
            if converted is None:
                # Currency is not in our conversion table; skip rather than guess.
                logger.warning(
                    "Skipping row with unsupported currency %r (supported: %s)",
                    currency,
                    ", ".join(CURRENCY_RATES),
                )
                continue

            yield Transaction(
                date=date_str,
                employee_id=employee_id,
                category=normalize_category(category),
                description=description,
                amount=converted,
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize(path: Path | str = DEFAULT_PATH) -> ExpenseSummary:
    """Process the expense CSV at *path* and return a structured summary.

    Parameters
    ----------
    path:
        Path to the transactions CSV.  Defaults to ``transactions.csv`` in the
        current working directory.

    Returns
    -------
    ExpenseSummary
        A typed dict with keys ``total``, ``by_category``, ``by_employee``,
        ``by_month``, ``flagged``, and ``needs_approval``.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    total: float = 0.0
    by_category: dict[str, float] = {}
    by_employee: dict[str, float] = {}
    by_month: dict[str, float] = {}
    flagged: list[Transaction] = []
    needs_approval: list[Transaction] = []

    for tx in load_transactions(path):
        # Accumulate spend buckets — category, employee, and calendar month.
        by_category[tx.category] = by_category.get(tx.category, 0.0) + tx.amount
        by_employee[tx.employee_id] = by_employee.get(tx.employee_id, 0.0) + tx.amount

        try:
            month_key = datetime.datetime.strptime(tx.date, "%Y-%m-%d").strftime("%Y-%m")
        except ValueError:
            # Malformed date: bin it under "unknown" rather than crashing.
            month_key = "unknown"
        by_month[month_key] = by_month.get(month_key, 0.0) + tx.amount

        # Apply policy rules.  Each transaction falls into exactly one bucket:
        # auto-flagged (high-value), flagged (excessive meal), or needs approval.
        # The elif chain prevents a high-value Meals row from being double-counted.
        if tx.amount > HIGH_VALUE_THRESHOLD:
            flagged.append(tx)
        elif tx.category == "Meals" and tx.amount > MEAL_FLAG_THRESHOLD:
            flagged.append(tx)
        elif APPROVAL_THRESHOLD < tx.amount <= HIGH_VALUE_THRESHOLD:
            needs_approval.append(tx)

        # Total always includes every valid row, regardless of its policy bucket.
        total += tx.amount

    return ExpenseSummary(
        total=total,
        by_category=by_category,
        by_employee=by_employee,
        by_month=by_month,
        flagged=flagged,
        needs_approval=needs_approval,
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(path: Path | str = DEFAULT_PATH) -> None:
    """Print a human-readable expense summary to stdout."""
    result = summarize(path)

    print("==== EXPENSE SUMMARY ====")
    print(f"total: {result['total']}")
    print()

    print("by category:")
    for category, total in result["by_category"].items():
        print(f"  {category}: {total}")
    print()

    print("by employee (top 5):")
    top_employees = sorted(result["by_employee"].items(), key=lambda item: item[1], reverse=True)
    for employee_id, total in top_employees[:5]:
        print(f"  {employee_id}: {total}")
    print()

    print("by month:")
    for month_key in sorted(result["by_month"]):
        print(f"  {month_key}: {result['by_month'][month_key]}")
    print()

    print(f"FLAGGED (over {HIGH_VALUE_THRESHOLD} or meals over {MEAL_FLAG_THRESHOLD}): {len(result['flagged'])}")
    for tx in result["flagged"]:
        print(f"  {tx}")
    print()

    print(f"NEEDS APPROVAL (over {APPROVAL_THRESHOLD}, under {HIGH_VALUE_THRESHOLD}): {len(result['needs_approval'])}")
    for tx in result["needs_approval"]:
        print(f"  {tx}")


if __name__ == "__main__":
    # Configure a basic handler so logger.warning() calls are visible at the terminal.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    main(path)
