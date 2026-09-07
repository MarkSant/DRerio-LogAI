"""Tests for :mod:`zebtrack.paths`, the project-root anchor.

The regression these guard: every configuration file the application reads used
to be addressed by a bare relative path, so ``poetry -C <repo> run zebtrack``
from any other directory died on "Configuration File Not Found" before a window
ever appeared.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from zebtrack.paths import (
    _ROOT_MARKERS,
    _find_repo_root,
    default_config_path,
    default_local_config_path,
    repo_root,
)


class TestRepoRoot(unittest.TestCase):
    def test_root_carries_every_marker(self):
        """The anchor is a directory that really holds the project markers."""
        root = repo_root()
        for marker in _ROOT_MARKERS:
            self.assertTrue((root / marker).exists(), f"missing marker: {marker}")

    def test_resolution_does_not_depend_on_the_working_directory(self):
        """Re-running the search from another cwd yields the same directory."""
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as elsewhere:
            os.chdir(elsewhere)
            try:
                found = _find_repo_root()
            finally:
                os.chdir(original)

        self.assertEqual(found, repo_root())

    def test_cached_constant_matches_a_fresh_search(self):
        """The module constant is what the search returns, not a stale value."""
        self.assertEqual(_find_repo_root(), repo_root())

    def test_returned_path_is_absolute(self):
        self.assertTrue(repo_root().is_absolute())


class TestConfigPaths(unittest.TestCase):
    def test_config_path_points_at_the_tracked_file(self):
        self.assertTrue(default_config_path().is_absolute())
        self.assertTrue(default_config_path().is_file())
        self.assertEqual(default_config_path().name, "config.yaml")

    def test_local_override_path_is_anchored_even_when_absent(self):
        """config.local.yaml is git-ignored, so it usually does not exist yet.

        The path must still be anchored: the first-run language prompt checks
        this location and ``write_local_override`` writes to it. Disagreeing on
        the directory would re-ask the language on every launch.
        """
        local = default_local_config_path()
        self.assertTrue(local.is_absolute())
        self.assertEqual(local.name, "config.local.yaml")
        self.assertEqual(local.parent, repo_root())

    def test_both_paths_share_the_repository_root(self):
        self.assertEqual(default_config_path().parent, default_local_config_path().parent)
        self.assertEqual(default_config_path().parent, repo_root())


class TestResolveWeightsDir(unittest.TestCase):
    """Where the ``.pt`` files are looked for."""

    def test_defaults_to_weights_under_the_repository_root(self):
        from zebtrack.paths import DEFAULT_WEIGHTS_DIR, resolve_weights_dir

        self.assertEqual(resolve_weights_dir(None), repo_root() / DEFAULT_WEIGHTS_DIR)

    def test_settings_source_dir_wins_over_the_default(self):
        from types import SimpleNamespace

        from zebtrack.paths import resolve_weights_dir

        settings = SimpleNamespace(weights=SimpleNamespace(source_dir="modelos"))
        self.assertEqual(resolve_weights_dir(settings), repo_root() / "modelos")

    def test_explicit_override_wins_over_settings(self):
        from types import SimpleNamespace

        from zebtrack.paths import resolve_weights_dir

        settings = SimpleNamespace(weights=SimpleNamespace(source_dir="modelos"))
        resolved = resolve_weights_dir(settings, override="outros")
        self.assertEqual(resolved, repo_root() / "outros")

    def test_absolute_paths_are_left_alone(self):
        from zebtrack.paths import resolve_weights_dir

        absolute = Path(tempfile.gettempdir()).resolve() / "pesos"
        self.assertEqual(resolve_weights_dir(None, override=absolute), absolute)

    def test_config_dir_anchors_relative_paths(self):
        from zebtrack.paths import resolve_weights_dir

        base = Path(tempfile.gettempdir()).resolve()
        self.assertEqual(resolve_weights_dir(None, config_dir=base), base / "weights")

    def test_a_mock_source_dir_falls_back_instead_of_being_used_as_a_path(self):
        """A MagicMock answers every attribute, so getattr alone cannot be trusted.

        Without the isinstance check a stubbed settings object would produce a
        path built from the repr of a mock.
        """
        from unittest.mock import MagicMock

        from zebtrack.paths import DEFAULT_WEIGHTS_DIR, resolve_weights_dir

        self.assertEqual(resolve_weights_dir(MagicMock()), repo_root() / DEFAULT_WEIGHTS_DIR)


class TestImportStaysCheap(unittest.TestCase):
    """``zebtrack.paths`` answers path questions during early startup.

    The startup pre-flight asks it where the weights are BEFORE the hardware
    benchmark, precisely so a missing-weights run fails in a second rather than
    a minute. That only holds while importing this module is cheap: the obvious
    alternative home for the resolver, ``core.services.weight_manager``, drags
    in torch, cv2, ultralytics and openvino and spawns a thread pool.

    Runs in a subprocess because the modules are already imported in-process by
    the rest of the suite, which would make any in-process assertion vacuous.
    """

    def test_importing_paths_does_not_drag_in_the_detector_stack(self):
        import subprocess
        import sys

        code = (
            "import sys\n"
            "import zebtrack.paths\n"
            "heavy = [m for m in ('torch', 'cv2', 'ultralytics', 'openvino')"
            " if m in sys.modules]\n"
            "print(','.join(heavy))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "",
            "zebtrack.paths must stay importable without the detector stack",
        )
