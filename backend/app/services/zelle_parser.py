import re
from typing import Optional, Tuple

ZELLE_KEYWORDS = ["zelle", "zelle®", "zelle payment", "send money with zelle"]

EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
)
PHONE_PATTERN = re.compile(
    r'(\+?1[-.\s]?)?(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})'
)

def is_zelle_transaction(name: str, description: Optional[str] = None) -> bool:
    text = f"{name or ''} {description or ''}".lower()
    return any(keyword in text for keyword in ZELLE_KEYWORDS)

def extract_zelle_counterparty(name: str, description: Optional[str] = None) -> Optional[str]:
    text = f"{name or ''} {description or ''}"
    email_match = EMAIL_PATTERN.search(text)
    if email_match:
        return email_match.group(0)
    phone_match = PHONE_PATTERN.search(text)
    if phone_match:
        return phone_match.group(0)
    from_match = re.search(r'(?:from|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', text)
    if from_match:
        return from_match.group(1)
    return None

def detect_zelle_direction(name: str, amount: float) -> str:
    if amount > 0:
        return "sent"
    return "received"

def parse_zelle(name: str, description: Optional[str], amount: float) -> Tuple[bool, Optional[str], Optional[str]]:
    if not is_zelle_transaction(name, description):
        return False, None, None
    counterparty = extract_zelle_counterparty(name, description)
    direction = detect_zelle_direction(name, amount)
    return True, counterparty, direction
