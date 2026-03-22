"""
Statement Parser — converts bank statement PDFs into structured transaction data
using GPT-4o vision. Supports single PDF or ZIP of PDFs.

TBK Management attribution rules applied at parse time:
  - Zelle (any direction)             → Bright
  - Walk-in / cash / teller deposit   → Bright
  - Debit card / POS purchase         → Kenny
  - Other credit                      → unassigned
"""

import base64
import json
import io
import re
import zipfile
import logging
from typing import Any

import fitz  # pymupdf
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt sent to GPT-4o for every page image
# ---------------------------------------------------------------------------
EXTRACTION_SYSTEM_PROMPT = """You are a financial data extraction specialist working for TBK Management.

Your ONLY job is to read a bank statement image and return ALL transactions on the page as a JSON array.

EXTRACTION RULES:
1. Extract EVERY transaction row — do not skip any, even small amounts.
2. Skip header rows, sub-total rows, balance rows, and any row without a date.
3. Return ONLY a valid JSON array. No markdown, no explanation, no code fences.
4. If the page has no transactions, return an empty array: []

FIELD DEFINITIONS for each transaction object:
- "date"              : string, format "YYYY-MM-DD". Convert any format (Jan 15, 01/15/24, etc.) to ISO.
- "name"              : string, the full transaction description exactly as printed.
- "amount"            : number, always a POSITIVE float (absolute value).
- "transaction_type"  : "credit" if money came IN (deposit, transfer received, refund).
                        "debit"  if money went OUT (payment, purchase, withdrawal, fee).
- "is_zelle"          : true if the description contains "Zelle", "ZLL", "ZELLE PMT", or similar.
- "zelle_counterparty": string — the other party's name if is_zelle is true, otherwise null.
- "zelle_direction"   : "received" if is_zelle AND transaction_type is "credit".
                        "sent"     if is_zelle AND transaction_type is "debit".
                        null       if not a Zelle transaction.
- "category"          : one of exactly these values:
                          "Transfer", "Zelle", "Food & Dining", "Shopping", "Gas & Fuel",
                          "Utilities", "ATM / Cash", "Payment", "Deposit", "Fee", "Other"
                        Use "Zelle" for all Zelle transactions regardless of direction.

EXAMPLE OUTPUT (return ONLY an array like this, nothing else):
[
  {
    "date": "2024-01-03",
    "name": "ZELLE PAYMENT FROM MARCUS HILL",
    "amount": 850.00,
    "transaction_type": "credit",
    "is_zelle": true,
    "zelle_counterparty": "Marcus Hill",
    "zelle_direction": "received",
    "category": "Zelle"
  },
  {
    "date": "2024-01-05",
    "name": "POS DEBIT WALMART #4821",
    "amount": 47.32,
    "transaction_type": "debit",
    "is_zelle": false,
    "zelle_counterparty": null,
    "zelle_direction": null,
    "category": "Shopping"
  }
]"""

# ---------------------------------------------------------------------------
# Walk-in / manual deposit keyword detection
# ---------------------------------------------------------------------------
_WALK_IN_KEYWORDS = [
    "walk-in", "walk in", "walkin",
    "cash deposit", "counter deposit",
    "teller deposit", "branch deposit",
    "manual deposit", "over the counter",
]

_DEBIT_CARD_KEYWORDS = [
    "pos debit", "pos purchase", "debit card",
    "card purchase", "visa debit", "mastercard debit",
    "purchase", "point of sale",
]

# Names that identify Kenny in transaction descriptions / Zelle counterparty fields
_KENNY_KEYWORDS = ["kenneth", "kenny", "manjo"]


def _is_kenny_zelle(name: str, zelle_counterparty: str | None) -> bool:
    counterparty = (zelle_counterparty or "").lower()
    desc = name.lower()
    return any(k in counterparty or k in desc for k in _KENNY_KEYWORDS)


def assign_user(
    name: str,
    transaction_type: str,
    is_zelle: bool,
    zelle_counterparty: str | None = None,
) -> str | None:
    """
    TBK Management attribution logic.
    Returns "Kenny", "Bright", or None.
    """
    if is_zelle:
        return "Kenny" if _is_kenny_zelle(name, zelle_counterparty) else "Bright"

    desc = name.lower()

    if transaction_type == "credit" and any(k in desc for k in _WALK_IN_KEYWORDS):
        return "Bright"

    if transaction_type == "debit" and any(k in desc for k in _DEBIT_CARD_KEYWORDS):
        return "Kenny"

    return None


# ---------------------------------------------------------------------------
# PDF → per-page base64 PNG images
# ---------------------------------------------------------------------------
def _pdf_bytes_to_page_images(pdf_bytes: bytes, dpi: int = 150) -> list[str]:
    """
    Render every page of a PDF as a base64-encoded PNG string.
    DPI 150 is a good balance between OCR quality and token cost.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[str] = []
    zoom = dpi / 72  # pymupdf default is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pix.tobytes("png")
        images.append(base64.b64encode(png_bytes).decode("utf-8"))

    doc.close()
    return images


# ---------------------------------------------------------------------------
# Single page → GPT-4o → list of raw transaction dicts
# ---------------------------------------------------------------------------
async def _extract_page(
    client: AsyncOpenAI,
    b64_image: str,
    page_num: int,
) -> list[dict[str, Any]]:
    """Send one page image to GPT-4o and return the parsed transaction list."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            temperature=0,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract all transactions from this bank statement page. "
                                "Return ONLY the JSON array, nothing else."
                            ),
                        },
                    ],
                },
            ],
        )
    except Exception as e:
        logger.error(f"OpenAI API error on page {page_num}: {e}")
        return []

    raw = response.choices[0].message.content or ""

    # Strip markdown code fences if the model wrapped the JSON anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            logger.warning(f"Page {page_num}: GPT-4o returned non-list JSON, skipping")
            return []
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Page {page_num}: JSON parse failed — {e}\nRaw: {raw[:300]}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def parse_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    client: AsyncOpenAI,
) -> list[dict[str, Any]]:
    """
    Parse a single PDF's worth of bytes.
    Returns a list of transaction dicts enriched with 'assigned_user' and 'source'.
    """
    logger.info(f"Parsing PDF: {filename}")
    page_images = _pdf_bytes_to_page_images(pdf_bytes)
    logger.info(f"  → {len(page_images)} page(s)")

    all_transactions: list[dict[str, Any]] = []
    for i, img_b64 in enumerate(page_images, start=1):
        page_txns = await _extract_page(client, img_b64, page_num=i)
        logger.info(f"  → Page {i}: {len(page_txns)} transaction(s) found")
        all_transactions.extend(page_txns)

    # Enrich each transaction with TBK attribution and source tag
    for tx in all_transactions:
        tx["assigned_user"] = assign_user(
            tx.get("name", ""),
            tx.get("transaction_type", ""),
            tx.get("is_zelle", False),
            tx.get("zelle_counterparty"),
        )
        tx["source"] = "statement_import"
        tx["statement_file"] = filename

    return all_transactions


async def parse_zip_bytes(
    zip_bytes: bytes,
    client: AsyncOpenAI,
) -> list[dict[str, Any]]:
    """
    Unzip and parse every PDF inside the ZIP archive.
    Returns a combined list of all extracted transactions.
    """
    all_transactions: list[dict[str, Any]] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        pdf_names = [
            name for name in zf.namelist()
            if name.lower().endswith(".pdf") and not name.startswith("__MACOSX")
        ]
        logger.info(f"ZIP contains {len(pdf_names)} PDF(s): {pdf_names}")

        for pdf_name in sorted(pdf_names):
            with zf.open(pdf_name) as f:
                pdf_bytes = f.read()
            txns = await parse_pdf_bytes(pdf_bytes, pdf_name, client)
            all_transactions.extend(txns)

    return all_transactions
