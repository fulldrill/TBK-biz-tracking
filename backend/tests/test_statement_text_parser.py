import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.services.statement_text_parser import (
    parse_statement_text,
    has_text_layer,
    extract_counterparty,
    extract_account_info,
    mask_account,
    enrich,
    _resolve_year,
    _bank_category,
)


def _make_pdf(lines: list[str]) -> bytes:
    """Render lines into a real PDF so the parser exercises its text layer."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 740
    for line in lines:
        if y < 40:
            c.showPage()
            y = 740
        c.drawString(48, y, line)
        y -= 12
    c.save()
    return buf.getvalue()


# A Truist statement, trimmed to the shape the parser cares about.
STATEMENT = [
    "Your account statement",
    "For 02/28/2025",
    "Other withdrawals, debits and service charges",
    "DATE",
    "DESCRIPTION",
    "AMOUNT($)",
    "02/14",
    "ZELLE BUSINESS PAYMENT TO Mimi S PAYMENT ID    BBT288056871",
    "1,000.00",
    "02/18",
    "INTERNET PAYMENT CASH       PENNYMAC 8203963792-0026",
    "3,873.66",
    "02/24",
    "OVERDRAFT ITEM FEE ($36/ITEM) 36",
    "36.00",
    "Total other withdrawals, debits and service charges",
    "= $4,909.66",
    "Deposits, credits and interest",
    "DATE",
    "DESCRIPTION",
    "AMOUNT($)",
    "02/14",
    "CORP PAY   CMCI- 6463 LITANRYAN TECHNOLOGIE CUSTOMER ID",
    "13,525.68",
    "Total deposits, credits and interest",
    "= $13,525.68",
]


def test_detects_text_layer():
    assert has_text_layer(_make_pdf(STATEMENT)) is True
    assert has_text_layer(b"not a pdf") is False


def test_extracts_every_row():
    r = parse_statement_text(_make_pdf(STATEMENT), "feb.pdf")
    assert len(r["transactions"]) == 4


def test_reconciles_against_printed_totals():
    r = parse_statement_text(_make_pdf(STATEMENT), "feb.pdf")
    assert r["checks"]["ok"] is True
    by_kind = {s["kind"]: s for s in r["checks"]["sections"]}
    assert by_kind["credit"]["extracted"] == 13525.68
    assert by_kind["debit"]["extracted"] == 4909.66


def test_reconciliation_fails_when_a_row_is_missing():
    # Drop one debit row but leave the stated total — the checksum must catch it.
    broken = [l for l in STATEMENT if l not in ("02/24", "OVERDRAFT ITEM FEE ($36/ITEM) 36", "36.00")]
    r = parse_statement_text(_make_pdf(broken), "broken.pdf")
    assert r["checks"]["ok"] is False
    debit = [s for s in r["checks"]["sections"] if s["kind"] == "debit"][0]
    assert debit["difference"] == -36.00


def test_credits_and_debits_split_by_section():
    r = parse_statement_text(_make_pdf(STATEMENT), "feb.pdf")
    kinds = {t["transaction_type"] for t in r["transactions"]}
    assert kinds == {"credit", "debit"}
    deposit = [t for t in r["transactions"] if "CORP PAY" in t["name"]][0]
    assert deposit["transaction_type"] == "credit"
    assert deposit["amount"] == 13525.68
    zelle = [t for t in r["transactions"] if "ZELLE" in t["name"]][0]
    assert zelle["transaction_type"] == "debit"


def test_period_end_is_read_from_the_header():
    r = parse_statement_text(_make_pdf(STATEMENT), "feb.pdf")
    assert r["period_end"] == "2025-02-28"


def test_wrapped_descriptions_are_joined():
    lines = [
        "For 03/31/2025",
        "Other withdrawals, debits and service charges",
        "03/05",
        "ACH CORP DEBIT MOBILE PMT CAPITAL ONE CUSTOMER ID",
        "42TKQOYD3YLQ68S",
        "279.49",
        "Total other withdrawals, debits and service charges",
        "= $279.49",
    ]
    r = parse_statement_text(_make_pdf(lines), "wrap.pdf")
    assert len(r["transactions"]) == 1
    assert "CAPITAL ONE" in r["transactions"][0]["name"]
    assert "42TKQOYD3YLQ68S" in r["transactions"][0]["name"]


# --- year inference: rows print MM/DD with no year ---

def test_december_row_on_a_january_statement_is_prior_year():
    assert _resolve_year(12, 30, datetime(2025, 1, 31)) == 2024


def test_same_month_row_keeps_statement_year():
    assert _resolve_year(1, 15, datetime(2025, 1, 31)) == 2025


def test_year_rolls_back_across_the_boundary_in_a_full_parse():
    lines = [
        "For 01/31/2025",
        "Deposits, credits and interest",
        "12/30",
        "CORP PAY   CMCI- 6463 LITANRYAN TECHNOLOGIE",
        "1,000.00",
        "Total deposits, credits and interest",
        "= $1,000.00",
    ]
    r = parse_statement_text(_make_pdf(lines), "jan.pdf")
    assert r["transactions"][0]["date"] == "2024-12-30"


# --- Zelle counterparty ---

def test_counterparty_from_uppercase_to():
    name = "ZELLE BUSINESS PAYMENT TO Mimi S PAYMENT ID    BBT288056871"
    assert extract_counterparty(name) == "Mimi S"


def test_counterparty_from_uppercase_from():
    name = "ZELLE BUSINESS PAYMENT FROM BRIGHT AMIBANG PAYMENT ID PNCA"
    assert extract_counterparty(name) == "BRIGHT AMIBANG"


def test_non_zelle_has_no_counterparty():
    assert extract_counterparty("ATM NETWORK CASH WITHDRAWAL") is None


# --- enrichment ---

def test_enrich_applies_priority_categories():
    rows = [
        {"date": "2025-02-14", "name": "CORP PAY CMCI- 6463 LITANRYAN TECHNOLOGIE",
         "amount": 13525.68, "transaction_type": "credit"},
        {"date": "2025-02-18", "name": "INTERNET PAYMENT CASH PENNYMAC 8203963792",
         "amount": 3873.66, "transaction_type": "debit"},
        {"date": "2025-02-14", "name": "ZELLE BUSINESS PAYMENT TO Mimi S PAYMENT ID BBT2",
         "amount": 1000.00, "transaction_type": "debit"},
    ]
    out = enrich(rows, "feb.pdf")
    assert out[0]["category"] == "Gross Revenue"
    assert out[1]["category"] == "Mortgage"
    assert out[2]["category"] == "Child Care"


def test_enrich_sets_zelle_direction_from_section_not_amount_sign():
    rows = [
        {"date": "2025-02-14", "name": "ZELLE BUSINESS PAYMENT TO Bee Amibang PAYMENT ID X",
         "amount": 500.0, "transaction_type": "debit"},
        {"date": "2025-02-15", "name": "ZELLE BUSINESS PAYMENT FROM Bright Litandaze PAYMENT ID Y",
         "amount": 500.0, "transaction_type": "credit"},
    ]
    out = enrich(rows, "feb.pdf")
    assert out[0]["zelle_direction"] == "sent"
    assert out[1]["zelle_direction"] == "received"


def test_enrich_confines_attribution_to_the_orgs_people():
    # Kenny's rule fires on the description, but this org is Bright's alone.
    rows = [{"date": "2025-02-14", "name": "ZELLE PAYMENT FROM KENNETH MANJO",
             "amount": 100.0, "transaction_type": "credit"}]
    out = enrich(rows, "feb.pdf", allowed_people=["Bright"])
    assert out[0]["assigned_user"] == "Bright"


def test_bank_category_fallbacks():
    assert _bank_category("TRUIST ATM CASH WITHDRAWAL", False) == "ATM / Cash"
    assert _bank_category("OVERDRAFT ITEM FEE", False) == "Fee"
    assert _bank_category("OUTGOING WIRE TRANSFER", False) == "Transfer"
    assert _bank_category("anything else entirely", False) == "Other"


# --- account provenance ---

def test_extracts_institution_and_masked_account():
    text = "\n".join([
        "Contact us", "Truist.com",
        "LITANRYAN TECHNOLOGIES INC",
        "Your account statement", "For 08/29/2025",
        "§ PAGE  1  OF  2",
        "0049787",
        "¡ TRUIST SIMPLE BUSINESS CHECKING 1000271537218",
    ])
    info = extract_account_info(text)
    assert info["institution"] == "Truist"
    assert info["account_name"] == "TRUIST SIMPLE BUSINESS CHECKING"
    assert info["account_masked"] == "••••7218"


def test_page_furniture_is_not_mistaken_for_an_account():
    # "PAGE 1 OF 2" sits directly above a stray number in the text layer.
    text = "§ PAGE  1  OF  2\n0049787\n"
    assert extract_account_info(text) == {}


def test_mask_account_keeps_only_last_four():
    assert mask_account("1000271537218") == "••••7218"
    assert mask_account("12") == ""


def test_enrich_stamps_provenance_on_every_row():
    rows = [{"date": "2025-08-15", "name": "ANY", "amount": 1.0,
             "transaction_type": "debit"}]
    out = enrich(
        rows, "August, 2025.pdf",
        period_end="2025-08-29",
        account={"account_name": "TRUIST SIMPLE BUSINESS CHECKING",
                 "account_masked": "••••7218"},
    )
    assert out[0]["statement_file"] == "August, 2025.pdf"
    assert out[0]["statement_period"] == "2025-08-29"
    assert out[0]["account_label"] == "TRUIST SIMPLE BUSINESS CHECKING ••••7218"


def test_enrich_without_account_leaves_label_empty():
    rows = [{"date": "2025-08-15", "name": "ANY", "amount": 1.0,
             "transaction_type": "debit"}]
    out = enrich(rows, "x.pdf")
    assert out[0]["account_label"] is None
