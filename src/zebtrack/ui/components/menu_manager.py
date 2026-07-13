"""Menu management for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles menu bar, context menus, and menu-related operations.
"""

from __future__ import annotations

import os
import tkinter.font as tkfont
from collections.abc import Callable
from pathlib import Path
from tkinter import Menu, Toplevel, messagebox, ttk
from typing import TYPE_CHECKING, Any

import structlog
from PIL import Image, ImageTk

from zebtrack.ui import payloads
from zebtrack.ui.dialogs.project_video_import_dialog import VideoMetadataDialog
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


class MenuManager:
    """Manages menu bar and context menus for ApplicationGUI."""

    def __init__(self, gui, *, dialog_manager: DialogManager | None = None):
        """Initialize MenuManager.

        Args:
            gui: Reference to ApplicationGUI instance
            dialog_manager: Optional DialogManager for dependency injection.
        """
        self.gui = gui
        self._dialog_manager = dialog_manager

        # Menu-related attributes
        self._overview_context_menu: Menu | None = None
        self._overview_menu_font: tkfont.Font | None = None
        self._about_logo_image: ImageTk.PhotoImage | None = None

    @property
    def dialog_manager(self) -> DialogManager:
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._dialog_manager or self.gui.dialog_manager

    def create_menu_bar(self):
        """Create the application menu bar with File and Help menus."""
        menubar = Menu(self.gui.root)
        self.gui.root.config(menu=menubar)

        # File menu
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Arquivo", menu=file_menu)
        file_menu.add_command(label="Sair", command=self.gui.root.quit, accelerator="Ctrl+Q")

        # Bind keyboard shortcuts
        self.gui.root.bind("<Control-q>", lambda e: self.gui.root.quit())

        # Tools menu
        tools_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ferramentas", menu=tools_menu)
        tools_menu.add_command(
            label="Restaurar Padrões (Reiniciar)",
            command=self._reset_defaults,
        )

        # Help menu
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ajuda", menu=help_menu)
        help_menu.add_command(label="Sobre DRerio LogAI", command=self.show_about_dialog)

    def _reset_defaults(self):
        """Reset benchmark cache and local config after user confirmation."""
        confirm = messagebox.askyesno(
            "Restaurar Padrões",
            "Isso irá remover o cache de benchmark e o config.local.yaml.\n"
            "O aplicativo será fechado e precisará ser reiniciado.\n\n"
            "Deseja continuar?",
            parent=self.gui.root,
        )
        if not confirm:
            return

        from zebtrack.core.app_runner import _perform_reset

        _perform_reset()
        messagebox.showinfo(
            "Restaurar Padrões",
            "Padrões restaurados com sucesso.\nO aplicativo será encerrado agora.",
            parent=self.gui.root,
        )
        self.gui.root.quit()

    def show_about_dialog(self):
        """Show the About dialog with application information."""
        about_window = Toplevel(self.gui.root)
        about_window.title("Sobre DRerio LogAI")
        about_window.resizable(False, False)

        # Set icon for About window
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(about_window)

        # Center the window
        about_window.geometry("400x450")
        about_window.transient(self.gui.root)
        about_window.grab_set()

        # Logo
        try:
            logo_path = Path(__file__).parent.parent / "assets" / "logo_about.png"
            if not logo_path.exists():
                logo_path = Path("src/zebtrack/ui/assets/logo_about.png")

            if logo_path.exists():
                logo_pil = Image.open(logo_path)
                self._about_logo_image = ImageTk.PhotoImage(logo_pil)
                logo_label = ttk.Label(about_window, image=self._about_logo_image)
                logo_label.pack(pady=(20, 10))
        except Exception as e:
            log.warning("about.logo.load_error", error=str(e))

        # Application name
        name_label = ttk.Label(
            about_window, text="DRerio LogAI", font=("TkDefaultFont", 18, "bold")
        )
        name_label.pack(pady=(10, 5))

        # Version (from pyproject.toml)
        try:
            import tomli

            pyproject_path = Path(__file__).parent.parent.parent.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    pyproject_data = tomli.load(f)
                    version = (
                        pyproject_data.get("tool", {}).get("poetry", {}).get("version", "Unknown")
                    )
            else:
                version = "Development"
        except Exception:
            version = "Unknown"

        version_label = ttk.Label(
            about_window, text=f"Versão {version}", font=("TkDefaultFont", 10)
        )
        version_label.pack(pady=(0, 15))

        # Description
        desc_text = (
            "Rastreamento e análise comportamental automatizada\n"
            "para pesquisa com Danio rerio (zebrafish)\n\n"
            "Integração de visão computacional (YOLO/OpenVINO),\n"
            "análise comportamental e geração de relatórios científicos"
        )
        desc_label = ttk.Label(
            about_window, text=desc_text, justify="center", font=("TkDefaultFont", 9)
        )
        desc_label.pack(pady=(0, 15))

        # Repository link
        repo_frame = ttk.Frame(about_window)
        repo_frame.pack(pady=(0, 10))

        ttk.Label(repo_frame, text="Repositório:", font=("TkDefaultFont", 9, "bold")).pack()
        repo_link = ttk.Label(
            repo_frame,
            text="github.com/MarkSant/DRerio-LogAI",
            font=("TkDefaultFont", 9),
            foreground="blue",
            cursor="hand2",
        )
        repo_link.pack()

        def open_repo(event):
            import webbrowser

            webbrowser.open("https://github.com/MarkSant/DRerio-LogAI")

        repo_link.bind("<Button-1>", open_repo)

        # License
        license_label = ttk.Label(about_window, text="Licença: MIT", font=("TkDefaultFont", 9))
        license_label.pack(pady=(10, 15))

        # Close button
        close_btn = ttk.Button(about_window, text="Fechar", command=about_window.destroy)
        close_btn.pack(pady=(0, 20))

        # Center window on screen
        about_window.update_idletasks()
        x = (about_window.winfo_screenwidth() // 2) - (400 // 2)
        y = (about_window.winfo_screenheight() // 2) - (450 // 2)
        about_window.geometry(f"400x450+{x}+{y}")

    def show_project_overview_context_menu(self, item_id: str, x: int, y: int) -> None:
        """Show context menu for project overview item (reusable implementation)."""
        tree = self.gui.project_overview_tree
        if not tree or not tree.winfo_exists():
            return

        tree.selection_set(item_id)

        video_path = self._resolve_project_overview_video_path(item_id)

        if not video_path:
            return

        if self._overview_context_menu:
            self._overview_context_menu.destroy()

        self._overview_context_menu = Menu(self.gui.root, tearoff=0)
        pvm = self.gui.project_view_manager
        self._overview_context_menu.add_command(
            label="Carregar vídeo",
            command=lambda: pvm.handle_project_overview_double_click(item_id),
        )
        self._overview_context_menu.add_command(
            label="🔄 Editar Grupo / Dia / Sujeitos",
            command=lambda: self._edit_video_metadata(video_path),
        )
        self._overview_context_menu.post(x, y)

    def edit_selected_project_overview_video_metadata(self) -> None:
        """Open metadata editor for the currently selected overview video."""
        tree = self.gui.project_overview_tree
        if not tree or not tree.winfo_exists():
            return

        selection = tree.selection()
        if not selection:
            self.dialog_manager.show_info(
                "Nenhum vídeo selecionado",
                "Selecione um vídeo do projeto para editar grupo, dia e sujeitos.",
            )
            return

        video_path = self._resolve_project_overview_video_path(selection[0])
        if not video_path:
            self.dialog_manager.show_info(
                "Seleção inválida",
                "Selecione um item de vídeo do projeto para editar seus metadados.",
            )
            return

        self._edit_video_metadata(video_path)

    def _resolve_project_overview_video_path(self, item_id: str) -> str | None:
        """Resolve a video path for a project overview tree item."""
        tree = self.gui.project_overview_tree
        if not tree or not tree.winfo_exists():
            return None

        tags = tree.item(item_id, "tags") or ()
        for tag in tags:
            if tag and not tag.startswith("status_"):
                return str(tag)

        overview_widget = getattr(self.gui, "project_overview_widget", None)
        iid_to_path = getattr(overview_widget, "_iid_to_path", None)
        if isinstance(iid_to_path, dict):
            video_path = iid_to_path.get(item_id)
            if video_path:
                return str(video_path)

        return None

    def _edit_video_metadata(self, video_path: Path | str) -> None:
        """Open the video metadata editor for a project video."""
        project_manager = getattr(getattr(self.gui, "controller", None), "project_manager", None)
        if project_manager is None:
            log.warning("menu_manager.video_metadata.no_project_manager", video=video_path)
            return

        video_entry = project_manager.find_video_entry(path=video_path)
        if not video_entry:
            self.dialog_manager.show_error(
                "Vídeo não encontrado",
                "Não foi possível localizar o vídeo selecionado no projeto.",
            )
            return

        calibration = project_manager.project_data.get("calibration", {})
        num_aquariums = max(1, int(calibration.get("num_aquariums", 1) or 1))
        animals_per_aquarium = max(1, int(calibration.get("animals_per_aquarium", 1) or 1))

        dialog = VideoMetadataDialog(
            self.gui.root,
            video_path=video_path,  # type: ignore[arg-type]
            available_groups=project_manager.get_available_groups(),
            initial_metadata=dict(video_entry.get("metadata") or {}),
            subject_entry_count=max(1, num_aquariums * animals_per_aquarium),
        )
        if not dialog.result:
            return

        changed = project_manager.update_video_metadata(video_path, dialog.result)
        if not changed:
            return

        basename = Path(video_path).name
        status_message = f"Metadados atualizados • {basename}"
        self.gui.set_status(status_message)

        if self.gui.event_bus_v2:
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_METADATA_UPDATED,
                    data=payloads.VideoMetadataUpdatedPayload(
                        video_path=video_path,  # type: ignore[arg-type]
                        metadata=dialog.result,
                    ),
                    source="MenuManager._edit_video_metadata",
                )
            )
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                    data=payloads.ProjectViewsRefreshRequestedPayload(
                        reason=status_message,
                        append_summary=True,
                        immediate=True,
                    ),
                    source="MenuManager._edit_video_metadata",
                )
            )
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(),
                    source="MenuManager._edit_video_metadata",
                )
            )

    def get_overview_badge_font(self) -> tkfont.Font:
        """Get or create the font used for overview badges."""
        if self._overview_menu_font is None:
            tree = self.gui.project_overview_tree
            font_name = tree.cget("font") if tree else ""
            try:
                if font_name:
                    self._overview_menu_font = tkfont.Font(font=font_name)
                else:
                    self._overview_menu_font = tkfont.nametofont("TkDefaultFont")
            except Exception:
                self._overview_menu_font = tkfont.nametofont("TkDefaultFont")

        return self._overview_menu_font

    def resolve_overview_asset_from_click(self, item_id: str, event_x: int) -> str | None:
        """Resolve which asset was clicked in the overview tree.

        Args:
            item_id: Tree item ID
            event_x: X coordinate of the click event

        Returns:
            Asset type ("arena", "rois", "trajectory", "summary") or None
        """
        tree = self.gui.project_overview_tree
        if not tree or not tree.winfo_exists():
            return None

        bbox = tree.bbox(item_id, "#2")
        if not bbox:
            return None

        cell_x = event_x - bbox[0]
        if cell_x < 0:
            return None

        data_text = tree.set(item_id, "data")
        if not data_text:
            return None

        tokens = [token for token in data_text.split("  ") if token.strip()]
        assets = ("arena", "rois", "trajectory", "summary")
        font = self.get_overview_badge_font()
        cursor = 0

        for token, asset in zip(tokens, assets, strict=False):
            segment = token.strip()
            if not segment:
                continue
            display = f"{segment}  "
            segment_width = font.measure(display)
            if cursor <= cell_x <= cursor + segment_width:
                return asset
            cursor += segment_width

        return None

    def show_overview_context_menu(
        self,
        event,
        video_path: Path | str,
        asset: str,
    ) -> None:
        """Show context menu for overview asset removal.

        Args:
            event: The event object containing position information
            video_path: Path to the video file
            asset: Asset type to remove ("arena", "rois", "trajectory", "summary", "video")
        """
        tree = self.gui.project_overview_tree
        if not tree or not tree.winfo_exists():
            return

        if self._overview_context_menu is None:
            self._overview_context_menu = Menu(tree, tearoff=0)

        labels = {
            "arena": "Apagar arena",
            "rois": "Apagar ROIs",
            "trajectory": "Apagar trajetória",
            "summary": "Apagar relatórios/sumários",
            "video": "Remover vídeo do projeto",
        }

        menu = self._overview_context_menu
        menu.delete(0, "end")
        menu.add_command(
            label=labels.get(asset, f"Remover {asset}"),
            command=lambda: self.handle_overview_asset_removal(video_path, asset),
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def handle_overview_asset_removal(self, video_path: Path | str, asset: str) -> None:
        """Handle removal of project assets (arena, ROIs, trajectory, summary, video).

        Args:
            video_path: Path to the video file
            asset: Asset type to remove
        """
        allowed, reason = self.gui.controller.project_vm.can_remove_project_asset(video_path, asset)
        if not allowed:
            self.dialog_manager.show_warning(
                "Ação indisponível",
                reason or "Não é possível remover o item selecionado neste momento.",
            )
            return

        basename = os.path.basename(video_path) or video_path

        # v2.3.2: Check for multi-aquarium mode to show appropriate warning
        is_multi_aquarium = False
        num_aquariums = 0
        if hasattr(self.gui.controller, "project_manager"):
            video_entry = self.gui.controller.project_manager.find_video_entry(path=video_path)
            if video_entry and isinstance(video_entry, dict):
                is_multi_aquarium = bool(video_entry.get("multi_aquarium_mode", False))
                multi_outputs = video_entry.get("multi_aquarium_outputs")
                if multi_outputs and isinstance(multi_outputs, dict):
                    num_aquariums = len(multi_outputs)

        prompts = {
            "arena": (
                "Remover arena",
                ("Deseja remover a arena deste vídeo? As ROIs associadas também serão limpas."),
            ),
            "rois": (
                "Remover ROIs",
                "Deseja remover todas as ROIs salvas para este vídeo?",
            ),
            "trajectory": (
                "Remover trajetória",
                "Deseja remover a trajetória gerada para este vídeo?",
            ),
            "summary": (
                "Remover relatórios",
                "Deseja remover os relatórios e sumários associados a este vídeo?",
            ),
            "video": (
                "Remover vídeo do projeto",
                (
                    "Deseja remover este vídeo do projeto? As arenas, ROIs e "
                    "trajetórias já removidas não poderão ser recuperadas "
                    "automaticamente."
                ),
            ),
        }

        title, message = prompts.get(
            asset,
            (
                "Remover item",
                "Confirma a remoção do item selecionado?",
            ),
        )

        # v2.3.2: Add multi-aquarium warning if applicable
        if is_multi_aquarium and asset == "video":
            message = (
                f"Este vídeo possui dados de {num_aquariums} aquário(s) separados.\n\n"
                f"⚠️ ATENÇÃO: Ao remover o vídeo, TODOS os dados e relatórios de "
                f"TODOS os aquários serão excluídos permanentemente.\n\n"
                f"Se deseja manter os dados de algum aquário, cancele esta operação "
                f"e exporte os relatórios antes de prosseguir.\n\n"
                f"Deseja continuar com a remoção?"
            )
        elif is_multi_aquarium and asset in ("trajectory", "summary"):
            message = (
                f"Este vídeo possui dados de {num_aquariums} aquário(s) separados.\n\n"
                f"⚠️ Ao remover este item, os dados de TODOS os aquários serão afetados.\n\n"
                f"{message}"
            )

        confirm = messagebox.askyesno(
            title,
            f"{message}\n\nVídeo: {basename}",
            icon="warning",
        )
        if not confirm:
            return

        delete_files = True
        if asset == "video":
            delete_files = messagebox.askyesno(
                "Excluir arquivo do disco?",
                (
                    "Deseja também remover o arquivo de vídeo do disco? Essa ação "
                    "não poderá ser desfeita."
                ),
                icon="question",
            )

        if asset == "video":
            self.gui.event_dispatcher.publish_event(
                UIEvents.PROJECT_DELETE_ASSET,
                {
                    "video_path": video_path,
                    "asset": asset,
                    "delete_source": delete_files,
                },
            )
            success = True  # Assume success
        else:
            self.gui.event_dispatcher.publish_event(
                UIEvents.PROJECT_DELETE_ASSET, {"video_path": video_path, "asset": asset}
            )
            success = True  # Assume success

        if not success:
            self.dialog_manager.show_error(
                "Remoção não realizada",
                (
                    "Não foi possível remover o item selecionado. Consulte os "
                    "logs para mais detalhes."
                ),
            )
            return

        status_labels = {
            "arena": "Arena removida",
            "rois": "ROIs removidas",
            "trajectory": "Trajetória removida",
            "summary": "Relatórios removidos",
            "video": "Vídeo removido do projeto",
        }

        status_message = f"{status_labels.get(asset, 'Item removido')} • {basename}"
        self.gui.set_status(status_message)

        if self.gui.event_bus_v2:
            # Refresh Project Views (Overview + Reports)
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                    data=payloads.ProjectViewsRefreshRequestedPayload(
                        reason=status_message, append_summary=True, immediate=True
                    ),
                    source="MenuManager.handle_overview_asset_removal",
                )
            )
            # Refresh Video Tree (Zone Configuration)
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(),
                    source="MenuManager.handle_overview_asset_removal",
                )
            )
            # v2.3.2: Clear zone display when video or arena is deleted
            if asset in ("video", "arena"):
                self.gui.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONE_DISPLAY_CLEARED,
                        data=payloads.ZoneDisplayClearedPayload(
                            deleted_video_path=str(video_path) if video_path else None, asset=asset
                        ),
                        source="MenuManager.handle_overview_asset_removal",
                    )
                )

    def show_processing_reports_context_menu(
        self,
        video_path: Path | str,
        column_id: str,
        x: int,
        y: int,
        callbacks: dict[str, Callable[..., Any]],
        *,
        asset_availability: dict[str, bool] | None = None,
    ) -> None:
        """Show context menu for processing reports tree items.

        Args:
            video_path: Path to the video file
            column_id: Tree column identifier (e.g., "#1", "#2")
            x: Screen X coordinate
            y: Screen Y coordinate
            callbacks: Dictionary of callback functions
        """
        menu = Menu(self.gui.root, tearoff=0)
        pm = self.gui.controller.project_manager

        # Asset Availability Checks
        has_arena = pm.has_arena_data(video_path)
        has_rois = pm.has_roi_data(video_path)
        has_trajectory = pm.has_trajectory_data(video_path)
        has_summary = pm.has_summary_data(video_path)

        if asset_availability is not None:
            has_arena = bool(asset_availability.get("arena", has_arena))
            has_rois = bool(asset_availability.get("rois", has_rois))
            has_trajectory = bool(asset_availability.get("trajectory", has_trajectory))
            has_summary = bool(asset_availability.get("summary", has_summary))

        # Map column ID to asset type for "Quick Action"
        column_map = {
            "#1": "arena",
            "#2": "rois",
            "#3": "trajectory",
            "#4": "summary",
        }
        clicked_asset = column_map.get(column_id)

        menu.add_command(
            label="🔄 Editar Grupo / Dia / Sujeitos",
            command=lambda: self._edit_video_metadata(str(video_path)),
        )
        menu.add_separator()

        # 1. Targeted Delete (if clicked specific column and asset exists)
        if clicked_asset:
            exists_map = {
                "arena": has_arena,
                "rois": has_rois,
                "trajectory": has_trajectory,
                "summary": has_summary,
            }
            if exists_map.get(clicked_asset):
                labels = {
                    "arena": "Apagar Arena",
                    "rois": "Apagar ROIs",
                    "trajectory": "Apagar Trajetória",
                    "summary": "Apagar Sumário",
                }
                label = labels.get(clicked_asset, f"Apagar {clicked_asset}")
                menu.add_command(
                    label=f"🗑️ {label} (Selecionado)",
                    command=lambda: callbacks["delete_asset"](video_path, clicked_asset),
                )
                menu.add_separator()

        # 2. General Delete Options (Available if asset exists)
        delete_menu = Menu(menu, tearoff=0)
        has_any_delete = False

        if has_arena:
            delete_menu.add_command(
                label="🏛️ Apagar Arena",
                command=lambda: callbacks["delete_asset"](video_path, "arena"),
            )
            has_any_delete = True

        if has_rois:
            delete_menu.add_command(
                label="📍 Apagar ROIs",
                command=lambda: callbacks["delete_asset"](video_path, "rois"),
            )
            has_any_delete = True

        if has_trajectory:
            delete_menu.add_command(
                label="📈 Apagar Trajetória",
                command=lambda: callbacks["delete_asset"](video_path, "trajectory"),
            )
            has_any_delete = True

        if has_summary:
            delete_menu.add_command(
                label="📝 Apagar Relatórios",
                command=lambda: callbacks["delete_asset"](video_path, "summary"),
            )
            has_any_delete = True

        if has_any_delete:
            menu.add_cascade(label="🗑️ Apagar Item Específico...", menu=delete_menu)
            menu.add_separator()

        delete_choice = callbacks.get("delete_choice")
        if delete_choice is not None:
            menu.add_command(
                label="🗑️ Excluir Vídeo / Dados...",
                command=lambda: delete_choice(video_path),
            )
        else:
            menu.add_command(
                label="🧹 Apagar Todos os Dados de Processamento",
                command=lambda: callbacks["delete_all_processing"](video_path),
            )

            menu.add_command(
                label="❌ Remover Vídeo do Projeto",
                command=lambda: callbacks["delete_video"](video_path),
            )

        menu.post(x, y)

    def create_roi_context_menu(self):
        """Cria menu de contexto para ROIs."""
        self.gui.roi_context_menu = Menu(self.gui.root, tearoff=0)
        self.gui.roi_context_menu.add_command(
            label="🔧 Editar Vértices",
            command=self.gui.canvas_manager.edit_selected_zone_vertices,
        )
        self.gui.roi_context_menu.add_separator()
        self.gui.roi_context_menu.add_command(
            label="✏️ Renomear", command=self.gui.dialog_manager.rename_selected_roi
        )
        self.gui.roi_context_menu.add_command(
            label="🎨 Mudar Cor", command=self.gui.dialog_manager.change_roi_color
        )
        self.gui.roi_context_menu.add_separator()
        self.gui.roi_context_menu.add_command(
            label="🗑️ Remover", command=self.gui.canvas_manager.remove_selected_roi
        )

    def show_roi_context_menu(self, event=None, x=None, y=None, item_id=None) -> None:
        """Show the ROI context menu.

        Args:
            event: Tkinter event object (optional)
            x: Screen X coordinate (optional, overrides event)
            y: Screen Y coordinate (optional, overrides event)
            item_id: ID of the item to show menu for (optional)
        """
        if x is None and event:
            x = event.x_root
        if y is None and event:
            y = event.y_root

        if x is None or y is None:
            return

        listbox = getattr(self.gui.zone_controls, "zone_listbox", None)
        if not listbox:
            return

        item = item_id
        if not item and event:
            item = listbox.identify_row(event.y)

        if item:
            listbox.selection_set(item)

            # Check if ROI (not main arena)
            values = listbox.item(item)["values"]
            if values and "Arena Principal" not in values[0]:
                # ROI - show full menu
                if self.gui.roi_context_menu:
                    self.gui.roi_context_menu.post(x, y)
            elif values and "Arena Principal" in values[0]:
                # Arena Principal - show limited menu (only edit vertices)
                arena_menu = Menu(self.gui.root, tearoff=0)
                arena_menu.add_command(
                    label="🔧 Editar Vértices",
                    command=self.gui.canvas_manager.edit_selected_zone_vertices,
                )
                arena_menu.post(x, y)
