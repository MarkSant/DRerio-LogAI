#!/usr/bin/env python3
"""Prove the test suite can fail: break the code on purpose and check it notices.

Coverage says a line RAN. It never says an assertion would have caught the line
being wrong. An audit of PRs #482-#509 found four test files whose 30 tests
executed ``weight_manager`` end to end and killed 0 of 5 deliberate defects --
100 % of the lines, 0 % of the behaviour.

This runner applies the curated defects in ``scripts/mutation_catalog.yaml`` one
at a time and reports which ones the suite fails to notice. A SURVIVOR is a hole
in the tests, not a bug in the code.

Every mutant is applied to a private COPY of the tree, never to the checkout:
killing the runner at any moment leaves nothing mutated on disk. Copies are made
once per worker and reused, and ``--jobs`` workers run side by side; the output
and the JSON report are still in catalogue order, whatever finishes first.

Usage::

    python scripts/mutation_check.py --all
    python scripts/mutation_check.py --all --jobs 4
    python scripts/mutation_check.py --changed-since origin/main
    python scripts/mutation_check.py --module mask_capture
    python scripts/mutation_check.py --list
    python scripts/mutation_check.py --all --json report.json

Exit codes: 0 = every mutation killed, 1 = at least one survivor, 2 = the run
could not be trusted (red baseline, runner self-tests failing, the checkout
changed under the run, a copy that could not be restored).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "scripts" / "mutation_catalog.yaml"

# pytest prints "3 failed, 12 passed in 4.20s". Coverage totals and rerun lines
# also contain numbers, so anchor on the words pytest uses for outcomes.
_OUTCOME_RE = re.compile(r"(\d+) (passed|failed|error|errors)")

# Touching this invalidates the file-to-module reasoning ``--changed-since`` is
# built on, so the scope widens back to the whole catalogue: the root conftest
# owns the autouse fixtures every module's tests run under, and one neutered
# fixture can hide a defect in a module the diff never named. Unlike the runner
# (below), a fixture change can affect each block differently, so a sample of
# blocks says nothing about the blocks left out.
_SCOPE_FORCING_PATHS = frozenset({"tests/conftest.py"})

# The runner itself is NOT scope-forcing any more. Its failure modes are
# uniform -- a broken copy, a lost PYTHONPATH, a mis-parsed pytest summary hit
# every block alike -- so they are caught by its own tests plus ONE mutant per
# block (each block's first, ``mutations[0]``), which still drives every source
# file and every test list in the catalogue through the new code. Forcing the
# full catalogue made every runner PR pay ~400 pytest processes; the nightly
# ``--all`` still runs every mutant of every block.
_RUNNER_REL = "scripts/mutation_check.py"
_RUNNER_TESTS = ("tests/quality/test_mutation_check.py",)

# The catalogue itself is scoped BLOCK by block: a change to it selects the
# blocks that were added or edited against the base. Every v8 front appends its
# own blocks, and "catalogue touched -> run all" re-ran ~110 mutations for a
# change that added a dozen. If the base catalogue cannot be read the scope
# widens to everything, as for any other question git cannot answer.
_CATALOG_REL = "scripts/mutation_catalog.yaml"

# What a worker's copy contains: these directories plus every regular file at
# the repository root (pytest.ini, pyproject.toml, config.yaml, a local
# config.local.yaml ...). ``zebtrack.paths`` derives the project root from the
# package location, so the copy is self-consistent: the code under test reads
# the copy's config and writes its logs into the copy. A catalogued test that
# reads a directory missing here shows up as a red baseline (exit 2), never as
# a silent pass.
_WORKSPACE_DIRS = ("src", "tests", "scripts", "resources")
_WORKSPACE_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".hypothesis", ".mypy_cache", ".ruff_cache"
)

# A pytest process that imports torch/ultralytics peaks between 1 and 1.5 GB.
_BYTES_PER_JOB = int(1.5 * 1024**3)


class UntrustedRunError(RuntimeError):
    """The run cannot vouch for its verdicts -- exit 2, never 0 or 1."""


@dataclass
class MutationResult:
    module: str
    mutation_id: str
    description: str
    killed: bool
    failures: int
    note: str = ""


@dataclass
class ModuleReport:
    name: str
    results: list[MutationResult] = field(default_factory=list)
    skipped_reason: str = ""
    # A red baseline is not a legitimate skip: the block was selected and
    # nothing about it was proven. It turns the run's exit code into 2.
    baseline_failed: bool = False

    @property
    def survivors(self) -> list[MutationResult]:
        return [r for r in self.results if not r.killed]


@dataclass
class Scope:
    """What ``--changed-since`` decided to run.

    ``blocks`` maps block name to its spec, in catalogue order; a sampled block's
    spec carries only its first mutation. ``runner_self_test`` asks for the
    runner's own tests before any mutant runs.
    """

    blocks: dict[str, Any]
    runner_self_test: bool = False


# --- running pytest ---------------------------------------------------------


def _pytest_env(root: Path) -> dict[str, str]:
    """The environment a pytest of ``root`` must run under.

    ``root/src`` goes FIRST on ``PYTHONPATH``. The main venv resolves
    ``zebtrack`` through ``site-packages/drerio_logai.pth``, an ABSOLUTE path to
    the main repository's ``src/``, and ``scripts/wt-env.sh`` adds the worktree's
    own ``src/`` on top. Without this prepend a pytest started inside a copy
    would import one of those -- the unmutated code -- and every verdict would be
    about the wrong file.
    """
    env = dict(os.environ)
    inherited = env.get("PYTHONPATH", "")
    src = str(root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + inherited if inherited else "")
    return env


def _run_pytest(
    test_paths: list[str], root: Path, *, basetemp: Path | None = None
) -> tuple[int, int, str]:
    """Run pytest on ``test_paths`` inside ``root``; return (failures, passes, output).

    ``--no-cov`` is not optional. The coverage gate used to live in the
    ``addopts`` of pytest.ini, which made pytest exit non-zero on EVERY partial
    run -- so an exit-code-based runner reported all mutations killed and the
    whole check was worthless. That is why this parses outcome counts instead of
    trusting the exit status, even now that the gate has moved to CI.

    ``basetemp`` gives concurrent pytest processes disjoint temporary trees:
    the shared default (``pytest-of-<user>``) prunes old numbered directories,
    and one worker could delete another's ``tmp_path`` mid-test.
    """
    command = [sys.executable, "-m", "pytest", *test_paths, "-q", "--no-cov", "-p", "no:randomly"]
    if basetemp is not None:
        command.append(f"--basetemp={basetemp}")
    completed = subprocess.run(
        command,
        cwd=root,
        env=_pytest_env(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    failures = 0
    passes = 0
    for count, word in _OUTCOME_RE.findall(output):
        if word == "passed":
            passes = int(count)
        else:
            failures += int(count)
    return failures, passes, output


# --- the copies the mutants live in -----------------------------------------


def _build_workspace(source_root: Path, dest: Path) -> Path:
    """Copy what the catalogued tests need from ``source_root`` into ``dest``."""
    dest.mkdir(parents=True, exist_ok=False)
    for entry in source_root.iterdir():
        if entry.is_file():
            shutil.copy2(entry, dest / entry.name)
    for name in _WORKSPACE_DIRS:
        directory = source_root / name
        if directory.is_dir():
            shutil.copytree(directory, dest / name, ignore=_WORKSPACE_IGNORE)
    return dest


_IMPORT_PROBE = (
    "import importlib.util as u; spec = u.find_spec('zebtrack'); "
    "print(spec.origin if spec and spec.origin else '')"
)


def _verify_import_origin(workspace: Path) -> None:
    """Prove a pytest started in ``workspace`` resolves ``zebtrack`` to the copy.

    ``_pytest_env`` handles the ``.pth`` and the inherited PYTHONPATH, but an
    editable install through a meta-path finder (setuptools' newer mode) is
    consulted BEFORE ``sys.path`` and would win anyway. Asking the interpreter
    once per copy costs a fraction of a second and turns that case into exit 2
    instead of a run of verdicts about the unmutated checkout.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=workspace,
        env=_pytest_env(workspace),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    origin = completed.stdout.strip()
    if not origin or not Path(origin).resolve().is_relative_to((workspace / "src").resolve()):
        raise UntrustedRunError(
            f"a pytest in {workspace} imports zebtrack from {origin or 'nowhere'}, not from "
            "the copy -- every verdict would be about the unmutated code"
        )


class _WorkspacePool:
    """One copy per worker thread, built on first use and reused afterwards.

    A copy is ~1000 files; rebuilding it per mutant would cost more than some
    of the pytest runs it hosts. Reuse is safe because a mutant is always
    restored -- and verified against the checkout's bytes -- before the next one.
    """

    def __init__(self, source_root: Path, parent: Path) -> None:
        self._source_root = source_root
        self._parent = parent
        self._local = threading.local()
        self._lock = threading.Lock()
        self.built: list[Path] = []

    def get(self) -> Path:
        workspace: Path | None = getattr(self._local, "path", None)
        if workspace is None:
            with self._lock:
                workspace = self._parent / f"w{len(self.built)}"
                self.built.append(workspace)
            _build_workspace(self._source_root, workspace)
            _verify_import_origin(workspace)
            self._local.path = workspace
        return workspace


def _purge_bytecode(source: Path) -> None:
    """Drop ``source``'s cached bytecode so the next import compiles the file as it is now.

    CPython validates a ``.pyc`` by the source's mtime (whole seconds) and size.
    A mutant the same length as the original (``!=`` for ``==``) written and
    restored inside one second would otherwise be served from the cache -- the
    next run would test the previous mutant.
    """
    cache = source.parent / "__pycache__"
    if cache.is_dir():
        for compiled in cache.glob(f"{source.stem}.*.pyc"):
            compiled.unlink(missing_ok=True)


def _apply(source: Path, find: str, replace: str) -> bytes:
    """Patch ``source`` in place and return the ORIGINAL bytes for restoration.

    Only ever called on a worker's copy. Byte I/O, not text I/O, and
    deliberately so. ``read_text``/``write_text`` translate newlines: on Windows
    every restored file came back with CRLF where the repository stores LF.
    Round-tripping bytes keeps the file identical.

    Refuses an ambiguous patch: if ``find`` matches more than once, which
    occurrence got mutated would depend on file layout, and the result would not
    be reproducible across refactors.
    """
    original = source.read_bytes()
    # Match against the same newline convention the file actually uses.
    needle = find.encode("utf-8")
    if b"\r\n" in original:
        needle = needle.replace(b"\n", b"\r\n")
    occurrences = original.count(needle)
    if occurrences != 1:
        raise ValueError(
            f"pattern must appear exactly once in {source.name}, found {occurrences}:\n  {find!r}"
        )
    substitute = replace.encode("utf-8")
    if b"\r\n" in original:
        substitute = substitute.replace(b"\n", b"\r\n")
    source.write_bytes(original.replace(needle, substitute, 1))
    return original


@contextmanager
def _mutated(source: Path, pristine: bytes, find: str, replace: str) -> Iterator[None]:
    """Hold one mutant applied to a worker's copy of ``source``.

    ``pristine`` is the checkout's content, read when the run started. The copy
    must match it before the mutant goes in -- otherwise the previous mutant was
    not restored, or the checkout changed while the copy was being built, and
    every later verdict in this worker would be about the wrong code.
    """
    if source.read_bytes() != pristine:
        raise UntrustedRunError(
            f"{source} no longer matches the checkout -- a previous mutant was not "
            "restored, or the file was edited during the run"
        )
    original = _apply(source, find, replace)
    _purge_bytecode(source)
    try:
        yield
    finally:
        source.write_bytes(original)
        _purge_bytecode(source)


# --- scheduling --------------------------------------------------------------


@dataclass(frozen=True)
class _Task:
    block: str
    # None is the block's baseline; an int indexes ``spec["mutations"]``.
    index: int | None


@dataclass
class _Outcome:
    failures: int = 0
    passes: int = 0
    output: str = ""
    note: str = ""


def _execute(
    task: _Task,
    spec: dict[str, Any],
    test_paths: list[str],
    pristine: bytes,
    pool: _WorkspacePool,
) -> _Outcome:
    """Run one baseline or one mutant in the calling worker's copy."""
    workspace = pool.get()
    paths = [str(workspace / path) for path in test_paths]
    basetemp = workspace / ".bt"
    if task.index is None:
        failures, passes, output = _run_pytest(paths, workspace, basetemp=basetemp)
        return _Outcome(failures, passes, output)

    mutation = spec["mutations"][task.index]
    try:
        with _mutated(workspace / spec["source"], pristine, mutation["find"], mutation["replace"]):
            failures, passes, output = _run_pytest(paths, workspace, basetemp=basetemp)
    except ValueError as exc:
        return _Outcome(note=str(exc))
    return _Outcome(failures, passes, output)


def _prepare(name: str, spec: dict[str, Any], source_root: Path) -> tuple[ModuleReport, list[str]]:
    """Skip what cannot run, and list the test files that exist for what can."""
    report = ModuleReport(name=name)
    if not (source_root / spec["source"]).exists():
        report.skipped_reason = f"source not found: {spec['source']}"
        return report, []
    if not spec.get("mutations"):
        report.skipped_reason = "no mutations defined yet"
        return report, []
    test_paths = [t for t in spec["tests"] if (source_root / t).exists()]
    if not test_paths:
        report.skipped_reason = "none of the listed test files exist"
    return report, test_paths


def _snapshot_sources(selected: dict[str, Any], source_root: Path) -> dict[str, bytes]:
    """The checkout's bytes for every selected source, read before anything runs."""
    snapshot: dict[str, bytes] = {}
    for spec in selected.values():
        path = source_root / spec["source"]
        if path.is_file():
            snapshot[spec["source"]] = path.read_bytes()
    return snapshot


def _tree_changes(snapshot: dict[str, bytes], source_root: Path) -> list[str]:
    """Sources whose bytes in the checkout differ from the snapshot.

    Mutants never touch the checkout, so this should always be empty; it is the
    cheap proof. Comparing against the snapshot -- not ``git status`` -- keeps a
    developer's own uncommitted edit to a catalogued source from being reported
    as a leak, and works with an empty selection or outside a git checkout.
    """
    changed = []
    for rel, content in snapshot.items():
        path = source_root / rel
        if not path.is_file() or path.read_bytes() != content:
            changed.append(rel)
    return changed


def _print_block(
    report: ModuleReport,
    spec: dict[str, Any],
    test_paths: list[str],
    baseline: _Outcome,
    mutants: dict[int, _Outcome],
    *,
    verbose: bool,
) -> None:
    """Print one block's section and fill ``report`` -- always in catalogue order."""
    mutations = spec["mutations"]
    print(f"\n=== {report.name}  ({len(mutations)} mutations, {len(test_paths)} test files)")
    if baseline.failures:
        report.baseline_failed = True
        report.skipped_reason = (
            f"baseline is not green ({baseline.failures} failing) -- "
            "fix the suite before trusting mutation results"
        )
        if verbose:
            print(baseline.output)
        print(f"  SKIPPED: {report.skipped_reason}")
        return
    print(f"  baseline: {baseline.passes} passed")

    for index, mutation in enumerate(mutations):
        outcome = mutants[index]
        killed = not outcome.note and outcome.failures > 0
        result = MutationResult(
            module=report.name,
            mutation_id=mutation.get("id", "?"),
            description=mutation.get("description", ""),
            killed=killed,
            failures=outcome.failures,
            note=outcome.note,
        )
        if verbose and not killed and outcome.output:
            print(outcome.output)
        report.results.append(result)
        mark = "KILLED  " if result.killed else "SURVIVED"
        detail = f" ({result.failures} failing)" if result.killed else ""
        print(f"  {mark} {result.mutation_id}{detail} -- {result.description}")
        if result.note:
            print(f"           ! {result.note}")


def _run_blocks(
    selected: dict[str, Any],
    *,
    jobs: int,
    verbose: bool,
    snapshot: dict[str, bytes],
    source_root: Path = REPO_ROOT,
    tmp_root: Path | None = None,
) -> list[ModuleReport]:
    """Run every selected block on ``jobs`` workers; reports come back in catalogue order.

    Every block's baseline is queued first. A block's mutants are queued only
    once its baseline is green: a mutant "killed" by a suite that was already
    failing proves nothing. Sections are printed in catalogue order as soon as
    each one -- and every block before it -- is complete, so the log reads the
    same with one worker or twenty.
    """
    order = list(selected)
    reports: dict[str, ModuleReport] = {}
    tests: dict[str, list[str]] = {}
    for name, spec in selected.items():
        reports[name], tests[name] = _prepare(name, spec, source_root)

    baselines: dict[str, _Outcome] = {}
    mutants: dict[str, dict[int, _Outcome]] = {name: {} for name in order}

    def complete(name: str) -> bool:
        if reports[name].skipped_reason:
            return True
        baseline = baselines.get(name)
        if baseline is None:
            return False
        return bool(baseline.failures) or len(mutants[name]) == len(selected[name]["mutations"])

    printed = 0

    def flush() -> None:
        nonlocal printed
        while printed < len(order) and complete(order[printed]):
            name = order[printed]
            if not reports[name].skipped_reason:
                _print_block(
                    reports[name],
                    selected[name],
                    tests[name],
                    baselines[name],
                    mutants[name],
                    verbose=verbose,
                )
            printed += 1
        sys.stdout.flush()

    with tempfile.TemporaryDirectory(
        prefix="mc_", dir=tmp_root, ignore_cleanup_errors=True
    ) as scratch:
        pool = _WorkspacePool(source_root, Path(scratch))
        executor = ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="mutation")
        pending: dict[Future[_Outcome], _Task] = {}

        def submit(task: _Task) -> None:
            spec = selected[task.block]
            future = executor.submit(
                _execute, task, spec, tests[task.block], snapshot[spec["source"]], pool
            )
            pending[future] = task

        try:
            for name in order:
                if not reports[name].skipped_reason:
                    submit(_Task(name, None))
            flush()
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    task = pending.pop(future)
                    outcome = future.result()
                    if task.index is None:
                        baselines[task.block] = outcome
                        if not outcome.failures:
                            for index in range(len(selected[task.block]["mutations"])):
                                submit(_Task(task.block, index))
                    else:
                        mutants[task.block][task.index] = outcome
                flush()
        finally:
            # On an error or Ctrl-C: drop what has not started, wait for what has
            # (each restores its copy on the way out), then remove the copies.
            executor.shutdown(wait=True, cancel_futures=True)

    return [reports[name] for name in order]


# --- selecting what to run ---------------------------------------------------


def _git(*args: str) -> tuple[int, str]:
    """Run git in the repository and return (exit code, stdout)."""
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode, completed.stdout


def _changed_paths(ref: str) -> set[str] | None:
    """Repo-relative paths this working tree changes against ``ref``.

    ``None`` means git could not answer -- an unfetched base on a shallow CI
    clone is the usual cause. The caller must then run everything: a scoped
    check that silently scopes itself to nothing is worse than no check, because
    it still reports success.

    Three dots first, so commits that landed on the base after the fork point do
    not drag in modules this branch never touched. Two dots is the shallow
    fallback: without the merge base git cannot subtract those commits, and
    over-selecting runs extra modules rather than skipping the one that matters.
    Uncommitted work is folded in so the flag is usable before the commit exists.
    """
    code, out = _git("diff", "--name-only", f"{ref}...HEAD")
    if code != 0:
        code, out = _git("diff", "--name-only", ref)
    if code != 0:
        return None

    paths = {line.strip() for line in out.splitlines() if line.strip()}

    status_code, status_out = _git("status", "--porcelain")
    if status_code == 0:
        for line in status_out.splitlines():
            entry = line[3:].strip()
            if not entry:
                continue
            # A rename reads "old -> new"; the new path is the one to match.
            paths.add(entry.split(" -> ")[-1].strip('"'))

    # git reports POSIX separators, but a status entry may arrive quoted on
    # Windows; normalise so comparison against the catalogue cannot miss.
    return {path.replace("\\", "/") for path in paths if path}


def _base_catalog_modules(ref: str) -> dict[str, Any] | None:
    """The catalogue's ``modules`` as they were where this branch started.

    Read at the merge base with ``ref`` (the same three-dot reasoning as
    ``_changed_paths``), falling back to ``ref`` itself on a shallow clone.
    ``None`` when git cannot show it or the file does not parse into a
    ``modules`` mapping -- the caller then runs everything.
    """
    candidates: list[str] = []
    code, out = _git("merge-base", ref, "HEAD")
    if code == 0 and out.strip():
        candidates.append(out.strip())
    candidates.append(ref)

    for rev in candidates:
        code, text = _git("show", f"{rev}:{_CATALOG_REL}")
        if code != 0:
            continue
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("modules"), dict):
            return None
        modules: dict[str, Any] = data["modules"]
        return modules
    return None


def _sample(spec: dict[str, Any]) -> dict[str, Any]:
    """The block reduced to its first mutation -- the sample a runner change runs."""
    return {**spec, "mutations": (spec.get("mutations") or [])[:1]}


def _scope_to_changed(specs: dict[str, Any], ref: str) -> Scope:
    """Narrow the catalogue to the modules a diff against ``ref`` can affect.

    A mutation only proves something about the module it patches, so a change
    touching neither a module's source nor its tests cannot change that module's
    verdict. Drift arriving through a shared dependency is what the nightly
    ``--all`` run in ``stress-tests.yml`` is for.

    A change to the runner adds its own tests and the first mutation of every
    block not already selected in full.
    """
    changed = _changed_paths(ref)
    if changed is None:
        print(f"changed-since: git cannot diff against {ref!r} -- running every module")
        return Scope(dict(specs))

    forcing = sorted(changed & _SCOPE_FORCING_PATHS)
    if forcing:
        print(f"changed-since: {', '.join(forcing)} changed -- running every module")
        return Scope(dict(specs))

    catalogue_blocks: set[str] = set()
    if _CATALOG_REL in changed:
        base = _base_catalog_modules(ref)
        if base is None:
            print(
                f"changed-since: {_CATALOG_REL} changed and its base version cannot be "
                "read -- running every module"
            )
            return Scope(dict(specs))
        catalogue_blocks = {name for name, spec in specs.items() if base.get(name) != spec}
        print(
            f"changed-since: {_CATALOG_REL} changed -- "
            f"{len(catalogue_blocks)} block(s) added or edited"
            + (f": {', '.join(sorted(catalogue_blocks))}" if catalogue_blocks else "")
        )

    runner_changed = _RUNNER_REL in changed
    selected: dict[str, Any] = {}
    sampled: list[str] = []
    for name, spec in specs.items():
        if name in catalogue_blocks or changed & {spec["source"], *spec["tests"]}:
            selected[name] = spec
        elif runner_changed:
            selected[name] = _sample(spec)
            sampled.append(name)

    full = [name for name in selected if name not in sampled]
    print(
        f"changed-since {ref}: {len(changed)} file(s) changed, "
        f"{len(full)}/{len(specs)} module(s) affected" + (f" -- {', '.join(full)}" if full else "")
    )
    if runner_changed:
        print(
            f"changed-since: {_RUNNER_REL} changed -- runner self-tests, plus the first "
            f"mutation of the {len(sampled)} other block(s)"
        )
    return Scope(selected, runner_self_test=runner_changed)


# --- the CLI -----------------------------------------------------------------


def _available_memory() -> int | None:
    """Free RAM in bytes, or None when psutil is not importable."""
    try:
        import psutil
    except ImportError:
        return None
    available: int = psutil.virtual_memory().available
    return available


def _default_jobs(
    cpu_count: Callable[[], int | None] = os.cpu_count,
    available_memory: Callable[[], int | None] = _available_memory,
) -> int:
    """One worker per core, capped by free RAM at ~1.5 GB per pytest with torch."""
    cpus = cpu_count() or 1
    memory = available_memory()
    if memory is None:
        return max(1, cpus)
    return max(1, min(cpus, memory // _BYTES_PER_JOB))


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _run_runner_self_test() -> bool:
    """The runner's own tests, in the checkout (they need its ``.git``)."""
    print(f"\n=== runner self-tests  ({', '.join(_RUNNER_TESTS)})")
    paths = [str(REPO_ROOT / path) for path in _RUNNER_TESTS]
    failures, passes, output = _run_pytest(paths, REPO_ROOT)
    if failures or not passes:
        print(output)
        print(f"  FAILED: {failures} failing, {passes} passed")
        return False
    print(f"  passed: {passes}")
    return True


def _print_summary(reports: list[ModuleReport]) -> None:
    total = sum(len(r.results) for r in reports)
    killed = sum(1 for r in reports for result in r.results if result.killed)
    survivors = [result for r in reports for result in r.survivors]

    print("\n" + "=" * 72)
    score = f"{killed}/{total}" if total else "0/0"
    percent = f" ({killed / total * 100:.0f}%)" if total else ""
    print(f"MUTATION SCORE: {score}{percent}")

    for report in reports:
        if report.skipped_reason:
            print(f"  skipped {report.name}: {report.skipped_reason}")

    if survivors:
        print(f"\n{len(survivors)} SURVIVOR(S) -- these defects ship undetected:")
        for result in survivors:
            print(f"  {result.module}::{result.mutation_id} -- {result.description}")
            if result.note:
                print(f"      {result.note}")
        print("\nEach survivor is a missing test. Add the test; do not delete the mutation.")


def _exit_code(reports: list[ModuleReport]) -> int:
    if any(report.baseline_failed for report in reports):
        return 2
    return 1 if any(report.survivors for report in reports) else 0


def _write_json(path: Path, reports: list[ModuleReport]) -> None:
    """Write the machine-readable report, including for an empty selection."""
    killed = sum(1 for report in reports for result in report.results if result.killed)
    total = sum(len(report.results) for report in reports)
    path.write_text(
        json.dumps(
            {
                "score": {"killed": killed, "total": total},
                "results": [
                    {
                        "module": result.module,
                        "mutation": result.mutation_id,
                        "description": result.description,
                        "killed": result.killed,
                        "note": result.note,
                    }
                    for report in reports
                    for result in report.results
                ],
                "skipped": {r.name: r.skipped_reason for r in reports if r.skipped_reason},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--all", action="store_true", help="run every module in the catalogue")
    parser.add_argument("--module", action="append", default=[], help="run one module (repeatable)")
    parser.add_argument(
        "--changed-since",
        metavar="REF",
        help="run only the modules whose source or tests differ from REF (implies --all)",
    )
    parser.add_argument(
        "--jobs",
        type=_positive_int,
        metavar="N",
        help="pytest processes to run at once (default: cores, capped at ~1.5 GB of free RAM each)",
    )
    parser.add_argument("--list", action="store_true", help="list the catalogue and exit")
    parser.add_argument("--json", type=Path, help="write a machine-readable report here")
    parser.add_argument("--verbose", action="store_true", help="print pytest output for survivors")
    args = parser.parse_args()

    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    specs: dict[str, Any] = catalog["modules"]

    if args.list:
        for name, spec in specs.items():
            mutations = spec.get("mutations") or []
            print(f"{name:32s} {len(mutations):2d} mutations  {spec['source']}")
            for mutation in mutations:
                print(f"    - {mutation['id']}: {mutation['description']}")
        return 0

    if args.module and args.changed_since:
        print("--module and --changed-since select differently; pass one", file=sys.stderr)
        return 2

    self_test = False
    if args.module:
        unknown = [m for m in args.module if m not in specs]
        if unknown:
            print(f"unknown module(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        selected = {m: specs[m] for m in args.module}
    elif args.changed_since:
        scope = _scope_to_changed(specs, args.changed_since)
        selected, self_test = scope.blocks, scope.runner_self_test
    elif args.all:
        selected = specs
    else:
        parser.print_help()
        return 2

    if self_test and not _run_runner_self_test():
        print("\n!! the runner's own tests fail -- its verdicts cannot be trusted", file=sys.stderr)
        return 2

    if not selected:
        # Not a silent pass: the line above already named the diff it looked at.
        print("nothing to mutate -- no catalogued module is affected by this change")
        if args.json:
            _write_json(args.json, [])
        return 0

    jobs = args.jobs or _default_jobs()
    print(f"jobs: {jobs}")
    snapshot = _snapshot_sources(selected, REPO_ROOT)
    try:
        reports = _run_blocks(selected, jobs=jobs, verbose=args.verbose, snapshot=snapshot)
    except (UntrustedRunError, OSError) as exc:
        # OSError: a copy could not be built or restored. Uncaught, it would exit
        # 1 -- the code that means "a survivor", not "this run proves nothing".
        print(f"\n!! the run cannot be trusted: {exc}", file=sys.stderr)
        return 2

    _print_summary(reports)

    changed = _tree_changes(snapshot, REPO_ROOT)
    if changed:
        # Mutants live in throwaway copies, so this is the checkout being edited
        # mid-run (the copies may hold either version) -- not a mutation leak.
        print(
            f"\n!! sources changed in the checkout during the run: {', '.join(changed)}",
            file=sys.stderr,
        )
        print("!! the verdicts may describe either version -- run again", file=sys.stderr)
        return 2

    if args.json:
        _write_json(args.json, reports)

    red = [report.name for report in reports if report.baseline_failed]
    if red:
        print(
            f"\n!! red baseline in {', '.join(red)} -- nothing about these blocks was proven",
            file=sys.stderr,
        )
    return _exit_code(reports)


if __name__ == "__main__":
    raise SystemExit(main())
