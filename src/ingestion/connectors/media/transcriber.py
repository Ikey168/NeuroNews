"""
Whisper transcription backends for the media connector.

Extraction chain (first that works):
  1. openai-whisper  — local model inference; best quality; needs GPU/CPU time.
  2. faster-whisper  — CTranslate2-based; faster on CPU; same model weights.
  3. OpenAI API      — cloud; requires OPENAI_API_KEY env var; no local GPU needed.
  4. "none"          — returns an empty transcript so the connector is always
                        importable and testable without any optional deps.

All backends produce a list of ``TranscriptSegment`` objects with start/end
timestamps. Whisper already segments by sentence, which is the natural atomic
unit for timestamp-linked RAG retrieval.

Audio format:
  Whisper expects 16 kHz mono PCM. The local backends handle resampling
  internally. The API backend accepts common formats (mp3, mp4, wav, webm)
  directly. If ffmpeg is available on the system, ``_to_wav()`` can normalize
  any input to wav for the local backends.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
from typing import Optional

from src.ingestion.connectors.media.models import MediaMetadata, TranscriptSegment


# --------------------------------------------------------------------------- #
# Audio normalization
# --------------------------------------------------------------------------- #

def _to_wav(audio_bytes: bytes) -> bytes:
    """
    Convert any audio/video bytes to 16kHz mono WAV via ffmpeg (system binary).

    Returns the original bytes unchanged if ffmpeg is not available so callers
    degrade gracefully.
    """
    if not _ffmpeg_available():
        return audio_bytes
    with (
        tempfile.NamedTemporaryFile(suffix=".input", delete=False) as inp,
        tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out,
    ):
        inp.write(audio_bytes)
        inp_path = inp.name
        out_path = out.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", inp_path,
                "-ar", "16000", "-ac", "1", "-f", "wav", out_path,
            ],
            check=True,
            capture_output=True,
        )
        with open(out_path, "rb") as f:
            return f.read()
    except subprocess.CalledProcessError:
        return audio_bytes
    finally:
        for p in (inp_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


# --------------------------------------------------------------------------- #
# Backend 1: openai-whisper (local model)
# --------------------------------------------------------------------------- #

def _transcribe_local_whisper(
    audio_bytes: bytes,
    model_size: str,
    language: Optional[str],
) -> Optional[MediaMetadata]:
    try:
        import whisper  # type: ignore
    except ImportError:
        return None

    wav_bytes = _to_wav(audio_bytes)

    # Write to a temp file; whisper's load_audio reads files, not bytes.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name

    try:
        model = whisper.load_model(model_size)
        kwargs = {"verbose": False}
        if language:
            kwargs["language"] = language
        result = model.transcribe(tmp_path, **kwargs)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    segments = [
        TranscriptSegment(
            start_s=float(seg["start"]),
            end_s=float(seg["end"]),
            text=seg["text"].strip(),
        )
        for seg in result.get("segments", [])
        if seg.get("text", "").strip()
    ]

    detected_language = result.get("language", language or "en")
    duration = float(result["segments"][-1]["end"]) if result.get("segments") else 0.0

    return MediaMetadata(
        title="",
        language=detected_language,
        duration_s=duration,
        segments=segments,
        model=model_size,
        extractor="whisper",
    )


# --------------------------------------------------------------------------- #
# Backend 2: faster-whisper
# --------------------------------------------------------------------------- #

def _transcribe_faster_whisper(
    audio_bytes: bytes,
    model_size: str,
    language: Optional[str],
) -> Optional[MediaMetadata]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return None

    wav_bytes = _to_wav(audio_bytes)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name

    try:
        model = WhisperModel(model_size, device="auto", compute_type="int8")
        transcribe_kwargs = {"beam_size": 5}
        if language:
            transcribe_kwargs["language"] = language
        segs, info = model.transcribe(tmp_path, **transcribe_kwargs)
        segments = [
            TranscriptSegment(
                start_s=float(seg.start),
                end_s=float(seg.end),
                text=seg.text.strip(),
            )
            for seg in segs
            if seg.text.strip()
        ]
        detected_language = info.language if hasattr(info, "language") else (language or "en")
        duration = float(info.duration) if hasattr(info, "duration") else 0.0
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return MediaMetadata(
        title="",
        language=detected_language,
        duration_s=duration,
        segments=segments,
        model=model_size,
        extractor="faster-whisper",
    )


# --------------------------------------------------------------------------- #
# Backend 3: OpenAI Whisper API
# --------------------------------------------------------------------------- #

def _transcribe_openai_api(
    audio_bytes: bytes,
    language: Optional[str],
    file_ext: str = "mp3",
) -> Optional[MediaMetadata]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    try:
        import httpx  # type: ignore
    except ImportError:
        return None

    # The OpenAI transcription API returns verbose JSON with segments.
    audio_file = (f"audio.{file_ext}", io.BytesIO(audio_bytes), f"audio/{file_ext}")
    data: dict = {"model": "whisper-1", "response_format": "verbose_json"}
    if language:
        data["language"] = language

    try:
        resp = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files={"file": audio_file},
            timeout=120.0,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return None

    segments = [
        TranscriptSegment(
            start_s=float(seg["start"]),
            end_s=float(seg["end"]),
            text=seg["text"].strip(),
        )
        for seg in payload.get("segments", [])
        if seg.get("text", "").strip()
    ]

    detected_language = payload.get("language", language or "en")
    duration = float(payload["duration"]) if "duration" in payload else 0.0

    return MediaMetadata(
        title="",
        language=detected_language,
        duration_s=duration,
        segments=segments,
        model="whisper-1",
        extractor="openai-api",
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def transcribe(
    audio_bytes: bytes,
    model_size: str = "base",
    language: Optional[str] = None,
    file_ext: str = "mp3",
) -> MediaMetadata:
    """
    Transcribe audio/video bytes to a list of timestamped segments.

    Tries backends in order: local whisper → faster-whisper → OpenAI API.
    Returns a MediaMetadata with empty segments if no backend is available.

    Args:
        audio_bytes: Raw audio/video file bytes.
        model_size:  Whisper model size ("tiny", "base", "small", "medium", "large").
        language:    ISO 639-1 language hint (e.g. "en"). None = auto-detect.
        file_ext:    File extension hint for the OpenAI API backend.
    """
    for attempt in (
        lambda: _transcribe_local_whisper(audio_bytes, model_size, language),
        lambda: _transcribe_faster_whisper(audio_bytes, model_size, language),
        lambda: _transcribe_openai_api(audio_bytes, language, file_ext),
    ):
        result = attempt()
        if result is not None:
            return result

    return MediaMetadata(title="", extractor="none", segments=[])
