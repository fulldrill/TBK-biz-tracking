"""Business-purpose notes for transactions.

A receipt that says only "OVERDRAFT ITEM FEE $36" does not show the fee was an
ordinary business cost. A note naming the transactions that drew the balance
down does — and that link is computable, not guessed.

Two tiers, in order:

1. Derived rules. Facts already in the ledger: which debits caused a fee, which
   withdrawal a fee is attached to, which month a payroll deposit was earned in.
2. AI restatement. For descriptions that need decoding ("ACH PMT AMEX
   EPAYMENT"), the model restates what the description says — nothing more.

Anything neither tier can establish is left empty and flagged. These records
support tax filings; inventing a purpose the data cannot show would be
manufacturing evidence, so the generator declines and asks the owner instead.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta
from typing import Any, Iterable, Optional

# Sources, in descending authority. "manual" is never overwritten.
SOURCE_MANUAL = "manual"
SOURCE_DERIVED = "derived"
SOURCE_AI = "ai"
SOURCE_NEEDS_INPUT = "needs_input"

_OVERDRAFT_RE = re.compile(r"overdraft|nsf|insufficient|returned item", re.I)
_ATM_FEE_RE = re.compile(r"atm fee|non-truist atm|foreign atm|surcharge", re.I)
_ATM_CASH_RE = re.compile(r"atm .*(withdrawal|cash)|cash withdrawal", re.I)
_SERVICE_CHARGE_RE = re.compile(r"service charge|maintenance fee|monthly fee", re.I)
_CHECK_RE = re.compile(r"^\*?\s*\d{6,}$")  # a check row is just its number
_CARD_ISSUERS = [
    (re.compile(r"\bamex\b|american express", re.I), "American Express"),
    (re.compile(r"capital\s*one", re.I), "Capital One"),
    (re.compile(r"\bchase\b", re.I), "Chase"),
    (re.compile(r"\bdiscover\b", re.I), "Discover"),
    (re.compile(r"credit card pmt|credit card payment", re.I), "credit card"),
]
_CMCI_RE = re.compile(r"corp\s*pay\s*(cmci|cml)", re.I)
_PENNYMAC_RE = re.compile(r"pennymac", re.I)

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _fmt(amount: float) -> str:
    return f"${abs(amount):,.2f}"


def _date_str(dt) -> str:
    return dt.strftime("%d %b %Y")


def _tx_type(tx) -> str:
    return tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)


def _prior_month_name(dt) -> str:
    m = dt.month - 1 or 12
    year = dt.year if dt.month > 1 else dt.year - 1
    return f"{_MONTHS[m - 1]} {year}"


def _is_fee(tx) -> bool:
    name = tx.name or ""
    return bool(_OVERDRAFT_RE.search(name) or _ATM_FEE_RE.search(name)
                or _SERVICE_CHARGE_RE.search(name))


def _causing_debits(tx, by_date: dict, window_days: int = 3) -> list:
    """Debits in the days up to and including this fee, largest first.

    A bank charges an overdraft after the withdrawals that took the balance
    negative, so the cause sits at or just before the fee's own date.
    """
    found = []
    for offset in range(window_days + 1):
        day = (tx.date - timedelta(days=offset)).date()
        for other in by_date.get(day, []):
            if other is tx or _tx_type(other) != "debit" or _is_fee(other):
                continue
            found.append(other)
    return sorted(found, key=lambda t: abs(t.amount or 0), reverse=True)


def derive_purpose(tx, ctx: dict) -> tuple[Optional[str], str]:
    """Return (note, source). note is None when nothing can be established."""
    name = (tx.name or "").strip()
    category = (tx.category or "").strip()
    ttype = _tx_type(tx)

    # --- fees: name what caused them ---
    if _OVERDRAFT_RE.search(name):
        causes = _causing_debits(tx, ctx["by_date"])[:3]
        if causes:
            listed = "; ".join(
                f"{(c.name or '').strip()[:44]} {_fmt(c.amount)} on {_date_str(c.date)}"
                for c in causes
            )
            return (
                f"Bank fee charged on the business operating account after the "
                f"following business payments drew the balance down — {listed}.",
                SOURCE_DERIVED,
            )
        return (
            "Bank fee charged on the business operating account.",
            SOURCE_DERIVED,
        )

    if _ATM_FEE_RE.search(name):
        for offset in (0, 1, 2):
            day = (tx.date - timedelta(days=offset)).date()
            for other in ctx["by_date"].get(day, []):
                if other is not tx and _ATM_CASH_RE.search(other.name or ""):
                    return (
                        f"Out-of-network ATM surcharge on the cash withdrawal of "
                        f"{_fmt(other.amount)} on {_date_str(other.date)} from the "
                        f"business operating account.",
                        SOURCE_DERIVED,
                    )
        return ("Out-of-network ATM surcharge on the business operating account.",
                SOURCE_DERIVED)

    if _SERVICE_CHARGE_RE.search(name):
        return ("Bank account maintenance charge on the business operating account.",
                SOURCE_DERIVED)

    # --- revenue ---
    if _CMCI_RE.search(name) or category == "Gross Revenue":
        return (
            f"Client remittance for services performed in {_prior_month_name(tx.date)}, "
            f"paid in arrears on the 15th of the following month.",
            SOURCE_DERIVED,
        )

    # --- financing / property ---
    if _PENNYMAC_RE.search(name):
        return ("Mortgage servicing payment to PennyMac.", SOURCE_DERIVED)

    for pattern, issuer in _CARD_ISSUERS:
        if pattern.search(name):
            return (f"Payment to the {issuer} account used for business purchases.",
                    SOURCE_DERIVED)

    # --- Zelle: name the counterparty, and say how regular it is ---
    if tx.is_zelle and tx.zelle_counterparty:
        party = tx.zelle_counterparty
        stats = ctx["payee"].get(party.lower())
        recurrence = ""
        if stats and stats["count"] > 1:
            recurrence = (
                f" One of {stats['count']} payments to this payee in the period, "
                f"{_fmt(stats['total'])} in total."
            )
        if ttype == "credit":
            return (f"Funds received from {party} into the business account.{recurrence}",
                    SOURCE_DERIVED)
        if category == "Child Care":
            return (f"Payment to {party} for childcare services.{recurrence}",
                    SOURCE_DERIVED)
        return (f"Payment to {party} from the business account.{recurrence}",
                SOURCE_DERIVED)

    # --- things the ledger genuinely cannot explain ---
    if _ATM_CASH_RE.search(name):
        return (None, SOURCE_NEEDS_INPUT)      # what the cash bought is unrecorded
    if _CHECK_RE.match(name):
        return (None, SOURCE_NEEDS_INPUT)      # a check number says nothing
    if not name:
        return (None, SOURCE_NEEDS_INPUT)

    return (None, "")  # no rule matched — hand to the AI tier


def build_context(transactions: Iterable) -> dict:
    """Indexes the derivation rules need: same-day lookup and payee totals."""
    by_date: dict = defaultdict(list)
    payee: dict = defaultdict(lambda: {"count": 0, "total": 0.0})
    for tx in transactions:
        by_date[tx.date.date()].append(tx)
        if tx.zelle_counterparty:
            key = tx.zelle_counterparty.lower()
            payee[key]["count"] += 1
            payee[key]["total"] += abs(tx.amount or 0.0)
    return {"by_date": by_date, "payee": payee}


AI_SYSTEM_PROMPT = """You annotate business bank transactions with a short purpose note.

You will receive transaction descriptions. For each, write one sentence stating
what the transaction was, for a business expense record.

HARD RULES:
- Use ONLY what the description itself states. Never infer, assume, or invent.
- If the description does not reveal what the money was for, return null for
  that entry. A missing note is correct; a guessed one is falsification.
- Do not speculate about business benefit, necessity, or deductibility.
- Name the merchant or counterparty when the description contains one.
- One sentence, under 25 words, plain factual language.

Respond with JSON: {"notes": [{"index": <int>, "note": <string or null>}]}

Examples:
  "DEBIT CARD PURCHASE DELTA 006240 800-221-1212 GA"
    -> "Airfare purchased from Delta Air Lines."
  "DEBIT CARD RECURRING PYMT Google IY SMY9SW"
    -> "Recurring subscription charge from Google."
  "ATM NETWORK CASH WITHDRAWAL LAUREL MD"
    -> null   (the description does not say what the cash was used for)
  "CHECK 7015761"
    -> null   (a check number reveals nothing about its purpose)
"""


async def ai_purposes(client, descriptions: list[str]) -> dict[int, Optional[str]]:
    """Ask the model to restate descriptions. Returns {index: note or None}."""
    import json

    if not descriptions:
        return {}

    numbered = "\n".join(f"{i}. {d}" for i, d in enumerate(descriptions))
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=4096,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": numbered},
            ],
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return {}

    out: dict[int, Optional[str]] = {}
    for item in data.get("notes", []):
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        note = item.get("note")
        out[idx] = note.strip() if isinstance(note, str) and note.strip() else None
    return out
