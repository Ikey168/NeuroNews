"""
Coverage-focused unit tests for src/argument_mining/dataset.py.

Targets the parquet-loading branches of load_claim_dataset / load_stance_dataset
/ load_frame_dataset that the bootstrap-only tests never reach:
  - reading claims.parquet / stance.parquet / frames.parquet
  - source_type column present vs. absent (default "news")
  - frames column stored as JSON string vs. as a native list
  - falling back to the bootstrap set when no parquet exists
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.argument_mining.dataset import (
    load_claim_dataset,
    load_frame_dataset,
    load_stance_dataset,
    FRAME_LABELS,
)

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")


@pytest.fixture()
def tmp_data_dir():
    return Path(tempfile.mkdtemp())


# ---------------------------------------------------------------------------
# load_claim_dataset — parquet path
# ---------------------------------------------------------------------------

class TestLoadClaimDatasetParquet:
    def test_reads_parquet_with_source_type(self, tmp_data_dir):
        pd.DataFrame(
            {
                "text": ["A factual claim.", "An opinion."],
                "is_claim": [1, 0],
                "source_type": ["news", "blog"],
            }
        ).to_parquet(tmp_data_dir / "claims.parquet")

        result = load_claim_dataset(tmp_data_dir)
        assert result == [("A factual claim.", 1, "news"), ("An opinion.", 0, "blog")]

    def test_is_claim_cast_to_int(self, tmp_data_dir):
        # store as bool -> loader must astype(int)
        pd.DataFrame(
            {"text": ["x"], "is_claim": [True], "source_type": ["news"]}
        ).to_parquet(tmp_data_dir / "claims.parquet")
        result = load_claim_dataset(tmp_data_dir)
        assert result[0][1] == 1
        assert isinstance(result[0][1], int)

    def test_missing_source_type_defaults_to_news(self, tmp_data_dir):
        pd.DataFrame({"text": ["x", "y"], "is_claim": [1, 0]}).to_parquet(
            tmp_data_dir / "claims.parquet"
        )
        result = load_claim_dataset(tmp_data_dir)
        assert [r[2] for r in result] == ["news", "news"]

    def test_falls_back_to_bootstrap_when_no_parquet(self, tmp_data_dir):
        # dir exists but no claims.parquet -> bootstrap set
        result = load_claim_dataset(tmp_data_dir)
        assert len(result) >= 20
        assert all(lbl in (0, 1) for _t, lbl, _s in result)


# ---------------------------------------------------------------------------
# load_stance_dataset — parquet path
# ---------------------------------------------------------------------------

class TestLoadStanceDatasetParquet:
    def test_reads_parquet_with_source_type(self, tmp_data_dir):
        pd.DataFrame(
            {
                "text": ["Supportive text."],
                "topic": ["energy"],
                "stance": ["supportive"],
                "source_type": ["paper"],
            }
        ).to_parquet(tmp_data_dir / "stance.parquet")

        result = load_stance_dataset(tmp_data_dir)
        assert result == [("Supportive text.", "energy", "supportive", "paper")]

    def test_missing_source_type_defaults_to_news(self, tmp_data_dir):
        pd.DataFrame(
            {"text": ["t"], "topic": ["x"], "stance": ["neutral"]}
        ).to_parquet(tmp_data_dir / "stance.parquet")
        result = load_stance_dataset(tmp_data_dir)
        assert result[0][3] == "news"

    def test_falls_back_to_bootstrap(self, tmp_data_dir):
        result = load_stance_dataset(tmp_data_dir)
        assert len(result) >= 20
        stances = {r[2] for r in result}
        assert stances == {"supportive", "critical", "neutral", "ambiguous"}


# ---------------------------------------------------------------------------
# load_frame_dataset — parquet path
# ---------------------------------------------------------------------------

class TestLoadFrameDatasetParquet:
    def test_frames_stored_as_json_string(self, tmp_data_dir):
        pd.DataFrame(
            {
                "text": ["An economic and legal story."],
                "source_type": ["news"],
                "frames": [json.dumps(["economic", "legal"])],
            }
        ).to_parquet(tmp_data_dir / "frames.parquet")

        result = load_frame_dataset(tmp_data_dir)
        assert result == [("An economic and legal story.", "news", ["economic", "legal"])]

    def test_frames_stored_as_native_list(self, tmp_data_dir):
        pd.DataFrame(
            {
                "text": ["A security story."],
                "source_type": ["blog"],
                "frames": [["security"]],
            }
        ).to_parquet(tmp_data_dir / "frames.parquet")

        result = load_frame_dataset(tmp_data_dir)
        text, source_type, frames = result[0]
        assert text == "A security story."
        assert source_type == "blog"
        assert frames == ["security"]

    def test_missing_source_type_defaults_to_news(self, tmp_data_dir):
        pd.DataFrame(
            {"text": ["t"], "frames": [["other"]]}
        ).to_parquet(tmp_data_dir / "frames.parquet")
        result = load_frame_dataset(tmp_data_dir)
        assert result[0][1] == "news"

    def test_falls_back_to_bootstrap(self, tmp_data_dir):
        result = load_frame_dataset(tmp_data_dir)
        assert len(result) >= 30
        all_frames: set = set()
        for _t, _s, frames in result:
            all_frames.update(frames)
        assert all_frames == set(FRAME_LABELS)

    def test_none_data_dir_returns_bootstrap(self):
        # data_dir=None short-circuits before touching the filesystem
        result = load_frame_dataset(None)
        assert len(result) >= 30
