"""
Coverage tests for src/ingestion/connectors/media/diarizer.py.

Targets the REMAINING uncovered lines (55, 59-109): the full pyannote
diarization path that existing tests skip because they only exercise the
no-token / empty-segments / no-pyannote guards.

pyannote.audio and torch ARE installed in this environment, so we drive the
real ``assign_speakers`` code path but replace ``Pipeline.from_pretrained``
with a fake pipeline that returns a synthetic diarization object. This
avoids any model download or GPU/audio decoding while still executing the
overlap-assignment, nearest-midpoint fallback, and exception branches.
"""

import os
import types

import pytest
from unittest.mock import MagicMock, patch

# Skip cleanly only if the optional model deps are genuinely absent.
pytest.importorskip("pyannote.audio")
pytest.importorskip("torch")

from src.ingestion.connectors.media.diarizer import assign_speakers
from src.ingestion.connectors.media.models import TranscriptSegment


def _turn(start, end):
    """A pyannote-like turn object exposing .start / .end floats."""
    return types.SimpleNamespace(start=float(start), end=float(end))


class _FakeDiarization:
    """Mimics a pyannote Annotation: yields (turn, track, label) tuples."""

    def __init__(self, tracks):
        # tracks: list of (turn, label)
        self._tracks = tracks

    def itertracks(self, yield_label=True):
        for turn, label in self._tracks:
            yield turn, None, label


def _fake_pipeline(diarization):
    """A MagicMock that behaves like a loaded pyannote Pipeline."""
    pipeline = MagicMock(name="pyannote_pipeline")
    # pipeline.to(device) returns the pipeline (chained in the source).
    pipeline.to.return_value = pipeline
    # pipeline(tmp_path) -> diarization result.
    pipeline.return_value = diarization
    return pipeline


class TestAssignSpeakersOverlap:
    """Exercise the successful diarization + overlap-assignment path."""

    def test_segments_labelled_by_max_overlap(self):
        diar = _FakeDiarization([
            (_turn(0.0, 5.0), "SPEAKER_00"),
            (_turn(5.0, 10.0), "SPEAKER_01"),
        ])
        pipeline = _fake_pipeline(diar)

        segments = [
            TranscriptSegment(start_s=0.0, end_s=4.0, text="hello there"),
            TranscriptSegment(start_s=6.0, end_s=9.5, text="world again"),
        ]

        with patch(
            "pyannote.audio.Pipeline.from_pretrained", return_value=pipeline
        ):
            result = assign_speakers(segments and b"RIFFxxxxWAVE", segments, hf_token="hf_fake")

        # A brand-new list is returned (not the same object) with speakers set.
        assert result is not segments
        assert [s.speaker for s in result] == ["SPEAKER_00", "SPEAKER_01"]
        # Text/timings preserved.
        assert result[0].text == "hello there"
        assert result[0].start_s == 0.0
        assert result[1].end_s == 9.5
        # from_pretrained + pipeline call + itertracks all happened.
        assert pipeline.to.called
        pipeline.assert_called_once()

    def test_token_passed_from_hf_token_env(self):
        """HF_TOKEN env var is used when no explicit token is given (lines 43-47)."""
        diar = _FakeDiarization([(_turn(0.0, 5.0), "SPEAKER_A")])
        pipeline = _fake_pipeline(diar)
        segments = [TranscriptSegment(start_s=0.0, end_s=4.0, text="hi")]

        with patch.dict(os.environ, {"HF_TOKEN": "env_token_value"}, clear=False), \
             patch(
                 "pyannote.audio.Pipeline.from_pretrained", return_value=pipeline
             ) as from_pretrained:
            # HUGGINGFACE_HUB_TOKEN must not shadow; ensure HF_TOKEN wins.
            os.environ.pop("HUGGINGFACE_HUB_TOKEN", None)
            result = assign_speakers(b"audio", segments)

        assert result[0].speaker == "SPEAKER_A"
        _, kwargs = from_pretrained.call_args
        assert kwargs["use_auth_token"] == "env_token_value"

    def test_nearest_midpoint_fallback_when_no_overlap(self):
        """When no turn overlaps a segment, nearest-by-midpoint wins (lines 95-101)."""
        # Turns are far in time from the segment so overlap stays 0.0.
        diar = _FakeDiarization([
            (_turn(100.0, 110.0), "SPEAKER_FAR"),
            (_turn(200.0, 210.0), "SPEAKER_FARTHER"),
        ])
        pipeline = _fake_pipeline(diar)
        # Segment midpoint = 1.0; nearest turn center is 105 (SPEAKER_FAR).
        segments = [TranscriptSegment(start_s=0.0, end_s=2.0, text="orphan")]

        with patch(
            "pyannote.audio.Pipeline.from_pretrained", return_value=pipeline
        ):
            result = assign_speakers(b"audio", segments, hf_token="hf_fake")

        assert result[0].speaker == "SPEAKER_FAR"

    def test_empty_diarization_leaves_speaker_none(self):
        """No turns at all: best_speaker stays None (loop bodies skipped)."""
        diar = _FakeDiarization([])
        pipeline = _fake_pipeline(diar)
        segments = [TranscriptSegment(start_s=0.0, end_s=2.0, text="alone")]

        with patch(
            "pyannote.audio.Pipeline.from_pretrained", return_value=pipeline
        ):
            result = assign_speakers(b"audio", segments, hf_token="hf_fake")

        assert result[0].speaker is None
        assert result[0].text == "alone"


class TestAssignSpeakersExceptionPaths:
    """Exercise the try/except guards that return segments unchanged."""

    def test_from_pretrained_raises_returns_original(self):
        """Model load failure -> original segments returned (lines 67-68)."""
        segments = [TranscriptSegment(start_s=0.0, end_s=4.0, text="x")]
        with patch(
            "pyannote.audio.Pipeline.from_pretrained",
            side_effect=RuntimeError("gated model / bad token"),
        ):
            result = assign_speakers(b"audio", segments, hf_token="hf_fake")

        # Same object returned, speakers untouched.
        assert result is segments
        assert result[0].speaker is None

    def test_pipeline_call_raises_returns_original(self):
        """Inference failure -> original segments returned; temp file cleaned (lines 76-82)."""
        pipeline = MagicMock(name="pipeline")
        pipeline.to.return_value = pipeline
        pipeline.side_effect = ValueError("cannot decode audio")

        segments = [TranscriptSegment(start_s=0.0, end_s=4.0, text="y")]
        with patch(
            "pyannote.audio.Pipeline.from_pretrained", return_value=pipeline
        ):
            result = assign_speakers(b"audio", segments, hf_token="hf_fake")

        assert result is segments
        assert result[0].speaker is None
        pipeline.assert_called_once()

    def test_import_error_returns_original(self):
        """If pyannote import fails, segments returned unchanged (lines 56-57)."""
        segments = [TranscriptSegment(start_s=0.0, end_s=4.0, text="z")]
        # Force the ``from pyannote.audio import Pipeline`` to raise ImportError.
        with patch.dict("sys.modules", {"pyannote.audio": None}):
            result = assign_speakers(b"audio", segments, hf_token="hf_fake")

        assert result is segments
        assert all(s.speaker is None for s in result)


class TestAssignSpeakersGuards:
    """Guard clauses that short-circuit before any model work."""

    def test_no_token_no_env_returns_original(self):
        segments = [TranscriptSegment(start_s=0.0, end_s=1.0, text="a")]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HF_TOKEN", None)
            os.environ.pop("HUGGINGFACE_HUB_TOKEN", None)
            result = assign_speakers(b"audio", segments, hf_token=None)
        assert result is segments

    def test_token_but_empty_segments_returns_empty(self):
        result = assign_speakers(b"audio", [], hf_token="hf_fake")
        assert result == []
