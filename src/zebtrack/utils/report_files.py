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


# Human labels for the session outputs, keyed by the filename prefix the
# writers actually use. Ordered: the list is rendered in this order so the
# researcher reads the outputs in pipeline order rather than alphabetically.
#
# Deliberately keyed on PREFIX rather than an exhaustive filename: several
# outputs are conditional (``2_AreasOfInterest`` only with ROIs,
# ``3b_Mascaras`` only with ``recorder.persist_masks`` + a seg model,
# ``5_ClosedLoop`` only with Arduino), so any static list is wrong for some
# fraction of sessions. The caller lists the real directory and looks each
# entry up here.
# The trailing underscore is part of the contract: every writer emits
# ``<prefix>_<base>``. Keeping it makes the match exact-by-construction (a
# hypothetical ``4_RelatorioX`` cannot be mistaken for ``4_Relatorio_``) and
# keeps these strings recognisable as the persistence contract they are —
# i18n: not-ui, they are filenames, never translated.
_SESSION_OUTPUT_LABELS: tuple[tuple[str, str], ...] = (
    ("1_ProcessingArea_", "arena / processing area"),
    ("2_AreasOfInterest_", "ROIs"),
    ("3_CoordMovimento_", "trajectory"),
    ("3b_Mascaras_", "segmentation masks"),
    ("4_Relatorio_", "report"),
    ("4_RelatorioSumario_", "summary"),
    ("5_RelatorioIndividual_", "individual report"),
    ("5_ClosedLoop_", "closed-loop latency (frame -> LED)"),
    ("6_FrameLedger_", "frame ledger (real capture timeline)"),
    ("_recording_metadata", "recording metadata"),
)


def describe_session_output(path: Path) -> str:
    """Return ``"<filename> (<what it is>)"`` for a session output file.

    Unknown files degrade to the bare filename: listing something without a
    label beats hiding it, because the directory listing is the ground truth
    the researcher will compare against.
    """
    name = path.name
    # Longest prefix first so ``3b_Mascaras`` is not shadowed by ``3_`` style
    # prefixes and ``4_RelatorioSumario`` is not shadowed by ``4_Relatorio``.
    for prefix, label in sorted(_SESSION_OUTPUT_LABELS, key=lambda kv: -len(kv[0])):
        if name.startswith(prefix):
            return f"{name} ({label})"
    if path.suffix.lower() in {".mp4", ".avi"}:
        return f"{name} (recorded video)"
    return name


def list_session_outputs(results_dir: Path | str | None) -> list[Path]:
    """Return the files a live session actually produced, in pipeline order.

    Built by listing the directory instead of hardcoding names. The previous
    hardcoded completion message named two files that do not exist
    (``*_trajectory.parquet``, ``*_zones.parquet``) and an extension never
    written (``.avi``), while omitting the reports, the closed-loop log and the
    frame ledger.
    """
    if results_dir is None:
        return []

    folder = Path(results_dir)
    if not folder.exists() or not folder.is_dir():
        return []

    order = {prefix: index for index, (prefix, _label) in enumerate(_SESSION_OUTPUT_LABELS)}

    def _sort_key(path: Path) -> tuple[int, str]:
        for prefix, index in sorted(order.items(), key=lambda kv: -len(kv[0])):
            if path.name.startswith(prefix):
                return (index, path.name.lower())
        # Unknown files (including the recorded video) go last, alphabetically.
        return (len(order), path.name.lower())

    return sorted((p for p in folder.iterdir() if p.is_file()), key=_sort_key)


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
