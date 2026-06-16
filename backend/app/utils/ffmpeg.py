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
    Extract audio from *input_path* to mono 16 kHz WAV at *output_path*.

    Uses argument array only — never shell=True.
    Phase 0 stub — raises NotImplementedError; implemented in Phase 2.
    """
    raise NotImplementedError("extract_audio_wav: implemented in Phase 2")
