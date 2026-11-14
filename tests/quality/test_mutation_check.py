"""Tests for ``scripts/mutation_check.py`` -- above all, for how it scopes itself.

CI no longer runs the whole catalogue on every PR: it passes
``--changed-since HEAD^`` and mutates only the modules the change touches. That
turns a file-to-module mapping into a gate, and a mapping that quietly selects
nothing would report success while checking nothing at all -- the exact failure
mode the mutation catalogue exists to prevent, reproduced one level up.

So these tests pin the two directions separately:

* what must be selected (source touched, tests touched, catalogue/conftest
  touched, the runner touched -- a sample --, git unable to answer);
* what the empty selection is allowed to do (exit 0 without running pytest).

And, since the runner went parallel, what makes a verdict trustworthy at all:

* a mutant lives only in a worker's COPY of the tree, and the pytest started in
  that copy imports the copy -- not the checkout the venv's ``.pth`` points at;
* the checkout is pristine at every instant a mutant runs, so killing the runner
  cannot leave a mutant behind;
* one worker or many, the report is the same, in catalogue order.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
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


def _result(*, killed: bool) -> mutation_check.MutationResult:
    return mutation_check.MutationResult(
        module="a", mutation_id="m", description="", killed=killed, failures=int(killed)
    )


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

    assert list(mutation_check._scope_to_changed(_SPECS, "origin/main").blocks) == [
        "weight_manager"
    ]


def test_touching_only_a_test_file_still_selects_its_module(monkeypatch):
    """A weakened assertion is exactly what a mutation is supposed to catch."""
    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"tests/core/services/test_mask_capture_extended.py"},
    )

    assert list(mutation_check._scope_to_changed(_SPECS, "origin/main").blocks) == ["mask_capture"]


def test_unrelated_change_selects_nothing(monkeypatch):
    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"docs/INDEX.md", "src/zebtrack/ui/gui.py"},
    )

    assert mutation_check._scope_to_changed(_SPECS, "origin/main").blocks == {}


def test_root_conftest_widens_to_the_whole_catalogue(monkeypatch):
    """The root conftest owns the autouse fixtures every block's tests run under."""
    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: {"tests/conftest.py"})

    scope = mutation_check._scope_to_changed(_MUTATED_SPECS, "origin/main")

    assert scope.blocks == _MUTATED_SPECS
    assert scope.runner_self_test is False


# --- a runner change: its own tests plus one mutant per block ---------------
#
# Forcing the whole catalogue made the v8 release PR (which edits the runner)
# blow the CI step's 20 minutes. A runner bug is uniform -- a lost PYTHONPATH or
# a broken copy breaks every block alike -- so one mutant per block, through
# every source and every test list, is enough to see it; the nightly --all
# still runs everything.

_MUTATED_SPECS = {
    name: {
        **spec,
        "mutations": [
            {"id": f"{name}-first", "description": "", "find": "a", "replace": "b"},
            {"id": f"{name}-second", "description": "", "find": "c", "replace": "d"},
        ],
    }
    for name, spec in _SPECS.items()
}


def test_runner_change_samples_the_first_mutation_of_every_block(monkeypatch):
    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: {"scripts/mutation_check.py"})

    scope = mutation_check._scope_to_changed(_MUTATED_SPECS, "origin/main")

    assert scope.runner_self_test is True
    assert list(scope.blocks) == ["mask_capture", "weight_manager"]
    assert {name: [m["id"] for m in spec["mutations"]] for name, spec in scope.blocks.items()} == {
        "mask_capture": ["mask_capture-first"],
        "weight_manager": ["weight_manager-first"],
    }
    # The sample is a view: the catalogue the nightly run reads is left whole.
    assert len(_MUTATED_SPECS["mask_capture"]["mutations"]) == 2


def test_runner_change_keeps_blocks_the_diff_selects_whole(monkeypatch):
    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"scripts/mutation_check.py", "src/zebtrack/core/services/weight_manager.py"},
    )

    scope = mutation_check._scope_to_changed(_MUTATED_SPECS, "origin/main")

    assert scope.blocks["weight_manager"] == _MUTATED_SPECS["weight_manager"]
    assert len(scope.blocks["mask_capture"]["mutations"]) == 1


def test_untouched_runner_runs_no_self_test(monkeypatch):
    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"src/zebtrack/core/services/weight_manager.py"},
    )

    scope = mutation_check._scope_to_changed(_MUTATED_SPECS, "origin/main")

    assert scope.runner_self_test is False
    assert list(scope.blocks) == ["weight_manager"]


def test_failing_runner_self_test_stops_before_any_mutant(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("the runner's tests failed; no verdict may be produced")

    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: {"scripts/mutation_check.py"})
    monkeypatch.setattr(mutation_check, "_run_runner_self_test", lambda: False)
    monkeypatch.setattr(mutation_check, "_run_blocks", explode)
    monkeypatch.setattr(sys, "argv", ["mutation_check.py", "--changed-since", "origin/main"])

    assert mutation_check.main() == 2


def test_runner_self_test_reads_pytest_outcomes(monkeypatch):
    seen: list[tuple[list[str], Path]] = []

    def fake_pytest(paths, root, *, basetemp=None):
        seen.append((paths, root))
        return answers.pop(0)

    answers = [(0, 12, "12 passed"), (1, 11, "1 failed, 11 passed"), (0, 0, "no tests ran")]
    monkeypatch.setattr(mutation_check, "_run_pytest", fake_pytest)

    assert mutation_check._run_runner_self_test() is True
    assert mutation_check._run_runner_self_test() is False
    # Nothing collected is not a pass: a moved test file must not wave the runner through.
    assert mutation_check._run_runner_self_test() is False
    # It runs in the checkout: its tests diff against the real .git.
    assert seen[0] == (
        [str(mutation_check.REPO_ROOT / "tests/quality/test_mutation_check.py")],
        mutation_check.REPO_ROOT,
    )


# --- catalogue edits: only the blocks that changed --------------------------
#
# Every front appends its own blocks to the catalogue, so "catalogue touched ->
# run everything" re-ran ~110 mutations (tens of minutes) for a change that
# added a dozen. A block that did not change, guarding a module the diff did
# not touch, cannot change its verdict; the nightly ``--all`` still runs it.

_CATALOG = "scripts/mutation_catalog.yaml"


def _with_base_catalogue(monkeypatch, changed: set[str], base: dict | None) -> None:
    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: changed)
    monkeypatch.setattr(mutation_check, "_base_catalog_modules", lambda ref: base)


def test_new_catalogue_block_selects_only_that_block(monkeypatch):
    _with_base_catalogue(monkeypatch, {_CATALOG}, {"weight_manager": _SPECS["weight_manager"]})

    assert list(mutation_check._scope_to_changed(_SPECS, "origin/main").blocks) == ["mask_capture"]


def test_edited_catalogue_block_selects_that_block(monkeypatch):
    base = {
        "mask_capture": {**_SPECS["mask_capture"], "mutations": [{"id": "old"}]},
        "weight_manager": _SPECS["weight_manager"],
    }
    current = {
        "mask_capture": {**_SPECS["mask_capture"], "mutations": [{"id": "new"}]},
        "weight_manager": _SPECS["weight_manager"],
    }
    _with_base_catalogue(monkeypatch, {_CATALOG}, base)

    assert list(mutation_check._scope_to_changed(current, "origin/main").blocks) == ["mask_capture"]


def test_catalogue_blocks_and_touched_files_are_united(monkeypatch):
    _with_base_catalogue(
        monkeypatch,
        {_CATALOG, "src/zebtrack/core/services/weight_manager.py"},
        {"weight_manager": _SPECS["weight_manager"]},
    )

    assert set(mutation_check._scope_to_changed(_SPECS, "origin/main").blocks) == {
        "mask_capture",
        "weight_manager",
    }


def test_removing_a_block_selects_nothing_from_the_catalogue(monkeypatch):
    """A deleted block has nothing left to run; the remaining ones are unchanged."""
    _with_base_catalogue(
        monkeypatch, {_CATALOG}, {**_SPECS, "gone": {"source": "x.py", "tests": []}}
    )

    assert mutation_check._scope_to_changed(_SPECS, "origin/main").blocks == {}


def test_unreadable_base_catalogue_widens_to_everything(monkeypatch):
    """Degrade towards running too much, never towards running nothing."""
    _with_base_catalogue(monkeypatch, {_CATALOG}, None)

    assert mutation_check._scope_to_changed(_SPECS, "origin/main").blocks == _SPECS


def test_runner_change_and_catalogue_edit_combine(monkeypatch):
    """The edited block runs whole; the runner change samples every other block."""
    base = {
        "mask_capture": {**_MUTATED_SPECS["mask_capture"], "mutations": []},
        "weight_manager": _MUTATED_SPECS["weight_manager"],
    }
    _with_base_catalogue(monkeypatch, {_CATALOG, "scripts/mutation_check.py"}, base)

    scope = mutation_check._scope_to_changed(_MUTATED_SPECS, "origin/main")

    assert scope.blocks["mask_capture"] == _MUTATED_SPECS["mask_capture"]
    assert len(scope.blocks["weight_manager"]["mutations"]) == 1
    assert scope.runner_self_test is True


# --- _base_catalog_modules: reading the catalogue the branch started from ----


def _catalogue_yaml(modules: dict) -> str:
    return yaml.safe_dump({"modules": modules})


def test_base_catalogue_is_read_at_the_merge_base(monkeypatch):
    calls: list[tuple[str, ...]] = []
    responses = {
        ("merge-base", "origin/main", "HEAD"): (0, "abc123\n"),
        ("show", f"abc123:{_CATALOG}"): (0, _catalogue_yaml(_SPECS)),
    }
    monkeypatch.setattr(mutation_check, "_git", _git_stub(responses, calls))

    assert mutation_check._base_catalog_modules("origin/main") == _SPECS
    assert ("show", f"abc123:{_CATALOG}") in calls


def test_base_catalogue_falls_back_to_the_ref_without_a_merge_base(monkeypatch):
    """Shallow clone: no merge base, but the ref itself may still be readable."""
    responses = {
        ("merge-base", "HEAD^", "HEAD"): (1, ""),
        ("show", f"HEAD^:{_CATALOG}"): (0, _catalogue_yaml(_SPECS)),
    }
    monkeypatch.setattr(mutation_check, "_git", _git_stub(responses, []))

    assert mutation_check._base_catalog_modules("HEAD^") == _SPECS


@pytest.mark.parametrize(
    "show_answer",
    [(128, ""), (0, "modules: [unclosed"), (0, "not_modules: {}\n"), (0, "- a list\n")],
)
def test_unusable_base_catalogue_is_none(monkeypatch, show_answer):
    responses = {
        ("merge-base", "origin/main", "HEAD"): (0, "abc123\n"),
        ("show", f"abc123:{_CATALOG}"): show_answer,
        ("show", f"origin/main:{_CATALOG}"): show_answer,
    }
    monkeypatch.setattr(mutation_check, "_git", _git_stub(responses, []))

    assert mutation_check._base_catalog_modules("origin/main") is None


def test_real_repository_reads_its_own_base_catalogue():
    modules = mutation_check._base_catalog_modules("HEAD")

    assert isinstance(modules, dict) and modules


def test_unknown_diff_widens_to_the_whole_catalogue(monkeypatch):
    """Degrade towards running too much, never towards running nothing."""
    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: None)

    assert mutation_check._scope_to_changed(_SPECS, "origin/main").blocks == _SPECS


# --- main(): the CLI contract CI depends on ---------------------------------


def test_module_and_changed_since_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["mutation_check.py", "--module", "mask_capture", "--changed-since", "HEAD^"]
    )

    assert mutation_check.main() == 2


def test_empty_scope_exits_clean_without_running_anything(monkeypatch, tmp_path):
    """Zero affected modules is success, with no copy built and no pytest started."""

    def explode(*args, **kwargs):
        raise AssertionError("no module is affected; nothing should have been checked")

    monkeypatch.setattr(mutation_check, "_changed_paths", lambda ref: {"docs/INDEX.md"})
    monkeypatch.setattr(mutation_check, "_run_blocks", explode)
    monkeypatch.setattr(mutation_check, "_run_pytest", explode)

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

    def record(selected: dict, **kwargs) -> list[mutation_check.ModuleReport]:
        checked.extend(selected)
        return [mutation_check.ModuleReport(name=name) for name in selected]

    monkeypatch.setattr(
        mutation_check,
        "_changed_paths",
        lambda ref: {"src/zebtrack/core/services/external_trigger_gate.py"},
    )
    monkeypatch.setattr(mutation_check, "_run_blocks", record)
    monkeypatch.setattr(sys, "argv", ["mutation_check.py", "--changed-since", "origin/main"])

    assert mutation_check.main() == 0
    assert checked == ["external_trigger_gate"]


@pytest.mark.parametrize(
    ("reports", "expected"),
    [
        ([], 0),
        ([mutation_check.ModuleReport("a", [_result(killed=True)])], 0),
        ([mutation_check.ModuleReport("a", [_result(killed=False)])], 1),
        # A red baseline proves nothing about its block. It used to be a "skip"
        # that left the exit code at 0 -- so a runner that broke every pytest
        # would have reported a clean run with a score of 0/0.
        ([mutation_check.ModuleReport("a", baseline_failed=True)], 2),
        (
            [
                mutation_check.ModuleReport("a", [_result(killed=False)]),
                mutation_check.ModuleReport("b", baseline_failed=True),
            ],
            2,
        ),
        # Legitimate skips (nothing to run) do not fail the run.
        ([mutation_check.ModuleReport("a", skipped_reason="no mutations defined yet")], 0),
    ],
)
def test_exit_code(reports, expected):
    assert mutation_check._exit_code(reports) == expected


def test_jobs_must_be_positive(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["mutation_check.py", "--all", "--jobs", "0"])

    with pytest.raises(SystemExit) as excinfo:
        mutation_check.main()

    assert excinfo.value.code == 2
    assert "--jobs" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("cpus", "memory_gib", "expected"),
    [
        (14, 12.0, 8),  # this machine: RAM, not cores, is the limit
        (4, 14.0, 4),  # a GitHub runner: cores are
        (8, 1.0, 1),  # never zero workers
        (None, 64.0, 1),  # cpu_count() may answer None
    ],
)
def test_default_jobs_is_bounded_by_cores_and_free_ram(cpus, memory_gib, expected):
    jobs = mutation_check._default_jobs(
        cpu_count=lambda: cpus, available_memory=lambda: int(memory_gib * 1024**3)
    )

    assert jobs == expected


def test_default_jobs_without_psutil_uses_the_cores():
    assert mutation_check._default_jobs(cpu_count=lambda: 6, available_memory=lambda: None) == 6


def test_jobs_reach_the_scheduler(monkeypatch):
    seen: dict = {}

    def record(selected: dict, **kwargs) -> list[mutation_check.ModuleReport]:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(mutation_check, "_run_blocks", record)
    monkeypatch.setattr(
        sys, "argv", ["mutation_check.py", "--module", "mask_capture", "--jobs", "3"]
    )

    assert mutation_check.main() == 0
    assert seen["jobs"] == 3


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


# --- isolation: mutants live in copies, never in the checkout ---------------
#
# Until v8 the runner patched the REAL file and restored it in a ``finally``.
# Killing the process between the two left the mutant on disk, twice in the v8
# cycle, restored by hand both times. These tests build a throwaway "checkout"
# whose package is named ``zebtrack`` on purpose: that name is what the main
# venv's ``drerio_logai.pth`` (and ``scripts/wt-env.sh``) resolve to the
# checkout, which is exactly the import a copy must win against.

_PROBE = "VALUE = 1\nNAME = 'probe'\n"

_PROBE_TESTS = """\
from pathlib import Path

import zebtrack.probe as probe


def test_value_is_one():
    assert probe.VALUE == 1


def test_probe_is_imported_from_the_directory_pytest_runs_in():
    assert Path(probe.__file__).resolve().is_relative_to(Path.cwd().resolve())
"""


def _fake_checkout(root: Path, modules: dict[str, str] | None = None) -> Path:
    """A minimal tree shaped like this repository, outside of it."""
    package = root / "src" / "zebtrack"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, body in (modules or {"probe": _PROBE}).items():
        (package / f"{name}.py").write_bytes(body.encode())
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "probe.cpython-312.pyc").write_bytes(b"stale")
    (root / "tests").mkdir()
    (root / "tests" / "test_probe.py").write_bytes(_PROBE_TESTS.encode())
    (root / "scripts").mkdir()
    (root / "scripts" / "helper.py").write_bytes(b"")
    (root / "config.yaml").write_bytes(b"camera: {}\n")
    (root / "weights").mkdir()
    (root / "weights" / "big.pt").write_bytes(b"not copied")
    return root


def _probe_spec(*mutations: tuple[str, str, str]) -> dict:
    return {
        "source": "src/zebtrack/probe.py",
        "tests": ["tests/test_probe.py"],
        "mutations": [
            {"id": mid, "description": f"{find} -> {replace}", "find": find, "replace": replace}
            for mid, find, replace in mutations
        ],
    }


def _run(selected: dict, checkout: Path, scratch: Path, *, jobs: int = 1):
    scratch.mkdir(exist_ok=True)
    return mutation_check._run_blocks(
        selected,
        jobs=jobs,
        verbose=False,
        snapshot=mutation_check._snapshot_sources(selected, checkout),
        source_root=checkout,
        tmp_root=scratch,
    )


def test_the_pytest_in_a_copy_imports_the_copy_not_the_checkout(tmp_path, monkeypatch):
    """The trap this isolation was built around, reproduced with real pytest runs.

    PYTHONPATH already names the checkout's ``src`` -- what ``wt-env.sh`` does,
    and what the venv's ``.pth`` does for the main repository. If the copy's
    ``src`` did not go in front of it, the pytest would import the unmutated
    checkout: the baseline's location check would fail, and the mutant would
    survive.
    """
    checkout = _fake_checkout(tmp_path / "checkout")
    monkeypatch.setenv("PYTHONPATH", str(checkout / "src"))
    spec = _probe_spec(("value", "VALUE = 1", "VALUE = 2"), ("name", "'probe'", "'other'"))

    [report] = _run({"probe": spec}, checkout, tmp_path / "scratch")

    assert report.baseline_failed is False, report.skipped_reason
    assert [(r.mutation_id, r.killed) for r in report.results] == [
        ("value", True),
        # NAME is asserted by nothing: a real survivor, proving "killed" above
        # came from the assertion and not from a pytest that could not start.
        ("name", False),
    ]
    assert (checkout / "src" / "zebtrack" / "probe.py").read_bytes() == _PROBE.encode()


def test_the_checkout_is_pristine_while_every_mutant_runs(tmp_path, monkeypatch):
    checkout = _fake_checkout(tmp_path / "checkout")
    real_source = checkout / "src" / "zebtrack" / "probe.py"
    observed: list[tuple[bytes, bytes, Path | None]] = []

    def fake_pytest(paths, root, *, basetemp=None):
        assert all(Path(path).is_relative_to(root) for path in paths)
        copy = (root / "src" / "zebtrack" / "probe.py").read_bytes()
        observed.append((real_source.read_bytes(), copy, basetemp))
        is_baseline = len(observed) == 1
        return (0, 2, "2 passed") if is_baseline else (1, 1, "1 failed, 1 passed")

    monkeypatch.setattr(mutation_check, "_run_pytest", fake_pytest)
    scratch = tmp_path / "scratch"

    [report] = _run(
        {"probe": _probe_spec(("value", "VALUE = 1", "VALUE = 2"), ("name", "'probe'", "'x'"))},
        checkout,
        scratch,
    )

    assert [r.killed for r in report.results] == [True, True]
    assert [entry[0] for entry in observed] == [_PROBE.encode()] * 3
    assert [entry[1] for entry in observed] == [
        _PROBE.encode(),
        _PROBE.replace("VALUE = 1", "VALUE = 2").encode(),
        _PROBE.replace("'probe'", "'x'").encode(),
    ]
    # Concurrent pytests must not share pytest-of-<user>: the basetemp is the copy's own.
    assert all(entry[2] is not None and entry[2].is_relative_to(scratch) for entry in observed)


def test_killing_the_runner_mid_mutant_leaves_nothing_behind(tmp_path, monkeypatch):
    """Ctrl-C (or a CI timeout) during a mutant: checkout intact, copies gone."""
    checkout = _fake_checkout(tmp_path / "checkout")
    calls = {"n": 0}

    def interrupted(paths, root, *, basetemp=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return 0, 2, "2 passed"
        assert b"VALUE = 2" in (root / "src" / "zebtrack" / "probe.py").read_bytes()
        raise KeyboardInterrupt

    monkeypatch.setattr(mutation_check, "_run_pytest", interrupted)
    scratch = tmp_path / "scratch"

    with pytest.raises(KeyboardInterrupt):
        _run({"probe": _probe_spec(("value", "VALUE = 1", "VALUE = 2"))}, checkout, scratch)

    assert calls["n"] == 2
    assert (checkout / "src" / "zebtrack" / "probe.py").read_bytes() == _PROBE.encode()
    assert list(scratch.iterdir()) == []


def test_red_baseline_runs_no_mutant_and_marks_the_block(tmp_path, monkeypatch, capsys):
    checkout = _fake_checkout(tmp_path / "checkout")
    calls: list[bytes] = []

    def red(paths, root, *, basetemp=None):
        calls.append((root / "src" / "zebtrack" / "probe.py").read_bytes())
        return 3, 1, "3 failed, 1 passed"

    monkeypatch.setattr(mutation_check, "_run_pytest", red)

    [report] = _run(
        {"probe": _probe_spec(("value", "VALUE = 1", "VALUE = 2"))}, checkout, tmp_path / "s"
    )

    assert calls == [_PROBE.encode()]
    assert report.baseline_failed is True
    assert report.results == []
    assert "SKIPPED: baseline is not green (3 failing)" in capsys.readouterr().out


def test_ambiguous_pattern_is_a_survivor_with_a_note_and_runs_no_pytest(tmp_path, monkeypatch):
    checkout = _fake_checkout(tmp_path / "checkout", {"probe": "A = 1\nB = 1\n"})
    calls = {"n": 0}

    def count(paths, root, *, basetemp=None):
        calls["n"] += 1
        return 0, 1, "1 passed"

    monkeypatch.setattr(mutation_check, "_run_pytest", count)

    [report] = _run({"probe": _probe_spec(("twice", "= 1", "= 2"))}, checkout, tmp_path / "s")

    assert calls["n"] == 1  # the baseline only
    [result] = report.results
    assert result.killed is False
    assert "exactly once" in result.note and "found 2" in result.note


# --- parallelism: same verdicts, same order, reused copies ------------------

_BLOCK_SOURCES = {f"m{i}": "A = 1\nB = 1\nC = 1\n" for i in range(3)}


def _three_blocks() -> dict:
    return {
        name: {
            "source": f"src/zebtrack/{name}.py",
            "tests": ["tests/test_probe.py"],
            "mutations": [
                {
                    "id": letter.lower(),
                    "description": f"{letter} flips",
                    "find": f"{letter} = 1",
                    "replace": f"{letter} = 2",
                }
                for letter in "ABC"
            ],
        }
        for name in _BLOCK_SOURCES
    }


def _scrambled_pytest(roots: set[Path]):
    """Answer like pytest would, after a delay that reorders completions.

    Every mutant is killed except ``m1``'s ``C``, so a result attributed to the
    wrong block or the wrong mutant changes the report.
    """
    lock = threading.Lock()

    def fake(paths, root, *, basetemp=None):
        with lock:
            roots.add(root)
        package = root / "src" / "zebtrack"
        mutated = [
            (name, text)
            for name in _BLOCK_SOURCES
            if "= 2" in (text := (package / f"{name}.py").read_text())
        ]
        assert len(mutated) <= 1, "two mutants applied to one copy at once"
        if not mutated:
            time.sleep(0.03)
            return 0, 4, "4 passed"
        name, text = mutated[0]
        # Later blocks and later mutants finish FIRST.
        time.sleep(0.01 * (9 - int(name[1]) * 3 - "ABC".index(text.split(" = 2")[0][-1])))
        survives = name == "m1" and "C = 2" in text
        return (0, 4, "4 passed") if survives else (2, 2, "2 failed, 2 passed")

    return fake


def test_parallel_run_reports_exactly_what_a_serial_run_does(tmp_path, monkeypatch, capsys):
    selected = _three_blocks()
    outputs: dict[int, str] = {}
    reports_json: dict[int, str] = {}
    roots_by_jobs: dict[int, set[Path]] = {}
    for jobs in (1, 4):
        checkout = _fake_checkout(tmp_path / f"checkout{jobs}", dict(_BLOCK_SOURCES))
        roots: set[Path] = set()
        monkeypatch.setattr(mutation_check, "_run_pytest", _scrambled_pytest(roots))
        reports = _run(selected, checkout, tmp_path / f"scratch{jobs}", jobs=jobs)
        outputs[jobs] = capsys.readouterr().out
        destination = tmp_path / f"report{jobs}.json"
        mutation_check._write_json(destination, reports)
        reports_json[jobs] = destination.read_text(encoding="utf-8")
        roots_by_jobs[jobs] = roots
        assert [r.name for r in reports] == ["m0", "m1", "m2"]

    assert outputs[4] == outputs[1]
    assert reports_json[4] == reports_json[1]
    report = json.loads(reports_json[1])
    assert report["score"] == {"killed": 8, "total": 9}
    assert [(r["module"], r["mutation"], r["killed"]) for r in report["results"]][3:6] == [
        ("m1", "a", True),
        ("m1", "b", True),
        ("m1", "c", False),
    ]
    # 12 pytest runs (3 baselines + 9 mutants) on at most 4 copies: copies are reused.
    assert len(roots_by_jobs[1]) == 1
    assert 1 < len(roots_by_jobs[4]) <= 4


# --- the pieces the isolation is made of ------------------------------------


def test_workspace_holds_the_code_tests_and_root_files_but_not_the_rest(tmp_path):
    checkout = _fake_checkout(tmp_path / "checkout")
    (checkout / ".git").mkdir()
    (checkout / ".git" / "HEAD").write_bytes(b"ref: x")

    workspace = mutation_check._build_workspace(checkout, tmp_path / "ws")

    copied = {p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()}
    assert copied == {
        "config.yaml",
        "scripts/helper.py",
        "src/zebtrack/__init__.py",
        "src/zebtrack/probe.py",
        "tests/test_probe.py",
    }


def test_pytest_env_puts_the_copys_src_first_and_keeps_the_rest(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", "elsewhere")

    env = mutation_check._pytest_env(tmp_path)

    assert env["PYTHONPATH"].split(os.pathsep) == [str(tmp_path / "src"), "elsewhere"]


def test_pytest_env_without_an_inherited_pythonpath(monkeypatch, tmp_path):
    monkeypatch.delenv("PYTHONPATH", raising=False)

    assert mutation_check._pytest_env(tmp_path)["PYTHONPATH"] == str(tmp_path / "src")


def test_mutated_restores_bytes_and_drops_stale_bytecode_even_on_error(tmp_path):
    source = tmp_path / "probe.py"
    source.write_bytes(b"VALUE = 1\r\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "probe.cpython-312.pyc").write_bytes(b"old")
    (cache / "other.cpython-312.pyc").write_bytes(b"keep")

    with pytest.raises(RuntimeError, match="inside"):
        with mutation_check._mutated(source, b"VALUE = 1\r\n", "VALUE = 1", "VALUE = 2"):
            assert source.read_bytes() == b"VALUE = 2\r\n"
            assert not (cache / "probe.cpython-312.pyc").exists()
            (cache / "probe.cpython-312.pyc").write_bytes(b"compiled from the mutant")
            raise RuntimeError("inside")

    assert source.read_bytes() == b"VALUE = 1\r\n"
    assert not (cache / "probe.cpython-312.pyc").exists()
    assert (cache / "other.cpython-312.pyc").read_bytes() == b"keep"


def test_a_copy_that_drifted_from_the_checkout_stops_the_run(tmp_path):
    source = tmp_path / "probe.py"
    source.write_bytes(b"VALUE = 2\n")  # a previous mutant that was never restored

    with pytest.raises(mutation_check.UntrustedRunError, match="no longer matches"):
        with mutation_check._mutated(source, b"VALUE = 1\n", "VALUE = 2", "VALUE = 3"):
            pytest.fail("a mutant must not be applied on top of a drifted copy")

    assert source.read_bytes() == b"VALUE = 2\n"


def test_tree_changes_reports_only_what_moved_since_the_snapshot(tmp_path):
    checkout = _fake_checkout(tmp_path / "checkout", {"probe": _PROBE, "other": "X = 1\n"})
    selected = {
        "probe": _probe_spec(),
        "other": {**_probe_spec(), "source": "src/zebtrack/other.py"},
    }
    snapshot = mutation_check._snapshot_sources(selected, checkout)

    assert mutation_check._tree_changes(snapshot, checkout) == []

    (checkout / "src" / "zebtrack" / "other.py").write_bytes(b"X = 2\n")
    assert mutation_check._tree_changes(snapshot, checkout) == ["src/zebtrack/other.py"]


@pytest.mark.parametrize("error", [mutation_check.UntrustedRunError("drifted"), OSError("full")])
def test_an_untrustworthy_run_exits_2(monkeypatch, error):
    def fail(selected: dict, **kwargs):
        raise error

    monkeypatch.setattr(mutation_check, "_run_blocks", fail)
    monkeypatch.setattr(
        sys, "argv", ["mutation_check.py", "--module", "mask_capture", "--jobs", "1"]
    )

    assert mutation_check.main() == 2


def test_a_copy_whose_pytest_would_import_the_checkout_stops_the_run(tmp_path, monkeypatch):
    """The runtime half of the PYTHONPATH guarantee, checked once per copy.

    Here the copy's ``src`` is NOT put first, as if a meta-path finder or a lost
    prepend sent ``import zebtrack`` to the checkout. The run must refuse to
    start, not produce verdicts about code nobody mutated.
    """
    checkout = _fake_checkout(tmp_path / "checkout")
    monkeypatch.setenv("PYTHONPATH", str(checkout / "src"))
    monkeypatch.setattr(mutation_check, "_pytest_env", lambda root: dict(os.environ))
    monkeypatch.setattr(
        mutation_check,
        "_run_pytest",
        lambda *a, **k: pytest.fail("no pytest may run in a copy that imports the checkout"),
    )

    with pytest.raises(mutation_check.UntrustedRunError, match="imports zebtrack from"):
        _run({"probe": _probe_spec(("value", "VALUE = 1", "VALUE = 2"))}, checkout, tmp_path / "s")

    assert (checkout / "src" / "zebtrack" / "probe.py").read_bytes() == _PROBE.encode()


def test_the_import_probe_accepts_a_copy_that_imports_itself(tmp_path):
    workspace = _fake_checkout(tmp_path / "copy")

    mutation_check._verify_import_origin(workspace)
