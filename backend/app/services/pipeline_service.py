"""
pipeline_service.py — Step implementations for the process_asset pipeline.

Each function does one pipeline step and returns plain data; orchestration,
status transitions, and persistence live in app.workers.tasks. Keeping steps
pure makes them unit-testable without a queue or heavy models.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.utils.ffmpeg import extract_audio_wav, extract_frames, run_ffprobe
from app.utils.waveform import write_waveform_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1 — probe
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    audio_codec: Optional[str] = None
    has_audio: bool = False


def _parse_fps(rate: str) -> Optional[float]:
    """Parse ffprobe's 'num/den' frame-rate strings; tolerate junk."""
    try:
        if "/" in rate:
            num, den = rate.split("/", 1)
            d = float(den)
            return round(float(num) / d, 3) if d else None
        return round(float(rate), 3)
    except (ValueError, ZeroDivisionError):
        return None


def probe_asset(stored_path: Path) -> ProbeResult:
    """Extract duration, video geometry, and audio stream metadata via ffprobe."""
    probe = run_ffprobe(stored_path)
    result = ProbeResult()

    fmt = probe.get("format", {})
    try:
        result.duration = round(float(fmt.get("duration", 0)), 3) or None
    except (TypeError, ValueError):
        result.duration = None

    for stream in probe.get("streams", []):
        ctype = stream.get("codec_type")
        if ctype == "video" and result.width is None:
            result.width = stream.get("width")
            result.height = stream.get("height")
            rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or ""
            result.fps = _parse_fps(rate)
        elif ctype == "audio" and not result.has_audio:
            result.has_audio = True
            try:
                result.sample_rate = int(stream.get("sample_rate", 0)) or None
            except (TypeError, ValueError):
                result.sample_rate = None
            result.channels = stream.get("channels")
            result.audio_codec = stream.get("codec_name")

    return result


# ---------------------------------------------------------------------------
# Step 2 — extract audio (+ waveform peaks, derived from the same WAV)
# ---------------------------------------------------------------------------

def audio_artifact_paths(project_id: str, asset_id: str) -> tuple[Path, Path]:
    """Server-generated artifact paths: (wav_path, waveform_json_path)."""
    settings = get_settings()
    base = Path(settings.storage_root) / "audio" / project_id
    return base / f"{asset_id}.wav", base / f"{asset_id}.waveform.json"


def extract_audio(stored_path: Path, wav_path: Path, waveform_path: Path) -> None:
    """Extract mono 16 kHz WAV and persist waveform peaks JSON next to it."""
    extract_audio_wav(stored_path, wav_path)
    write_waveform_json(wav_path, waveform_path)


# ---------------------------------------------------------------------------
# Step 3 — VAD
# ---------------------------------------------------------------------------

@dataclass
class VadResult:
    speech_ratio: float = 0.0
    segment_count: int = 0


def run_vad(wav_path: Path) -> VadResult:
    """Run Silero VAD (bundled with faster-whisper) over the extracted WAV."""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = decode_audio(str(wav_path), sampling_rate=16000)
    total_samples = len(audio)
    if total_samples == 0:
        return VadResult()

    speech_chunks = get_speech_timestamps(audio, VadOptions())
    speech_samples = sum(c["end"] - c["start"] for c in speech_chunks)
    return VadResult(
        speech_ratio=round(min(1.0, speech_samples / total_samples), 4),
        segment_count=len(speech_chunks),
    )


# ---------------------------------------------------------------------------
# Step 4 — transcribe
# ---------------------------------------------------------------------------

@dataclass
class RawSegment:
    start: float
    end: float
    text: str
    speaker: str = "Speaker 1"


@dataclass
class TranscribeResult:
    segments: list[RawSegment] = field(default_factory=list)
    language: Optional[str] = None


def transcribe(wav_path: Path) -> TranscribeResult:
    """faster-whisper with built-in VAD filtering and word timestamps."""
    from app.services.ml_models import get_whisper_model

    model = get_whisper_model()
    segments_iter, info = model.transcribe(
        str(wav_path),
        vad_filter=True,
        word_timestamps=True,
        beam_size=5,
    )

    segments: list[RawSegment] = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        # Word timestamps give tighter boundaries than segment times
        start, end = seg.start, seg.end
        if seg.words:
            start, end = seg.words[0].start, seg.words[-1].end
        segments.append(RawSegment(start=round(start, 3), end=round(end, 3), text=text))

    return TranscribeResult(segments=segments, language=getattr(info, "language", None))


# ---------------------------------------------------------------------------
# Step 5 — diarize (optional; single-speaker fallback)
# ---------------------------------------------------------------------------

def diarize(wav_path: Path, segments: list[RawSegment]) -> list[RawSegment]:
    """
    Assign speaker labels via pyannote when available; otherwise leave the
    default "Speaker 1" on every segment. Never raises — diarization is
    strictly optional and must not fail the pipeline.
    """
    try:
        from app.services.ml_models import get_diarization_pipeline

        pipeline = get_diarization_pipeline()
        if pipeline is None:
            return segments

        annotation = pipeline(str(wav_path))
        turns = [
            (turn.start, turn.end, label)
            for turn, _, label in annotation.itertracks(yield_label=True)
        ]
        if not turns:
            return segments

        # Stable human-friendly names in order of first appearance
        label_names: dict[Any, str] = {}
        for seg in segments:
            best_label, best_overlap = None, 0.0
            for t_start, t_end, label in turns:
                overlap = min(seg.end, t_end) - max(seg.start, t_start)
                if overlap > best_overlap:
                    best_overlap, best_label = overlap, label
            if best_label is not None:
                if best_label not in label_names:
                    label_names[best_label] = f"Speaker {len(label_names) + 1}"
                seg.speaker = label_names[best_label]
        return segments
    except Exception as exc:
        logger.warning("Diarization failed; keeping single-speaker labels: %s", exc)
        return segments


# ---------------------------------------------------------------------------
# Step 6 — chunk
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    start: float
    end: float
    text: str


_CHUNK_MIN_S = 20.0
_CHUNK_MAX_S = 60.0
_SENTENCE_ENDINGS = (".", "!", "?", "…")


def chunk_segments(segments: list[RawSegment]) -> list[Chunk]:
    """
    Group transcript segments into 20–60 s chunks, preferring to close a
    chunk at a sentence-ish boundary once it passes the 20 s minimum, and
    force-closing at 60 s regardless.
    """
    chunks: list[Chunk] = []
    cur_texts: list[str] = []
    cur_start: Optional[float] = None
    cur_end = 0.0

    def close() -> None:
        nonlocal cur_texts, cur_start
        if cur_texts and cur_start is not None:
            chunks.append(
                Chunk(start=cur_start, end=cur_end, text=" ".join(cur_texts))
            )
        cur_texts, cur_start = [], None

    for seg in segments:
        if cur_start is None:
            cur_start = seg.start
        cur_texts.append(seg.text)
        cur_end = seg.end
        duration = cur_end - cur_start
        ends_sentence = seg.text.rstrip().endswith(_SENTENCE_ENDINGS)
        if duration >= _CHUNK_MAX_S or (duration >= _CHUNK_MIN_S and ends_sentence):
            close()
    close()
    return chunks


# ---------------------------------------------------------------------------
# Step 7 — embed
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed *texts* with MiniLM; normalised so cosine distance is meaningful."""
    from app.services.ml_models import get_embedding_model

    if not texts:
        return []
    model = get_embedding_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


# ---------------------------------------------------------------------------
# Step 8 — visual indexing (video assets only)
# ---------------------------------------------------------------------------

_MIN_FRAME_INTERVAL_S = 2.5
_MAX_FRAMES_PER_ASSET = 240
_CLIP_BATCH = 16


@dataclass
class SampledFrame:
    frame_index: int
    timestamp: float
    path: Path


def frames_dir(project_id: str, asset_id: str) -> Path:
    """Server-generated frames directory for an asset."""
    settings = get_settings()
    return Path(settings.storage_root) / "frames" / project_id / asset_id


def frame_sample_interval(duration: Optional[float]) -> float:
    """
    One frame every 2.5 s, stretched so long footage caps at ~240 frames.
    Clamped to the clip duration — ffmpeg's fps filter fails when the
    sampling period exceeds the whole input.
    """
    if not duration or duration <= 0:
        return _MIN_FRAME_INTERVAL_S
    interval = max(_MIN_FRAME_INTERVAL_S, duration / _MAX_FRAMES_PER_ASSET)
    return round(max(0.5, min(interval, duration)), 3)


def sample_frames(
    stored_path: Path, out_dir: Path, duration: Optional[float]
) -> list[SampledFrame]:
    """Extract sampled frames and pair each with its mid-interval timestamp."""
    interval = frame_sample_interval(duration)
    paths = extract_frames(stored_path, out_dir, interval)
    return [
        SampledFrame(
            frame_index=i,
            # ffmpeg's fps filter grabs a frame per interval; the midpoint is
            # a closer estimate of when the frame appears than the boundary.
            timestamp=round(min(i * interval + interval / 2, duration or i * interval), 3),
            path=p,
        )
        for i, p in enumerate(paths)
    ]


def embed_images(paths: list[Path]) -> list[list[float]]:
    """Embed frame JPEGs with CLIP's image encoder (normalised, batched)."""
    from PIL import Image

    from app.services.ml_models import get_clip_model

    if not paths:
        return []
    model = get_clip_model()
    vectors: list[list[float]] = []
    for i in range(0, len(paths), _CLIP_BATCH):
        batch = []
        for p in paths[i : i + _CLIP_BATCH]:
            with Image.open(p) as img:
                batch.append(img.convert("RGB"))
        encoded = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        vectors.extend(v.tolist() for v in encoded)
    return vectors


def embed_query_clip(query: str) -> list[float]:
    """Embed a text query with CLIP's text encoder (same space as frames)."""
    from app.services.ml_models import get_clip_model

    model = get_clip_model()
    vec = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
    return vec.tolist()
