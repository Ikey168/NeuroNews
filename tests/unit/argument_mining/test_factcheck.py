"""
Unit tests for src/argument_mining/factcheck.py (#97).

All HTTP calls are mocked so these tests run offline without an API key.
"""
from __future__ import annotations

import json
import threading
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from src.argument_mining.factcheck import (
    FactCheckResult,
    _normalize_verdict,
    lookup_claim,
    run_factcheck_batch,
    store_result,
)


# ---------------------------------------------------------------------------
# _normalize_verdict
# ---------------------------------------------------------------------------

class TestNormalizeVerdict(unittest.TestCase):
    def test_true_variants(self):
        for rating in ["True", "Mostly True", "Correct", "Accurate", "CONFIRMED"]:
            self.assertEqual(_normalize_verdict(rating), "verified", rating)

    def test_false_variants(self):
        for rating in ["False", "Mostly False", "Incorrect", "Pants on Fire", "FABRICATED"]:
            self.assertEqual(_normalize_verdict(rating), "disputed", rating)

    def test_mixed_variants(self):
        for rating in ["Mixed", "Half True", "Misleading", "Needs Context", "Partly True"]:
            self.assertEqual(_normalize_verdict(rating), "mixed", rating)

    def test_unknown_rating(self):
        self.assertEqual(_normalize_verdict("Unknown"), "unverified")

    def test_partial_match_true(self):
        self.assertEqual(_normalize_verdict("Largely true"), "verified")

    def test_partial_match_false(self):
        self.assertEqual(_normalize_verdict("Demonstrably false"), "disputed")

    def test_partial_match_mixed(self):
        self.assertEqual(_normalize_verdict("Highly misleading"), "mixed")

    def test_empty_string(self):
        self.assertEqual(_normalize_verdict(""), "unverified")

    def test_whitespace_stripped(self):
        self.assertEqual(_normalize_verdict("  True  "), "verified")


# ---------------------------------------------------------------------------
# lookup_claim — no API key
# ---------------------------------------------------------------------------

class TestLookupClaimNoKey(unittest.TestCase):
    def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = lookup_claim("The earth orbits the sun.")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# lookup_claim — mocked HTTP
# ---------------------------------------------------------------------------

def _mock_response(payload: dict) -> MagicMock:
    body = json.dumps(payload).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = body
    return mock_resp


class TestLookupClaimMocked(unittest.TestCase):
    def _patch_urlopen(self, payload: dict):
        return patch(
            "src.argument_mining.factcheck.urllib.request.urlopen",
            return_value=_mock_response(payload),
        )

    def test_verified_result(self):
        payload = {
            "claims": [{
                "text": "The unemployment rate fell to 3.8%",
                "claimReview": [{
                    "publisher": {"name": "PolitiFact", "site": "politifact.com"},
                    "url": "https://politifact.com/fc/1",
                    "textualRating": "Mostly True",
                }],
            }]
        }
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with self._patch_urlopen(payload):
                result = lookup_claim("The unemployment rate fell to 3.8%")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.verdict, "verified")
        self.assertEqual(result.publisher, "PolitiFact")
        self.assertEqual(result.url, "https://politifact.com/fc/1")
        self.assertEqual(result.textual_rating, "Mostly True")

    def test_disputed_result(self):
        payload = {
            "claims": [{
                "text": "Vaccines cause autism",
                "claimReview": [{
                    "publisher": {"name": "FactCheck.org"},
                    "url": "https://factcheck.org/fc/2",
                    "textualRating": "False",
                }],
            }]
        }
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with self._patch_urlopen(payload):
                result = lookup_claim("Vaccines cause autism")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.verdict, "disputed")

    def test_mixed_result(self):
        payload = {
            "claims": [{
                "text": "Drug prices dropped by half",
                "claimReview": [{
                    "publisher": {"name": "Snopes"},
                    "url": "https://snopes.com/fc/3",
                    "textualRating": "Misleading",
                }],
            }]
        }
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with self._patch_urlopen(payload):
                result = lookup_claim("Drug prices dropped by half")

        assert result is not None
        self.assertEqual(result.verdict, "mixed")

    def test_empty_claims_list_returns_unverified(self):
        payload: dict = {"claims": []}
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with self._patch_urlopen(payload):
                result = lookup_claim("Some obscure claim")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.verdict, "unverified")
        self.assertIsNone(result.url)

    def test_no_claims_key_returns_unverified(self):
        payload: dict = {}
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with self._patch_urlopen(payload):
                result = lookup_claim("Another claim")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.verdict, "unverified")

    def test_api_error_returns_none(self):
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with patch(
                "src.argument_mining.factcheck.urllib.request.urlopen",
                side_effect=OSError("network error"),
            ):
                result = lookup_claim("Any claim")
        self.assertIsNone(result)

    def test_checked_at_is_iso_utc(self):
        payload = {
            "claims": [{"text": "x", "claimReview": [{"publisher": {}, "textualRating": "True"}]}]
        }
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with self._patch_urlopen(payload):
                result = lookup_claim("x")
        assert result is not None
        self.assertIn("T", result.checked_at)
        self.assertIn("+", result.checked_at)


# ---------------------------------------------------------------------------
# store_result
# ---------------------------------------------------------------------------

class TestStoreResult(unittest.TestCase):
    def test_store_updates_db(self):
        conn = MagicMock()
        lock = threading.Lock()
        result = FactCheckResult(
            verdict="disputed",
            url="https://example.com",
            publisher="TestCheck",
            textual_rating="False",
            checked_at="2026-06-26T00:00:00+00:00",
        )
        store_result(conn, lock, "claim-123", result)
        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        self.assertIn("UPDATE argument_claims", args[0])
        self.assertIn("disputed", args[1])
        self.assertIn("claim-123", args[1])


# ---------------------------------------------------------------------------
# run_factcheck_batch
# ---------------------------------------------------------------------------

class TestRunFactcheckBatch(unittest.TestCase):
    def test_skips_when_no_api_key(self):
        conn = MagicMock()
        lock = threading.Lock()
        with patch.dict("os.environ", {}, clear=True):
            result = run_factcheck_batch(conn, lock)
        self.assertEqual(result, {"checked": 0, "updated": 0, "skipped": 0})
        conn.execute.assert_not_called()

    def test_processes_unchecked_claims(self):
        conn = MagicMock()
        lock = threading.Lock()
        conn.execute.return_value.fetchall.return_value = [
            ("claim-1", "Unemployment fell to 3.8%"),
            ("claim-2", "GDP grew by 5.2%"),
        ]

        fake_result = FactCheckResult(
            verdict="verified", url=None, publisher="TestCheck",
            textual_rating="True", checked_at="2026-06-26T00:00:00+00:00",
        )

        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with patch("src.argument_mining.factcheck.lookup_claim", return_value=fake_result):
                with patch("src.argument_mining.factcheck.store_result") as mock_store:
                    with patch("src.argument_mining.factcheck.time.sleep"):
                        result = run_factcheck_batch(conn, lock)

        self.assertEqual(result["checked"], 2)
        self.assertEqual(result["updated"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(mock_store.call_count, 2)

    def test_skips_blank_claim_text(self):
        conn = MagicMock()
        lock = threading.Lock()
        conn.execute.return_value.fetchall.return_value = [
            ("claim-blank", ""),
            ("claim-whitespace", "   "),
        ]
        with patch.dict("os.environ", {"GOOGLE_FACTCHECK_API_KEY": "test-key"}):
            with patch("src.argument_mining.factcheck.lookup_claim") as mock_lookup:
                result = run_factcheck_batch(conn, lock)

        self.assertEqual(result["skipped"], 2)
        self.assertEqual(result["checked"], 0)
        mock_lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
