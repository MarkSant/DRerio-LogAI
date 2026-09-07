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
