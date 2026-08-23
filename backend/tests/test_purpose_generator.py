import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

from app.services.purpose_generator import (
    build_context,
    derive_purpose,
    SOURCE_DERIVED,
    SOURCE_NEEDS_INPUT,
)


class _Type:
    def __init__(self, value):
        self.value = value


class _Tx:
    def __init__(self, date, amount, name, ttype="debit", category=None,
                 is_zelle=False, counterparty=None):
        self.date = date
        self.amount = amount
        self.name = name
        self.category = category
        self.is_zelle = is_zelle
        self.zelle_counterparty = counterparty
        self.transaction_type = _Type(ttype)


def _derive(target, others=()):
    rows = list(others) + [target]
    return derive_purpose(target, build_context(rows))


# --- the flagship case: an overdraft fee must name what caused it ---

def test_overdraft_fee_cites_the_debits_that_caused_it():
    amex = _Tx(datetime(2025, 11, 17), 5000.0, "ACH CORP DEBIT ACH PMT AMEX EPAYMENT")
    check = _Tx(datetime(2025, 11, 17), 2000.0, "10365041")
    fee = _Tx(datetime(2025, 11, 20), 36.0, "OVERDRAFT ITEM FEE ($36/ITEM) 36")
    note, source = _derive(fee, [amex, check])

    assert source == SOURCE_DERIVED
    assert "AMEX" in note
    assert "$5,000.00" in note
    assert "17 Nov 2025" in note


def test_overdraft_note_lists_largest_causes_first():
    small = _Tx(datetime(2025, 11, 19), 50.0, "SMALL DEBIT")
    large = _Tx(datetime(2025, 11, 19), 900.0, "LARGE DEBIT")
    fee = _Tx(datetime(2025, 11, 20), 36.0, "OVERDRAFT ITEM FEE ($36/ITEM) 36")
    note, _ = _derive(fee, [small, large])
    assert note.index("LARGE DEBIT") < note.index("SMALL DEBIT")


def test_overdraft_does_not_cite_other_fees_as_the_cause():
    other_fee = _Tx(datetime(2025, 11, 20), 3.0, "DEBIT CARD NON-TRUIST ATM FEE")
    fee = _Tx(datetime(2025, 11, 20), 36.0, "OVERDRAFT ITEM FEE ($36/ITEM) 36")
    note, _ = _derive(fee, [other_fee])
    assert "ATM FEE" not in note


def test_overdraft_with_no_nearby_debits_still_gets_a_factual_note():
    fee = _Tx(datetime(2025, 11, 20), 36.0, "OVERDRAFT ITEM FEE ($36/ITEM) 36")
    note, source = _derive(fee)
    assert source == SOURCE_DERIVED
    assert "Bank fee" in note


def test_causes_outside_the_window_are_not_cited():
    old = _Tx(datetime(2025, 11, 1), 900.0, "ANCIENT DEBIT")
    fee = _Tx(datetime(2025, 11, 20), 36.0, "OVERDRAFT ITEM FEE ($36/ITEM) 36")
    note, _ = _derive(fee, [old])
    assert "ANCIENT DEBIT" not in note


# --- ATM surcharge pairs with its withdrawal ---

def test_atm_fee_is_linked_to_the_withdrawal():
    cash = _Tx(datetime(2025, 11, 20), 203.25, "ATM NETWORK CASH WITHDRAWAL 11-19-25 LAUREL")
    fee = _Tx(datetime(2025, 11, 20), 3.0, "DEBIT CARD NON-TRUIST ATM FEE 11-19-25 LAUREL")
    note, source = _derive(fee, [cash])
    assert source == SOURCE_DERIVED
    assert "$203.25" in note


# --- revenue and financing ---

def test_payroll_deposit_names_the_month_it_was_earned():
    dep = _Tx(datetime(2025, 8, 15), 12479.05,
              "CORP PAY CMCI- 6463 LITANRYAN TECHNOLOGIE", ttype="credit",
              category="Gross Revenue")
    note, source = _derive(dep)
    assert source == SOURCE_DERIVED
    assert "July 2025" in note        # paid 15 Aug, earned in July


def test_january_deposit_rolls_back_to_december_of_the_prior_year():
    dep = _Tx(datetime(2025, 1, 15), 13563.72, "CORP PAY CMCI- 6463", ttype="credit",
              category="Gross Revenue")
    note, _ = _derive(dep)
    assert "December 2024" in note


def test_card_payments_name_the_issuer():
    amex = _Tx(datetime(2025, 8, 18), 3056.0, "ACH CORP DEBIT ACH PMT AMEX EPAYMENT")
    assert "American Express" in _derive(amex)[0]
    cap1 = _Tx(datetime(2025, 8, 18), 250.0, "ACH CORP DEBIT MOBILE PMT CAPITAL ONE")
    assert "Capital One" in _derive(cap1)[0]


def test_mortgage_payment_is_named():
    m = _Tx(datetime(2025, 8, 18), 3576.14, "INTERNET PAYMENT CASH PENNYMAC 8203963792")
    note, source = _derive(m)
    assert source == SOURCE_DERIVED
    assert "PennyMac" in note


# --- Zelle ---

def test_zelle_payment_names_the_counterparty():
    z = _Tx(datetime(2025, 8, 15), 580.0, "ZELLE BUSINESS PAYMENT TO Bee Amibang",
            is_zelle=True, counterparty="Bee Amibang")
    note, source = _derive(z)
    assert source == SOURCE_DERIVED
    assert "Bee Amibang" in note


def test_repeat_payee_note_reports_the_run():
    rows = [
        _Tx(datetime(2025, 8, d), 100.0, "ZELLE BUSINESS PAYMENT TO Bee Amibang",
            is_zelle=True, counterparty="Bee Amibang")
        for d in (1, 8, 15)
    ]
    note, _ = derive_purpose(rows[0], build_context(rows))
    assert "3 payments" in note
    assert "$300.00" in note


def test_childcare_zelle_says_what_it_was_for():
    z = _Tx(datetime(2025, 8, 15), 1600.0, "ZELLE BUSINESS PAYMENT TO Mimi S",
            is_zelle=True, counterparty="Mimi S", category="Child Care")
    assert "childcare" in _derive(z)[0].lower()


def test_incoming_zelle_is_described_as_received():
    z = _Tx(datetime(2025, 8, 15), 2000.0, "ZELLE BUSINESS PAYMENT FROM BRIGHT AMIBANG",
            ttype="credit", is_zelle=True, counterparty="BRIGHT AMIBANG")
    assert "received" in _derive(z)[0].lower()


# --- the honesty guardrail ---

def test_cash_withdrawal_is_flagged_not_invented():
    # Nothing in the ledger says what the cash bought, so no note is written.
    cash = _Tx(datetime(2025, 11, 20), 203.25, "ATM NETWORK CASH WITHDRAWAL LAUREL MD")
    note, source = _derive(cash)
    assert note is None
    assert source == SOURCE_NEEDS_INPUT


def test_bare_check_number_is_flagged():
    chk = _Tx(datetime(2025, 8, 15), 1865.0, "14345952")
    note, source = _derive(chk)
    assert note is None
    assert source == SOURCE_NEEDS_INPUT


def test_starred_check_number_is_flagged():
    chk = _Tx(datetime(2025, 8, 15), 1500.0, "* 14363127")
    assert _derive(chk)[1] == SOURCE_NEEDS_INPUT


def test_unmatched_description_falls_through_to_the_ai_tier():
    other = _Tx(datetime(2025, 2, 23), 751.79, "DEBIT CARD PURCHASE DELTA 006240")
    note, source = _derive(other)
    assert note is None
    assert source == ""          # empty source means "hand to the model"
