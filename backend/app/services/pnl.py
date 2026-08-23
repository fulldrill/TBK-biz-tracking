"""Profit & Loss statement builder.

Bank data records money when it *moves*, so this is cash-basis by default —
with one deliberate exception. The CMCI payroll deposit lands on the 15th of
the month *after* the work was done, so it is recognised in the month earned
(see DEFERRED_REVENUE_CATEGORIES). That makes monthly margins meaningful
instead of parking a month's whole revenue in the wrong column, and the
statement labels itself accordingly.

Classification is rule-based and lives in this module — no per-org config
table. Credits become revenue, debits become operating expenses, and a small
set of categories is excluded because they are balance-sheet movements rather
than income or expense.
"""

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
# "Mortgage": a personal mortgage paid from the business account is an owner
# draw. The home-office cost belongs on the P&L as a manual rent entry
# instead; counting both would double-dip.
#
# "Owner's Draw" / "Owner's Contribution": paying yourself by Zelle looks like
# any other payment, but it is equity movement. Booking a draw as an expense
# understates profit and claims a personal withdrawal as a business cost.
#
# All are surfaced in their own section so the number stays visible rather
# than silently dropped.
EXCLUDED_CATEGORIES = {
    "Loan Payments", "Transfer", "Mortgage",
    "Owner's Draw", "Owner's Contribution",
}

# Categories paid in arrears: the deposit arrives the month after it is earned,
# so its P&L month is shifted back by one. Everything else uses its own date.
DEFERRED_REVENUE_CATEGORIES = {"Gross Revenue"}

# Credit-side (money in) category -> revenue line label.
REVENUE_LINE_MAP = {
    "Gross Revenue": "Gross Revenue",
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
    "Child Care": "Child Care",
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
    "Gross Revenue",
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
    "Child Care",
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


def shift_month(dt: datetime, months: int) -> datetime:
    """Move a datetime by whole months, clamping the day to the target month."""
    total = (dt.year * 12 + (dt.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    # Clamp: shifting Mar 31 back a month must land on Feb 28/29, not overflow.
    day = dt.day
    while day > 1:
        try:
            return dt.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1
    return dt.replace(year=year, month=month, day=1)


def effective_date(tx_date: datetime, category: Optional[str]) -> datetime:
    """The date the P&L should book this transaction under.

    Deferred revenue is paid a month in arrears, so it belongs to the prior
    month. Everything else books on the date the money moved.
    """
    if (category or "").strip() in DEFERRED_REVENUE_CATEGORIES:
        return shift_month(tx_date, -1)
    return tx_date


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
    """Turn {label: {"amount", "count", "monthly", "manual"}} into an ordered list."""
    lines = []
    for label in sorted(bucket.keys(), key=_order_key(order)):
        entry = bucket[label]
        lines.append({
            "label": label,
            "amount": round(entry["amount"], 2),
            "count": entry["count"],
            "manual": entry.get("manual", False),
            "user_excluded": False,
            "monthly": {m: round(entry["monthly"].get(m, 0.0), 2) for m in months},
        })
    return lines


def _add(bucket: dict, label: str, amount: float, month_key: str, manual: bool = False):
    entry = bucket.setdefault(
        label, {"amount": 0.0, "count": 0, "monthly": {}, "manual": manual}
    )
    entry["amount"] += amount
    entry["count"] += 1
    entry["monthly"][month_key] = entry["monthly"].get(month_key, 0.0) + amount
    if not manual:
        # A line carrying any bank data is not purely manual.
        entry["manual"] = False


def expand_manual_entries(entries: Iterable, months: List[str]) -> List[tuple]:
    """Expand manual entries into (month_key, entry_type, label, amount) rows.

    A monthly entry produces one row per month of the period that falls inside
    its own start/end window; a one-off produces a single row.
    """
    rows = []
    for e in entries:
        if getattr(e, "is_active", True) is False:
            continue
        start = e.start_date
        end = e.end_date
        # Signed on purpose: a negative entry subtracts from its section, which
        # is how a correction or partial credit gets recorded.
        amount = e.amount or 0.0

        if e.recurrence == "once":
            key = start.strftime("%Y-%m")
            if key in months:
                rows.append((key, e.entry_type, e.label, amount))
            continue

        for key in months:
            y, m = int(key[:4]), int(key[5:7])
            # Month must fall on or after the entry's start month...
            if (y, m) < (start.year, start.month):
                continue
            # ...and on or before its end month, when one is set.
            if end and (y, m) > (end.year, end.month):
                continue
            rows.append((key, e.entry_type, e.label, amount))
    return rows


def build_pnl(
    transactions: Iterable,
    period_start: datetime,
    period_end: datetime,
    manual_entries: Optional[Iterable] = None,
    excluded_labels: Optional[Iterable[str]] = None,
) -> dict:
    """Aggregate transactions and manual entries into a P&L statement.

    `transactions` may span a wider window than the period — rows are filtered
    on their *effective* date, so a deposit dated just after period_end can
    still belong inside it once shifted back to the month it was earned.
    """
    months = month_range(period_start, period_end)
    month_set = set(months)

    revenue: dict = {}
    expense: dict = {}
    excluded: dict = {}
    sections = {"revenue": revenue, "expense": expense, "excluded": excluded}

    counted = 0
    deferred_count = 0
    bank_months: set = set()
    for tx in transactions:
        tx_type = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)

        # Track the month the row was actually *dated*, not where it lands on
        # the statement. A deferred deposit shifted back a month would
        # otherwise make an unimported month look covered.
        native_key = tx.date.strftime("%Y-%m")
        if native_key in month_set:
            bank_months.add(native_key)

        eff = effective_date(tx.date, tx.category)
        key = eff.strftime("%Y-%m")
        if key not in month_set:
            continue  # outside the period once shifted

        if eff != tx.date:
            deferred_count += 1

        section, label = classify(tx.category, tx_type)
        _add(sections[section], label, abs(tx.amount or 0.0), key)
        counted += 1

    manual_rows = expand_manual_entries(manual_entries or [], months)
    for key, entry_type, label, amount in manual_rows:
        bucket = revenue if entry_type == "revenue" else expense
        _add(bucket, label, amount, key, manual=True)

    revenue_lines = _build_lines(revenue, months, REVENUE_LINE_ORDER)
    expense_lines = _build_lines(expense, months, EXPENSE_LINE_ORDER)
    excluded_lines = _build_lines(excluded, months, [])

    # Lines the user has removed from the statement. They move to the excluded
    # section rather than vanishing, and every total below is computed after
    # this step so the sums stay consistent.
    removed = set(excluded_labels or ())
    if removed:
        for lines, section in ((revenue_lines, "revenue"), (expense_lines, "expense")):
            for line in lines:
                if line["label"] in removed:
                    excluded_lines.append({**line, "user_excluded": True, "section": section})
        revenue_lines = [l for l in revenue_lines if l["label"] not in removed]
        expense_lines = [l for l in expense_lines if l["label"] not in removed]

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

    # Months no statement covers — nothing was *dated* in them. Almost always
    # an upload that never happened rather than a month with no activity.
    #
    # Deliberately blind to two things that would otherwise hide the gap: a
    # recurring manual entry lands in every month, and a deferred deposit
    # shifted back from the following month would make an unimported month
    # look covered.
    empty_months = [m for m in months if m not in bank_months]

    return {
        "period_start": period_start,
        "period_end": period_end,
        "basis": "accrual-adjusted" if deferred_count else "cash",
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
        "manual_entry_count": len(manual_rows),
        "deferred_count": deferred_count,
        "empty_months": empty_months,
    }
