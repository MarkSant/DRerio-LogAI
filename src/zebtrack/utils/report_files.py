"""Helpers for locating session and block report outputs."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

_SUMMARY_EXCEL_SUFFIXES = {".xlsx", ".xls"}
_PRIMARY_SUMMARY_TOKENS = ("summary", "resumo")
_SECONDARY_SUMMARY_TOKENS = ("relatorio", "report")
_PARTIAL_REPORT_SUFFIXES = {".xlsx", ".docx"}


def is_summary_excel_file(path: Path) -> bool:
    """Return True when *path* looks like a session summary/report Excel output."""
    if not path.is_file() or path.suffix.lower() not in _SUMMARY_EXCEL_SUFFIXES:
        return False

    name = path.name.lower()
    return any(token in name for token in (*_PRIMARY_SUMMARY_TOKENS, *_SECONDARY_SUMMARY_TOKENS))


def find_summary_excel_file(results_dir: Path | str | None) -> Path | None:
    """Return the preferred summary/report Excel file inside a session folder."""
    if results_dir is None:
        return None

    folder = Path(results_dir)
    if not folder.exists() or not folder.is_dir():
        return None

    candidates = [path for path in folder.iterdir() if is_summary_excel_file(path)]
    if not candidates:
        return None

    def _sort_key(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if any(token in name for token in _PRIMARY_SUMMARY_TOKENS):
            return (0, name)
        if any(token in name for token in _SECONDARY_SUMMARY_TOKENS):
            return (1, name)
        return (2, name)

    return sorted(candidates, key=_sort_key)[0]


def has_summary_excel_output(results_dir: Path | str | None) -> bool:
    """Return True when a session folder already contains a summary/report Excel."""
    return find_summary_excel_file(results_dir) is not None


def normalize_day_number(day_id: str | int | None) -> int | None:
    """Normalize ``1``, ``Dia_1`` or ``D1`` to an integer day number."""
    if isinstance(day_id, int):
        return day_id
    if day_id in (None, ""):
        return None

    digits = "".join(ch for ch in str(day_id).strip() if ch.isdigit())
    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def find_block_partial_report_files(
    project_path: Path | str | None,
    *,
    day_id: str | int | None,
    group_candidates: Iterable[str | int],
) -> list[Path]:
    """Return partial report files matching a given day/group block."""
    if project_path is None:
        return []

    try:
        project_root = Path(project_path)
    except (TypeError, ValueError):
        return []

    reports_dir = project_root / "partial_reports"
    if not reports_dir.exists() or not reports_dir.is_dir():
        return []

    day_number = normalize_day_number(day_id)
    if day_number is None:
        return []

    prefixes = {
        f"PartialReport_Dia{day_number}_{candidate_str}"
        for candidate in group_candidates
        for candidate_str in [str(candidate).strip()]
        if candidate_str
    }
    if not prefixes:
        return []

    matches = [
        path
        for path in reports_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in _PARTIAL_REPORT_SUFFIXES
        and any(path.name.startswith(prefix) for prefix in prefixes)
    ]

    return sorted(matches, key=lambda path: (path.suffix.lower() != ".xlsx", path.name.lower()))
