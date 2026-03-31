"""Report Asset Actions — Deletion, file opening, and artifact helpers.

Extracted from ReportsTreeManager (Phase 5 decomposition).
Owns all methods for video asset deletion, double-click handling,
file opening in explorer, and artifact manipulation from entries.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


class ReportAssetActions:
    """Video asset deletion, file opening, and artifact helpers.

    Extracted from ReportsTreeManager to isolate asset lifecycle and
    file handling from tree building and report generation logic.
    """

    def __init__(
        self,
        *,
        project_manager_getter: Any,
        dialog_manager: DialogManager | None = None,
        menu_manager: Any | None = None,
        widget_factory: Any | None = None,
        video_selector_manager: Any | None = None,
        processing_reports_widget: Any | None = None,
        tree_metadata: dict | None = None,
        report_tree_metadata: dict | None = None,
        reports_tree_getter: Any | None = None,
    ) -> None:
        """Initialise with required dependencies.

        Args:
            project_manager_getter: Callable returning the current ProjectManager.
            dialog_manager: DialogManager for user dialogs.
            menu_manager: MenuManager for asset removal.
            widget_factory: WidgetFactory for artifact ID generation.
            video_selector_manager: VideoSelectorManager for view refresh.
            processing_reports_widget: The ProcessingReportsWidget reference.
            tree_metadata: Shared metadata dict for processing_reports tree nodes.
            report_tree_metadata: Shared metadata dict for legacy reports tree nodes.
            reports_tree_getter: Callable returning the legacy reports tree widget.
        """
        self._project_manager_getter = project_manager_getter
        self._dialog_manager = dialog_manager
        self._menu_manager = menu_manager
        self._widget_factory = widget_factory
        self._video_selector_manager = video_selector_manager
        self._processing_reports_widget = processing_reports_widget
        self._tree_metadata: dict = tree_metadata if tree_metadata is not None else {}
        self._report_tree_metadata: dict = (
            report_tree_metadata if report_tree_metadata is not None else {}
        )
        self._reports_tree_getter = reports_tree_getter

    @property
    def project_manager(self) -> Any:
        """Return the current ProjectManager (supports hot-swap)."""
        if callable(self._project_manager_getter):
            return self._project_manager_getter()
        return self._project_manager_getter

    @property
    def dialog_manager(self) -> DialogManager:
        """Return the DialogManager."""
        return self._dialog_manager  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Deletion helpers
    # ------------------------------------------------------------------

    def delete_video_asset(self, video_path: Path | str, asset: str) -> None:
        """Delete specific asset via MenuManager reuse."""
        assert self._menu_manager is not None
        self._menu_manager.handle_overview_asset_removal(video_path, asset)

    def delete_all_processing_data(self, video_path: Path | str) -> None:
        """Delete all processing data (arena, rois, trajectory, summary)."""
        pm = self.project_manager

        confirm = self.dialog_manager.ask_ok_cancel(
            "Apagar Dados de Processamento",
            f"Tem certeza que deseja apagar TODOS os dados de processamento "
            f"(Arena, ROIs, Trajetória, Relatórios) para:\n\n{os.path.basename(video_path)}?\n\n"
            f"O vídeo será mantido no projeto.",
        )
        if not confirm:
            return

        assets = ["summary", "trajectory", "rois", "arena"]
        changed = False

        for asset in assets:
            if pm.remove_asset(video_path, asset, delete_files=True):
                changed = True

        if changed:
            assert self._video_selector_manager is not None
            self._video_selector_manager.refresh_project_views(
                reason="Dados de processamento apagados", append_summary=True
            )

    def delete_video_from_project(self, video_path: Path | str) -> None:
        """Delete video from project."""
        assert self._menu_manager is not None
        self._menu_manager.handle_overview_asset_removal(video_path, "video")

    # ------------------------------------------------------------------
    # Artifact helpers (legacy reports tree)
    # ------------------------------------------------------------------

    def append_report_artifacts_from_entry(self, parent_id: str, entry: dict) -> None:
        """Append report artifacts (docx, xlsx) from video entry to reports tree."""
        reports_tree = self._reports_tree_getter() if callable(self._reports_tree_getter) else None
        if not reports_tree:
            return

        video_path = entry.get("path")
        if not video_path:
            return

        results_dir = entry.get("results_dir") or ""
        parquet_files = entry.get("parquet_files") or {}
        experiment_id = Path(video_path).stem if video_path else None

        def _resolve_artifact(candidate: str | None, suffix: str) -> str | None:
            if candidate and os.path.exists(candidate):
                return candidate
            if results_dir and experiment_id:
                guess_path = Path(results_dir) / f"{experiment_id}_{suffix}"
                if guess_path.exists():
                    return str(guess_path)
            return None

        docx_path = _resolve_artifact(parquet_files.get("report_docx"), "report.docx")
        excel_path = _resolve_artifact(parquet_files.get("summary_excel"), "summary.xlsx")

        artifacts: list[tuple[str, str, str]] = []
        if docx_path:
            artifacts.append(("file", docx_path, "📝 Word: " + Path(docx_path).name))
        if excel_path:
            artifacts.append(("file", excel_path, "📊 Excel: " + Path(excel_path).name))

        if not artifacts:
            return

        for _kind, artifact_path, label in artifacts:
            child_id = reports_tree.insert(
                parent_id,
                "end",
                text=label,
                values=("", "", "", "", "Abrir"),
                tags=("report-file",),
            )
            self._report_tree_metadata[child_id] = {
                "type": "file",
                "path": artifact_path,
                "parent_video": video_path,
            }

        reports_tree.item(parent_id, open=True)

    # ------------------------------------------------------------------
    # Double-click / file opening
    # ------------------------------------------------------------------

    def on_processing_reports_item_click(self, event: Any | None = None) -> None:
        """Handle single-click on processing reports tree.

        Single click opens file nodes only. Folder/video nodes keep normal
        selection behavior and still require double-click to open.
        """
        widget = self._processing_reports_widget
        if not widget or not widget.tree:
            return

        tree = widget.tree

        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        metadata = self._tree_metadata.get(item_id)
        if not metadata:
            return

        if metadata.get("type") == "file":
            self._handle_report_file_node(metadata)

    def on_processing_reports_item_double_click(self, event: Any | None = None) -> None:
        """Handle double-click on items in the Processing Reports tree."""
        widget = self._processing_reports_widget
        if not widget or not widget.tree:
            return

        tree = widget.tree

        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        metadata = self._tree_metadata.get(item_id)
        if not metadata:
            return

        node_type = metadata.get("type")

        if node_type == "file":
            self._handle_report_file_node(metadata)
            return

        if node_type == "video":
            results_dir = metadata.get("results_dir")
            if results_dir and os.path.exists(results_dir):
                log.info("gui.open_results_folder", path=results_dir)
                self._open_path_in_explorer(results_dir)
            return

        if node_type == "aquarium":
            results_dir = metadata.get("results_dir")
            if results_dir and os.path.exists(results_dir):
                log.info(
                    "gui.open_aquarium_results_folder",
                    path=results_dir,
                    aquarium_id=metadata.get("aquarium_id"),
                )
                self._open_path_in_explorer(results_dir)
            return

    def _handle_report_file_node(self, metadata: dict) -> None:
        """Handle opening of report file node."""
        file_path = metadata.get("file_path") or metadata.get("path")
        if not file_path:
            log.warning("gui.open_report_file.missing_path", metadata_keys=list(metadata.keys()))
            self.dialog_manager.show_warning(
                "Arquivo indisponível", "Caminho do relatório não foi encontrado."
            )
            return

        if not os.path.exists(file_path):
            log.warning("gui.open_report_file.not_found", path=file_path)
            self.dialog_manager.show_warning(
                "Arquivo não encontrado", f"O arquivo não existe mais:\n{file_path}"
            )
            return

        log.info("gui.open_report_file", path=file_path)
        self._open_path_in_explorer(file_path)

    def open_unified_report(self, file_type: str) -> None:
        """Open the latest unified report of the specified type."""
        pm = self.project_manager
        if not pm.project_path:
            return

        unified_dir = Path(pm.project_path) / "unified_reports"
        if not unified_dir.exists():
            self.dialog_manager.show_warning(
                "Indisponível", "Nenhum relatório unificado encontrado."
            )
            return

        pattern = ""
        if file_type == "word":
            pattern = "*.docx"
        elif file_type == "excel":
            pattern = "*.xlsx"
        elif file_type == "parquet":
            pattern = "*.parquet"

        if not pattern:
            return

        files = list(unified_dir.glob(pattern))
        if not files:
            self.dialog_manager.show_warning(
                "Indisponível", f"Nenhum relatório {file_type} encontrado."
            )
            return

        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        self._handle_report_file_node({"file_path": str(latest_file)})

    def handle_report_video_node(self, metadata: dict) -> None:
        """Handle double-click on report video node — opens results directory."""
        video_path = metadata.get("video_path")
        if not video_path:
            return

        pm = self.project_manager
        if not pm:
            return

        entry = pm.find_video_entry(path=video_path)
        results_dir = metadata.get("results_dir") or ""
        metadata_hint: dict = {}
        has_results = False

        if entry:
            metadata_hint = dict(entry.get("metadata") or {})
            if not results_dir:
                results_dir = entry.get("results_dir") or ""
            for key in ("group", "group_display_name", "day", "subject"):
                if entry.get(key) is not None and key not in metadata_hint:
                    metadata_hint[key] = entry[key]
            parquet_files = entry.get("parquet_files") or {}
            for key in ("summary", "summary_excel", "report_docx"):
                candidate_path = parquet_files.get(key)
                if candidate_path and os.path.exists(candidate_path):
                    has_results = True
                    break

        experiment_id = Path(video_path).stem
        if not results_dir:
            results_path = pm.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_hint,
            )
            results_dir = str(results_path)

        if not has_results and results_dir:
            summary_candidate = Path(results_dir) / f"{experiment_id}_summary.parquet"
            report_candidate = Path(results_dir) / f"{experiment_id}_report.docx"
            excel_candidate = Path(results_dir) / f"{experiment_id}_summary.xlsx"
            if summary_candidate.exists() or report_candidate.exists() or excel_candidate.exists():
                has_results = True

        if not results_dir or not os.path.isdir(results_dir) or not has_results:
            self.dialog_manager.show_warning(
                "Relatórios indisponíveis",
                "Gere o relatório para este vídeo antes de abrir a pasta de resultados.",
            )
            return

        self._open_path_in_explorer(results_dir)

    # ------------------------------------------------------------------
    # Private utilities
    # ------------------------------------------------------------------

    def _open_path_in_explorer(self, path: Path | str) -> None:
        """Open a file or folder in the system file explorer."""
        try:
            from zebtrack.utils.os_opener import open_path

            open_path(path)
        except OSError as e:
            log.error("gui.open_path.failed", path=path, error=str(e))
            self.dialog_manager.show_error("Erro", f"Não foi possível abrir: {e}")
