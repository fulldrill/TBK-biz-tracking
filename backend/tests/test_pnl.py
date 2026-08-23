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


def test_rows_outside_the_period_are_excluded():
    # The router over-fetches (see _LOOKAHEAD) so deferred revenue dated after
    # period_end can shift back into range. Everything else that falls outside
    # must be dropped, or a July deposit would leak into a Q1 statement.
    txs = [_Tx(datetime(2025, 7, 4), 100.0, "Business Revenue", "credit")]
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 3, 31))
    assert pnl["total_revenue"] == 0.0
    assert pnl["transaction_count"] == 0


# --- deferred revenue: CMCI payroll lands the month after it is earned ---

def test_cash_basis_is_the_default():
    # Self-employment reporting is cash basis: revenue counts when received.
    from app.services.pnl import DEFERRED_REVENUE_CATEGORIES, effective_date
    assert DEFERRED_REVENUE_CATEGORIES == set()
    assert effective_date(datetime(2025, 1, 15), "Gross Revenue").strftime("%Y-%m") == "2025-01"


def test_deferring_a_category_books_it_to_the_month_earned():
    # The machinery stays available for revenue genuinely paid in arrears.
    from app.services import pnl as pnl_mod
    pnl_mod.DEFERRED_REVENUE_CATEGORIES.add("Deferred")
    try:
        assert pnl_mod.effective_date(datetime(2025, 1, 15), "Deferred").strftime("%Y-%m") == "2024-12"
        assert pnl_mod.effective_date(datetime(2025, 1, 15), "Deposit").strftime("%Y-%m") == "2025-01"
    finally:
        pnl_mod.DEFERRED_REVENUE_CATEGORIES.discard("Deferred")


def test_shift_month_clamps_short_months():
    from app.services.pnl import shift_month
    # 31 March has no counterpart in February.
    assert shift_month(datetime(2025, 3, 31), -1).date() == datetime(2025, 2, 28).date()
    assert shift_month(datetime(2024, 3, 31), -1).date() == datetime(2024, 2, 29).date()  # leap
    assert shift_month(datetime(2025, 1, 10), -1).date() == datetime(2024, 12, 10).date()


def test_a_deposit_counts_in_the_year_it_was_received():
    # Cash basis: the 15 Jan 2025 deposit is 2025 revenue, not 2024.
    txs = [_Tx(datetime(2025, 1, 15), 12000.0, "Gross Revenue", "credit")]
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 12, 31, 23, 59, 59))
    assert pnl["total_revenue"] == 12000.0
    assert pnl["monthly_summary"][0]["revenue"] == 12000.0
    assert pnl["basis"] == "cash"


def test_a_deposit_received_next_year_is_not_claimed():
    # Money arriving 15 Jan 2026 is 2026 revenue, however it was earned.
    txs = [_Tx(datetime(2026, 1, 15), 12000.0, "Gross Revenue", "credit")]
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 12, 31, 23, 59, 59))
    assert pnl["total_revenue"] == 0.0
    assert pnl["transaction_count"] == 0


def test_a_deferred_category_still_shifts_when_configured():
    from app.services import pnl as pnl_mod
    pnl_mod.DEFERRED_REVENUE_CATEGORIES.add("Deferred")
    try:
        txs = [_Tx(datetime(2026, 1, 15), 12000.0, "Deferred", "credit")]
        pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 12, 31, 23, 59, 59))
        assert pnl["total_revenue"] == 12000.0
        assert pnl["monthly_summary"][-1]["month"] == "2025-12"
        assert pnl["basis"] == "accrual-adjusted"
    finally:
        pnl_mod.DEFERRED_REVENUE_CATEGORIES.discard("Deferred")


def test_mortgage_is_excluded():
    assert classify("Mortgage", "debit")[0] == "excluded"


def test_child_care_is_its_own_expense_line():
    assert classify("Child Care", "debit") == ("expense", "Child Care")


# --- manual entries ---

class _Entry:
    def __init__(self, label, amount, entry_type, recurrence, start_date, end_date=None):
        self.label = label
        self.amount = amount
        self.entry_type = entry_type
        self.recurrence = recurrence
        self.start_date = start_date
        self.end_date = end_date
        self.is_active = True


def test_monthly_entry_repeats_across_the_period():
    e = _Entry("Basement Office Rent", 1600.0, "expense", "monthly", datetime(2025, 1, 1))
    pnl = build_pnl([], datetime(2025, 1, 1), datetime(2025, 12, 31), manual_entries=[e])
    assert pnl["total_expenses"] == 19200.0            # 1600 * 12
    assert pnl["manual_entry_count"] == 12
    line = pnl["expense_lines"][0]
    assert line["label"] == "Basement Office Rent"
    assert line["manual"] is True
    assert line["monthly"]["2025-06"] == 1600.0


def test_monthly_entry_respects_its_own_window():
    e = _Entry("Rent", 1000.0, "expense", "monthly",
               datetime(2025, 4, 1), datetime(2025, 6, 30))
    pnl = build_pnl([], datetime(2025, 1, 1), datetime(2025, 12, 31), manual_entries=[e])
    assert pnl["total_expenses"] == 3000.0             # Apr, May, Jun only
    assert pnl["expense_lines"][0]["monthly"]["2025-03"] == 0.0


def test_one_off_entry_lands_in_a_single_month():
    e = _Entry("Equipment", 2500.0, "expense", "once", datetime(2025, 7, 9))
    pnl = build_pnl([], datetime(2025, 1, 1), datetime(2025, 12, 31), manual_entries=[e])
    assert pnl["total_expenses"] == 2500.0
    assert pnl["expense_lines"][0]["monthly"]["2025-07"] == 2500.0


def test_manual_revenue_counts_as_income():
    e = _Entry("Cash Sales", 900.0, "revenue", "once", datetime(2025, 3, 3))
    pnl = build_pnl([], datetime(2025, 1, 1), datetime(2025, 12, 31), manual_entries=[e])
    assert pnl["total_revenue"] == 900.0
    assert pnl["net_profit"] == 900.0


def test_inactive_entries_are_ignored():
    e = _Entry("Old Rent", 500.0, "expense", "monthly", datetime(2025, 1, 1))
    e.is_active = False
    pnl = build_pnl([], datetime(2025, 1, 1), datetime(2025, 12, 31), manual_entries=[e])
    assert pnl["total_expenses"] == 0.0


def test_manual_and_bank_lines_coexist():
    txs = [_Tx(datetime(2025, 5, 2), 400.0, "Utilities", "debit")]
    e = _Entry("Basement Office Rent", 1600.0, "expense", "monthly", datetime(2025, 5, 1))
    pnl = build_pnl(txs, datetime(2025, 5, 1), datetime(2025, 5, 31), manual_entries=[e])
    assert pnl["total_expenses"] == 2000.0
    labels = {l["label"]: l["manual"] for l in pnl["expense_lines"]}
    assert labels["Basement Office Rent"] is True
    assert labels["Utilities & Telecom"] is False


# --- data-completeness signal ---

def test_months_with_no_activity_are_reported():
    txs = [
        _Tx(datetime(2025, 1, 8), 100.0, "Utilities", "debit"),
        _Tx(datetime(2025, 3, 8), 100.0, "Utilities", "debit"),
    ]
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 3, 31))
    assert pnl["empty_months"] == ["2025-02"]


def test_manual_entries_do_not_mask_missing_statements():
    # A recurring rent line lands in every month. It must not make a month with
    # no bank data look like a month that simply broke even.
    txs = [_Tx(datetime(2025, 1, 8), 100.0, "Utilities", "debit")]
    rent = _Entry("Rent", 1600.0, "expense", "monthly", datetime(2025, 1, 1))
    pnl = build_pnl(txs, datetime(2025, 1, 1), datetime(2025, 3, 31), manual_entries=[rent])
    assert pnl["empty_months"] == ["2025-02", "2025-03"]


def test_shifted_deposit_does_not_mask_an_unimported_month():
    # With deferral configured, June's deposit shifts back into May. May's own
    # statement is missing, and that must still be reported.
    from app.services import pnl as pnl_mod
    pnl_mod.DEFERRED_REVENUE_CATEGORIES.add("Deferred")
    try:
        txs = [
            _Tx(datetime(2025, 6, 13), 14000.0, "Deferred", "credit"),
            _Tx(datetime(2025, 6, 20), 300.0, "Utilities", "debit"),
        ]
        pnl = build_pnl(txs, datetime(2025, 5, 1), datetime(2025, 6, 30))
        assert pnl["monthly_summary"][0]["revenue"] == 14000.0   # May shows it
        assert pnl["empty_months"] == ["2025-05"]                # still flagged
    finally:
        pnl_mod.DEFERRED_REVENUE_CATEGORIES.discard("Deferred")


# --- removing a line from the statement ---

def _mixed():
    return [
        _Tx(datetime(2025, 3, 5), 10000.0, "Deposit", "credit"),
        _Tx(datetime(2025, 3, 6), 2000.0, "Zelle", "credit"),
        _Tx(datetime(2025, 3, 7), 1500.0, "Child Care", "debit"),
        _Tx(datetime(2025, 3, 8), 500.0, "Utilities", "debit"),
    ]


def test_excluding_an_expense_line_lowers_total_expenses():
    base = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31))
    assert base["total_expenses"] == 2000.0
    assert base["net_profit"] == 10000.0

    cut = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    excluded_labels=["Child Care"])
    assert cut["total_expenses"] == 500.0          # 2000 - 1500
    assert cut["net_profit"] == 11500.0            # net rises by the same 1500
    assert all(l["label"] != "Child Care" for l in cut["expense_lines"])


def test_excluding_a_revenue_line_lowers_total_revenue():
    cut = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    excluded_labels=["Zelle Received"])
    assert cut["total_revenue"] == 10000.0         # 12000 - 2000
    assert cut["net_profit"] == 8000.0


def test_excluded_line_moves_to_the_excluded_section():
    cut = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    excluded_labels=["Child Care"])
    moved = [l for l in cut["excluded_lines"] if l["label"] == "Child Care"]
    assert len(moved) == 1
    assert moved[0]["user_excluded"] is True
    assert moved[0]["amount"] == 1500.0            # the money is still visible
    assert moved[0]["section"] == "expense"


def test_exclusion_updates_the_monthly_columns_too():
    cut = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    excluded_labels=["Child Care"])
    march = cut["monthly_summary"][0]
    assert march["expenses"] == 500.0
    assert march["net"] == 11500.0


def test_totals_still_reconcile_after_exclusion():
    cut = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    excluded_labels=["Child Care", "Zelle Received"])
    assert round(sum(l["amount"] for l in cut["revenue_lines"]), 2) == cut["total_revenue"]
    assert round(sum(l["amount"] for l in cut["expense_lines"]), 2) == cut["total_expenses"]
    assert cut["net_profit"] == round(cut["total_revenue"] - cut["total_expenses"], 2)


def test_unknown_exclusion_label_is_harmless():
    cut = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    excluded_labels=["Does Not Exist"])
    assert cut["net_profit"] == 10000.0


def test_a_manual_line_can_be_excluded_too():
    rent = _Entry("Basement Office Rent", 1600.0, "expense", "monthly", datetime(2025, 3, 1))
    with_rent = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                          manual_entries=[rent])
    assert with_rent["total_expenses"] == 3600.0
    cut = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    manual_entries=[rent], excluded_labels=["Basement Office Rent"])
    assert cut["total_expenses"] == 2000.0


# --- manual entries that subtract ---

def test_negative_manual_entry_subtracts_from_expenses():
    credit = _Entry("Vendor Refund", -300.0, "expense", "once", datetime(2025, 3, 10))
    pnl = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    manual_entries=[credit])
    assert pnl["total_expenses"] == 1700.0         # 2000 - 300
    assert pnl["net_profit"] == 10300.0


def test_negative_manual_entry_subtracts_from_revenue():
    adj = _Entry("Overstated Income", -1000.0, "revenue", "once", datetime(2025, 3, 10))
    pnl = build_pnl(_mixed(), datetime(2025, 3, 1), datetime(2025, 3, 31),
                    manual_entries=[adj])
    assert pnl["total_revenue"] == 11000.0
    assert pnl["net_profit"] == 9000.0


def test_recurring_negative_entry_applies_every_month():
    adj = _Entry("Monthly Credit", -100.0, "expense", "monthly", datetime(2025, 1, 1))
    pnl = build_pnl([], datetime(2025, 1, 1), datetime(2025, 12, 31), manual_entries=[adj])
    assert pnl["total_expenses"] == -1200.0


# --- revenue is only what the business earned ---

def test_a_reversed_payment_touches_neither_side():
    # The outgoing leg and its reversal must both sit outside the statement,
    # or expenses and revenue are each inflated by the same amount.
    txs = [
        _Tx(datetime(2025, 4, 15), 1600.0, "Reversal", "debit"),
        _Tx(datetime(2025, 4, 22), 1600.0, "Reversal", "credit"),
    ]
    pnl = build_pnl(txs, datetime(2025, 4, 1), datetime(2025, 4, 30))
    assert pnl["total_revenue"] == 0.0
    assert pnl["total_expenses"] == 0.0
    assert pnl["total_excluded"] == 3200.0


def test_refund_nets_off_the_expense_side():
    txs = [
        _Tx(datetime(2025, 3, 5), 500.0, "Office Supplies", "debit"),
        _Tx(datetime(2025, 3, 9), 120.0, "Refund", "credit"),
    ]
    pnl = build_pnl(txs, datetime(2025, 3, 1), datetime(2025, 3, 31))
    assert pnl["total_revenue"] == 0.0
    assert pnl["total_expenses"] == 380.0
    line = [l for l in pnl["expense_lines"] if l["label"] == "Refunds & Credits"][0]
    assert line["amount"] == -120.0
