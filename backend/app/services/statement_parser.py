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
from app.services.attribution import assign_user
from app.services.categorizer import categorize_transaction
from app.services.statement_text_parser import (
    has_text_layer,
    parse_statement_text,
    enrich,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt sent to GPT-4o for every page image
# ---------------------------------------------------------------------------
EXTRACTION_SYSTEM_PROMPT = """You are a financial data extraction specialist working for TBK Management.

Your ONLY job is to read a bank statement image and return ALL transactions on the page.

EXTRACTION RULES:
1. Extract EVERY transaction row — do not skip any, even small amounts.
2. Skip header rows, sub-total rows, balance rows, and any row without a date.
3. Return a JSON object of the form {"transactions": [...]}. No markdown, no code fences.
4. If the page has no transactions, return {"transactions": []}.
5. Never truncate. If the page is long, keep going until every row is captured.
6. Deposits are critical — a payroll or corporate deposit must never be missed.

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

EXAMPLE OUTPUT (return an object shaped exactly like this):
{"transactions": [
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
]}"""

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
    attempts: int = 3,
) -> tuple[list[dict[str, Any]], str | None]:
    """Send one page image to GPT-4o.

    Returns (transactions, error). A non-None error means this page produced
    nothing *and we do not know whether it was empty* — the caller must
    surface that rather than let it read as a page with no transactions.

    Uses JSON mode and a high token ceiling: the previous version asked for a
    bare array with max_tokens=4096, so a dense statement page truncated
    mid-JSON, failed to parse, and silently returned zero rows.
    """
    last_error: str | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=16384,
                temperature=0,
                response_format={"type": "json_object"},
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
                                    'Respond with a JSON object: {"transactions": [...]}'
                                ),
                            },
                        ],
                    },
                ],
            )
        except Exception as e:
            last_error = f"API error: {e}"
            logger.warning(f"Page {page_num} attempt {attempt}/{attempts}: {last_error}")
            continue

        finish = response.choices[0].finish_reason
        raw = (response.choices[0].message.content or "").strip()

        if finish == "length":
            last_error = "response hit the token limit — page may be truncated"
            logger.warning(f"Page {page_num} attempt {attempt}/{attempts}: {last_error}")
            continue

        # Strip markdown fences if the model wrapped the JSON anyway
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = f"JSON parse failed: {e}"
            logger.warning(
                f"Page {page_num} attempt {attempt}/{attempts}: {last_error}\nRaw: {raw[:300]}"
            )
            continue

        # JSON mode always returns an object; accept a bare array too in case
        # the model ignores the wrapper.
        if isinstance(data, dict):
            data = data.get("transactions", data.get("data", []))
        if not isinstance(data, list):
            last_error = "model returned no transaction array"
            logger.warning(f"Page {page_num} attempt {attempt}/{attempts}: {last_error}")
            continue

        return data, None

    logger.error(f"Page {page_num}: giving up after {attempts} attempts — {last_error}")
    return [], last_error


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def parse_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    client: AsyncOpenAI,
    reports: list[dict[str, Any]] | None = None,
    allowed_people: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Parse a single PDF's worth of bytes.
    Returns a list of transaction dicts enriched with 'assigned_user' and 'source'.

    When `reports` is passed, a per-file summary is appended to it — page
    count, transaction count, and any pages that failed. The caller surfaces
    that so a file yielding nothing is visibly a failure rather than looking
    like a statement with no activity.
    """
    logger.info(f"Parsing PDF: {filename}")

    # Text layer first. These statements are generated PDFs, so the exact rows
    # are already in the file — reading them is lossless and free, and the
    # statement's own printed totals confirm nothing was dropped. Vision is the
    # fallback for scans, where it is the only option.
    if has_text_layer(pdf_bytes):
        result = parse_statement_text(pdf_bytes, filename)
        checks = result["checks"]
        if checks["ok"] and result["transactions"]:
            txns = enrich(
                result["transactions"], filename, allowed_people,
                period_end=result.get("period_end"),
                account=result.get("account"),
            )
            logger.info(
                f"  → text layer: {len(txns)} transaction(s), reconciles with "
                f"statement totals"
            )
            if reports is not None:
                reports.append({
                    "file": filename,
                    "method": "text",
                    "pages": 0,
                    "transactions": len(txns),
                    "failed_pages": [],
                    "period_end": result["period_end"],
                    "reconciled": True,
                    "months": sorted({t["date"][:7] for t in txns}),
                })
            return txns
        logger.warning(
            f"  → text layer did not reconcile for {filename} "
            f"({checks.get('sections')}) — falling back to vision"
        )

    page_images = _pdf_bytes_to_page_images(pdf_bytes)
    logger.info(f"  → {len(page_images)} page(s)")

    all_transactions: list[dict[str, Any]] = []
    failed_pages: list[dict[str, Any]] = []

    for i, img_b64 in enumerate(page_images, start=1):
        page_txns, error = await _extract_page(client, img_b64, page_num=i)
        if error:
            failed_pages.append({"page": i, "error": error})
        logger.info(f"  → Page {i}: {len(page_txns)} transaction(s) found")
        all_transactions.extend(page_txns)

    # Enrich each transaction with attribution, category, and source tag
    for tx in all_transactions:
        tx["assigned_user"] = assign_user(
            tx.get("name", ""),
            tx.get("transaction_type", ""),
            tx.get("is_zelle", False),
            tx.get("zelle_counterparty"),
            allowed=allowed_people,
        )
        # Priority rules (CMCI payroll, mortgage, child care) outrank the
        # coarse category the model assigns from the statement text.
        tx["category"] = categorize_transaction(
            tx.get("name", ""),
            None,
            tx.get("category"),
            tx.get("zelle_counterparty"),
        )
        tx["source"] = "statement_import"
        tx["statement_file"] = filename

    if reports is not None:
        reports.append({
            "file": filename,
            "method": "vision",
            "pages": len(page_images),
            "transactions": len(all_transactions),
            "failed_pages": failed_pages,
            "reconciled": False,
            "months": sorted({
                str(t.get("date", ""))[:7]
                for t in all_transactions
                if str(t.get("date", ""))[:7]
            }),
        })

    return all_transactions


async def parse_zip_bytes(
    zip_bytes: bytes,
    client: AsyncOpenAI,
    reports: list[dict[str, Any]] | None = None,
    allowed_people: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Unzip and parse every PDF inside the ZIP archive.
    Returns a combined list of all extracted transactions.

    One unreadable PDF no longer takes the whole batch down — it is recorded
    in `reports` and the remaining files still parse.
    """
    all_transactions: list[dict[str, Any]] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        pdf_names = [
            name for name in zf.namelist()
            if name.lower().endswith(".pdf") and not name.startswith("__MACOSX")
        ]
        logger.info(f"ZIP contains {len(pdf_names)} PDF(s): {pdf_names}")

        for pdf_name in sorted(pdf_names):
            try:
                with zf.open(pdf_name) as f:
                    pdf_bytes = f.read()
                txns = await parse_pdf_bytes(
                    pdf_bytes, pdf_name, client,
                    reports=reports, allowed_people=allowed_people,
                )
                all_transactions.extend(txns)
            except Exception as e:
                logger.error(f"Failed to parse {pdf_name}: {e}")
                if reports is not None:
                    reports.append({
                        "file": pdf_name,
                        "pages": 0,
                        "transactions": 0,
                        "failed_pages": [{"page": 0, "error": f"could not read PDF: {e}"}],
                        "months": [],
                    })

    return all_transactions
