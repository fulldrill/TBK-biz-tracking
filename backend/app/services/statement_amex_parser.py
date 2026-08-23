"""Parsing an American Express Year-End Summary.

A card statement is a different animal from a bank statement. The rows are
charges against a liability rather than movements of cash, they are grouped
under Amex's own spending categories, and — critically — a charge and a refund
print identically as "$12.34". Only the *column* tells them apart, and reading
the page as a stream of text throws that away.

So this parser works from word coordinates: the Charges column sits at roughly
x=460 and Credits at x=550, and an amount is classified by which side of the
midpoint it falls on. A refund becomes a negative amount, which is what makes
the totals reconcile.

Every category prints its own subtotal, so extraction is checked against them
the same way the bank parser checks against the statement's printed totals.

The report covers charges only — it contains no payments to the card — so
importing it cannot create phantom revenue. The matching payments live on the
bank statement and are excluded there instead.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import fitz  # pymupdf

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_MONEY_RE = re.compile(r"^-?\$([\d,]+\.\d{2})$")
_SUBTOTAL_RE = re.compile(r"^(.*?)\s*Subtotal$", re.I)
_ACCOUNT_RE = re.compile(r"(X{4}-X{6}-(\d{4,5}))")
_PREPARED_RE = re.compile(r"Prepared for (.+?)\s*-\s*\d+", re.I)
_YEAR_RE = re.compile(r"(\d{4}) Year-End Summary")

_MONTHS = {
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
}

# Column midpoint between Charges (~x=460) and Credits (~x=550).
_CREDIT_X_THRESHOLD = 520.0


def is_amex_report(text: str) -> bool:
    """True when this looks like an Amex Year-End Summary."""
    return bool(_YEAR_RE.search(text or "")) and "Card Member" in (text or "")


def _page_lines(page) -> list[tuple[str, list[tuple[str, float]]]]:
    """Group a page's words into visual lines, preserving x positions."""
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
    rows: dict[int, list[tuple[float, str]]] = {}
    for x0, y0, _x1, _y1, word, *_ in words:
        rows.setdefault(round(y0), []).append((x0, word))
    lines = []
    for y in sorted(rows):
        ordered = sorted(rows[y], key=lambda t: t[0])
        text = " ".join(w for _, w in ordered)
        lines.append((text, [(w, x) for x, w in ordered]))
    return lines


def _amounts_in(tokens: list[tuple[str, float]]) -> list[tuple[float, bool]]:
    """Money tokens on a line as (value, is_credit)."""
    out = []
    for word, x in tokens:
        m = _MONEY_RE.match(word)
        if m:
            out.append((float(m.group(1).replace(",", "")), x >= _CREDIT_X_THRESHOLD))
    return out


def parse_amex_report(pdf_bytes: bytes, filename: str = "") -> dict[str, Any]:
    """Extract itemised charges from an Amex Year-End Summary.

    Returns {"transactions", "checks", "account", "period_end"}. Refunds carry a
    negative amount so a category's rows sum to its printed net.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        full_text = "".join(p.get_text() for p in doc)
        all_lines: list[tuple[str, list[tuple[str, float]]]] = []
        for page in doc:
            all_lines.extend(_page_lines(page))
    finally:
        doc.close()

    year_match = _YEAR_RE.search(full_text)
    year = year_match.group(1) if year_match else None

    account: dict[str, str] = {}
    acc = _ACCOUNT_RE.search(full_text)
    if acc:
        account["account_masked"] = f"••••{acc.group(2)[-4:]}"
    prepared = _PREPARED_RE.search(full_text)
    account["account_name"] = (
        f"AMERICAN EXPRESS {prepared.group(1).strip()}" if prepared else "AMERICAN EXPRESS"
    )
    account["institution"] = "American Express"

    transactions: list[dict[str, Any]] = []
    stated: dict[str, dict[str, float]] = {}
    extracted: dict[str, dict[str, float]] = {}

    # The category name is printed just above its "Card Member" header; the
    # subtotal that closes a section repeats it, which is what we key on.
    pending: list[dict[str, Any]] = []
    section_guess = ""

    for idx, (text, tokens) in enumerate(all_lines):
        stripped = text.strip()

        sub = _SUBTOTAL_RE.match(stripped.split("$")[0].strip())
        if sub and "$" in stripped:
            name = sub.group(1).strip() or section_guess
            amounts = _amounts_in(tokens)
            charges = sum(v for v, is_c in amounts if not is_c)
            credits = sum(v for v, is_c in amounts if is_c)
            if name:
                # A section closes with a group subtotal then a category
                # subtotal carrying the same figures; keep the named one.
                stated[name] = {"charges": charges, "credits": credits}
                for row in pending:
                    row["amex_category"] = name
                    extracted.setdefault(name, {"charges": 0.0, "credits": 0.0})
                    key = "credits" if row["amount"] < 0 else "charges"
                    extracted[name][key] += abs(row["amount"])
                transactions.extend(pending)
                pending = []
            continue

        # Remember the last plain heading — it names the section below it.
        if stripped and "$" not in stripped and not _DATE_RE.match(stripped.split(" ")[0]):
            if idx + 1 < len(all_lines) and "Card Member" in all_lines[idx + 1][0]:
                section_guess = stripped

        first = stripped.split(" ")[0] if stripped else ""
        if not _DATE_RE.match(first):
            continue

        amounts = _amounts_in(tokens)
        if not amounts:
            continue

        try:
            when = datetime.strptime(first, "%m/%d/%Y")
        except ValueError:
            continue

        words = [w for w, _ in tokens]
        # Drop the date, the "Month Billed" column, and the money tokens.
        body = [w for w in words[1:] if not _MONEY_RE.match(w)]
        if body and body[0] in _MONTHS:
            body = body[1:]
        name = re.sub(r"\s+", " ", " ".join(body)).strip()

        value, is_credit = amounts[0]
        pending.append({
            "date": when.strftime("%Y-%m-%d"),
            "name": name or "(no description)",
            # Negative for a refund: it reduces the expense rather than adding.
            "amount": -value if is_credit else value,
            "transaction_type": "credit" if is_credit else "debit",
            "amex_category": section_guess,
        })

    # Anything after the final subtotal still belongs in the output.
    transactions.extend(pending)

    checks = {"sections": [], "ok": True}
    for name, figures in stated.items():
        ours = extracted.get(name, {"charges": 0.0, "credits": 0.0})
        ok = (
            abs(round(ours["charges"], 2) - round(figures["charges"], 2)) < 0.01
            and abs(round(ours["credits"], 2) - round(figures["credits"], 2)) < 0.01
        )
        if not ok:
            checks["ok"] = False
        checks["sections"].append({
            "section": name,
            "extracted_charges": round(ours["charges"], 2),
            "stated_charges": round(figures["charges"], 2),
            "extracted_credits": round(ours["credits"], 2),
            "stated_credits": round(figures["credits"], 2),
            "ok": ok,
        })

    return {
        "transactions": transactions,
        "checks": checks,
        "account": account,
        "period_end": f"{year}-12-31" if year else None,
        "filename": filename,
    }


# ---------------------------------------------------------------------------
# Category handling
# ---------------------------------------------------------------------------
#
# Amex's own categories are more useful than anything we could re-derive, so
# most pass through as the P&L line. A few fold into lines the bank feed
# already uses, so card and bank spending on the same thing land together.
AMEX_CATEGORY_MAP = {
    "Mailing & Shipping": "Office Supplies",
    "Office Supplies": "Office Supplies",
    "Computer Supplies": "Supplies & Equipment",
    "Electronics Stores": "Supplies & Equipment",
    "Hardware Supplies": "Supplies & Equipment",
    "Furnishing": "Supplies & Equipment",
    "Banking Services": "Bank Fees",
    "Fees & Adjustments": "Bank Fees",
    "Insurance Services": "Insurance",
    "Internet Services": "Utilities & Telecom",
    "Other Telecom": "Utilities & Telecom",
    "Contracting Services": "Payroll & Contractors",
    "Fuel": "Travel & Transportation",
    "Parking Charges": "Travel & Transportation",
    "Lodging": "Travel & Transportation",
    "Other Travel": "Travel & Transportation",
    "Restaurant": "Meals & Entertainment",
    "Bar & Café": "Meals & Entertainment",
}

# Categories where only the owner can say whether a charge was for the
# business. Groceries and clothing are not business costs by default, and
# guessing either way on an itemised, auditable record would be wrong — so
# these import at face value and are flagged for review rather than silently
# deducted or silently dropped.
REVIEW_CATEGORIES = {
    "Groceries", "Clothing Stores", "Department Stores", "General Retail",
    "Internet Purchase", "Mail Order", "Wholesale Stores", "Sporting Goods Stores",
    "Arts & Jewelry", "Florists & Garden", "Theme Parks", "Theatrical Events",
    "General Attractions", "General Events", "Other Entertainment",
    "Health Care Services", "Education", "Other Services", "Miscellaneous",
    "Associations", "Government Services", "Professional Services",
    "Conferences & Training",
}


def amex_purpose(name: str, category: str, is_refund: bool) -> tuple[str | None, str]:
    """(note, purpose_source) for one card charge."""
    merchant = re.sub(r"\s{2,}", " ", (name or "")).strip()
    if is_refund:
        return (
            f"Refund credited by {merchant} to the business card account.",
            "derived",
        )
    if category in REVIEW_CATEGORIES:
        # The merchant alone does not establish a business purpose here.
        return (None, "needs_input")
    return (f"Business card purchase from {merchant}.", "derived")


def enrich_amex(
    transactions: list[dict[str, Any]],
    filename: str,
    account: dict[str, str],
    period_end: str | None,
) -> list[dict[str, Any]]:
    """Attach P&L category, purpose note, and provenance to card charges."""
    label = f'{account.get("account_name", "")} {account.get("account_masked", "")}'.strip()
    for tx in transactions:
        amex_cat = tx.get("amex_category") or "Miscellaneous"
        is_refund = tx["amount"] < 0
        # A refund is not income. The P&L sums transaction magnitudes and has
        # no signed-amount concept for bank rows, so refunds land on their own
        # revenue line where they stay visible rather than being buried in a
        # category they would silently offset.
        tx["category"] = (
            "Refund" if is_refund else AMEX_CATEGORY_MAP.get(amex_cat, amex_cat)
        )
        note, source = amex_purpose(tx["name"], amex_cat, is_refund)
        tx["business_purpose"] = note
        tx["purpose_source"] = source
        tx["is_zelle"] = False
        tx["zelle_counterparty"] = None
        tx["zelle_direction"] = None
        tx["assigned_user"] = None
        tx["source"] = "statement_import"
        tx["statement_file"] = filename
        tx["statement_period"] = period_end
        tx["account_label"] = label or None
        # Amount is carried as a signed value; the importer stores the
        # magnitude and uses transaction_type for direction.
        tx["amount"] = abs(tx["amount"])
    return transactions
