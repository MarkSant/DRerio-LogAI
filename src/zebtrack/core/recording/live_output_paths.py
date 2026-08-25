"""Where an ad-hoc live session writes when there is no project to hold it.

A live session started from the main window ("Analyze Live Camera") has no
project folder behind it, so ``LiveCameraService`` fell back to the RELATIVE
path ``live_analysis_sessions/`` — relative to the process working directory.
That is wherever the app happened to be launched from: a shortcut's "start in"
folder, ``C:\\Windows\\System32``, or a directory the user cannot write to. The
recording either landed somewhere unfindable or failed after the fact.

The dialog's folder field and the service fallback MUST agree on the default,
otherwise the field would show one path and the recording would go to another —
hence this single function instead of two literals.

Pure module: computes a path, creates nothing.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["LIVE_SESSIONS_FOLDER_NAME", "default_live_sessions_dir"]

LIVE_SESSIONS_FOLDER_NAME = "live_analysis_sessions"


def default_live_sessions_dir() -> Path:
    """Default output directory for a live session with no project.

    ``~/ZebTrack/live_analysis_sessions`` — the home directory is writable, is
    stable across launches, and matches where projects already default to
    (``Path.home() / "ZebTrack" / "Projects"`` in ``ProjectCoordinator``).
    """
    return Path.home() / "ZebTrack" / LIVE_SESSIONS_FOLDER_NAME
