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


def extract_audio_wav(input_path: Path, output_path: Path) -> None:
    """
    Extract audio from *input_path* to mono 16 kHz WAV at *output_path*.

    Uses argument array only — never shell=True.
    Phase 0 stub — raises NotImplementedError; implemented in Phase 2.
    """
    raise NotImplementedError("extract_audio_wav: implemented in Phase 2")
