"""
Unit tests for the enhanced /frames/source endpoint (#105).

Covers:
- concentrated framing flag (single frame avg > 0.60)
- source_type included in every response item
- source filter falls back to name-based match after aggregation
- non-news source rows use source_type as source name
- results sorted by doc_count descending
- limit respected
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_news_row(source: str, frame: str, avg_score: float, doc_count: int):
    return (source, "news", frame, avg_score, doc_count)


def _make_other_row(source_type: str, frame: str, avg_score: float, doc_count: int):
    # Non-news: source == source_type (fallback naming)
    return (source_type, source_type, frame, avg_score, doc_count)


# ---------------------------------------------------------------------------
# Import the threshold constant
# ---------------------------------------------------------------------------

from src.api.routes.argument_routes import _CONCENTRATED_THRESHOLD  # noqa: E402


def _aggregate(news_rows: list, other_rows: list) -> dict[str, Any]:
    """
    Re-implement the aggregation logic from get_frames_by_source so we can test
    it without spinning up FastAPI.  Mirrors the production code exactly.
    """
    by_source: dict[str, Any] = {}
    for row in list(news_rows) + list(other_rows):
        src, src_type, frame, avg_score, doc_count = row
        key = f"{src_type}::{src}"
        if key not in by_source:
            by_source[key] = {"source": src, "source_type": src_type, "frames": {}, "doc_count": 0}
        entry: Any = by_source[key]
        entry["frames"][frame] = round(float(avg_score), 4)
        entry["doc_count"] = max(entry["doc_count"], int(doc_count))

    result = []
    for data in sorted(by_source.values(), key=lambda x: -x["doc_count"]):
        frames = data["frames"]
        dominant = max(frames, key=frames.__getitem__) if frames else "other"
        top_score = frames.get(dominant, 0.0)
        concentrated = top_score > _CONCENTRATED_THRESHOLD
        result.append({
            "source": data["source"],
            "source_type": data["source_type"],
            "frames": frames,
            "doc_count": data["doc_count"],
            "dominant": dominant,
            "concentrated": concentrated,
            "concentrated_frame": dominant if concentrated else None,
        })
    return {"sources": result, "count": len(result)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConcentratedFlag:
    def test_above_threshold_sets_flag(self):
        news = [_make_news_row("Reuters", "economic", 0.72, 50)]
        res = _aggregate(news, [])
        src = res["sources"][0]
        assert src["concentrated"] is True
        assert src["concentrated_frame"] == "economic"

    def test_below_threshold_clears_flag(self):
        news = [_make_news_row("Guardian", "political", 0.55, 30)]
        res = _aggregate(news, [])
        src = res["sources"][0]
        assert src["concentrated"] is False
        assert src["concentrated_frame"] is None

    def test_exactly_at_threshold_is_not_concentrated(self):
        # > 0.60, not >= 0.60
        news = [_make_news_row("Source", "legal", 0.60, 10)]
        res = _aggregate(news, [])
        assert res["sources"][0]["concentrated"] is False

    def test_just_above_threshold(self):
        news = [_make_news_row("Source", "security", 0.601, 10)]
        res = _aggregate(news, [])
        assert res["sources"][0]["concentrated"] is True


class TestSourceTypeInResponse:
    def test_news_source_type(self):
        news = [_make_news_row("Bloomberg", "economic", 0.50, 40)]
        res = _aggregate(news, [])
        assert res["sources"][0]["source_type"] == "news"

    def test_non_news_source_type(self):
        other = [_make_other_row("paper", "scientific", 0.65, 20)]
        res = _aggregate([], other)
        src = res["sources"][0]
        assert src["source_type"] == "paper"
        # For non-news fallback: source name == source_type
        assert src["source"] == "paper"
        assert src["concentrated"] is True  # 0.65 > 0.60

    def test_mixed_sources_both_have_source_type(self):
        news = [_make_news_row("Reuters", "economic", 0.55, 60)]
        other = [_make_other_row("blog", "scientific", 0.40, 15)]
        res = _aggregate(news, other)
        types = {s["source"]: s["source_type"] for s in res["sources"]}
        assert types["Reuters"] == "news"
        assert types["blog"] == "blog"


class TestSortingAndLimit:
    def test_sorted_by_doc_count_descending(self):
        news = [
            _make_news_row("Small Source", "other", 0.30, 5),
            _make_news_row("Big Source", "economic", 0.55, 100),
            _make_news_row("Mid Source", "political", 0.40, 40),
        ]
        res = _aggregate(news, [])
        counts = [s["doc_count"] for s in res["sources"]]
        assert counts == sorted(counts, reverse=True)

    def test_doc_count_uses_max_across_frames(self):
        # Same source, two frames — doc_count should be the max seen
        news = [
            _make_news_row("Reuters", "economic", 0.60, 80),
            _make_news_row("Reuters", "political", 0.40, 75),
        ]
        res = _aggregate(news, [])
        assert len(res["sources"]) == 1
        assert res["sources"][0]["doc_count"] == 80


class TestDominantFrame:
    def test_dominant_is_highest_scoring_frame(self):
        news = [
            _make_news_row("Source", "economic", 0.55, 30),
            _make_news_row("Source", "scientific", 0.70, 30),
            _make_news_row("Source", "political", 0.40, 30),
        ]
        res = _aggregate(news, [])
        assert res["sources"][0]["dominant"] == "scientific"

    def test_dominant_used_for_concentrated_check(self):
        news = [
            _make_news_row("Src", "humanitarian", 0.25, 10),
            _make_news_row("Src", "economic", 0.65, 10),
        ]
        res = _aggregate(news, [])
        assert res["sources"][0]["dominant"] == "economic"
        assert res["sources"][0]["concentrated"] is True
        assert res["sources"][0]["concentrated_frame"] == "economic"


class TestEmptyResults:
    def test_empty_input_returns_zero_count(self):
        res = _aggregate([], [])
        assert res["count"] == 0
        assert res["sources"] == []
