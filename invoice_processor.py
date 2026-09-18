import csv
import sys
import datetime

# Thresholds — do not change without ops sign-off
THRESH = 500
THRESH2 = 5000
APPROVAL_THRESH = 2500

DEFAULT_PATH = "transactions.csv"

CURRENCY_RATES = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.26,
}

CATEGORY_ALIASES = {
    "Travel-Air": "Travel",
    "Travel-Ground": "Travel",
    "Travel - Air": "Travel",
    "T&E": "Travel",
    "meals": "Meals",
    "Meal": "Meals",
    "client-meal": "Meals",
}


def normalize_currency(amount, currency):
    """Return amount converted to USD, or None for unsupported currencies."""
    rate = CURRENCY_RATES.get(currency)
    if rate is None:
        return None
    return amount * rate


def normalize_category(category):
    """Return the canonical category name, collapsing legacy aliases."""
    return CATEGORY_ALIASES.get(category, category)


def load_transactions(path):
    """Yield parsed rows from the CSV, skipping the header and bad rows."""
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            try:
                date_str = row[0]
                employee_id = row[1]
                category = row[2]
                description = row[3]
                amount = float(row[4])
                currency = row[5]
            except (ValueError, IndexError):
                print(f"bad row: {row}")
                continue

            converted = normalize_currency(amount, currency)
            if converted is None:
                print(f"unknown currency {currency}")
                continue

            yield date_str, employee_id, normalize_category(category), description, converted


def summarize(path=DEFAULT_PATH):
    """
    Process the expense CSV and return a summary dict with keys:
        total, by_category, by_employee, by_month, flagged, needs_approval
    """
    total = 0.0
    by_category = {}
    by_employee = {}
    by_month = {}
    flagged = []
    needs_approval = []

    for date_str, employee_id, category, description, amount in load_transactions(path):
        # Accumulate buckets
        by_category[category] = by_category.get(category, 0.0) + amount
        by_employee[employee_id] = by_employee.get(employee_id, 0.0) + amount

        try:
            month_key = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m")
        except ValueError:
            month_key = "unknown"
        by_month[month_key] = by_month.get(month_key, 0.0) + amount

        # Flag high-value rows; only flag meals separately when not already flagged
        if amount > THRESH2:
            flagged.append((date_str, employee_id, category, description, amount))
        elif category == "Meals" and amount > THRESH:
            flagged.append((date_str, employee_id, category, description, amount))
        elif APPROVAL_THRESH < amount <= THRESH2:
            needs_approval.append((date_str, employee_id, category, description, amount))

        total += amount

    return {
        "total": total,
        "by_category": by_category,
        "by_employee": by_employee,
        "by_month": by_month,
        "flagged": flagged,
        "needs_approval": needs_approval,
    }


def main(path=DEFAULT_PATH):
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

    print(f"FLAGGED (over {THRESH2} or meals over {THRESH}): {len(result['flagged'])}")
    for row in result["flagged"]:
        print(f"  {row}")
    print()

    print(f"NEEDS APPROVAL (over {APPROVAL_THRESH}, under {THRESH2}): {len(result['needs_approval'])}")
    for row in result["needs_approval"]:
        print(f"  {row}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    main(path)
