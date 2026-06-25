"""
Speaker diarization for the media connector.

Uses pyannote.audio when installed and a HuggingFace token is available.
The token must accept the pyannote/speaker-diarization-3.1 model's terms of
service at https://hf.co/pyannote/speaker-diarization-3.1.

If pyannote is not installed or the token is missing, segments are returned
unchanged with ``speaker=None`` so the connector works without diarization.

Usage::

    from src.ingestion.connectors.media.diarizer import assign_speakers
    segments = assign_speakers(audio_bytes, segments, hf_token="hf_...")
"""

from __future__ import annotations

import os
import tempfile
from typing import List, Optional

from src.ingestion.connectors.media.models import TranscriptSegment


def assign_speakers(
    audio_bytes: bytes,
    segments: List[TranscriptSegment],
    hf_token: Optional[str] = None,
) -> List[TranscriptSegment]:
    """
    Assign speaker labels to transcript segments via pyannote diarization.

    Returns segments unchanged (speaker=None) if pyannote.audio is not
    installed or no HuggingFace token is available.

    Args:
        audio_bytes: Raw audio bytes (any format ffmpeg can read).
        segments:    List of TranscriptSegment from the transcriber.
        hf_token:    HuggingFace access token. Falls back to ``HF_TOKEN``
                     and ``HUGGINGFACE_HUB_TOKEN`` env vars.
    """
    token = (
        hf_token
        or os.environ.get("HF_TOKEN", "")
        or os.environ.get("HUGGINGFACE_HUB_TOKEN", "")
    )
    if not token:
        return segments
    if not segments:
        return segments

    try:
        from pyannote.audio import Pipeline  # type: ignore
        import torch  # type: ignore
    except ImportError:
        return segments

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
        # Move to GPU if available.
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline = pipeline.to(device)
    except Exception:
        return segments

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        diarization = pipeline(tmp_path)
    except Exception:
        return segments
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Map each segment's midpoint to the speaker with the most overlap.
    labelled = list(segments)
    for i, seg in enumerate(labelled):
        midpoint = (seg.start_s + seg.end_s) / 2.0
        best_speaker = None
        best_overlap = 0.0
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            overlap = min(turn.end, seg.end_s) - max(turn.start, seg.start_s)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        if best_speaker is None:
            # Nearest speaker by midpoint distance.
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                dist = abs((turn.start + turn.end) / 2.0 - midpoint)
                if best_overlap == 0.0 or dist < best_overlap:
                    best_overlap = dist
                    best_speaker = speaker
        labelled[i] = TranscriptSegment(
            start_s=seg.start_s,
            end_s=seg.end_s,
            text=seg.text,
            speaker=best_speaker,
        )

    return labelled
