# Media connector

Audio/video ingestion with Whisper transcription for the knowledge-engine
pipeline (#523). Podcasts, talks, and lectures become searchable knowledge with
timestamp-linked answers.

## What it does

Transcribes an audio/video file and emits **one `Document` per Whisper
segment** so semantic search returns timestamp-linked answers:

```
podcast.mp3  →  MediaConnector.harvest()  →  Document(
    source_type="transcript",
    content="…what I mean by alignment is…",
    metadata={"start_s": 742.3, "end_s": 756.1, "speaker": "SPEAKER_00"},
    content_ref="file:///podcasts/ep42.mp3#t=742.300,756.100",
)
```

Each `content_ref` is a **Media Fragment URI** (W3C spec): `base#t=start,end`.
A player can seek directly to the matching moment.

## Usage

```python
from src.ingestion.connectors import get_connector

connector = get_connector("transcript")

# File paths or HTTP(S) URLs
for doc in connector.harvest(["podcast.mp3", "lecture.mp4"]):
    start = doc.metadata["start_s"]
    end   = doc.metadata["end_s"]
    print(f"{start:.0f}s–{end:.0f}s  {doc.content[:80]}")
```

### Speaker diarization

Pass a HuggingFace token (after accepting
[pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1)
terms) to get per-segment speaker labels:

```python
connector = MediaConnector(diarize=True, hf_token="hf_...")
```

Without a token, `speaker` is absent from the metadata.

### Model size

```python
connector = MediaConnector(model_size="medium")  # tiny/base/small/medium/large
```

## Transcription backends

| Priority | Backend          | When used                                      |
|----------|-----------------|------------------------------------------------|
| 1        | openai-whisper   | `pip install openai-whisper` (local GPU/CPU)   |
| 2        | faster-whisper   | `pip install faster-whisper` (faster on CPU)   |
| 3        | OpenAI API       | `OPENAI_API_KEY` env var set (cloud, no GPU)   |
| 4        | none             | No backend — returns empty segment list        |

`ffmpeg` (system package) is used to normalize audio to 16 kHz mono WAV before
local inference. It is available in the project environment already.

## Document metadata fields

| Field                         | Description                                         |
|-------------------------------|-----------------------------------------------------|
| `metadata["media_title"]`     | Title of the source file/episode                    |
| `metadata["media_id"]`        | Stable `media:<hash>` identifier for the source     |
| `metadata["start_s"]`         | Segment start in seconds                            |
| `metadata["end_s"]`           | Segment end in seconds                              |
| `metadata["duration_s"]`      | Segment duration in seconds                         |
| `metadata["segment_index"]`   | Position in the transcript (0-based)                |
| `metadata["speaker"]`         | Speaker label, e.g. `"SPEAKER_00"` (if diarized)   |
| `metadata["media_duration_s"]`| Total media duration in seconds                     |
| `metadata["model"]`           | Whisper model size used                             |
| `metadata["extractor"]`       | Which backend ran (`"whisper"`, `"openai-api"`, …)  |
| `content_ref`                 | Media Fragment URI: `file://...#t=start,end`        |

## Exit criterion

Semantic search over a podcast returns results where each hit includes
`metadata["start_s"]` / `metadata["end_s"]` and `content_ref` pointing to the
exact audio moment — satisfying "timestamp-linked answers".
