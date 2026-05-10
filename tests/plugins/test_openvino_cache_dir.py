"""Phase 3 / A4 tests for OpenVINO cache_dir resolution.

Verifies that ``_resolve_openvino_cache_dir`` anchors relative paths
to the project root, accepts absolute paths verbatim, creates the
target directory, and falls back to a tempdir when the requested
location is not writable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zebtrack.plugins.openvino_detector import _resolve_openvino_cache_dir


def test_resolve_returns_none_for_empty(tmp_path: Path) -> None:
    assert _resolve_openvino_cache_dir(None) is None
    assert _resolve_openvino_cache_dir("") is None


def test_resolve_creates_absolute_path(tmp_path: Path) -> None:
    target = tmp_path / "ov_cache"
    resolved = _resolve_openvino_cache_dir(str(target))

    assert resolved == str(target)
    assert target.exists()
    assert target.is_dir()


def test_resolve_anchors_relative_to_project_root() -> None:
    """Relative paths must NOT resolve against the current working directory.

    The plugin always anchors to the repo root so cache survives a
    `cd` and is shared across processes started from different CWDs.
    """
    resolved = _resolve_openvino_cache_dir("openvino_model_cache/test_resolve_phase3")

    assert resolved is not None
    try:
        resolved_path = Path(resolved)
        assert resolved_path.is_absolute()
        assert resolved_path.exists()
        # The repo root is two parents above this file's dir.
        expected_root = Path(__file__).resolve().parents[2]
        assert resolved_path.parent.parent == expected_root
    finally:
        # Only remove the leaf we created. The parent
        # ``openvino_model_cache`` may pre-exist in the repo and is
        # shared across cache entries.
        leaf = Path(resolved)
        if leaf.exists() and leaf.is_dir() and leaf.name == "test_resolve_phase3":
            leaf.rmdir()


def test_resolve_falls_back_when_not_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate an unwritable directory and verify the tempdir fallback path."""
    target = tmp_path / "ov_cache_ro"
    target.mkdir()

    # Pretend the directory is not writable.
    def fake_access(path: object, mode: int) -> bool:
        return False

    monkeypatch.setattr("zebtrack.plugins.openvino_detector.os.access", fake_access)

    resolved = _resolve_openvino_cache_dir(str(target))

    assert resolved is not None
    assert resolved != str(target)
    assert "zebtrack_openvino_cache" in resolved
    assert Path(resolved).exists()
