"""
Tests for the media connector (issue #523).

Covers:
- TranscriptSegment / MediaMetadata models
- media_id / segment_id stability
- format_timestamp formatting
- transcriber.transcribe() with all backends mocked away → "none" extractor
- connector.MediaConnector: discover, fetch (file + URL), parse
- media_metadata_to_documents: one Document per segment, timestamp metadata
- segment_to_document: URI fragment construction, field mapping
- diarizer.assign_speakers: no-op without pyannote or token
- registry: "transcript" is registered after importing connectors
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.ingestion.connectors.base import SourceRef
from src.ingestion.connectors.media.connector import (
    MediaConnector,
    media_metadata_to_documents,
    segment_to_document,
)
from src.ingestion.connectors.media.diarizer import assign_speakers
from src.ingestion.connectors.media.models import (
    MediaMetadata,
    TranscriptSegment,
    format_timestamp,
    media_id,
    segment_id,
)
from src.ingestion.connectors.media.transcriber import transcribe


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _segments(n: int = 3) -> list:
    return [
        TranscriptSegment(
            start_s=float(i * 10),
            end_s=float(i * 10 + 9),
            text=f"Segment {i} text here.",
        )
        for i in range(n)
    ]


def _meta(title: str = "Test Podcast", n_segments: int = 3) -> MediaMetadata:
    return MediaMetadata(
        title=title,
        language="en",
        file_path="/media/podcast.mp3",
        media_format="mp3",
        duration_s=30.0,
        segments=_segments(n_segments),
        model="base",
        extractor="whisper",
    )


# --------------------------------------------------------------------------- #
# Model tests
# --------------------------------------------------------------------------- #

class TestMediaId:
    def test_url_preferred(self):
        result = media_id(url="https://example.com/pod.mp3")
        assert result.startswith("media:")

    def test_stable(self):
        assert media_id(url="https://x.com/a") == media_id(url="https://x.com/a")

    def test_different_keys_differ(self):
        assert media_id(url="https://a.com") != media_id(url="https://b.com")

    def test_file_path_fallback(self):
        a = media_id(file_path="/foo/bar.mp3")
        b = media_id(file_path="/foo/baz.mp3")
        assert a != b


class TestSegmentId:
    def test_format(self):
        did = media_id(url="https://example.com/pod.mp3")
        sid = segment_id(did, 12.345)
        assert sid == f"{did}#t=12.345"

    def test_zero_start(self):
        did = media_id(url="https://x.com")
        sid = segment_id(did, 0.0)
        assert "#t=0.0" in sid


class TestFormatTimestamp:
    def test_seconds_only(self):
        assert format_timestamp(45.0) == "0:45"

    def test_minutes(self):
        assert format_timestamp(90.0) == "1:30"

    def test_hours(self):
        assert format_timestamp(3661.0) == "1:01:01"

    def test_zero(self):
        assert format_timestamp(0.0) == "0:00"


class TestTranscriptSegment:
    def test_duration(self):
        seg = TranscriptSegment(start_s=10.0, end_s=20.0, text="Hello")
        assert seg.duration_s == 10.0

    def test_duration_clamped(self):
        seg = TranscriptSegment(start_s=20.0, end_s=10.0, text="Oops")
        assert seg.duration_s == 0.0

    def test_timestamp_label(self):
        seg = TranscriptSegment(start_s=70.0, end_s=130.0, text="x")
        assert seg.timestamp_label == "[1:10 - 2:10]"

    def test_media_fragment(self):
        seg = TranscriptSegment(start_s=12.5, end_s=20.0, text="x")
        uri = seg.media_fragment("https://example.com/pod.mp3")
        assert uri == "https://example.com/pod.mp3#t=12.500,20.000"


class TestMediaMetadata:
    def test_document_id_stable(self):
        meta = MediaMetadata(title="T", file_path="/a.mp3")
        assert meta.document_id == meta.document_id

    def test_full_text(self):
        meta = _meta(n_segments=2)
        text = meta.full_text
        assert "Segment 0" in text
        assert "Segment 1" in text

    def test_base_uri_file(self):
        meta = MediaMetadata(title="T", file_path="/podcasts/ep1.mp3")
        assert meta.base_uri == "file:///podcasts/ep1.mp3"

    def test_base_uri_url(self):
        meta = MediaMetadata(title="T", source_url="https://example.com/ep1.mp3")
        assert meta.base_uri == "https://example.com/ep1.mp3"


# --------------------------------------------------------------------------- #
# Transcriber tests
# --------------------------------------------------------------------------- #

class TestTranscriber:
    def test_no_backends_returns_empty(self):
        with (
            patch("src.ingestion.connectors.media.transcriber._transcribe_local_whisper", return_value=None),
            patch("src.ingestion.connectors.media.transcriber._transcribe_faster_whisper", return_value=None),
            patch("src.ingestion.connectors.media.transcriber._transcribe_openai_api", return_value=None),
        ):
            result = transcribe(b"fake audio", model_size="base")
            assert result.extractor == "none"
            assert result.segments == []

    def test_first_backend_wins(self):
        fake_result = _meta()
        with (
            patch(
                "src.ingestion.connectors.media.transcriber._transcribe_local_whisper",
                return_value=fake_result,
            ),
            patch(
                "src.ingestion.connectors.media.transcriber._transcribe_faster_whisper",
                return_value=None,
            ) as mock_fw,
        ):
            result = transcribe(b"audio", model_size="base")
            assert result.extractor == "whisper"
            mock_fw.assert_not_called()

    def test_fallback_to_second_backend(self):
        fake_result = _meta()
        fake_result.extractor = "faster-whisper"
        with (
            patch("src.ingestion.connectors.media.transcriber._transcribe_local_whisper", return_value=None),
            patch(
                "src.ingestion.connectors.media.transcriber._transcribe_faster_whisper",
                return_value=fake_result,
            ),
        ):
            result = transcribe(b"audio")
            assert result.extractor == "faster-whisper"

    def test_openai_api_skipped_without_key(self):
        with (
            patch("src.ingestion.connectors.media.transcriber._transcribe_local_whisper", return_value=None),
            patch("src.ingestion.connectors.media.transcriber._transcribe_faster_whisper", return_value=None),
            patch.dict(os.environ, {}, clear=True),
        ):
            # No OPENAI_API_KEY → API backend returns None → extractor="none"
            result = transcribe(b"audio")
            assert result.extractor == "none"


# --------------------------------------------------------------------------- #
# Diarizer tests
# --------------------------------------------------------------------------- #

class TestDiarizer:
    def test_no_token_returns_unchanged(self):
        segs = _segments(2)
        result = assign_speakers(b"audio", segs, hf_token=None)
        assert result is segs or result == segs
        assert all(s.speaker is None for s in result)

    def test_empty_segments_returns_empty(self):
        result = assign_speakers(b"audio", [], hf_token="hf_token")
        assert result == []

    def test_no_pyannote_returns_unchanged(self):
        segs = _segments(2)
        with patch.dict("sys.modules", {"pyannote.audio": None}):
            result = assign_speakers(b"audio", segs, hf_token="hf_token")
        assert all(s.speaker is None for s in result)


# --------------------------------------------------------------------------- #
# segment_to_document tests
# --------------------------------------------------------------------------- #

class TestSegmentToDocument:
    def test_source_type(self):
        seg = TranscriptSegment(start_s=0.0, end_s=10.0, text="Hello world.")
        doc = segment_to_document(seg, _meta(), ingested_at=1000, index=0)
        assert doc.source_type == "transcript"

    def test_content_is_segment_text(self):
        seg = TranscriptSegment(start_s=0.0, end_s=10.0, text="Hello world.")
        doc = segment_to_document(seg, _meta(), ingested_at=1000, index=0)
        assert doc.content == "Hello world."

    def test_timestamp_metadata(self):
        seg = TranscriptSegment(start_s=12.5, end_s=20.0, text="x")
        doc = segment_to_document(seg, _meta(), ingested_at=1000, index=0)
        assert doc.metadata["start_s"] == 12.5
        assert doc.metadata["end_s"] == 20.0

    def test_speaker_in_metadata(self):
        seg = TranscriptSegment(start_s=0.0, end_s=5.0, text="Hi.", speaker="SPEAKER_00")
        doc = segment_to_document(seg, _meta(), ingested_at=1000, index=0)
        assert doc.metadata["speaker"] == "SPEAKER_00"

    def test_no_speaker_key_when_none(self):
        seg = TranscriptSegment(start_s=0.0, end_s=5.0, text="Hi.")
        doc = segment_to_document(seg, _meta(), ingested_at=1000, index=0)
        assert "speaker" not in doc.metadata

    def test_title_includes_timestamp(self):
        seg = TranscriptSegment(start_s=70.0, end_s=130.0, text="x")
        doc = segment_to_document(seg, _meta(title="My Podcast"), ingested_at=1000, index=0)
        assert "My Podcast" in doc.title
        assert "1:10" in doc.title

    def test_content_ref_is_fragment_uri(self):
        seg = TranscriptSegment(start_s=5.0, end_s=15.0, text="x")
        meta = _meta()
        meta.file_path = "/pods/ep.mp3"
        doc = segment_to_document(seg, meta, ingested_at=1000, index=0)
        assert doc.content_ref is not None
        assert "#t=5.000,15.000" in doc.content_ref

    def test_url_source(self):
        seg = TranscriptSegment(start_s=0.0, end_s=10.0, text="x")
        meta = MediaMetadata(
            title="Talk",
            source_url="https://example.com/talk.mp3",
            language="en",
            extractor="whisper",
            model="base",
        )
        doc = segment_to_document(seg, meta, ingested_at=1000, index=0)
        assert "example.com" in (doc.content_ref or "")

    def test_language_propagated(self):
        seg = TranscriptSegment(start_s=0.0, end_s=5.0, text="Bonjour.")
        meta = _meta()
        meta.language = "fr"
        doc = segment_to_document(seg, meta, ingested_at=1000, index=0)
        assert doc.language == "fr"


# --------------------------------------------------------------------------- #
# media_metadata_to_documents tests
# --------------------------------------------------------------------------- #

class TestMediaMetadataToDocuments:
    def test_one_doc_per_segment(self):
        meta = _meta(n_segments=4)
        docs = media_metadata_to_documents(meta, ingested_at=1)
        assert len(docs) == 4

    def test_empty_segments_empty_list(self):
        meta = _meta(n_segments=0)
        docs = media_metadata_to_documents(meta, ingested_at=1)
        assert docs == []

    def test_whitespace_only_segments_skipped(self):
        meta = _meta(n_segments=1)
        meta.segments = [TranscriptSegment(start_s=0.0, end_s=5.0, text="   ")]
        docs = media_metadata_to_documents(meta, ingested_at=1)
        assert docs == []

    def test_segment_index_in_metadata(self):
        meta = _meta(n_segments=3)
        docs = media_metadata_to_documents(meta, ingested_at=1)
        assert [d.metadata["segment_index"] for d in docs] == [0, 1, 2]

    def test_unique_document_ids(self):
        meta = _meta(n_segments=5)
        docs = media_metadata_to_documents(meta, ingested_at=1)
        ids = [d.document_id for d in docs]
        assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# MediaConnector integration tests
# --------------------------------------------------------------------------- #

class TestMediaConnector:
    def test_source_type(self):
        assert MediaConnector.source_type == "transcript"

    def test_discover_file_paths(self):
        c = MediaConnector()
        refs = list(c.discover(["/pods/ep1.mp3", "/pods/ep2.mp4"]))
        assert len(refs) == 2
        assert refs[0].metadata["format"] == "mp3"
        assert refs[1].metadata["format"] == "mp4"

    def test_discover_single_string(self):
        c = MediaConnector()
        refs = list(c.discover("/pods/ep.mp3"))
        assert len(refs) == 1

    def test_discover_none_yields_nothing(self):
        c = MediaConnector()
        assert list(c.discover(None)) == []

    def test_discover_url(self):
        c = MediaConnector()
        refs = list(c.discover(["https://example.com/ep.mp3"]))
        assert len(refs) == 1
        assert refs[0].locator == "https://example.com/ep.mp3"

    def test_fetch_missing_file(self):
        c = MediaConnector()
        ref = SourceRef(locator="/no/such/file.mp3")
        with pytest.raises(FileNotFoundError):
            c.fetch(ref)

    def test_fetch_reads_file(self, tmp_path):
        audio = tmp_path / "ep.mp3"
        audio.write_bytes(b"fake mp3 data")
        c = MediaConnector()
        ref = SourceRef(locator=str(audio), title="ep", metadata={"format": "mp3"})
        raw = c.fetch(ref)
        assert raw.content == b"fake mp3 data"

    def test_parse_calls_transcribe_and_returns_docs(self, tmp_path):
        audio = tmp_path / "pod.mp3"
        audio.write_bytes(b"fake audio")
        c = MediaConnector(model_size="tiny")
        ref = SourceRef(locator=str(audio), title="pod", metadata={"format": "mp3"})
        raw = c.fetch(ref)

        fake_meta = _meta(title="pod", n_segments=2)

        with patch("src.ingestion.connectors.media.connector.transcribe", return_value=fake_meta):
            docs = c.parse(raw)

        assert len(docs) == 2
        assert all(d.source_type == "transcript" for d in docs)

    def test_parse_diarize_called_when_flag_set(self, tmp_path):
        audio = tmp_path / "ep.mp3"
        audio.write_bytes(b"audio")
        c = MediaConnector(diarize=True, hf_token="hf_test")
        ref = SourceRef(locator=str(audio), title="ep", metadata={"format": "mp3"})
        raw = c.fetch(ref)

        fake_meta = _meta(n_segments=2)
        labelled_segs = [
            TranscriptSegment(s.start_s, s.end_s, s.text, speaker=f"SPK_{i}")
            for i, s in enumerate(fake_meta.segments)
        ]

        with (
            patch("src.ingestion.connectors.media.connector.transcribe", return_value=fake_meta),
            patch("src.ingestion.connectors.media.connector.assign_speakers", return_value=labelled_segs) as mock_diar,
        ):
            docs = c.parse(raw)

        mock_diar.assert_called_once()
        assert docs[0].metadata["speaker"] == "SPK_0"

    def test_parse_diarize_skipped_when_flag_false(self, tmp_path):
        audio = tmp_path / "ep.mp3"
        audio.write_bytes(b"audio")
        c = MediaConnector(diarize=False)
        ref = SourceRef(locator=str(audio), title="ep", metadata={"format": "mp3"})
        raw = c.fetch(ref)
        fake_meta = _meta(n_segments=1)

        with (
            patch("src.ingestion.connectors.media.connector.transcribe", return_value=fake_meta),
            patch("src.ingestion.connectors.media.connector.assign_speakers") as mock_diar,
        ):
            c.parse(raw)

        mock_diar.assert_not_called()

    def test_harvest_skips_missing_files(self):
        c = MediaConnector()
        docs = list(c.harvest(["/no/such/podcast.mp3"]))
        assert docs == []

    def test_registered_in_registry(self):
        import src.ingestion.connectors  # noqa: F401 — triggers registration
        from src.ingestion.connectors.registry import is_registered
        assert is_registered("transcript")
