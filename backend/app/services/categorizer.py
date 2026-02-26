from typing import Optional
import re

CATEGORY_RULES = [
    (re.compile(r'grocery|safeway|kroger|whole foods|trader joe|aldi|publix|wegmans', re.I), "Groceries"),
    (re.compile(r'shell|chevron|exxon|bp|gas|fuel|mobil|citgo|sunoco', re.I), "Gas & Fuel"),
    (re.compile(r'electric|pge|con ed|utility|water bill|sewage|duke energy|southern company', re.I), "Utilities"),
    (re.compile(r'at&t|verizon|t-mobile|comcast|internet|phone bill|spectrum|xfinity', re.I), "Telecom"),
    (re.compile(r'amazon|ebay|walmart|target|costco|bestbuy|home depot|lowes', re.I), "Shopping"),
    (re.compile(r'starbucks|dunkin|coffee|mcdonald|burger king|chipotle|doordash|uber eats|grubhub|instacart', re.I), "Food & Dining"),
    (re.compile(r'delta|united|southwest|american air|hotel|airbnb|marriott|hilton|hyatt|expedia', re.I), "Travel"),
    (re.compile(r'payroll|salary|direct deposit|gusto|adp|paychex|rippling', re.I), "Payroll"),
    (re.compile(r'stripe|paypal|square|shopify|invoice|venmo', re.I), "Business Revenue"),
    (re.compile(r'rent|lease|property|landlord', re.I), "Rent"),
    (re.compile(r'insurance|allstate|geico|progressive|anthem|cigna|aetna|metlife', re.I), "Insurance"),
    (re.compile(r'office depot|staples|supplies|printing|uline', re.I), "Office Supplies"),
    (re.compile(r'bank fee|monthly fee|service charge|overdraft|maintenance fee', re.I), "Bank Fees"),
    (re.compile(r'loan|mortgage|payment due|interest charge|auto loan', re.I), "Loan Payments"),
    (re.compile(r'zelle', re.I), "Zelle Transfer"),
    (re.compile(r'netflix|spotify|hulu|adobe|microsoft|google|apple|subscription|saas', re.I), "Software & Subscriptions"),
    (re.compile(r'doctor|hospital|pharmacy|cvs|walgreens|medical|dental|health', re.I), "Healthcare"),
    (re.compile(r'uber|lyft|taxi|parking|metro|transit|train|bus', re.I), "Transportation"),
]

def categorize_transaction(
    name: str,
    description: Optional[str] = None,
    plaid_category: Optional[str] = None,
) -> str:
    if plaid_category:
        return plaid_category
    text = f"{name or ''} {description or ''}"
    for pattern, category in CATEGORY_RULES:
        if pattern.search(text):
            return category
    return "Uncategorized"
