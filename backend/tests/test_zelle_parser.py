import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.zelle_parser import parse_zelle, is_zelle_transaction, extract_zelle_counterparty

def test_detects_zelle_by_keyword():
    assert is_zelle_transaction("Zelle payment from John") is True
    assert is_zelle_transaction("ZELLE® to jane@example.com") is True
    assert is_zelle_transaction("ACH Direct Deposit Payroll") is False

def test_extracts_email_counterparty():
    cp = extract_zelle_counterparty("Zelle from john.doe@gmail.com", None)
    assert cp == "john.doe@gmail.com"

def test_extracts_phone_counterparty():
    cp = extract_zelle_counterparty("Zelle payment 555-867-5309", None)
    assert cp is not None

def test_zelle_direction_debit():
    is_z, party, direction = parse_zelle("Zelle to sarah@biz.com", None, 250.00)
    assert is_z is True
    assert direction == "sent"
    assert party == "sarah@biz.com"

def test_zelle_direction_credit():
    is_z, party, direction = parse_zelle("Zelle from mike@company.com", None, -500.00)
    assert is_z is True
    assert direction == "received"

def test_non_zelle_transaction():
    is_z, party, direction = parse_zelle("AMAZON.COM PURCHASE", None, 89.99)
    assert is_z is False
    assert party is None
    assert direction is None

def test_zelle_no_counterparty():
    is_z, party, direction = parse_zelle("Zelle Payment", None, 100.00)
    assert is_z is True
    assert direction == "sent"

if __name__ == "__main__":
    test_detects_zelle_by_keyword()
    test_extracts_email_counterparty()
    test_extracts_phone_counterparty()
    test_zelle_direction_debit()
    test_zelle_direction_credit()
    test_non_zelle_transaction()
    test_zelle_no_counterparty()
    print("All zelle parser tests passed!")
