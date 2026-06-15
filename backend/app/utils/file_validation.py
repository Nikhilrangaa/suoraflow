"""
file_validation.py — Upload validation and safe path helpers.

Safety contract:
- Never trust uploaded filenames; always generate UUID-based paths.
- Validate extension AND (in Phase 2+) ffprobe-confirmed media type.
- All paths stay under STORAGE_ROOT.

Phase 0: signatures and constants only. Full validation in Phase 1–2.
"""
import uuid
from pathlib import Path

ALLOWED_EXTENSIONS = {
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mts", ".m2ts"},
    "audio": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"},
}

ALL_ALLOWED_EXTENSIONS = {
    ext for exts in ALLOWED_EXTENSIONS.values() for ext in exts
}


def generate_asset_id() -> str:
    """Return a new UUID4 string for use as an asset identifier."""
    return str(uuid.uuid4())


def safe_asset_path(storage_root: str, project_id: str, asset_id: str, ext: str) -> Path:
    """
    Build a safe storage path: <storage_root>/raw/<project_id>/<asset_id><ext>

    The extension must already be validated/normalised by the caller.
    Never derived from uploaded filename.
    """
    root = Path(storage_root)
    dest_dir = root / "raw" / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / f"{asset_id}{ext}"


def validate_extension(filename: str) -> str:
    """
    Return the lowercased extension if it is in the allow-list.

    Raises ValueError if not allowed.
    Never trusts the filename for anything other than extracting the extension.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALL_ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Extension '{ext}' is not allowed. "
            f"Permitted: {sorted(ALL_ALLOWED_EXTENSIONS)}"
        )
    return ext
