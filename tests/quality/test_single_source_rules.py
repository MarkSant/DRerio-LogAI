"""Mechanical single-source rules from ``CLAUDE.md`` (A4, TASK-087).

``CLAUDE.md`` names one place for several scientific decisions. Two of them are
mechanical enough for an AST scan, and both were broken in production before:

* **Counting animals** is ``count_subjects()`` / ``screen_subjects()`` in
  ``analysis/track_significance.py`` (#649, #671). A raw
  ``df["track_id"].nunique()`` counts a one-row ByteTrack glitch as a second
  animal; until F2-R-001 the live completion dialog did exactly that (A4-02).
  The scan flags ``nunique()``, ``factorize``, ``len(... .unique())`` and
  ``.ngroups`` whenever the expression mentions ``track_id``.
* **Zones in report contexts** come from ``get_multi_aquarium_zone_data()``;
  ``get_zone_data()`` is the aquarium-0 shim. Reading ROI names through it
  dropped every ROI of aquarium 1 from the unified report (A4-01). The scan
  covers the report-generation modules and flags every ``get_zone_data(`` call.

Each rule has an allowlist keyed by ``<path>::<enclosing function>`` with the
exact number of calls there and the reason it is the right answer. A new call,
a second call in an allowed function, or a call in a new function fails; an
entry whose calls are gone (or fewer) fails as stale. The lists only SHRINK.

Not built (2026-11-19): a rule for ``match.group(1)`` on a user regex outside
``core/services/pattern_match.py``. Of the ~20 ``.group(1)`` calls in ``src``,
almost all read fixed internal patterns (``Dia_(\\d+)``, ``aquarium_(\\d+)``),
and whether a pattern came from the user is a data-flow question an AST scan
cannot answer; the list would carry no signal.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"

Detector = Callable[[ast.AST], bool]

# --- rule (a): counting animals ----------------------------------------------

SUBJECT_COUNT_HOME = "src/zebtrack/analysis/track_significance.py"

ALLOWED_SUBJECT_COUNTS: dict[str, tuple[int, str]] = {
    "src/zebtrack/analysis/behavior.py::BehavioralAnalyzer._assign_track_labels": (
        1,
        "builds the POSITIONAL subject axis (labels, PR #457) of a trajectory that "
        "run_full_analysis already screened with screen_subjects; it labels rows, it "
        "does not report a count",
    ),
}

# --- rule (b): aquarium-0 zones in report contexts ---------------------------

REPORT_CONTEXT_PATHS = (
    "src/zebtrack/analysis/reporters",
    "src/zebtrack/coordinators/report_generation_coordinator.py",
    "src/zebtrack/coordinators/_unified_report_mixin.py",
    "src/zebtrack/core/recording/live_analysis_post_processor.py",
)

ALLOWED_ZONE_SHIM_CALLS: dict[str, tuple[int, str]] = {
    "src/zebtrack/coordinators/report_generation_coordinator.py"
    "::ReportGenerationCoordinator._generate_multi_aquarium_reports": (
        1,
        "fallback after get_multi_aquarium_zone_data(video_path) returned nothing",
    ),
    "src/zebtrack/coordinators/report_generation_coordinator.py"
    "::ReportGenerationCoordinator._generate_standard_report": (
        1,
        "single-aquarium report path: runs only when the video is not multi-aquarium, "
        "and passes video_path (A4-01)",
    ),
    "src/zebtrack/coordinators/report_generation_coordinator.py"
    "::ReportGenerationCoordinator._resolve_summary_zone_data": (
        1,
        "single-aquarium summary; falls back to the session folder's own "
        "2_AreasOfInterest parquet (A4-01)",
    ),
    "src/zebtrack/coordinators/_unified_report_mixin.py::UnifiedReportMixin._video_zone_sets": (
        1,
        "fallback after get_multi_aquarium_zone_data(path) has no aquariums (A4-01 fix)",
    ),
    "src/zebtrack/core/recording/live_analysis_post_processor.py"
    "::LiveAnalysisPostProcessorMixin._resolve_post_analysis_scale": (
        1,
        "uncalibrated live px/cm from the aquarium-0 arena, applied to every aquarium: "
        "valid while a project declares ONE tank size (aquarium_width_cm/height_cm) "
        "for all aquariums under one camera; recorded as A4-14",
    ),
    "src/zebtrack/core/recording/live_analysis_post_processor.py"
    "::LiveAnalysisPostProcessorMixin._on_session_complete._run_post_analysis": (
        1,
        "single-aquarium post-analysis branch; the multi branch returned before it "
        "and reads _resolve_live_multi_aquarium_zone_data",
    ),
    "src/zebtrack/core/recording/live_analysis_post_processor.py"
    "::LiveAnalysisPostProcessorMixin._start_recording_after_arena": (
        1,
        "fallback after _resolve_session_multi_zone_data() returned None (#635)",
    ),
}


# --- scanner -----------------------------------------------------------------


def _mentions_track_id(node: ast.AST | None) -> bool:
    if node is None:
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and sub.value == "track_id":
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == "track_id":
            return True
        if isinstance(sub, ast.Name) and sub.id in {"track_id", "track_ids"}:
            return True
    return False


def counts_subjects(node: ast.AST) -> bool:
    """True for an expression that counts distinct ``track_id`` values."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "nunique":
            return _mentions_track_id(func.value)
        if isinstance(func, ast.Attribute) and func.attr == "factorize":
            return _mentions_track_id(func.value) or any(map(_mentions_track_id, node.args))
        if isinstance(func, ast.Name) and func.id == "factorize":
            return any(map(_mentions_track_id, node.args))
        if isinstance(func, ast.Name) and func.id == "len" and node.args:
            arg = node.args[0]
            return (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "unique"
                and _mentions_track_id(arg.func.value)
            )
    if isinstance(node, ast.Attribute) and node.attr == "ngroups":
        return _mentions_track_id(node.value)
    return False


def calls_zone_shim(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_zone_data"
    )


def _walk_with_scope(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    def visit(node: ast.AST, scope: tuple[str, ...]) -> Iterator[tuple[str, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                yield from visit(child, (*scope, child.name))
            else:
                yield ".".join(scope) or "<module>", child
                yield from visit(child, scope)

    yield from visit(tree, ())


def find_calls(files: Iterable[Path], detector: Detector, root: Path = REPO_ROOT) -> Counter[str]:
    """Count detector hits per ``<path>::<enclosing scope>``."""
    hits: Counter[str] = Counter()
    for path in files:
        rel = path.resolve().relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for scope, node in _walk_with_scope(tree):
            if detector(node):
                hits[f"{rel}::{scope}"] += 1
    return hits


def _python_files(paths: Iterable[str], root: Path = REPO_ROOT) -> list[Path]:
    files: list[Path] = []
    for entry in paths:
        path = root / entry
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def violations(
    hits: Counter[str], allowed: dict[str, tuple[int, str]]
) -> tuple[dict[str, int], dict[str, int]]:
    """(calls beyond the allowance, allowances with fewer calls than listed)."""
    extra = {key: n - allowed.get(key, (0, ""))[0] for key, n in hits.items()}
    extra = {key: n for key, n in extra.items() if n > 0}
    stale = {
        key: count - hits.get(key, 0)
        for key, (count, _reason) in allowed.items()
        if hits.get(key, 0) < count
    }
    return extra, stale


def _subject_count_hits() -> Counter[str]:
    files = [
        path
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if path.resolve().relative_to(REPO_ROOT).as_posix() != SUBJECT_COUNT_HOME
    ]
    return find_calls(files, counts_subjects)


def _zone_shim_hits() -> Counter[str]:
    return find_calls(_python_files(REPORT_CONTEXT_PATHS), calls_zone_shim)


def _format(entries: dict[str, int]) -> str:
    return "\n".join(f"  {key} ({n})" for key, n in sorted(entries.items()))


# --- the rules ---------------------------------------------------------------


def test_animals_are_counted_only_in_track_significance() -> None:
    extra, _ = violations(_subject_count_hits(), ALLOWED_SUBJECT_COUNTS)
    assert not extra, (
        "track_id counted outside analysis/track_significance.py (use count_subjects() / "
        "screen_subjects(); a raw nunique shows a one-row glitch as an animal):\n" + _format(extra)
    )


def test_report_contexts_do_not_read_the_aquarium_zero_shim() -> None:
    extra, _ = violations(_zone_shim_hits(), ALLOWED_ZONE_SHIM_CALLS)
    assert not extra, (
        "get_zone_data() (aquarium 0 only) in a report-generation context; use "
        "get_multi_aquarium_zone_data(), or justify the single-aquarium path:\n" + _format(extra)
    )


@pytest.mark.parametrize(
    ("hits", "allowed"),
    [
        pytest.param(_subject_count_hits, ALLOWED_SUBJECT_COUNTS, id="subject-counts"),
        pytest.param(_zone_shim_hits, ALLOWED_ZONE_SHIM_CALLS, id="zone-shim"),
    ],
)
def test_allowlists_have_no_stale_entries(
    hits: Callable[[], Counter[str]], allowed: dict[str, tuple[int, str]]
) -> None:
    _, stale = violations(hits(), allowed)
    assert not stale, "allowed calls that are gone; shrink the allowlist:\n" + _format(stale)


@pytest.mark.parametrize(
    "allowed",
    [ALLOWED_SUBJECT_COUNTS, ALLOWED_ZONE_SHIM_CALLS],
    ids=["subject-counts", "zone-shim"],
)
def test_every_allowance_states_its_reason(allowed: dict[str, tuple[int, str]]) -> None:
    assert all(count >= 1 and len(reason) >= 30 for count, reason in allowed.values())


# --- the scanner itself -------------------------------------------------------


def _hits(source: str, detector: Detector, tmp_path: Path) -> Counter[str]:
    module = tmp_path / "mod.py"
    module.write_text(source, encoding="utf-8")
    return find_calls([module], detector, root=tmp_path)


@pytest.mark.parametrize(
    "expression",
    [
        'df["track_id"].nunique()',
        "df.track_id.nunique()",
        'df["track_id"].dropna().nunique()',
        'pd.factorize(df["track_id"])',
        'df["track_id"].factorize()',
        'len(df["track_id"].unique())',
        'df.groupby("track_id").ngroups',
        "track_ids.nunique()",
    ],
)
def test_counts_subjects_flags_every_counting_idiom(expression: str, tmp_path: Path) -> None:
    source = f"def f(df, pd, track_ids):\n    return {expression}\n"
    assert _hits(source, counts_subjects, tmp_path) == Counter({"mod.py::f": 1})


@pytest.mark.parametrize(
    "expression",
    [
        'df["frame"].nunique()',
        'df["track_id"].unique()',
        'len(df["frame"].unique())',
        'pd.factorize(df["roi"])',
    ],
)
def test_counts_subjects_ignores_other_columns_and_plain_unique(
    expression: str, tmp_path: Path
) -> None:
    source = f"def f(df, pd):\n    return {expression}\n"
    assert _hits(source, counts_subjects, tmp_path) == Counter()


def test_calls_are_keyed_by_their_enclosing_scope(tmp_path: Path) -> None:
    source = (
        "class C:\n"
        "    def m(self, pm):\n"
        "        def inner():\n"
        "            return pm.get_zone_data()\n"
        "        return pm.get_zone_data(video_path=1), pm.get_multi_aquarium_zone_data()\n"
        "\n"
        "top = pm.get_zone_data()\n"
    )
    assert _hits(source, calls_zone_shim, tmp_path) == Counter(
        {"mod.py::C.m.inner": 1, "mod.py::C.m": 1, "mod.py::<module>": 1}
    )


def test_violations_counts_extra_calls_and_stale_allowances() -> None:
    hits = Counter({"a::f": 2, "b::g": 1})
    allowed = {"a::f": (1, "reason"), "c::h": (1, "reason")}
    assert violations(hits, allowed) == ({"a::f": 1, "b::g": 1}, {"c::h": 1})
