import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.categorizer import categorize_transaction

def test_grocery():
    assert categorize_transaction("WHOLE FOODS MARKET") == "Groceries"

def test_gas():
    assert categorize_transaction("CHEVRON GAS STATION") == "Gas & Fuel"

def test_zelle_category():
    assert categorize_transaction("Zelle payment") == "Zelle Transfer"

def test_uncategorized():
    assert categorize_transaction("RANDOM MERCHANT XYZ 12345") == "Uncategorized"

def test_plaid_category_override():
    result = categorize_transaction("Some store", plaid_category="Travel > Airlines")
    assert result == "Travel > Airlines"

def test_telecom():
    assert categorize_transaction("AT&T MONTHLY BILL") == "Telecom"

def test_shopping():
    assert categorize_transaction("AMAZON.COM ORDER") == "Shopping"

def test_food():
    assert categorize_transaction("DOORDASH ORDER") == "Food & Dining"

if __name__ == "__main__":
    test_grocery()
    test_gas()
    test_zelle_category()
    test_uncategorized()
    test_plaid_category_override()
    test_telecom()
    test_shopping()
    test_food()
    print("All categorizer tests passed!")
