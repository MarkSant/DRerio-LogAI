"""
Custom Regex Patterns Dialog

Allows user to define custom regex patterns for detecting groups, days, and subjects
from folder structure or filenames.
"""

import re
from tkinter import (
    Button,
    Entry,
    Frame,
    Label,
    Text,
    messagebox,
)
from tkinter import (
    font as tkfont,
)
from tkinter.simpledialog import Dialog

import structlog

log = structlog.get_logger()


class CustomRegexDialog(Dialog):
    r"""
    Dialog for defining custom regex patterns for design detection.

    Allows user to specify regex patterns for:
    - Groups: e.g., (Control|Treatment|Group\d+)
    - Days: e.g., Day(\d+) or D(\d+)
    - Subjects: e.g., S(\d+) or Subject(\d+)

    Args:
        parent: Parent window
        current_patterns: Current custom patterns (if any)

    Returns:
        Dict with custom patterns or None if cancelled
    """

    def __init__(self, parent, current_patterns: dict | None = None):
        """
        Initialize custom regex dialog.

        Args:
            parent: Parent window
            current_patterns: Dict with keys:
                - group_pattern: str (regex for groups)
                - day_pattern: str (regex for days)
                - subject_pattern: str (regex for subjects)
        """
        self.current_patterns = current_patterns or {}
        self.result_patterns = None

        super().__init__(parent, title="Configurar Padrões Regex Personalizados")

    def body(self, master):
        """Build dialog UI."""
        # Title
        title_font = tkfont.Font(size=12, weight="bold")
        Label(
            master,
            text="Padrões Regex Personalizados",
            font=title_font,
        ).pack(pady=(0, 10))

        subtitle = Label(
            master,
            text=(
                "Defina padrões regex personalizados para detectar grupos, dias e "
                "sujeitos.\nUse grupos de captura () para extrair os valores."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        subtitle.pack(pady=(0, 15))

        # Group pattern
        group_frame = Frame(master)
        group_frame.pack(fill="x", padx=10, pady=5)

        Label(
            group_frame,
            text="Padrão de Grupos:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        Label(
            group_frame,
            text="Ex: (Control|Treatment|Group\\d+) ou (\\w+)_Group",
            fg="gray",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w")

        self.group_pattern_entry = Entry(group_frame, width=50)
        self.group_pattern_entry.pack(fill="x", pady=5)
        self.group_pattern_entry.insert(
            0,
            self.current_patterns.get("group_pattern", "") or "",
        )

        # Day pattern
        day_frame = Frame(master)
        day_frame.pack(fill="x", padx=10, pady=5)

        Label(
            day_frame,
            text="Padrão de Dias:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        Label(
            day_frame,
            text="Ex: Day(\\d+) ou D(\\d+) ou (\\d{4}-\\d{2}-\\d{2})",
            fg="gray",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w")

        self.day_pattern_entry = Entry(day_frame, width=50)
        self.day_pattern_entry.pack(fill="x", pady=5)
        self.day_pattern_entry.insert(
            0,
            self.current_patterns.get("day_pattern", "") or "",
        )

        # Subject pattern
        subject_frame = Frame(master)
        subject_frame.pack(fill="x", padx=10, pady=5)

        Label(
            subject_frame,
            text="Padrão de Sujeitos:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        Label(
            subject_frame,
            text="Ex: S(\\d+) ou Subject(\\d+) ou Animal_(\\w+)",
            fg="gray",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w")

        self.subject_pattern_entry = Entry(subject_frame, width=50)
        self.subject_pattern_entry.pack(fill="x", pady=5)
        self.subject_pattern_entry.insert(
            0,
            self.current_patterns.get("subject_pattern", "") or "",
        )

        # Test section
        test_frame = Frame(master)
        test_frame.pack(fill="both", expand=True, padx=10, pady=15)

        Label(
            test_frame,
            text="Testar Padrões:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        Label(
            test_frame,
            text="Digite um caminho de exemplo para testar os padrões:",
            fg="gray",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w")

        test_input_frame = Frame(test_frame)
        test_input_frame.pack(fill="x", pady=5)

        self.test_path_entry = Entry(test_input_frame, width=40)
        self.test_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.test_path_entry.insert(0, "/Control/Day01/Subject_S01.mp4")

        Button(
            test_input_frame,
            text="Testar",
            command=self._test_patterns,
        ).pack(side="left")

        # Test results
        self.test_results_text = Text(test_frame, height=4, width=60, state="disabled")
        self.test_results_text.pack(fill="both", expand=True, pady=5)

        # Help text
        help_frame = Frame(master)
        help_frame.pack(fill="x", padx=10, pady=10)

        help_text = Label(
            help_frame,
            text=(
                "💡 Dicas:\n"
                "• Use grupos de captura () para extrair valores\n"
                "• \\d+ = um ou mais dígitos\n"
                "• \\w+ = um ou mais caracteres alfanuméricos\n"
                "• | = OU lógico (Control|Treatment)\n"
                "• Deixe em branco para usar detecção padrão"
            ),
            fg="gray",
            wraplength=500,
            justify="left",
            font=("TkDefaultFont", 9),
        )
        help_text.pack(anchor="w")

        return self.group_pattern_entry  # Initial focus

    def buttonbox(self):
        """Override to add OK and Cancel buttons."""
        box = Frame(self)

        Button(
            box,
            text="Salvar",
            width=10,
            command=self.ok,
            default="active",
        ).pack(side="left", padx=5, pady=5)
        Button(
            box,
            text="Cancelar",
            width=10,
            command=self.cancel,
        ).pack(side="left", padx=5, pady=5)
        Button(
            box,
            text="Limpar Tudo",
            width=12,
            command=self._clear_all,
        ).pack(side="left", padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def _test_patterns(self):
        """Test the regex patterns against the test path."""
        test_path = self.test_path_entry.get().strip()
        if not test_path:
            messagebox.showwarning(
                "Caminho Vazio",
                "Digite um caminho para testar.",
                parent=self,
            )
            return

        group_pattern = self.group_pattern_entry.get().strip()
        day_pattern = self.day_pattern_entry.get().strip()
        subject_pattern = self.subject_pattern_entry.get().strip()

        results = []

        # Test group pattern
        if group_pattern:
            try:
                match = re.search(group_pattern, test_path)
                if match:
                    results.append(
                        "✓ Grupo: '"
                        f"{match.group(1) if match.groups() else match.group(0)}'"
                    )
                else:
                    results.append("✗ Grupo: Nenhuma correspondência")
            except re.error as e:
                results.append(f"✗ Grupo: Regex inválido - {e}")
        else:
            results.append("○ Grupo: Padrão não definido")

        # Test day pattern
        if day_pattern:
            try:
                match = re.search(day_pattern, test_path)
                if match:
                    results.append(
                        "✓ Dia: '"
                        f"{match.group(1) if match.groups() else match.group(0)}'"
                    )
                else:
                    results.append("✗ Dia: Nenhuma correspondência")
            except re.error as e:
                results.append(f"✗ Dia: Regex inválido - {e}")
        else:
            results.append("○ Dia: Padrão não definido")

        # Test subject pattern
        if subject_pattern:
            try:
                match = re.search(subject_pattern, test_path)
                if match:
                    results.append(
                        "✓ Sujeito: '"
                        f"{match.group(1) if match.groups() else match.group(0)}'"
                    )
                else:
                    results.append("✗ Sujeito: Nenhuma correspondência")
            except re.error as e:
                results.append(f"✗ Sujeito: Regex inválido - {e}")
        else:
            results.append("○ Sujeito: Padrão não definido")

        # Display results
        self.test_results_text.config(state="normal")
        self.test_results_text.delete("1.0", "end")
        self.test_results_text.insert("1.0", "\n".join(results))
        self.test_results_text.config(state="disabled")

    def _clear_all(self):
        """Clear all pattern entries."""
        self.group_pattern_entry.delete(0, "end")
        self.day_pattern_entry.delete(0, "end")
        self.subject_pattern_entry.delete(0, "end")
        self.test_path_entry.delete(0, "end")
        self.test_path_entry.insert(0, "/Control/Day01/Subject_S01.mp4")

        self.test_results_text.config(state="normal")
        self.test_results_text.delete("1.0", "end")
        self.test_results_text.config(state="disabled")

    def validate(self):
        """Validate regex patterns before saving."""
        group_pattern = self.group_pattern_entry.get().strip()
        day_pattern = self.day_pattern_entry.get().strip()
        subject_pattern = self.subject_pattern_entry.get().strip()

        # Test each pattern for validity
        for name, pattern in [
            ("Grupo", group_pattern),
            ("Dia", day_pattern),
            ("Sujeito", subject_pattern),
        ]:
            if pattern:
                try:
                    re.compile(pattern)
                except re.error as e:
                    messagebox.showerror(
                        "Regex Inválido",
                        f"Padrão de {name} inválido:\n{pattern}\n\nErro: {e}",
                        parent=self,
                    )
                    return False

        return True

    def apply(self):
        """Apply changes (called when OK is clicked)."""
        self.result_patterns = {
            "group_pattern": self.group_pattern_entry.get().strip() or None,
            "day_pattern": self.day_pattern_entry.get().strip() or None,
            "subject_pattern": self.subject_pattern_entry.get().strip() or None,
        }

        # Log if any custom patterns were set
        active_patterns = [k for k, v in self.result_patterns.items() if v]
        if active_patterns:
            log.info(
                "custom_regex.saved",
                patterns=active_patterns,
            )

    def get_result(self):
        """Get custom patterns (call after dialog closes)."""
        return self.result_patterns
