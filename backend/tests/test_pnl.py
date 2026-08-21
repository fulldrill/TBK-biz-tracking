import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

from app.services.pnl import build_pnl, classify, month_range


class _Type:
    def __init__(self, value):
        self.value = value


class _Tx:
    """Minimal stand-in for a Transaction ORM row."""
    def __init__(self, date, amount, category, ttype):
        self.date = date
        self.amount = amount
        self.category = category
        self.transaction_type = _Type(ttype)


def _year_2025():
    """One full year: revenue, expenses, and an excluded loan payment each month."""
    txs = []
    for month in range(1, 13):
        txs.append(_Tx(datetime(2025, month, 5), 10000.0, "Business Revenue", "credit"))
        txs.append(_Tx(datetime(2025, month, 12), 2000.0, "Zelle Transfer", "credit"))
        txs.append(_Tx(datetime(2025, month, 1), 2500.0, "Rent", "debit"))
        txs.append(_Tx(datetime(2025, month, 15), 3000.0, "Payroll", "debit"))
        txs.append(_Tx(datetime(2025, month, 28), 1800.0, "Loan Payments", "debit"))
    return txs


# --- classification ---

def test_credit_becomes_revenue():
    assert classify("Business Revenue", "credit") == ("revenue", "Business Revenue")


def test_zelle_splits_by_direction():
    assert classify("Zelle Transfer", "credit") == ("revenue", "Zelle Received")
    assert classify("Zelle Transfer", "debit") == ("expense", "Zelle Payments Out")


def test_loan_payments_are_excluded():
    section, _ = classify("Loan Payments", "debit")
    assert section == "excluded"


def test_related_categories_merge_into_one_line():
    assert classify("Utilities", "debit")[1] == "Utilities & Telecom"
    assert classify("Telecom", "debit")[1] == "Utilities & Telecom"


def test_missing_category_falls_back():
    assert classify(None, "credit") == ("revenue", "Other Income")
    assert classify(None, "debit") == ("expense", "Uncategorized Expense")
    assert classify("", "debit") == ("expense", "Uncategorized Expense")


def test_unknown_category_still_renders():
    # A new rule in the categorizer must not silently vanish from the statement.
    assert classify("Brand New Category", "debit") == ("expense", "Brand New Category")


# --- raw bank/Plaid category vocabulary ---
# categorize_transaction passes plaid_category through untouched, so real
# ledgers carry these labels alongside the categorizer's own.

def test_bank_deposit_is_revenue():
    assert classify("Deposit", "credit") == ("revenue", "Deposits")


def test_bare_zelle_label_splits_by_direction():
    assert classify("Zelle", "credit") == ("revenue", "Zelle Received")
    assert classify("Zelle", "debit") == ("expense", "Zelle Payments Out")


def test_transfer_is_excluded_both_directions():
    # Owner-to-business P2P and wires are capital movement, not revenue.
    assert classify("Transfer", "credit")[0] == "excluded"
    assert classify("Transfer", "debit")[0] == "excluded"


def test_bank_fee_folds_into_bank_fees():
    assert classify("Fee", "debit")[1] == "Bank Fees"


def test_atm_withdrawal_has_its_own_line():
    assert classify("ATM / Cash", "debit")[1] == "Cash Withdrawals"


def test_owner_contribution_stays_out_of_revenue():
    txs = [
        _Tx(datetime(2025, 8, 19), 2000.0, "Transfer", "credit"),   # P2P from a partner
        _Tx(datetime(2025, 8, 20), 500.0, "Deposit", "credit"),     # real revenue
    ]
    pnl = build_pnl(txs, datetime(2025, 8, 1), datetime(2025, 8, 31))
    assert pnl["total_revenue"] == 500.0
    assert pnl["total_excluded"] == 2000.0


# --- month range ---

def test_month_range_spans_year_boundary():
    assert month_range(datetime(2024, 11, 1), datetime(2025, 2, 28)) == [
        "2024-11", "2024-12", "2025-01", "2025-02",
    ]


def test_month_range_single_month():
    assert month_range(datetime(2025, 6, 3), datetime(2025, 6, 29)) == ["2025-06"]


# --- aggregation ---

def test_full_year_totals():
    pnl = build_pnl(_year_2025(), datetime(2025, 1, 1), datetime(2025, 12, 31, 23, 59, 59))
    assert len(pnl["months"]) == 12
    assert pnl["total_revenue"] == 144000.0        # (10000 + 2000) * 12
    assert pnl["total_expenses"] == 66000.0        # (2500 + 3000) * 12
    assert pnl["net_profit"] == 78000.0
    assert pnl["total_excluded"] == 21600.0        # 1800 * 12


def test_line_items_sum_to_totals():
    pnl = build_pnl(_year_2025(), datetime(2025, 1, 1), datetime(2025, 12, 31))
    assert round(sum(l["amount"] for l in pnl["revenue_lines"]), 2) == pnl["total_revenue"]
    assert round(sum(l["amount"] for l in pnl["expense_lines"]), 2) == pnl["total_expenses"]


def test_monthly_columns_sum_to_totals():
    pnl = build_pnl(_year_2025(), datetime(2025, 1, 1), datetime(2025, 12, 31))
    assert round(sum(m["revenue"] for m in pnl["monthly_summary"]), 2) == pnl["total_revenue"]
    assert round(sum(m["expenses"] for m in pnl["monthly_summary"]), 2) == pnl["total_expenses"]


def test_every_transaction_is_accounted_for():
    txs = _year_2025()
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 12, 31))
    counted = sum(
        l["count"]
        for l in pnl["revenue_lines"] + pnl["expense_lines"] + pnl["excluded_lines"]
    )
    assert counted == len(txs) == pnl["transaction_count"]


def test_excluded_never_leaks_into_expenses():
    pnl = build_pnl(_year_2025(), datetime(2025, 1, 1), datetime(2025, 12, 31))
    assert all("Loan" not in l["label"] for l in pnl["expense_lines"])
    assert pnl["excluded_lines"][0]["label"] == "Loan Payments"


def test_amount_sign_is_ignored_in_favor_of_type():
    # Statement imports may carry negative amounts for debits; transaction_type rules.
    txs = [
        _Tx(datetime(2025, 1, 5), -500.0, "Rent", "debit"),
        _Tx(datetime(2025, 1, 6), 500.0, "Rent", "debit"),
    ]
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 1, 31))
    assert pnl["total_expenses"] == 1000.0


def test_empty_period_does_not_divide_by_zero():
    pnl = build_pnl([], datetime(2025, 1, 1), datetime(2025, 12, 31))
    assert pnl["total_revenue"] == 0
    assert pnl["net_profit"] == 0
    assert pnl["margin_pct"] == 0.0


def test_net_loss_is_negative():
    txs = [_Tx(datetime(2025, 5, 1), 500.0, "Rent", "debit")]
    pnl = build_pnl(txs, datetime(2025, 5, 1), datetime(2025, 5, 31))
    assert pnl["net_profit"] == -500.0


def test_margin_percentage():
    txs = [
        _Tx(datetime(2025, 1, 5), 1000.0, "Business Revenue", "credit"),
        _Tx(datetime(2025, 1, 6), 250.0, "Rent", "debit"),
    ]
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 1, 31))
    assert pnl["net_profit"] == 750.0
    assert pnl["margin_pct"] == 75.0


def test_transactions_outside_month_list_still_total_correctly():
    # Defensive: a row whose date sits outside the requested window (caller passed a
    # wider set) must still land in the totals rather than being dropped silently.
    txs = [_Tx(datetime(2025, 7, 4), 100.0, "Business Revenue", "credit")]
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 3, 31))
    assert pnl["total_revenue"] == 100.0
