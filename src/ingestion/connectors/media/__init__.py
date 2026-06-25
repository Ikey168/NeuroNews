"""
Media connector: audio/video transcription to timestamped transcript Documents.

Importing this package registers the ``transcript`` connector.
"""

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

__all__ = [
    "MediaConnector",
    "media_metadata_to_documents",
    "segment_to_document",
    "assign_speakers",
    "MediaMetadata",
    "TranscriptSegment",
    "format_timestamp",
    "media_id",
    "segment_id",
    "transcribe",
]
