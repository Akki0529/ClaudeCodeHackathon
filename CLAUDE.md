# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What it does

Reads `transactions.csv` (columns: date, employee_id, category, description, amount, currency), applies Deloitte expense-policy rules, and produces a structured summary. The legacy `run()` entrypoint prints results to stdout. The refactored module must additionally expose a `summarize(path) -> dict` function — the regression suite (`test_invoice_processor.py`) calls that function directly to verify behaviour is preserved.

**Business rules that must not change (per spec §Scenario A):**
- Thresholds: `THRESH = 500` (meal flag), `THRESH2 = 5000` (high-value flag), `APPROVAL_THRESH = 2500` (approval band). Do not alter without ops sign-off.
- Currency conversion: USD × 1.0, EUR × 1.08, GBP × 1.26. Unknown currencies are skipped silently.
- Category aliases collapse to canonical names: `Travel-Air / Travel-Ground / Travel - Air / T&E → Travel`; `meals / Meal / client-meal → Meals`.

## Entry point

```
python invoice_processor.py                  # reads transactions.csv
python invoice_processor.py <path>           # custom path
pytest test_invoice_processor.py -v          # run all 7 regression tests
pytest test_invoice_processor.py::test_meals_not_double_flagged -v  # run Test 7 alone
```

`summarize(path="transactions.csv") -> dict` — the public API the tests call. Return keys:
`total` (float), `by_category` (dict), `by_employee` (dict), `by_month` (dict, keys `"YYYY-MM"`), `flagged` (list), `needs_approval` (list).

## Known issues

**Bug — double-flagging (Test 7, per spec §Scenario A) — FIXED:** The original code appended to `flagged` twice for a high-value Meals row. Fixed with `elif` on the meal-threshold branch — each row now lands in exactly one bucket.

**Production-grade additions (all 7 tests still pass):**
- `Transaction` NamedTuple — flagged/needs_approval rows are named, not anonymous tuples.
- `ExpenseSummary` TypedDict — return type of `summarize()` is statically checkable.
- Full type annotations on every function.
- `logging.getLogger(__name__)` replaces `print()` for warnings — callers control verbosity.
- `pathlib.Path` for file handling; existence validated with a clear `FileNotFoundError`.
- Threshold constants renamed: `MEAL_FLAG_THRESHOLD`, `HIGH_VALUE_THRESHOLD`, `APPROVAL_THRESHOLD`.
- Module docstring, `__all__ = ["summarize"]`, and inline comments explaining the `elif` precedence rule.

## Do not

- Change threshold constants without explicit ops approval (per spec §Scenario A note on THRESH).
- Add performance optimisations (async, generators, numpy) — the spec explicitly excludes these.
- Produce a wholesale rewrite that alters observable output on `transactions.csv` — the regression suite is the proof of preserved behaviour.
- Remove the CLI `__main__` entrypoint — it must still work after the refactor.
- Use `pytest.approx` tolerances wider than those in the test file — do not relax the tests to pass the code.

## Next step

All 7 regression tests must pass, including Test 7 (double-flag bug fix). Run `pytest test_invoice_processor.py -v` after each change to confirm nothing regressed. Once green, tighten the direction log and submit.
