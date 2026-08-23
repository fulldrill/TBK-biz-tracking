"""Deterministic statement parsing from a PDF's embedded text layer.

Most bank statements are generated documents, not scans — the exact text is
already in the file. Rendering those pages to PNG and asking a vision model to
read them back is slower, costs money, and loses rows: a dense page truncates
the response and the transactions on it vanish silently.

This module reads the text directly. It also self-checks: statements print
their own section totals ("Total deposits, credits and interest = $13,525.68"),
so extracted rows are summed and compared against them. A mismatch is reported
rather than swallowed, which is what makes a missing row detectable at all.

Falls back to the vision parser when a PDF has no usable text layer.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import fitz  # pymupdf

logger = logging.getLogger(__name__)

# A statement row starts with a bare MM/DD on its own line.
_DATE_RE = re.compile(r"^(\d{2})/(\d{2})$")
# ...and ends with a bare money amount on its own line.
_AMOUNT_RE = re.compile(r"^-?\$?([\d,]+\.\d{2})$")
# "For 02/28/2025" in the header gives the statement's closing date.
_PERIOD_RE = re.compile(r"For (\d{2})/(\d{2})/(\d{4})")

# Section headings, and whether rows beneath them are money in or money out.
_SECTIONS = [
    ("deposits, credits and interest", "credit"),
    ("other withdrawals, debits and service charges", "debit"),
    ("checks", "debit"),
    ("other withdrawals and service charges", "debit"),
    ("withdrawals and service charges", "debit"),
]
_TOTAL_RE = re.compile(r"^Total (.+?)\s*$", re.I)

# Lines that are structural, not data.
_NOISE = {"date", "description", "amount($)", "amount", "check number", "ref"}


def has_text_layer(pdf_bytes: bytes, min_chars: int = 200) -> bool:
    """True when the PDF carries enough embedded text to parse directly."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return False
    try:
        chars = sum(len(page.get_text()) for page in doc)
    finally:
        doc.close()
    return chars >= min_chars


# The account header line, e.g. "TRUIST SIMPLE BUSINESS CHECKING 1000271537218".
# Leading junk covers the bullet glyphs the PDF uses ("¡", "§").
#
# Uses [ \t] rather than \s so the match cannot run across a line break — the
# page-footer line ("PAGE 1 OF 3") sits directly above a stray number and would
# otherwise match.
_ACCOUNT_LINE_RE = re.compile(
    r"^[^A-Za-z0-9\n]*([A-Z][A-Z0-9 &'\-]{6,60}?)[ \t]+(\d{6,})[ \t]*$", re.M
)
# Page furniture that looks like an account line but is not.
_NOT_ACCOUNT = re.compile(r"\b(PAGE|STATEMENT|ACCOUNT SUMMARY)\b")


def mask_account(number: str) -> str:
    """Last four only. A receipt identifies the account; it does not expose it."""
    digits = re.sub(r"\D", "", number or "")
    return f"••••{digits[-4:]}" if len(digits) >= 4 else ""


def extract_account_info(text: str) -> dict[str, str]:
    """Pull the institution and account identity out of a statement header.

    This is what turns a receipt from a floating third-party summary into a
    voucher that ties back to primary documentation.
    """
    info: dict[str, str] = {}
    for m in _ACCOUNT_LINE_RE.finditer(text or ""):
        account_name = re.sub(r"\s+", " ", m.group(1)).strip()
        if _NOT_ACCOUNT.search(account_name):
            continue
        info["account_name"] = account_name
        info["account_masked"] = mask_account(m.group(2))
        # The institution is the leading word of the account description.
        first = account_name.split()[0] if account_name.split() else ""
        info["institution"] = first.title() if first else ""
        break
    return info


def _statement_period(text: str) -> datetime | None:
    m = _PERIOD_RE.search(text)
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _resolve_year(month: int, day: int, period_end: datetime | None) -> int:
    """Statement rows print MM/DD with no year — infer it from the period.

    A December row on a January statement belongs to the previous year, so any
    row whose month is ahead of the closing month rolls back one year.
    """
    if not period_end:
        return datetime.utcnow().year
    year = period_end.year
    if month > period_end.month:
        year -= 1
    return year


def _clean(desc_lines: list[str]) -> str:
    """Join a wrapped description into one line."""
    return re.sub(r"\s+", " ", " ".join(desc_lines)).strip()


def parse_statement_text(pdf_bytes: bytes, filename: str = "") -> dict[str, Any]:
    """Extract transactions from a text-layer PDF.

    Returns {"transactions": [...], "period_end": date|None, "checks": {...}}
    where `checks` reports the statement's own totals against ours.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

    period_end = _statement_period(text)
    account = extract_account_info(text)
    lines = [ln.strip() for ln in text.split("\n")]

    transactions: list[dict[str, Any]] = []
    stated_totals: dict[str, float] = {}

    section: str | None = None
    pending_date: tuple[int, int] | None = None
    desc: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower().rstrip(":")

        # Section totals — the statement's own checksum.
        total_match = _TOTAL_RE.match(line)
        if total_match:
            label = total_match.group(1).lower()
            # The amount sits on this line or the next ("= $13,525.68").
            blob = line
            if i + 1 < len(lines):
                blob += " " + lines[i + 1]
            amt = re.search(r"\$?(-?[\d,]+\.\d{2})", blob.split("=")[-1])
            if amt:
                for name, _kind in _SECTIONS:
                    if name.startswith(label[:20]) or label.startswith(name[:20]):
                        stated_totals[name] = float(amt.group(1).replace(",", ""))
                        break
            pending_date, desc = None, []
            section = None
            i += 1
            continue

        # Section heading.
        matched_section = None
        for name, kind in _SECTIONS:
            if low == name:
                matched_section = kind
                break
        if matched_section:
            section = matched_section
            pending_date, desc = None, []
            i += 1
            continue

        if low in _NOISE or not line:
            i += 1
            continue

        date_match = _DATE_RE.match(line)
        if date_match and section:
            # A new date ends any half-built row (a row with no amount is not
            # a transaction — usually a continued description).
            pending_date = (int(date_match.group(1)), int(date_match.group(2)))
            desc = []
            i += 1
            continue

        amount_match = _AMOUNT_RE.match(line)
        if amount_match and pending_date and section:
            month, day = pending_date
            year = _resolve_year(month, day, period_end)
            try:
                tx_date = datetime(year, month, day)
            except ValueError:
                pending_date, desc = None, []
                i += 1
                continue

            transactions.append({
                "date": tx_date.strftime("%Y-%m-%d"),
                "name": _clean(desc) or "(no description)",
                "amount": float(amount_match.group(1).replace(",", "")),
                "transaction_type": section,
            })
            pending_date, desc = None, []
            i += 1
            continue

        if pending_date is not None:
            desc.append(line)
        i += 1

    # --- self-check against the statement's printed totals ---
    # Several debit sections (withdrawals, checks) roll into one kind, so
    # compare kind-by-kind rather than section-by-section.
    checks: dict[str, Any] = {"sections": [], "ok": True}
    for kind in ("credit", "debit"):
        names = [n for n, k in _SECTIONS if k == kind and n in stated_totals]
        if not names:
            continue
        stated = round(sum(stated_totals[n] for n in names), 2)
        ours = round(sum(t["amount"] for t in transactions if t["transaction_type"] == kind), 2)
        ok = abs(ours - stated) < 0.01
        if not ok:
            checks["ok"] = False
        checks["sections"].append({
            "kind": kind,
            "sections": names,
            "extracted": ours,
            "stated": stated,
            "ok": ok,
            "difference": round(ours - stated, 2),
        })

    return {
        "transactions": transactions,
        "period_end": period_end.strftime("%Y-%m-%d") if period_end else None,
        "checks": checks,
        "filename": filename,
        "account": account,
    }


# ---------------------------------------------------------------------------
# Enrichment — Zelle, category, attribution
# ---------------------------------------------------------------------------

# "ZELLE BUSINESS PAYMENT TO Mimi S PAYMENT ID BBT288056871"
# The shared extractor in zelle_parser is case-sensitive on "to"/"from" and so
# never matches this bank's uppercase wording.
_ZELLE_PARTY_RE = re.compile(
    r"ZELLE[^\n]*?\b(?:TO|FROM)\s+(.+?)\s*(?:PAYMENT\s*ID|REF|$)",
    re.I,
)


def extract_counterparty(name: str) -> str | None:
    m = _ZELLE_PARTY_RE.search(name or "")
    if not m:
        return None
    party = re.sub(r"\s+", " ", m.group(1)).strip(" -–—")
    return party or None


def enrich(
    transactions: list[dict[str, Any]],
    filename: str = "",
    allowed_people: list[str] | None = None,
    period_end: str | None = None,
    account: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Add Zelle fields, category, and attribution to raw text-parsed rows."""
    from app.services.attribution import assign_user
    from app.services.categorizer import categorize_transaction
    from app.services.zelle_parser import is_zelle_transaction
    from app.services.owner_transfers import (
        owner_tokens, classify_owner_transfer, purpose_note, kind_of,
    )

    # Transfers to and from the org's own people are equity movement, not
    # expense. Classifying at import time keeps a re-import from silently
    # undoing it — the previous version only applied this as a one-off pass.
    owners = owner_tokens(allowed_people or [])
    names = [
        p if isinstance(p, str) else getattr(p, "name", "")
        for p in (allowed_people or [])
    ]
    names = [n for n in names if n]

    for tx in transactions:
        name = tx.get("name", "")
        is_zelle = is_zelle_transaction(name)
        tx["is_zelle"] = is_zelle
        tx["zelle_counterparty"] = extract_counterparty(name) if is_zelle else None
        # Direction comes from the statement section, not the amount sign —
        # the sign convention in zelle_parser is inverted and easy to trip on.
        tx["zelle_direction"] = (
            ("received" if tx["transaction_type"] == "credit" else "sent")
            if is_zelle else None
        )
        tx["category"] = categorize_transaction(
            name, None, _bank_category(name, is_zelle), tx["zelle_counterparty"]
        )
        tx["assigned_user"] = assign_user(
            name, tx["transaction_type"], is_zelle,
            tx["zelle_counterparty"], allowed=names or None,
        )

        owner_category, owner = classify_owner_transfer(
            is_zelle, tx["zelle_counterparty"], tx["zelle_direction"],
            tx["transaction_type"], owners,
        )
        if owner_category:
            tx["category"] = owner_category
            tx["business_purpose"] = purpose_note(
                owner_category, owner, kind=kind_of(owners, owner)
            )
            tx["purpose_source"] = "derived"
        tx["source"] = "statement_import"
        tx["statement_file"] = filename
        tx["statement_period"] = period_end
        acct = account or {}
        tx["account_label"] = (
            f'{acct.get("account_name", "")} {acct.get("account_masked", "")}'.strip()
            or None
        )

    return transactions


# Coarse labels matching what the vision path produced, so both parsers feed
# the P&L the same vocabulary.
_BANK_CATEGORY_RULES = [
    (re.compile(r"\bzelle\b", re.I), "Zelle"),
    (re.compile(r"atm|cash withdrawal", re.I), "ATM / Cash"),
    (re.compile(r"\bfee\b|overdraft|service charge", re.I), "Fee"),
    (re.compile(r"wire transfer|p2p|\btransfer\b", re.I), "Transfer"),
    (re.compile(r"deposit|corp pay", re.I), "Deposit"),
    (re.compile(r"payment|ach|check", re.I), "Payment"),
]


def _bank_category(name: str, is_zelle: bool) -> str:
    if is_zelle:
        return "Zelle"
    for pattern, label in _BANK_CATEGORY_RULES:
        if pattern.search(name or ""):
            return label
    return "Other"
