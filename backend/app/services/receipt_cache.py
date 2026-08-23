"""Cached receipt PDFs are invalidated here.

Receipts are rendered once and kept on disk. Every field that prints on one —
the attributed person, the business-purpose note — can be edited afterwards, so
the cached file has to be dropped when that happens or the next download serves
a PDF built before the change.
"""

import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)


def receipt_path(org_id: str, plaid_transaction_id: str) -> str:
    """Where a single transaction's receipt is cached.

    The _v2 suffix is the layout version — see routers/receipts.py.
    """
    return os.path.join(
        settings.RECEIPT_STORAGE_PATH, str(org_id), f"{plaid_transaction_id}_v2.pdf"
    )


def invalidate_receipt_cache(org_id: str, tx) -> None:
    """Drop the cached PDF so the next request rebuilds it from current data."""
    path = receipt_path(org_id, tx.plaid_transaction_id)
    try:
        os.remove(path)
        logger.info(f"Invalidated cached receipt {path}")
    except FileNotFoundError:
        pass  # never generated, nothing to drop
    except OSError as e:
        # A stale receipt is bad but not worth failing the user's edit over.
        logger.warning(f"Could not remove cached receipt {path}: {e}")
    if getattr(tx, "receipt_path", None):
        tx.receipt_path = None
