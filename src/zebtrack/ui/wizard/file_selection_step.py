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
)
from tkinter import (
    font as tkfont,
)

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip


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

        return {
            "video_paths": self.video_paths,
            "summary": {
                "total_files": len(files),
                "total_folders": len(folders),
                "total_paths": len(self.video_paths),
            },
        }

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected file selection data
        """
        if "video_paths" in data:
            self.video_paths = data["video_paths"]
            self._update_display()
        self._update_template_banner()

    def on_show(self):
        """Called when step becomes visible."""
        # Refresh display in case data changed
        self._update_display()
        self._update_template_banner()

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
