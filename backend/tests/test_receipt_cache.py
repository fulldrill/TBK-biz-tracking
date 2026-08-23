import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("SECRET_KEY", "test")
os.environ.setdefault("PLAID_CLIENT_ID", "x")
os.environ.setdefault("PLAID_SECRET", "x")

from app.config import settings
from app.services import receipt_cache
from app.services.pdf_generator import generate_receipt_pdf


class _Tx:
    def __init__(self, tid="stmt_abc123"):
        self.plaid_transaction_id = tid
        self.receipt_path = None


def _with_storage(fn):
    """Run fn with RECEIPT_STORAGE_PATH pointed at a temp dir."""
    original = settings.RECEIPT_STORAGE_PATH
    with tempfile.TemporaryDirectory() as tmp:
        settings.RECEIPT_STORAGE_PATH = tmp
        try:
            return fn(tmp)
        finally:
            settings.RECEIPT_STORAGE_PATH = original


def test_path_includes_the_layout_version():
    def check(tmp):
        path = receipt_cache.receipt_path("org1", "stmt_abc")
        assert path.endswith("stmt_abc_v2.pdf")
        assert "org1" in path
    _with_storage(check)


def test_invalidate_removes_the_cached_pdf():
    def check(tmp):
        tx = _Tx()
        path = receipt_cache.receipt_path("org1", tx.plaid_transaction_id)
        generate_receipt_pdf({"date": "2025-01-01", "name": "X", "amount": 1.0,
                              "transaction_type": "debit"}, path)
        assert os.path.exists(path)

        receipt_cache.invalidate_receipt_cache("org1", tx)
        assert not os.path.exists(path)
        assert tx.receipt_path is None
    _with_storage(check)


def test_invalidate_is_safe_when_nothing_was_cached():
    def check(tmp):
        # Must not raise — most transactions never had a receipt generated.
        receipt_cache.invalidate_receipt_cache("org1", _Tx("never_rendered"))
    _with_storage(check)


def test_edited_note_appears_after_regeneration():
    """The round trip that matters: edit a note, get a receipt carrying it."""
    def check(tmp):
        tx = _Tx()
        path = receipt_cache.receipt_path("org1", tx.plaid_transaction_id)

        base = {"date": "2025-11-20", "name": "OVERDRAFT ITEM FEE", "amount": 36.0,
                "transaction_type": "debit"}
        generate_receipt_pdf(base, path)
        before = open(path, "rb").read()
        assert b"Context / Purpose" not in before

        # The owner writes a note; the cache is dropped and the receipt rebuilt.
        receipt_cache.invalidate_receipt_cache("org1", tx)
        assert not os.path.exists(path)
        generate_receipt_pdf({**base, "business_purpose": "Fee from the Nov 17 AMEX payment."}, path)

        after = open(path, "rb").read()
        assert after != before
    _with_storage(check)
