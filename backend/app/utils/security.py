"""
security.py — Security helpers.

Phase 0: minimal stubs. Expand in Phase 1+ as auth is added.
"""
from pathlib import Path


def is_path_within_root(path: Path, root: Path) -> bool:
    """
    Return True iff *path* resolves strictly under *root*.

    Use to prevent path-traversal attacks before opening any user-influenced path.
    """
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
