import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.statement_amex_parser import (
    is_amex_report,
    amex_purpose,
    enrich_amex,
    AMEX_CATEGORY_MAP,
    REVIEW_CATEGORIES,
)
from app.services.categorizer import categorize_transaction
from app.services.pnl import classify


def test_detects_an_amex_year_end_summary():
    assert is_amex_report("2025 Year-End Summary\nCard Member B AMIBANG") is True


def test_does_not_claim_a_bank_statement():
    assert is_amex_report("Your account statement\nFor 08/29/2025") is False
    assert is_amex_report("") is False


# --- category routing ---

def test_card_categories_fold_into_existing_pnl_lines():
    assert AMEX_CATEGORY_MAP["Restaurant"] == "Meals & Entertainment"
    assert AMEX_CATEGORY_MAP["Fuel"] == "Travel & Transportation"
    assert AMEX_CATEGORY_MAP["Insurance Services"] == "Insurance"
    assert AMEX_CATEGORY_MAP["Banking Services"] == "Bank Fees"


def test_unmapped_categories_keep_their_own_line():
    # "Groceries" is not in the map, so it stays visible as itself rather than
    # being folded into a business line.
    assert "Groceries" not in AMEX_CATEGORY_MAP
    assert classify("Groceries", "debit")[1] == "Meals & Entertainment"


# --- the review flag ---

def test_personal_looking_categories_are_flagged_not_asserted():
    note, source = amex_purpose("WHOLEFDS SILVER SPRING MD", "Groceries", False)
    assert note is None
    assert source == "needs_input"


def test_clearly_business_categories_get_a_note():
    note, source = amex_purpose("USPS PO 2351310046 LAUREL MD", "Mailing & Shipping", False)
    assert source == "derived"
    assert "USPS" in note


def test_refunds_are_described_as_refunds():
    note, source = amex_purpose("AMAZON.COM SEATTLE WA", "Groceries", True)
    assert source == "derived"
    assert "Refund" in note


def test_review_set_covers_the_obviously_personal():
    for cat in ("Groceries", "Clothing Stores", "Theme Parks", "Health Care Services"):
        assert cat in REVIEW_CATEGORIES


# --- enrichment ---

def _rows():
    return [
        {"date": "2025-03-04", "name": "WHOLEFDS MD", "amount": 82.10,
         "transaction_type": "debit", "amex_category": "Groceries"},
        {"date": "2025-03-05", "name": "SHELL OIL", "amount": 60.00,
         "transaction_type": "debit", "amex_category": "Fuel"},
        {"date": "2025-03-06", "name": "OLIVE GARDEN", "amount": -40.00,
         "transaction_type": "credit", "amex_category": "Restaurant"},
    ]


def test_enrich_sets_category_purpose_and_provenance():
    out = enrich_amex(
        _rows(), "AnnualManagementReport2025.pdf",
        {"account_name": "AMERICAN EXPRESS Business Gold Card",
         "account_masked": "••••2005"},
        "2025-12-31",
    )
    assert out[1]["category"] == "Travel & Transportation"
    assert out[1]["purpose_source"] == "derived"
    assert out[0]["purpose_source"] == "needs_input"
    assert out[0]["account_label"].endswith("••••2005")
    assert out[0]["statement_period"] == "2025-12-31"
    assert out[0]["source"] == "statement_import"


def test_refund_does_not_become_revenue_in_its_spending_category():
    out = enrich_amex(_rows(), "x.pdf", {}, "2025-12-31")
    refund = out[2]
    assert refund["category"] == "Refund"
    assert refund["amount"] == 40.00          # magnitude; direction is on the type
    assert classify("Refund", "credit")[1] == "Refunds & Credits"


def test_enrich_clears_zelle_fields():
    out = enrich_amex(_rows(), "x.pdf", {}, None)
    assert all(t["is_zelle"] is False for t in out)
    assert all(t["zelle_counterparty"] is None for t in out)


# --- the bank-side payment must be separable ---

def test_amex_payments_get_their_own_line():
    cat = categorize_transaction(
        "ACH CORP DEBIT ACH PMT AMEX EPAYMENT BRIGHT AMIBANG CUSTOMER ID", None, "Payment"
    )
    assert cat == "Amex Card Payment"
    assert classify(cat, "debit")[1] == "Amex Card Payment"


def test_other_card_payments_are_untouched():
    # Capital One statements are not imported, so those payments must stay put.
    cat = categorize_transaction(
        "ACH CORP DEBIT MOBILE PMT CAPITAL ONE BRIGHT AMIBANG", None, "Payment"
    )
    assert cat == "Payment"
    assert classify(cat, "debit")[1] == "Card & Finance Payments"
