"""
Data models for the media connector: transcript segments and media metadata.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional


def media_id(url: Optional[str] = None, file_path: Optional[str] = None, title: Optional[str] = None) -> str:
    """Stable document id for a media file, preferring URL, then file path, then title."""
    key = (url or file_path or title or "").strip()
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    return f"media:{digest}"


def segment_id(doc_id: str, start_s: float) -> str:
    """Stable id for a transcript segment within a media document."""
    return f"{doc_id}#t={start_s:.3f}"


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


@dataclass
class TranscriptSegment:
    """A timestamped chunk of transcript text, optionally attributed to a speaker."""

    start_s: float
    end_s: float
    text: str
    speaker: Optional[str] = None

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)

    @property
    def timestamp_label(self) -> str:
        return f"[{format_timestamp(self.start_s)} - {format_timestamp(self.end_s)}]"

    def media_fragment(self, base_uri: str) -> str:
        """Return a Media Fragment URI (RFC 7826) for this segment."""
        return f"{base_uri}#t={self.start_s:.3f},{self.end_s:.3f}"


@dataclass
class MediaMetadata:
    """Normalized metadata and transcript for a media file (audio or video)."""

    title: str
    language: str = "en"
    source_url: Optional[str] = None
    file_path: Optional[str] = None
    media_format: str = "unknown"  # "mp3", "mp4", "wav", "ogg", "webm", …
    duration_s: float = 0.0
    segments: List[TranscriptSegment] = field(default_factory=list)
    speakers: List[str] = field(default_factory=list)
    model: str = "none"      # which Whisper model was used
    extractor: str = "none"  # "whisper", "faster-whisper", "openai-api", "none"

    @property
    def document_id(self) -> str:
        return media_id(self.source_url, self.file_path, self.title)

    @property
    def base_uri(self) -> str:
        return self.source_url or (
            f"file://{self.file_path}" if self.file_path else ""
        )

    @property
    def full_text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments if seg.text.strip())
