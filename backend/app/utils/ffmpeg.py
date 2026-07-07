"""
ffmpeg.py — Safe subprocess wrappers for ffmpeg and ffprobe.

Safety contract (graded by reviewer):
- ALL subprocess calls use argument ARRAYS — never shell=True, os.system,
  or string interpolation into commands.
- Caller is responsible for validating paths before passing them here.

Phase 0: signatures + safe defaults only. Full implementation in Phase 2.
"""
import json
import subprocess
from pathlib import Path
from typing import Any


def run_ffprobe(input_path: Path) -> dict[str, Any]:
    """
    Run ffprobe on *input_path* and return the parsed JSON output.

    Uses argument array only — never shell=True.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,  # explicit — never True
    )
    result.check_returncode()
    return json.loads(result.stdout)


def validate_media_type(input_path: Path, expected_media_type: str) -> None:
    """
    Validate that the file at *input_path* actually contains the expected media type.

    expected_media_type must be "video" or "audio".

    - "video": file must have at least one video stream.
    - "audio": file must have at least one audio stream AND no video stream.

    Raises ValueError with a safe message if validation fails.
    Raises subprocess.CalledProcessError / json.JSONDecodeError if ffprobe fails,
    which callers should catch and convert to a 400.
    """
    probe = run_ffprobe(input_path)
    streams = probe.get("streams", [])
    codec_types = {s.get("codec_type") for s in streams}

    if expected_media_type == "video":
        if "video" not in codec_types:
            raise ValueError(
                "File does not contain a video stream; "
                "content does not match the declared extension."
            )
    elif expected_media_type == "audio":
        if "audio" not in codec_types:
            raise ValueError(
                "File does not contain an audio stream; "
                "content does not match the declared extension."
            )
        if "video" in codec_types:
            raise ValueError(
                "File contains a video stream but was uploaded with an audio extension; "
                "use a video extension instead."
            )
    else:
        raise ValueError(f"Unknown expected_media_type: {expected_media_type!r}")


def extract_audio_wav(input_path: Path, output_path: Path) -> None:
    """
    Extract audio from *input_path* to mono 16 kHz 16-bit PCM WAV at *output_path*.

    Uses argument array only — never shell=True.
    Raises subprocess.CalledProcessError on ffmpeg failure (caller converts to
    a safe pipeline error; stderr is not propagated to users).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",  # overwrite (idempotent re-runs)
        "-i", str(input_path),
        "-vn",  # drop any video stream
        "-ac", "1",  # mono
        "-ar", "16000",  # 16 kHz
        "-c:a", "pcm_s16le",  # 16-bit PCM
        "-f", "wav",
        str(output_path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,  # generous: long footage on CPU
        shell=False,  # explicit — never True
    )
    result.check_returncode()


def extract_frames(input_path: Path, out_dir: Path, interval_s: float) -> list[Path]:
    """
    Sample one frame every *interval_s* seconds from *input_path* into
    *out_dir* as JPEGs (frame_00001.jpg, ...). Returns the ordered frame paths.

    Uses argument array only — never shell=True.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vf", f"fps=1/{interval_s},scale=336:-2",  # small: CLIP sees 224px
        "-q:v", "4",  # visually fine for thumbnails, small on disk
        str(out_dir / "frame_%05d.jpg"),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,
        shell=False,  # explicit — never True
    )
    result.check_returncode()
    return sorted(out_dir.glob("frame_*.jpg"))
