"""
waveform.py — Compute downsampled peak data from a mono 16-bit PCM WAV.

The peaks power the frontend waveform canvas without shipping raw audio:
one normalised max-abs amplitude value (0..1) per time bucket.

Memory-bounded: frames are read in chunks, never the whole file at once.
"""
import json
import wave
from pathlib import Path

import numpy as np

_TARGET_PEAKS = 1200  # enough horizontal resolution for any reasonable canvas
_READ_CHUNK_FRAMES = 262144  # 16 s of 16 kHz audio per read


def compute_waveform_peaks(wav_path: Path, target_peaks: int = _TARGET_PEAKS) -> dict:
    """
    Return {"peaks": [float 0..1, ...], "duration": seconds} for *wav_path*.

    Expects mono 16-bit PCM (what extract_audio_wav produces). Raises
    ValueError on unexpected formats so the pipeline can fail safely.
    """
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        n_frames = wf.getnframes()

        if n_channels != 1 or sample_width != 2:
            raise ValueError(
                f"Expected mono 16-bit WAV, got channels={n_channels} width={sample_width}"
            )

        duration = n_frames / frame_rate if frame_rate else 0.0
        if n_frames == 0:
            return {"peaks": [], "duration": 0.0}

        bucket_size = max(1, n_frames // target_peaks)
        peaks: list[int] = []
        leftover = np.empty(0, dtype=np.int16)

        while True:
            raw = wf.readframes(_READ_CHUNK_FRAMES)
            if not raw:
                break
            samples = np.frombuffer(raw, dtype=np.int16)
            data = np.concatenate([leftover, samples]) if leftover.size else samples
            n_full = data.size // bucket_size
            if n_full:
                # int32 cast before abs: |int16 -32768| overflows int16
                full = np.abs(
                    data[: n_full * bucket_size].astype(np.int32)
                ).reshape(n_full, bucket_size)
                peaks.extend(int(v) for v in full.max(axis=1))
                leftover = data[n_full * bucket_size:]
            else:
                leftover = data
        if leftover.size:
            peaks.append(int(np.abs(leftover.astype(np.int32)).max()))

    return {
        "peaks": [round(p / 32768.0, 4) for p in peaks],
        "duration": round(duration, 3),
    }


def write_waveform_json(wav_path: Path, out_path: Path) -> dict:
    """Compute peaks for *wav_path* and persist them as JSON at *out_path*."""
    data = compute_waveform_peaks(wav_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data))
    return data
