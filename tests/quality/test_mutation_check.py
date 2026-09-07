"""Tests for ``scripts/mutation_check.py`` -- above all, for how it scopes itself.

CI no longer runs the whole catalogue on every PR: it passes
``--changed-since HEAD^`` and mutates only the modules the change touches. That
turns a file-to-module mapping into a gate, and a mapping that quietly selects
nothing would report success while checking nothing at all -- the exact failure
mode the mutation catalogue exists to prevent, reproduced one level up.

So these tests pin the two directions separately:

* what must be selected (source touched, tests touched, runner/catalogue/conftest
  touched, git unable to answer);
* what the empty selection is allowed to do (exit 0 without running pytest, and
  without letting ``_verify_tree_restored`` inspect the whole repository).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_check  # noqa: E402

pytestmark = pytest.mark.unit

_SPECS = {
    "mask_capture": {
        "source": "src/zebtrack/core/services/mask_capture.py",
        "tests": [
            "tests/core/detection/test_mask_capture.py",
            "tests/core/services/test_mask_capture_extended.py",
        ],
    },
    "weight_manager": {
        "source": "src/zebtrack/core/services/weight_manager.py",
        "tests": ["tests/core/services/test_weight_manager_extended.py"],
    },
}


def _git_stub(responses: dict[tuple[str, ...], tuple[int, str]], calls: list[tuple[str, ...]]):
    """A ``_git`` replacement answering from ``responses``, recording every call."""

    def fake_git(*args: str) -> tuple[int, str]:
        calls.append(args)
        return responses.get(args, (0, ""))

    return fake_git


# --- _changed_paths: what the diff actually reports -------------------------


def test_three_dot_diff_is_preferred(monkeypatch):
    """The fork point is what separates this branch's work from the base's."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        mutation_check,
        "_git",
        _git_stub(
            {
                ("diff", "--name-only", "origin/main...HEAD"): (
                    0,
                    "src/zebtrack/core/services/mask_capture.py\n",
                )
            },
            calls,
        ),
    )

    assert mutation_check._changed_paths("origin/main") == {
        "src/zebtrack/core/services/mask_capture.py"
    }
    assert ("diff", "--name-only", "origin/main") not in calls


def test_two_dot_diff_rescues_a_shallow_clone(monkeypatch):
    """No merge base on a depth-limited clone: compare the trees instead.

    Over-selecting there means running extra modules; the alternative -- giving
    up and selecting nothing -- would report a green mutation check for a branch
    nobody mutated.
    """
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        mutation_check,
        "_git",
        _git_stub(
            {
                ("diff", "--name-only", "origin/main...HEAD"): (128, ""),
                ("diff", "--name-only", "origin/main"): (
                    0,
                    "src/zebtrack/core/services/weight_manager.py\n",
                ),
            },
            calls,
        ),
    )

    assert mutation_check._changed_paths("origin/main") == {
        "src/zebtrack/core/services/weight_manager.py"
    }
    assert ("diff", "--name-only", "origin/main...HEAD") in calls
    assert ("diff", "--name-only", "origin/main") in calls


def test_unanswerable_diff_returns_none(monkeypatch):
    """Both diffs failing is not an empty diff, and must not be read as one."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        mutation_check,
        "_git",
        _git_stub(
            {
                ("diff", "--name-only", "nope...HEAD"): (128, ""),
                ("diff", "--name-only", "nope"): (128, ""),
            },
            calls,
        ),
    )

    assert mutation_check._changed_paths("nope") is None


def test_uncommitted_and_renamed_files_are_included(monkeypatch):
    """Work in progress counts, and a rename is matched by its NEW path.

    Renaming a module's test file away is precisely when the check must not go
    quiet, and porcelain reports that as ``R  old -> new``.
    """
    calls: list[tuple[str, ...]] = []
    status = (
        " M src/zebtrack/core/services/mask_capture.py\n"
        "?? tests/core/services/test_brand_new.py\n"
        "R  tests/old_name.py -> tests/core/services/test_weight_manager_extended.py\n"
    )
    monkeypatch.setattr(
        mutation_check,
        "_git",
        _git_stub(
            {
                ("diff", "--name-only", "HEAD...HEAD"): (0, ""),
                ("status", "--porcelain"): (0, status),
            },
            calls,
        ),
    )

    assert mutation_check._changed_paths("HEAD") == {
        "src/zebtrack/core/services/mask_capture.py",
        "tests/core/services/test_brand_new.py",
        "tests/core/services/test_weight_manager_extended.py",
    }


def test_windows_separators_are_normalised(monkeypatch):
    """The catalogue stores POSIX paths; a backslash must still match."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        mutation_check,
        "_git",
        _git_stub(
            {
                ("diff", "--name-only", "HEAD...HEAD"): (
                    0,
                    "src\\zebtrack\\core\\services\\mask_capture.py\n",
                )
            },
            calls,
        ),
    )

    changed = mutation_check._changed_paths("HEAD")
    assert changed == {"src/zebtrack/core/services/mask_capture.py"}


def test_real_repository_answers_the_diff():
    """The call shape works against this checkout, not only against a stub."""
    changed = mutation_check._changed_paths("HEAD")
    assert changed is not None, "git could not diff HEAD in the repository under test"
    assert all("\\" not in path for path in changed)


# --- _scope_to_changed: mapping files onto catalogue modules ----------------


def test_touching_a_source_selects_its_module(monkeypatch):
    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"src/zebtrack/core/services/weight_manager.py", "README.md"},
    )

    assert list(mutation_check._scope_to_changed(_SPECS, "origin/main")) == ["weight_manager"]


def test_touching_only_a_test_file_still_selects_its_module(monkeypatch):
    """A weakened assertion is exactly what a mutation is supposed to catch."""
    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"tests/core/services/test_mask_capture_extended.py"},
    )

    assert list(mutation_check._scope_to_changed(_SPECS, "origin/main")) == ["mask_capture"]


def test_unrelated_change_selects_nothing(monkeypatch):
    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"docs/INDEX.md", "src/zebtrack/ui/gui.py"},
    )

    assert mutation_check._scope_to_changed(_SPECS, "origin/main") == {}


@pytest.mark.parametrize(
    "path",
    ["scripts/mutation_check.py", "scripts/mutation_catalog.yaml", "tests/conftest.py"],
)
def test_scope_forcing_paths_widen_to_the_whole_catalogue(monkeypatch, path):
    """These three decide what a mutation is, or what every test runs under."""
    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: {path})

    assert mutation_check._scope_to_changed(_SPECS, "origin/main") == _SPECS


def test_unknown_diff_widens_to_the_whole_catalogue(monkeypatch):
    """Degrade towards running too much, never towards running nothing."""
    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: None)

    assert mutation_check._scope_to_changed(_SPECS, "origin/main") == _SPECS


# --- main(): the CLI contract CI depends on ---------------------------------


def test_module_and_changed_since_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["mutation_check.py", "--module", "mask_capture", "--changed-since", "HEAD^"]
    )

    assert mutation_check.main() == 2


def test_empty_scope_exits_clean_without_running_anything(monkeypatch, tmp_path):
    """Zero affected modules is success -- and must not touch the tree.

    ``_verify_tree_restored`` builds a ``git status`` pathspec from the selected
    sources; with an empty selection that pathspec disappears and git reports the
    WHOLE repository, so any unrelated edit in the working tree would be
    announced as a mutation leak and exit 2.
    """

    def explode(*args, **kwargs):
        raise AssertionError("no module is affected; nothing should have been checked")

    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: {"docs/INDEX.md"})
    monkeypatch.setattr(mutation_check, "_check_module", explode)
    monkeypatch.setattr(mutation_check, "_verify_tree_restored", explode)

    report = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["mutation_check.py", "--changed-since", "origin/main", "--json", str(report)],
    )

    assert mutation_check.main() == 0
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "score": {"killed": 0, "total": 0},
        "results": [],
        "skipped": {},
    }


def test_changed_since_narrows_the_real_catalogue(monkeypatch):
    """End to end on the shipped catalogue, with only the diff faked."""
    checked: list[str] = []

    def record(name: str, spec: dict, *, verbose: bool) -> mutation_check.ModuleReport:
        checked.append(name)
        return mutation_check.ModuleReport(name=name)

    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"src/zebtrack/core/services/external_trigger_gate.py"},
    )
    monkeypatch.setattr(mutation_check, "_check_module", record)
    monkeypatch.setattr(mutation_check, "_verify_tree_restored", lambda specs: [])
    monkeypatch.setattr(sys, "argv", ["mutation_check.py", "--changed-since", "origin/main"])

    assert mutation_check.main() == 0
    assert checked == ["external_trigger_gate"]


# --- the catalogue itself ---------------------------------------------------


def test_every_catalogued_path_exists():
    """A moved file must break the build, not silently shrink the scope.

    ``_check_module`` degrades to "none of the listed test files exist" when a
    test file moves, which was visible while CI ran ``--all``. Under
    ``--changed-since`` the stale entry never gets selected in the first place,
    so the module simply stops being checked without saying so.
    """
    catalog = yaml.safe_load((SCRIPTS_DIR / "mutation_catalog.yaml").read_text(encoding="utf-8"))

    missing = [
        path
        for spec in catalog["modules"].values()
        for path in [spec["source"], *spec["tests"]]
        if not (REPO_ROOT / path).exists()
    ]

    assert not missing, f"mutation_catalog.yaml points at files that no longer exist: {missing}"
