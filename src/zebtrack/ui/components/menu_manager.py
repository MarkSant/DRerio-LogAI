"""Menu management for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles menu bar, context menus, and menu-related operations.
"""

import os
import tkinter.font as tkfont
from pathlib import Path
from tkinter import Menu, Toplevel, messagebox, ttk

import structlog
from PIL import Image, ImageTk

from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.events import Events

log = structlog.get_logger()


class MenuManager:
    """Manages menu bar and context menus for ApplicationGUI."""

    def __init__(self, gui):
        """Initialize MenuManager.

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui

        # Menu-related attributes
        self._overview_context_menu: Menu | None = None
        self._overview_menu_font: tkfont.Font | None = None
        self._about_logo_image = None

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

        # Help menu
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ajuda", menu=help_menu)
        help_menu.add_command(label="Sobre DRerio LogAI", command=self.show_about_dialog)

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
            text="github.com/YOUR_USERNAME/ZebTrack-AI",
            font=("TkDefaultFont", 9),
            foreground="blue",
            cursor="hand2",
        )
        repo_link.pack()

        def open_repo(event):
            import webbrowser

            webbrowser.open("https://github.com/YOUR_USERNAME/ZebTrack-AI")

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

        tags = tree.item(item_id, "tags") or ()
        video_path = None
        for tag in tags:
            if tag and not tag.startswith("status_"):
                video_path = tag
                break

        if not video_path:
            return

        # For now, show a simple context menu - can be expanded later
        if self._overview_context_menu:
            self._overview_context_menu.destroy()

        self._overview_context_menu = Menu(self.gui.root, tearoff=0)
        self._overview_context_menu.add_command(
            label="Carregar vídeo",
            command=lambda: self.gui._on_project_overview_tree_double_click_impl(item_id),
        )
        self._overview_context_menu.post(x, y)

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
        video_path: str,
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

    def handle_overview_asset_removal(self, video_path: str, asset: str) -> None:
        """Handle removal of project assets (arena, ROIs, trajectory, summary, video).

        Args:
            video_path: Path to the video file
            asset: Asset type to remove
        """
        allowed, reason = self.gui.controller.can_remove_project_asset(video_path, asset)
        if not allowed:
            self.gui.show_warning(
                "Ação indisponível",
                reason or "Não é possível remover o item selecionado neste momento.",
            )
            return

        basename = os.path.basename(video_path) or video_path
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
            self.gui.publish_event(
                Events.PROJECT_DELETE_ASSET,
                {
                    "video_path": video_path,
                    "asset": asset,
                    "delete_source": delete_files,
                },
            )
            success = True  # Assume success
        else:
            self.gui.publish_event(
                Events.PROJECT_DELETE_ASSET, {"video_path": video_path, "asset": asset}
            )
            success = True  # Assume success

        if not success:
            self.gui.show_error(
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
            self.gui.event_bus_v2.publish(Event(
                type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                data={
                    "reason": status_message,
                    "append_summary": True,
                    "immediate": True
                },
                source="MenuManager.handle_overview_asset_removal"
            ))

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

    def show_roi_context_menu(
        self, event=None, x=None, y=None, item_id=None
    ) -> None:
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
