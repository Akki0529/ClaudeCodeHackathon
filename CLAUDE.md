# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run tests
pip install pytest
pytest test_invoice_processor.py -v

# Run a single test
pytest test_invoice_processor.py::test_total_is_preserved -v

# Run the processor directly
python invoice_processor.py                   # uses transactions.csv
python invoice_processor.py other_file.csv   # custom path
```

## Project overview

This is a Python expense-processing exercise. The original `invoice_processor.py` reads `transactions.csv`, applies business rules, and prints a summary. The task is to **refactor it** so it exposes a `summarize(path="transactions.csv") -> dict` function (while keeping the CLI entrypoint working), so that `test_invoice_processor.py` can test it programmatically.

## Refactoring contract

The refactored module must expose:

```python
summarize(path="transactions.csv") -> dict
```

Return keys: `total` (float), `by_category` (dict), `by_employee` (dict), `by_month` (dict, keys as `"YYYY-MM"`), `flagged` (list), `needs_approval` (list).

## Business rules (preserve exactly)

**Thresholds** — do not change without consulting ops:
- `THRESH = 500` — meal amount that triggers a flag
- `THRESH2 = 5000` — any category amount that triggers a flag
- `APPROVAL_THRESH = 2500` — lower bound for the needs-approval band (over 2500, under 5000)

**Currency conversion rates:**
- USD: × 1.0
- EUR: × 1.08
- GBP: × 1.26
- Any other currency: skip the row (don't crash)

**Category normalisation** (aliases → canonical):
- `Travel-Air`, `Travel-Ground`, `Travel - Air`, `T&E` → `Travel`
- `meals`, `Meal`, `client-meal` → `Meals`

## Known bug to fix (Test 7)

The original code double-flags a meal that also exceeds `THRESH2`: it first appends to `flagged` because `amt > THRESH2`, then appends again because `cat == "Meals" and amt > THRESH`. Fix: use `elif` so that a row flagged by the high threshold is not also flagged by the meal threshold. Test 7 encodes this fix — it passes only after the bug is corrected.

## CSV format

`transactions.csv` columns (header row present): `date`, `employee_id`, `category`, `description`, `amount`, `currency`.
