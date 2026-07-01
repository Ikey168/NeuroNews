"""Real coverage tests for the media transcriber backends.

Whisper/faster-whisper model loading and inference are mocked (to avoid model
downloads and GPU work), but the surrounding real logic — segment mapping,
ffmpeg normalization, backend fallthrough, and MediaMetadata construction — is
exercised and asserted against the actual returned objects.
"""

from __future__ import annotations

import subprocess
import sys
import types

import pytest

import src.ingestion.connectors.media.transcriber as tr
from src.ingestion.connectors.media.models import MediaMetadata, TranscriptSegment


# --------------------------------------------------------------------------- #
# ffmpeg helpers.
# --------------------------------------------------------------------------- #

def test_ffmpeg_available_true(monkeypatch):
    def fake_run(cmd, **kwargs):
        assert cmd[0] == "ffmpeg"
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(tr.subprocess, "run", fake_run)
    assert tr._ffmpeg_available() is True


def test_ffmpeg_available_false_when_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("no ffmpeg")

    monkeypatch.setattr(tr.subprocess, "run", fake_run)
    assert tr._ffmpeg_available() is False


def test_ffmpeg_available_false_on_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(tr.subprocess, "run", fake_run)
    assert tr._ffmpeg_available() is False


def test_to_wav_returns_input_when_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(tr, "_ffmpeg_available", lambda: False)
    raw = b"original-audio-bytes"
    assert tr._to_wav(raw) == raw


def test_to_wav_converts_via_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "_ffmpeg_available", lambda: True)

    converted = b"RIFFwav-converted-bytes"

    def fake_run(cmd, **kwargs):
        # ffmpeg writes to the output path (last arg). Emulate that.
        out_path = cmd[-1]
        with open(out_path, "wb") as f:
            f.write(converted)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(tr.subprocess, "run", fake_run)
    result = tr._to_wav(b"some-input-audio")
    assert result == converted


def test_to_wav_falls_back_to_input_on_ffmpeg_error(monkeypatch):
    monkeypatch.setattr(tr, "_ffmpeg_available", lambda: True)

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(tr.subprocess, "run", fake_run)
    raw = b"input-when-conversion-fails"
    assert tr._to_wav(raw) == raw


# --------------------------------------------------------------------------- #
# Backend 1: local openai-whisper (mocked model).
# --------------------------------------------------------------------------- #

def _install_fake_whisper(monkeypatch, transcribe_result):
    fake = types.ModuleType("whisper")

    class _Model:
        def transcribe(self, path, **kwargs):
            _Model.last_kwargs = kwargs
            _Model.last_path = path
            return transcribe_result

    fake.load_model = lambda size: _Model()
    fake._Model = _Model
    monkeypatch.setitem(sys.modules, "whisper", fake)
    return fake


def test_local_whisper_builds_metadata(monkeypatch):
    monkeypatch.setattr(tr, "_to_wav", lambda b: b)
    result = {
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 1.5, "text": " Hello world "},
            {"start": 1.5, "end": 3.0, "text": "second segment"},
            {"start": 3.0, "end": 3.2, "text": "   "},  # blank -> dropped
        ],
    }
    _install_fake_whisper(monkeypatch, result)

    meta = tr._transcribe_local_whisper(b"audio", "base", None)
    assert isinstance(meta, MediaMetadata)
    assert meta.extractor == "whisper"
    assert meta.model == "base"
    assert meta.language == "en"
    # duration is the end of the LAST raw segment (3.2), even though that
    # blank segment is dropped from the emitted segment list.
    assert meta.duration_s == 3.2
    assert [s.text for s in meta.segments] == ["Hello world", "second segment"]
    assert meta.segments[0].start_s == 0.0
    assert meta.segments[0].end_s == 1.5


def test_local_whisper_passes_language_kwarg(monkeypatch):
    monkeypatch.setattr(tr, "_to_wav", lambda b: b)
    fake = _install_fake_whisper(monkeypatch, {"segments": [], "language": "de"})

    meta = tr._transcribe_local_whisper(b"audio", "small", "de")
    assert fake._Model.last_kwargs.get("language") == "de"
    assert meta.language == "de"
    assert meta.duration_s == 0.0
    assert meta.segments == []


def test_local_whisper_returns_none_when_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "whisper":
            raise ImportError("no whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert tr._transcribe_local_whisper(b"a", "base", None) is None


# --------------------------------------------------------------------------- #
# Backend 2: faster-whisper (mocked model).
# --------------------------------------------------------------------------- #

def _install_fake_faster_whisper(monkeypatch, segments, info):
    fake = types.ModuleType("faster_whisper")

    class _WhisperModel:
        def __init__(self, size, device="auto", compute_type="int8"):
            _WhisperModel.init_args = (size, device, compute_type)

        def transcribe(self, path, **kwargs):
            _WhisperModel.last_kwargs = kwargs
            return iter(segments), info

    fake.WhisperModel = _WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    return fake


def test_faster_whisper_builds_metadata(monkeypatch):
    monkeypatch.setattr(tr, "_to_wav", lambda b: b)
    Seg = types.SimpleNamespace
    segments = [
        Seg(start=0.0, end=2.0, text=" alpha "),
        Seg(start=2.0, end=4.0, text="beta"),
        Seg(start=4.0, end=4.1, text="  "),  # blank -> dropped
    ]
    info = types.SimpleNamespace(language="fr", duration=4.1)
    _install_fake_faster_whisper(monkeypatch, segments, info)

    meta = tr._transcribe_faster_whisper(b"audio", "medium", "fr")
    assert meta.extractor == "faster-whisper"
    assert meta.model == "medium"
    assert meta.language == "fr"
    assert meta.duration_s == 4.1
    assert [s.text for s in meta.segments] == ["alpha", "beta"]
    assert meta.segments[1].start_s == 2.0


def test_faster_whisper_defaults_without_info_attrs(monkeypatch):
    monkeypatch.setattr(tr, "_to_wav", lambda b: b)

    class _Info:  # no .language / .duration attributes
        pass

    _install_fake_faster_whisper(monkeypatch, [], _Info())
    meta = tr._transcribe_faster_whisper(b"audio", "tiny", None)
    assert meta.language == "en"  # falls back to language or "en"
    assert meta.duration_s == 0.0
    assert meta.segments == []


def test_faster_whisper_returns_none_when_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("no faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert tr._transcribe_faster_whisper(b"a", "base", None) is None


# --------------------------------------------------------------------------- #
# Backend 3: OpenAI API (mocked httpx).
# --------------------------------------------------------------------------- #

def test_openai_api_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert tr._transcribe_openai_api(b"audio", None) is None


def test_openai_api_builds_metadata(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    payload = {
        "language": "en",
        "duration": 5.0,
        "segments": [
            {"start": 0.0, "end": 2.5, "text": " first "},
            {"start": 2.5, "end": 5.0, "text": "second"},
            {"start": 5.0, "end": 5.0, "text": ""},  # blank -> dropped
        ],
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    fake_httpx = types.ModuleType("httpx")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        captured["headers"] = kwargs.get("headers")
        return _Resp()

    fake_httpx.post = fake_post
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    meta = tr._transcribe_openai_api(b"audio", "en", file_ext="wav")
    assert meta.extractor == "openai-api"
    assert meta.model == "whisper-1"
    assert meta.language == "en"
    assert meta.duration_s == 5.0
    assert [s.text for s in meta.segments] == ["first", "second"]
    assert captured["url"].endswith("/v1/audio/transcriptions")
    assert captured["data"]["language"] == "en"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_openai_api_returns_none_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    fake_httpx = types.ModuleType("httpx")

    def fake_post(url, **kwargs):
        raise RuntimeError("network down")

    fake_httpx.post = fake_post
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    assert tr._transcribe_openai_api(b"audio", None) is None


def test_openai_api_returns_none_when_httpx_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("no httpx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert tr._transcribe_openai_api(b"audio", None) is None


def test_openai_api_defaults_language_and_duration(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"segments": []}  # no language, no duration

    fake_httpx = types.ModuleType("httpx")
    fake_httpx.post = lambda url, **kwargs: _Resp()
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    meta = tr._transcribe_openai_api(b"audio", None)
    assert meta.language == "en"
    assert meta.duration_s == 0.0
    assert meta.segments == []


# --------------------------------------------------------------------------- #
# Public transcribe() fallthrough.
# --------------------------------------------------------------------------- #

def test_transcribe_uses_first_available_backend(monkeypatch):
    sentinel = MediaMetadata(title="", extractor="whisper", segments=[])
    monkeypatch.setattr(tr, "_transcribe_local_whisper", lambda *a: sentinel)
    monkeypatch.setattr(
        tr, "_transcribe_faster_whisper",
        lambda *a: pytest.fail("should not reach faster-whisper"),
    )
    result = tr.transcribe(b"audio", model_size="base")
    assert result is sentinel


def test_transcribe_falls_through_to_faster_whisper(monkeypatch):
    sentinel = MediaMetadata(title="", extractor="faster-whisper", segments=[])
    monkeypatch.setattr(tr, "_transcribe_local_whisper", lambda *a: None)
    monkeypatch.setattr(tr, "_transcribe_faster_whisper", lambda *a: sentinel)
    monkeypatch.setattr(
        tr, "_transcribe_openai_api",
        lambda *a: pytest.fail("should not reach openai api"),
    )
    result = tr.transcribe(b"audio")
    assert result.extractor == "faster-whisper"


def test_transcribe_falls_through_to_openai(monkeypatch):
    sentinel = MediaMetadata(title="", extractor="openai-api", segments=[])
    monkeypatch.setattr(tr, "_transcribe_local_whisper", lambda *a: None)
    monkeypatch.setattr(tr, "_transcribe_faster_whisper", lambda *a: None)
    monkeypatch.setattr(tr, "_transcribe_openai_api", lambda *a: sentinel)
    result = tr.transcribe(b"audio", language="en", file_ext="mp3")
    assert result.extractor == "openai-api"


def test_transcribe_returns_empty_none_backend_when_all_fail(monkeypatch):
    monkeypatch.setattr(tr, "_transcribe_local_whisper", lambda *a: None)
    monkeypatch.setattr(tr, "_transcribe_faster_whisper", lambda *a: None)
    monkeypatch.setattr(tr, "_transcribe_openai_api", lambda *a: None)

    result = tr.transcribe(b"audio")
    assert isinstance(result, MediaMetadata)
    assert result.extractor == "none"
    assert result.segments == []
    assert result.full_text == ""


def test_transcribe_full_text_from_real_segments(monkeypatch):
    # End-to-end through the local backend with a mocked model, asserting the
    # MediaMetadata.full_text property joins the real segment texts.
    monkeypatch.setattr(tr, "_to_wav", lambda b: b)
    _install_fake_whisper(
        monkeypatch,
        {
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "one"},
                {"start": 1.0, "end": 2.0, "text": "two"},
            ],
        },
    )
    result = tr.transcribe(b"audio", model_size="tiny")
    assert result.extractor == "whisper"
    assert result.full_text == "one two"
    assert isinstance(result.segments[0], TranscriptSegment)
