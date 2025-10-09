"""
Step 2: File Selection Dialog

Allows user to select video files and folders for analysis.
Provides summary of selection and validates that at least one video is chosen.
"""

import os
from tkinter import (
    Button,
    Frame,
    Label,
    LabelFrame,
    Listbox,
    Scrollbar,
    StringVar,
    filedialog,
    ttk,
)
from tkinter import font as tkfont

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip

MAX_TREE_DEPTH = 3
MAX_TREE_CHILDREN = 12
MAX_TREE_NODES = 120


class FileSelectionStep(WizardStep):
    """
    File Selection step - gather video files/folders.

    Questions:
        - Which video files/folders do you want to analyze?

    Output:
        {
            "video_paths": [str, ...],  # Mixed: file paths and folder paths
            "summary": {
                "total_files": int,
                "total_folders": int,
                "estimated_videos": int  # After recursive scan
            }
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize file selection step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.FILE_SELECTION

        # UI state
        self.video_paths = []  # Mixed: files and folders
        self.summary_var = StringVar(value="Nenhum vídeo/pasta selecionado.")
        self.template_info_var = StringVar(value="")
        self.template_info_label = None
        self.folder_tree = None
        self.folder_tree_placeholder = None
        self.folder_preview_data: list[dict] = []

    def build_ui(self):
        """Build file selection UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self, text="Seleção de Vídeos", font=title_font
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text=(
                "Selecione os vídeos que deseja analisar (arquivos individuais ou "
                "pastas inteiras)."
            ),
            fg="gray",
            wraplength=500,
        )
        subtitle.pack(pady=(0, 20))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=500,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # Selection buttons
        button_frame = Frame(self)
        button_frame.pack(pady=(0, 15))

        btn_files = Button(
            button_frame,
            text="📁 Adicionar Arquivos...",
            command=self._select_video_files,
            width=20,
        )
        btn_files.pack(side="left", padx=5)
        ToolTip(
            btn_files,
            (
                "Selecionar vídeos individuais (.mp4, .avi, .mov). Suporta "
                "seleção múltipla (Ctrl+Click)."
            ),
        )

        btn_folder = Button(
            button_frame,
            text="📂 Adicionar Pasta...",
            command=self._select_video_folder,
            width=20,
        )
        btn_folder.pack(side="left", padx=5)
        ToolTip(
            btn_folder,
            (
                "Selecionar pasta contendo vídeos. O wizard fará varredura "
                "recursiva nas subpastas automaticamente."
            ),
        )

        btn_remove = Button(
            button_frame,
            text="❌ Remover Selecionado",
            command=self._remove_selected,
            width=20,
        )
        btn_remove.pack(side="left", padx=5)
        ToolTip(
            btn_remove,
            (
                "Remover o item selecionado na lista (clique no item para "
                "selecioná-lo)."
            ),
        )

        btn_clear = Button(
            button_frame,
            text="🗑️ Limpar Tudo",
            command=self._clear_selection,
            width=20,
        )
        btn_clear.pack(side="left", padx=5)
        ToolTip(
            btn_clear,
            "Remover todos os vídeos e pastas selecionados.",
        )

        # Summary
        summary_frame = LabelFrame(self, text="Resumo da Seleção", padx=10, pady=10)
        summary_frame.pack(fill="x", pady=(0, 15))

        Label(
            summary_frame,
            textvariable=self.summary_var,
            fg="blue",
            wraplength=500,
            justify="left",
        ).pack(anchor="w")

        # List of selected paths
        list_frame = LabelFrame(self, text="Itens Selecionados", padx=10, pady=10)
        list_frame.pack(fill="both", expand=True)

        # Scrollable listbox
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.paths_listbox = Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            height=10,
        )
        self.paths_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.paths_listbox.yview)

        # Folder preview tree
        tree_frame = LabelFrame(
            self,
            text="Pré-visualização da Estrutura",
            padx=10,
            pady=10,
        )
        tree_frame.pack(fill="both", expand=True, pady=(10, 0))

        tree_scroll = Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")

        self.folder_tree = ttk.Treeview(
            tree_frame,
            columns=("detalhes",),
            show="tree headings",
            height=8,
        )
        self.folder_tree.column("#0", width=280, stretch=True)
        self.folder_tree.column("detalhes", width=160, stretch=True)
        self.folder_tree.heading("#0", text="Pasta / Arquivo")
        self.folder_tree.heading("detalhes", text="Resumo")
        self.folder_tree.pack(side="left", fill="both", expand=True)
        self.folder_tree.config(yscrollcommand=tree_scroll.set)
        tree_scroll.config(command=self.folder_tree.yview)

        self.folder_tree_placeholder = Label(
            tree_frame,
            text=(
                "Selecione pastas para visualizar a estrutura. Arquivos isolados "
                "são listados automaticamente."
            ),
            fg="#666666",
            wraplength=460,
            justify="left",
        )
        self.folder_tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Help text
        help_text = Label(
            self,
            text=(
                "💡 Dica: Ao selecionar pastas, todos os vídeos dentro delas "
                "(incluindo subpastas) serão incluídos."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack(pady=(15, 0))
        self._update_template_banner()

    def _select_video_files(self):
        """Open file dialog to select video files."""
        files = filedialog.askopenfilenames(
            title="Selecione os Arquivos de Vídeo",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if files:
            # Add new files (avoid duplicates)
            for f in files:
                if f not in self.video_paths:
                    self.video_paths.append(f)

            self._update_display()

    def _select_video_folder(self):
        """Open folder dialog to select a directory."""
        folder = filedialog.askdirectory(
            title="Selecione uma Pasta Contendo Vídeos"
        )
        if folder:
            # Add folder (avoid duplicates)
            if folder not in self.video_paths:
                self.video_paths.append(folder)

            self._update_display()

    def _remove_selected(self):
        """Remove currently selected item from the list."""
        selection = self.paths_listbox.curselection()
        if selection:
            index = selection[0]
            # Remove from data
            del self.video_paths[index]
            # Refresh display
            self._update_display()

    def _clear_selection(self):
        """Clear all selected paths."""
        self.video_paths = []
        self._update_display()

    def _update_display(self):
        """Update summary and listbox with current selection."""
        # Update listbox
        self.paths_listbox.delete(0, "end")
        for path in self.video_paths:
            # Show type indicator
            if os.path.isfile(path):
                display_name = f"📄 {os.path.basename(path)}"
            else:
                display_name = f"📁 {os.path.basename(path)}"

            self.paths_listbox.insert("end", display_name)

        # Update summary
        if not self.video_paths:
            self.summary_var.set("Nenhum vídeo/pasta selecionado.")
            self.folder_preview_data = []
            self._refresh_folder_preview()
            return

        # Count files and folders
        files = [p for p in self.video_paths if os.path.isfile(p)]
        folders = [p for p in self.video_paths if os.path.isdir(p)]

        parts = []
        if files:
            parts.append(f"{len(files)} arquivo(s)")
        if folders:
            parts.append(f"{len(folders)} pasta(s)")

        summary = " + ".join(parts) + " selecionado(s)"

        # Estimate total videos (quick count, not recursive yet)
        # Full scan will happen in Step 3
        if folders:
            summary += " (detecção de vídeos em pastas será feita na próxima etapa)"

        self.summary_var.set(summary)
        self.folder_preview_data = self._build_folder_preview_data(files, folders)
        self._refresh_folder_preview()

    def validate(self) -> tuple[bool, str]:
        """
        Validate file selection.

        Returns:
            tuple[bool, str]: (True, "") if at least 1 video/folder selected,
                             (False, error_message) otherwise
        """
        if not self.video_paths:
            return (
                False,
                "Por favor, selecione pelo menos um arquivo de vídeo ou pasta.",
            )

        # Basic validation: check that paths exist
        invalid_paths = [p for p in self.video_paths if not os.path.exists(p)]
        if invalid_paths:
            return (
                False,
                f"Os seguintes caminhos não existem:\n{chr(10).join(invalid_paths)}",
            )

        return (True, "")

    def get_data(self) -> dict:
        """
        Extract file selection data.

        Returns:
            dict: File selection data with keys:
                - video_paths (list[str]): Selected file/folder paths
                - summary (dict): Quick summary for logging
        """
        files = [p for p in self.video_paths if os.path.isfile(p)]
        folders = [p for p in self.video_paths if os.path.isdir(p)]

        if self.video_paths and not self.folder_preview_data:
            self.folder_preview_data = self._build_folder_preview_data(files, folders)

        return {
            "video_paths": self.video_paths,
            "summary": {
                "total_files": len(files),
                "total_folders": len(folders),
                "total_paths": len(self.video_paths),
            },
            "folder_preview": self.folder_preview_data,
        }

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected file selection data
        """
        if "video_paths" in data:
            self.video_paths = data["video_paths"]
            self.folder_preview_data = data.get("folder_preview", [])
            self._update_display()
        self._update_template_banner()

    def on_show(self):
        """Called when step becomes visible."""
        # Refresh display in case data changed
        self._update_display()
        self._update_template_banner()

    def _refresh_folder_preview(self):
        if not self.folder_tree:
            return

        for item in self.folder_tree.get_children():
            self.folder_tree.delete(item)

        if not self.folder_preview_data:
            if self.folder_tree_placeholder:
                self.folder_tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            return

        if self.folder_tree_placeholder:
            self.folder_tree_placeholder.place_forget()

        for entry in self.folder_preview_data:
            details = self._format_entry_details(entry.get("counts", {}))
            root_text = entry.get("label", entry.get("path", ""))
            root_id = self.folder_tree.insert(
                "",
                "end",
                text=root_text,
                values=(details,),
            )
            for node in entry.get("nodes", []):
                self._insert_tree_node(root_id, node)

            if entry.get("truncated"):
                self.folder_tree.insert(
                    root_id,
                    "end",
                    text="…",
                    values=("Prévia limitada",),
                )

    def _insert_tree_node(self, parent_id: str, node: dict):
        text = node.get("label", node.get("path", ""))
        details = self._format_entry_details(node.get("counts", {}))
        node_id = self.folder_tree.insert(
            parent_id,
            "end",
            text=text,
            values=(details,),
        )
        for child in node.get("children", []):
            self._insert_tree_node(node_id, child)

    def _build_folder_preview_data(
        self,
        files: list[str],
        folders: list[str],
    ) -> list[dict]:
        preview: list[dict] = []

        for folder in sorted(folders):
            entry = self._scan_folder(folder)
            preview.append(entry)

        if files:
            file_nodes = []
            for path in sorted(files):
                base = os.path.basename(path)
                file_nodes.append(
                    {
                        "label": f"📄 {base}",
                        "path": path,
                        "counts": {"files": 1, "folders": 0},
                        "children": [],
                    }
                )

            preview.append(
                {
                    "label": "Arquivos Individuais",
                    "path": "files",
                    "counts": {"files": len(files), "folders": 0},
                    "nodes": file_nodes,
                    "truncated": False,
                }
            )

        return preview

    def _scan_folder(self, folder: str) -> dict:
        budget = {"remaining": MAX_TREE_NODES}
        nodes, counts, truncated = self._walk_folder(folder, depth=0, budget=budget)
        label = f"📁 {os.path.basename(folder) or folder}"
        return {
            "label": label,
            "path": folder,
            "counts": counts,
            "nodes": nodes,
            "truncated": truncated or budget["remaining"] <= 0,
        }

    def _walk_folder(
        self,
        path: str,
        *,
        depth: int,
        budget: dict,
    ) -> tuple[list[dict], dict, bool]:
        counts = {"files": 0, "folders": 0}
        if depth >= MAX_TREE_DEPTH or budget["remaining"] <= 0:
            return [], counts, True

        try:
            entries = sorted(
                os.scandir(path),
                key=lambda entry: (not entry.is_dir(), entry.name.lower()),
            )
        except (FileNotFoundError, PermissionError, NotADirectoryError):
            return [], counts, False

        nodes: list[dict] = []
        truncated = False

        for entry in entries:
            if budget["remaining"] <= 0:
                truncated = True
                break
            if len(nodes) >= MAX_TREE_CHILDREN:
                truncated = True
                break

            budget["remaining"] -= 1

            if entry.is_dir():
                counts["folders"] += 1
                child_nodes, child_counts, child_truncated = self._walk_folder(
                    entry.path,
                    depth=depth + 1,
                    budget=budget,
                )

                counts["files"] += child_counts["files"]
                counts["folders"] += child_counts["folders"]

                node = {
                    "label": f"📁 {entry.name}",
                    "path": entry.path,
                    "counts": child_counts,
                    "children": child_nodes,
                }
                nodes.append(node)
                truncated = truncated or child_truncated
            else:
                counts["files"] += 1
                node = {
                    "label": f"📄 {entry.name}",
                    "path": entry.path,
                    "counts": {"files": 1, "folders": 0},
                    "children": [],
                }
                nodes.append(node)

        return nodes, counts, truncated

    def _format_entry_details(self, counts: dict) -> str:
        files = counts.get("files", 0)
        folders = counts.get("folders", 0)
        parts = []
        if folders:
            parts.append(f"{folders} pasta(s)")
        if files:
            parts.append(f"{files} arquivo(s)")
        if not parts:
            return "vazio"
        return ", ".join(parts)

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if (
                self.template_info_label
                and not self.template_info_label.winfo_ismapped()
            ):
                self.template_info_label.pack(pady=(0, 10))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()
