"""Report Generator Actions — Unified report generation and deletion.

Extracted from ReportsTreeManager (Phase 5 decomposition).
Owns all report generation commands, conflict resolution dialogs,
and the unified report deletion workflow.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui import payloads

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


class ReportGeneratorActions:
    """Report generation commands and unified report lifecycle.

    Extracted from ReportsTreeManager to isolate report generation and
    deletion logic from tree building and event wiring concerns.

    Attributes:
        project_manager_getter: Callable returning the current ProjectManager.
        event_dispatcher: The event dispatcher for publishing events.
        dialog_manager: DialogManager for user dialogs.
        set_status: Callable to set the UI status bar text.
        processing_reports_widget: The ProcessingReportsWidget reference.
    """

    def __init__(
        self,
        *,
        project_manager_getter: Any,
        event_dispatcher: Any | None = None,
        dialog_manager: DialogManager | None = None,
        processing_reports_widget: Any | None = None,
        set_status: Any | None = None,
        tree_metadata: dict | None = None,
        report_tree_metadata: dict | None = None,
        reports_tree_getter: Any | None = None,
    ) -> None:
        """Initialise with required dependencies.

        Args:
            project_manager_getter: Callable that returns the current
                ProjectManager (supports hot-swapping).
            event_dispatcher: EventDispatcher for publishing REPORT_GENERATE.
            dialog_manager: DialogManager for user dialogs.
            processing_reports_widget: The ProcessingReportsWidget reference.
            set_status: Callable to set the UI status bar text.
            tree_metadata: Shared metadata dict for processing_reports tree nodes.
            report_tree_metadata: Shared metadata dict for legacy reports tree nodes.
            reports_tree_getter: Callable returning the legacy reports tree widget.
        """
        self._project_manager_getter = project_manager_getter
        self._event_dispatcher = event_dispatcher
        self._dialog_manager = dialog_manager
        self._processing_reports_widget = processing_reports_widget
        self._set_status = set_status
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
        dialog_manager = self._dialog_manager
        assert dialog_manager is not None, "DialogManager must be available"
        return dialog_manager

    # ------------------------------------------------------------------
    # Public API — Generation commands
    # ------------------------------------------------------------------

    def generate_unified_report(self) -> None:
        """Generate a unified report for all project videos."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        all_videos = self.project_manager.get_all_videos()
        if not all_videos:
            self.dialog_manager.show_warning(
                "Sem Dados",
                "Não há vídeos processados neste projeto para gerar um relatório.",
            )
            return

        replace_existing = self._resolve_unified_generation_strategy("all")
        if replace_existing is None:
            return

        assert self._event_dispatcher is not None
        self._event_dispatcher.publish_event(
            UIEvents.REPORT_GENERATE,
            payloads.ReportGeneratePayload(
                videos=all_videos,
                report_type="unified",
                report_scope="all",
                replace_existing=replace_existing,
            ),
        )

    def on_processing_reports_generate_partial(self) -> None:
        """Handle partial report generation from the unified tab."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        widget = self._processing_reports_widget
        if not widget:
            return

        selection = widget.get_selection()
        if not selection:
            return

        selected_videos: list[dict] = []
        all_videos = self.project_manager.get_all_videos()

        for item_id in selection:
            metadata = self._tree_metadata.get(item_id)
            if not metadata or metadata.get("type") != "video":
                continue
            video_path = metadata.get("video_path")
            if not video_path:
                continue
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            replace_existing = self._resolve_unified_generation_strategy("selected")
            if replace_existing is None:
                return

            assert self._event_dispatcher is not None
            self._event_dispatcher.publish_event(
                UIEvents.REPORT_GENERATE,
                payloads.ReportGeneratePayload(
                    videos=selected_videos,
                    report_type="unified",
                    report_scope="selected",
                    replace_existing=replace_existing,
                ),
            )

    def generate_partial_report(self) -> None:
        """Gather selected videos and generate a unified partial report from reports tree."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        reports_tree = self._reports_tree_getter() if callable(self._reports_tree_getter) else None
        if not reports_tree:
            return

        selected_items = reports_tree.selection()
        if not selected_items:
            return

        selected_videos: list[dict] = []
        all_videos = self.project_manager.get_all_videos()

        for item_id in selected_items:
            if not reports_tree.exists(item_id):
                continue
            metadata = self._report_tree_metadata.get(item_id)
            if not metadata or metadata.get("type") != "video":
                continue
            video_path = metadata.get("video_path")
            if not video_path:
                continue
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            replace_existing = self._resolve_unified_generation_strategy("selected")
            if replace_existing is None:
                return

            assert self._event_dispatcher is not None
            self._event_dispatcher.publish_event(
                UIEvents.REPORT_GENERATE,
                payloads.ReportGeneratePayload(
                    videos=selected_videos,
                    report_type="unified",
                    report_scope="selected",
                    replace_existing=replace_existing,
                ),
            )

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def _resolve_unified_generation_strategy(self, scope: str = "all") -> bool | None:
        """Resolve conflict strategy when unified reports already exist.

        Args:
            scope: ``"all"`` para o relatório total, ``"selected"`` para o parcial.
                Determina a subpasta verificada (total/ ou selecionados/), de modo
                que a checagem de conflito reflita só o que será substituído.

        Returns:
            True to overwrite, False to keep and append, None if user cancels.
        """
        pm = self.project_manager
        if not pm.project_path:
            return False

        scope_dir = "selecionados" if scope == "selected" else "total"
        unified_dir = Path(pm.project_path) / "unified_reports" / scope_dir
        if not unified_dir.exists():
            return False

        has_existing = (
            any(unified_dir.glob("*.parquet"))
            or any(unified_dir.glob("*.xlsx"))
            or any(unified_dir.glob("*.docx"))
        )
        if not has_existing:
            return False

        response = self.dialog_manager.ask_yes_no_cancel(
            "Relatórios Unificados Existentes",
            (
                "Já existem relatórios unificados neste projeto.\n\n"
                "Sim: apagar os anteriores e gerar novo\n"
                "Não: manter anteriores e gerar outro com novo nome\n"
                "Cancelar: abortar geração"
            ),
            icon="warning",
        )

        if response is None:
            if self._set_status:
                self._set_status("Geração de relatório unificado cancelada pelo usuário.")
            return None

        return bool(response)

    # ------------------------------------------------------------------
    # Unified report deletion
    # ------------------------------------------------------------------

    def delete_all_unified_reports(self, data: dict | None = None) -> None:
        """Delete the entire unified_reports directory.

        May be subscribed to event ``reports.delete_unified``.
        """
        pm = self.project_manager
        if not pm.project_path:
            return

        import shutil
        import stat
        import time

        unified_dir = os.path.join(pm.project_path, "unified_reports")

        def on_rm_error(func: Any, path: Path | str, exc_info: Any) -> None:
            """Handler to clear read-only/locked files."""
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except OSError:
                log.debug(
                    "report_generator_actions.rmtree_retry.suppressed",
                    path=path,
                    exc_info=True,
                )

        if os.path.exists(unified_dir):
            success = False
            last_error = None

            for _ in range(3):
                try:
                    shutil.rmtree(unified_dir, onerror=on_rm_error)
                    success = True
                    break
                except OSError as e:
                    last_error = e
                    time.sleep(0.5)

            if success:
                log.info("project.delete_unified.success", path=unified_dir)
                self.dialog_manager.show_info(
                    "Sucesso", "Todos os relatórios unificados foram apagados."
                )

                widget = self._processing_reports_widget
                if widget and hasattr(widget, "_update_button_states"):
                    widget._update_button_states(pm.project_path)
            else:
                log.warning("project.delete_unified.failed", error=str(last_error))

                msg = "Não foi possível apagar a pasta.\nVerifique se algum arquivo está aberto."
                if last_error and "OneDrive" in str(unified_dir):
                    msg += (
                        "\n\nO OneDrive pode estar bloqueando arquivos. "
                        "Tente novamente em instantes."
                    )

                self.dialog_manager.show_error("Erro ao Apagar", f"{msg}\n\nErro: {last_error}")

        # Always refresh button states regardless of success/failure
        widget = self._processing_reports_widget
        if widget and hasattr(widget, "_update_button_states"):
            widget._update_button_states(pm.project_path)
        else:
            self.dialog_manager.show_info("Aviso", "Não havia relatórios unificados para apagar.")
