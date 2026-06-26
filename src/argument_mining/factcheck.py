"""
Fact-check claim lookup via Google Fact Check Tools API (#97).

    result = lookup_claim("The unemployment rate fell to 3.8% in March")
    # FactCheckResult | None

    # Nightly batch (finds unchecked / stale claims and processes them)
    run_factcheck_batch(conn, lock, limit=50)

Requires GOOGLE_FACTCHECK_API_KEY in the environment.  When the key is absent
every call returns None immediately so the rest of the pipeline continues
without modification.

Rate limits: free tier = 1 000 queries/day.  The batch runner respects this
with a 1-second inter-request sleep and a configurable batch cap.

Verdicts are normalised from ClaimReview textualRating strings to four values:
    verified    — True / Mostly True / Correct
    disputed    — False / Mostly False / Incorrect / Pants on Fire
    mixed       — Mixed / Half True / Partly True
    unverified  — no matching review / rating not recognised
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_API_BASE = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
_RECHECK_DAYS = 7  # re-query after this many days even if a result is cached

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class FactCheckResult:
    verdict: str            # verified | disputed | mixed | unverified
    url: Optional[str]      # canonical review URL
    publisher: Optional[str]
    textual_rating: Optional[str]
    checked_at: str         # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Verdict normalisation
# ---------------------------------------------------------------------------

_TRUE_RATINGS = {
    "true", "mostly true", "correct", "accurate", "confirmed",
    "this is true", "verdict: true", "fact", "verified",
}
_FALSE_RATINGS = {
    "false", "mostly false", "incorrect", "wrong", "inaccurate",
    "pants on fire", "four pinocchios", "three pinocchios", "fabricated",
    "lie", "this is false", "verdict: false",
}
_MIXED_RATINGS = {
    "mixed", "half true", "half-true", "partly true", "partially true",
    "partially correct", "misleading", "needs context", "complicated",
    "in the middle", "two pinocchios", "one pinocchio",
}


def _normalize_verdict(textual_rating: str) -> str:
    """Map a ClaimReview textualRating string to one of our four verdict values."""
    r = textual_rating.strip().lower()
    if r in _TRUE_RATINGS:
        return "verified"
    if r in _FALSE_RATINGS:
        return "disputed"
    if r in _MIXED_RATINGS:
        return "mixed"
    # Partial-match fallback
    for token in ("true", "correct", "accurate", "verified"):
        if token in r:
            return "verified"
    for token in ("false", "incorrect", "fabricat", "lie"):
        if token in r:
            return "disputed"
    for token in ("mix", "mislead", "partial", "half", "context"):
        if token in r:
            return "mixed"
    return "unverified"


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def lookup_claim(
    text: str,
    api_key: Optional[str] = None,
    language_code: str = "en",
    max_age_days: int = 90,
) -> Optional[FactCheckResult]:
    """
    Query the Google Fact Check Tools API for an existing review of *text*.

    Returns a FactCheckResult if a matching review is found, None otherwise
    (including when GOOGLE_FACTCHECK_API_KEY is not configured).
    """
    key = api_key or os.getenv("GOOGLE_FACTCHECK_API_KEY")
    if not key:
        logger.debug("GOOGLE_FACTCHECK_API_KEY not set — skipping fact-check lookup")
        return None

    query = urllib.parse.urlencode({
        "key": key,
        "query": text[:500],  # API limit
        "languageCode": language_code,
        "maxAgeDays": max_age_days,
        "pageSize": 5,
    })
    url = f"{_API_BASE}?{query}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Noesis/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            import json as _json
            data: dict[str, Any] = _json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("Fact Check Tools API request failed: %s", exc)
        return None

    claims = data.get("claims") or []
    if not claims:
        return FactCheckResult(
            verdict="unverified",
            url=None,
            publisher=None,
            textual_rating=None,
            checked_at=_now_iso(),
        )

    # Take the first ClaimReview from the best-matching claim
    for claim in claims:
        reviews = claim.get("claimReview") or []
        if not reviews:
            continue
        review = reviews[0]
        textual_rating = review.get("textualRating") or ""
        pub = review.get("publisher") or {}
        publisher_name = pub.get("name") or pub.get("site")
        return FactCheckResult(
            verdict=_normalize_verdict(textual_rating),
            url=review.get("url"),
            publisher=publisher_name,
            textual_rating=textual_rating or None,
            checked_at=_now_iso(),
        )

    return FactCheckResult(
        verdict="unverified",
        url=None,
        publisher=None,
        textual_rating=None,
        checked_at=_now_iso(),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------

def store_result(
    conn: Any,
    lock: threading.Lock,
    claim_id: str,
    result: FactCheckResult,
) -> None:
    """Write a FactCheckResult back to argument_claims."""
    with lock:
        conn.execute(
            """
            UPDATE argument_claims
            SET factcheck_verdict    = ?,
                factcheck_url        = ?,
                factcheck_publisher  = ?,
                factcheck_checked_at = ?
            WHERE claim_id = ?
            """,
            [result.verdict, result.url, result.publisher, result.checked_at, claim_id],
        )


# ---------------------------------------------------------------------------
# Batch runner (for nightly scheduler)
# ---------------------------------------------------------------------------

def run_factcheck_batch(
    conn: Any,
    lock: threading.Lock,
    limit: int = 50,
    sleep_between: float = 1.1,
    api_key: Optional[str] = None,
) -> dict[str, int]:
    """
    Find claims that have never been fact-checked (or whose check is stale) and
    look them up via the API.  Safe to call from a scheduler or background thread.

    Returns a summary dict: {"checked": n, "updated": n, "skipped": n}.
    """
    key = api_key or os.getenv("GOOGLE_FACTCHECK_API_KEY")
    if not key:
        logger.info("run_factcheck_batch: GOOGLE_FACTCHECK_API_KEY not set — nothing to do")
        return {"checked": 0, "updated": 0, "skipped": 0}

    stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=_RECHECK_DAYS)).isoformat(timespec="seconds")

    with lock:
        rows = conn.execute(
            """
            SELECT claim_id, claim_text
            FROM argument_claims
            WHERE factcheck_checked_at IS NULL
               OR factcheck_checked_at < ?
            ORDER BY extracted_at DESC NULLS LAST
            LIMIT ?
            """,
            [stale_cutoff, limit],
        ).fetchall()

    checked = updated = skipped = 0
    for claim_id, claim_text in rows:
        if not claim_text or not claim_text.strip():
            skipped += 1
            continue
        result = lookup_claim(claim_text, api_key=key)
        checked += 1
        if result is not None:
            store_result(conn, lock, claim_id, result)
            updated += 1
            logger.debug(
                "fact-check %s → %s (%s)",
                claim_id, result.verdict, result.publisher or "—",
            )
        time.sleep(sleep_between)

    logger.info(
        "run_factcheck_batch: checked=%d updated=%d skipped=%d",
        checked, updated, skipped,
    )
    return {"checked": checked, "updated": updated, "skipped": skipped}
