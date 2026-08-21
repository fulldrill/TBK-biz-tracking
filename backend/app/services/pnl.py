"""Profit & Loss statement builder.

Turns raw transactions into a cash-basis income statement. Bank data records
money when it *moves*, so everything here is cash-basis, never accrual.

Classification is rule-based and lives entirely in this module — no schema
change, no per-org config table. Credits become revenue, debits become
operating expenses, and a small set of categories is excluded outright
because they are balance-sheet movements rather than income or expense.
"""

from collections import OrderedDict
from datetime import datetime
from typing import Iterable, List, Optional

# Two vocabularies reach the `category` column: the labels from
# services/categorizer.py, and raw bank/Plaid labels that pass straight through
# (categorize_transaction returns plaid_category unchanged when present).
# Both are mapped below — a real ledger contains a mix of the two.

# Categories that must never hit the P&L.
#
# "Loan Payments": principal moves between the balance sheet and the bank
# account; only the interest portion is a real expense, and bank data cannot
# separate the two.
#
# "Transfer": wires and P2P between the owners' own accounts. Booking a partner
# topping up the account as revenue would overstate income — it is a capital
# contribution, not a sale.
#
# Both are surfaced in their own section so the number stays visible rather
# than silently dropped.
EXCLUDED_CATEGORIES = {"Loan Payments", "Transfer"}

# Credit-side (money in) category -> revenue line label.
REVENUE_LINE_MAP = {
    "Business Revenue": "Business Revenue",
    "Zelle Transfer": "Zelle Received",
    "Zelle": "Zelle Received",
    "Deposit": "Deposits",
    "Payment": "Customer Payments",
    "Refund": "Refunds & Credits",
}
DEFAULT_REVENUE_LINE = "Other Income"

# Debit-side (money out) category -> expense line label. Several raw
# categories collapse into one line so the statement reads like a real P&L
# instead of a category dump.
EXPENSE_LINE_MAP = {
    "Payroll": "Payroll & Contractors",
    "Rent": "Rent & Lease",
    "Utilities": "Utilities & Telecom",
    "Telecom": "Utilities & Telecom",
    "Insurance": "Insurance",
    "Office Supplies": "Office Supplies",
    "Software & Subscriptions": "Software & Subscriptions",
    "Travel": "Travel & Transportation",
    "Transportation": "Travel & Transportation",
    "Gas & Fuel": "Travel & Transportation",
    "Food & Dining": "Meals & Entertainment",
    "Groceries": "Meals & Entertainment",
    "Shopping": "Supplies & Equipment",
    "Healthcare": "Healthcare & Benefits",
    "Bank Fees": "Bank Fees",
    "Zelle Transfer": "Zelle Payments Out",
    # Raw bank labels
    "Zelle": "Zelle Payments Out",
    "Fee": "Bank Fees",
    "Payment": "Card & Finance Payments",
    "ATM / Cash": "Cash Withdrawals",
    "Other": "Other Expenses",
    "Deposit": "Other Expenses",
}
DEFAULT_EXPENSE_LINE = "Uncategorized Expense"

# Display order. Anything not listed sorts after these, alphabetically, so a
# new category from the categorizer still renders instead of disappearing.
REVENUE_LINE_ORDER = [
    "Business Revenue",
    "Deposits",
    "Zelle Received",
    "Customer Payments",
    "Refunds & Credits",
    "Other Income",
]
EXPENSE_LINE_ORDER = [
    "Payroll & Contractors",
    "Zelle Payments Out",
    "Card & Finance Payments",
    "Rent & Lease",
    "Utilities & Telecom",
    "Insurance",
    "Software & Subscriptions",
    "Office Supplies",
    "Supplies & Equipment",
    "Travel & Transportation",
    "Meals & Entertainment",
    "Healthcare & Benefits",
    "Bank Fees",
    "Cash Withdrawals",
    "Other Expenses",
    "Uncategorized Expense",
]


def classify(category: Optional[str], transaction_type: str) -> tuple[str, str]:
    """Map one transaction to (section, line_label).

    section is one of: "revenue", "expense", "excluded".
    """
    cat = (category or "").strip()

    if cat in EXCLUDED_CATEGORIES:
        return "excluded", cat

    if transaction_type == "credit":
        return "revenue", REVENUE_LINE_MAP.get(cat, DEFAULT_REVENUE_LINE)

    return "expense", EXPENSE_LINE_MAP.get(cat, DEFAULT_EXPENSE_LINE if not cat else cat)


def month_range(start: datetime, end: datetime) -> List[str]:
    """Every "YYYY-MM" key from start to end inclusive."""
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _order_key(order: List[str]):
    def key(label: str):
        try:
            return (0, order.index(label), "")
        except ValueError:
            return (1, 0, label)
    return key


def _build_lines(bucket: dict, months: List[str], order: List[str]) -> List[dict]:
    """Turn {label: {"amount", "count", "monthly"}} into an ordered list."""
    lines = []
    for label in sorted(bucket.keys(), key=_order_key(order)):
        entry = bucket[label]
        lines.append({
            "label": label,
            "amount": round(entry["amount"], 2),
            "count": entry["count"],
            "monthly": {m: round(entry["monthly"].get(m, 0.0), 2) for m in months},
        })
    return lines


def build_pnl(
    transactions: Iterable,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """Aggregate transactions into a cash-basis P&L statement."""
    months = month_range(period_start, period_end)

    revenue: dict = {}
    expense: dict = {}
    excluded: dict = {}
    sections = {"revenue": revenue, "expense": expense, "excluded": excluded}

    counted = 0
    for tx in transactions:
        tx_type = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)
        section, label = classify(tx.category, tx_type)
        bucket = sections[section]

        entry = bucket.setdefault(label, {"amount": 0.0, "count": 0, "monthly": {}})
        amount = abs(tx.amount or 0.0)
        entry["amount"] += amount
        entry["count"] += 1

        key = tx.date.strftime("%Y-%m")
        entry["monthly"][key] = entry["monthly"].get(key, 0.0) + amount
        counted += 1

    revenue_lines = _build_lines(revenue, months, REVENUE_LINE_ORDER)
    expense_lines = _build_lines(expense, months, EXPENSE_LINE_ORDER)
    excluded_lines = _build_lines(excluded, months, [])

    total_revenue = round(sum(line["amount"] for line in revenue_lines), 2)
    total_expenses = round(sum(line["amount"] for line in expense_lines), 2)
    net_profit = round(total_revenue - total_expenses, 2)

    monthly_summary = []
    for m in months:
        rev = round(sum(line["monthly"].get(m, 0.0) for line in revenue_lines), 2)
        exp = round(sum(line["monthly"].get(m, 0.0) for line in expense_lines), 2)
        monthly_summary.append({
            "month": m,
            "revenue": rev,
            "expenses": exp,
            "net": round(rev - exp, 2),
        })

    return {
        "period_start": period_start,
        "period_end": period_end,
        "basis": "cash",
        "months": months,
        "revenue_lines": revenue_lines,
        "total_revenue": total_revenue,
        "expense_lines": expense_lines,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "margin_pct": round((net_profit / total_revenue * 100), 1) if total_revenue else 0.0,
        "excluded_lines": excluded_lines,
        "total_excluded": round(sum(line["amount"] for line in excluded_lines), 2),
        "monthly_summary": monthly_summary,
        "transaction_count": counted,
    }
