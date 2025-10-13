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
    StringVar,
    Text,
    messagebox,
    ttk,
)
from tkinter import font as tkfont
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

    def __init__(
        self,
        parent,
        current_patterns: dict | None = None,
        sample_paths: list[str] | None = None,
    ):
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
        self.sample_paths = (sample_paths or [])[:50]
        self._live_update_job: str | None = None
        self._compiled_patterns: dict[str, re.Pattern] = {}
        self._pattern_errors: dict[str, str] = {}
        self._geometry_initialized = False

        self.group_pattern_var = StringVar(
            value=self.current_patterns.get("group_pattern", "") or ""
        )
        self.day_pattern_var = StringVar(
            value=self.current_patterns.get("day_pattern", "") or ""
        )
        self.subject_pattern_var = StringVar(
            value=self.current_patterns.get("subject_pattern", "") or ""
        )

        # Use real path from sample_paths if available
        if self.sample_paths:
            default_preview_path = self.sample_paths[0]
            log.info(
                "custom_regex.init",
                sample_count=len(self.sample_paths),
                using_real_path=True,
            )
        else:
            default_preview_path = "/Control/Day01/Subject_S01.mp4"
            log.warning(
                "custom_regex.init",
                sample_count=0,
                using_real_path=False,
                message="No sample paths provided, using default example",
            )

        self.test_path_var = StringVar(value=default_preview_path)

        super().__init__(parent, title="Configurar Padrões Regex Personalizados")

    def body(self, master):
        """Build dialog UI."""
        # Enable resizing
        try:
            self.resizable(True, True)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("custom_regex.geometry.resizable_failed", error=str(exc))

        # Title
        title_font = tkfont.Font(size=10, weight="bold")
        Label(
            master,
            text="Padrões Regex Personalizados",
            font=title_font,
        ).pack(pady=(0, 3))

        subtitle = Label(
            master,
            text=(
                "Defina padrões regex para detectar grupos, dias e sujeitos. "
                "Use grupos de captura ()."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
            font=("TkDefaultFont", 8),
        )
        subtitle.pack(pady=(0, 5))

        # Group pattern
        group_frame = Frame(master)
        group_frame.pack(fill="x", padx=10, pady=3)

        Label(
            group_frame,
            text="Padrão de Grupos:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        Label(
            group_frame,
            text="Ex: (Control|Treatment|Group\\d+) ou (\\w+)_Group",
            fg="gray",
            font=("TkDefaultFont", 8),
        ).pack(anchor="w")

        self.group_pattern_entry = Entry(
            group_frame,
            width=50,
            textvariable=self.group_pattern_var,
        )
        self.group_pattern_entry.pack(fill="x", pady=3)

        # Day pattern
        day_frame = Frame(master)
        day_frame.pack(fill="x", padx=10, pady=3)

        Label(
            day_frame,
            text="Padrão de Dias:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        Label(
            day_frame,
            text="Ex: Day(\\d+) ou D(\\d+) ou (\\d{4}-\\d{2}-\\d{2})",
            fg="gray",
            font=("TkDefaultFont", 8),
        ).pack(anchor="w")

        self.day_pattern_entry = Entry(
            day_frame,
            width=50,
            textvariable=self.day_pattern_var,
        )
        self.day_pattern_entry.pack(fill="x", pady=3)

        # Subject pattern
        subject_frame = Frame(master)
        subject_frame.pack(fill="x", padx=10, pady=3)

        Label(
            subject_frame,
            text="Padrão de Sujeitos:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        Label(
            subject_frame,
            text="Ex: S(\\d+) ou Subject(\\d+) ou Animal_(\\w+)",
            fg="gray",
            font=("TkDefaultFont", 8),
        ).pack(anchor="w")

        self.subject_pattern_entry = Entry(
            subject_frame,
            width=50,
            textvariable=self.subject_pattern_var,
        )
        self.subject_pattern_entry.pack(fill="x", pady=3)

        # Test section
        test_frame = Frame(master)
        test_frame.pack(fill="both", expand=True, padx=10, pady=5)

        Label(
            test_frame,
            text="Testar Padrões:",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w")

        test_input_frame = Frame(test_frame)
        test_input_frame.pack(fill="x", pady=2)

        self.test_path_entry = Entry(
            test_input_frame,
            width=40,
            textvariable=self.test_path_var,
        )
        self.test_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        Button(
            test_input_frame,
            text="Testar",
            command=self._test_patterns,
        ).pack(side="left")

        # Test results
        self.test_results_text = Text(test_frame, height=2, width=60, state="disabled")
        self.test_results_text.pack(fill="both", expand=True, pady=2)

        # Live preview
        preview_frame = Frame(master)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(3, 5))

        Label(
            preview_frame,
            text="Pré-visualização (Primeiros 15 caminhos)",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w")

        tree_outer = Frame(preview_frame)
        tree_outer.pack(fill="both", expand=True, pady=(2, 0))

        self.preview_tree = ttk.Treeview(
            tree_outer,
            columns=("path", "group", "day", "subject"),
            show="headings",
            height=4,
        )
        self.preview_tree.heading("path", text="Caminho")
        self.preview_tree.heading("group", text="Grupo")
        self.preview_tree.heading("day", text="Dia")
        self.preview_tree.heading("subject", text="Sujeito")
        self.preview_tree.column("path", width=260, anchor="w")
        self.preview_tree.column("group", width=100, anchor="center")
        self.preview_tree.column("day", width=80, anchor="center")
        self.preview_tree.column("subject", width=90, anchor="center")
        self.preview_tree.pack(side="left", fill="both", expand=True)

        preview_scroll = ttk.Scrollbar(
            tree_outer,
            orient="vertical",
            command=self.preview_tree.yview,
        )
        preview_scroll.pack(side="right", fill="y")
        self.preview_tree.configure(yscrollcommand=preview_scroll.set)

        self._schedule_live_update(immediate=True)

        self.group_pattern_var.trace_add("write", self._on_pattern_change)
        self.day_pattern_var.trace_add("write", self._on_pattern_change)
        self.subject_pattern_var.trace_add("write", self._on_pattern_change)
        self.test_path_var.trace_add("write", self._on_pattern_change)

        # Initialize geometry after widgets are realized
        self.after_idle(self._initialize_geometry)

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
        self._render_test_feedback(results)
        self._refresh_live_previews()

    def _clear_all(self):
        """Clear all pattern entries."""
        self.group_pattern_entry.delete(0, "end")
        self.day_pattern_entry.delete(0, "end")
        self.subject_pattern_entry.delete(0, "end")
        self.test_path_entry.delete(0, "end")
        default_preview_path = (
            self.sample_paths[0]
            if self.sample_paths
            else "/Control/Day01/Subject_S01.mp4"
        )
        self.test_path_entry.insert(0, default_preview_path)

        self.test_results_text.config(state="normal")
        self.test_results_text.delete("1.0", "end")
        self.test_results_text.config(state="disabled")
        self._schedule_live_update(immediate=True)

    def validate(self):
        """Validate regex patterns before saving."""
        group_pattern = self.group_pattern_var.get().strip()
        day_pattern = self.day_pattern_var.get().strip()
        subject_pattern = self.subject_pattern_var.get().strip()

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
            "group_pattern": self.group_pattern_var.get().strip() or None,
            "day_pattern": self.day_pattern_var.get().strip() or None,
            "subject_pattern": self.subject_pattern_var.get().strip() or None,
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

    def _initialize_geometry(self):
        """
        Configure initial geometry with conservative height.

        Sets a fixed height to ensure buttons remain visible above taskbar.
        """
        if self._geometry_initialized or not self.winfo_exists():
            return

        try:
            self.resizable(True, True)
        except Exception:
            return

        self.update_idletasks()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Reserve space for taskbar and decorations
        usable_w = screen_w - 80
        usable_h = screen_h - 220

        # Target size: moderate width, sufficient height for all buttons
        target_width = 800
        target_height = 580

        # Don't exceed available space on smaller screens
        width = min(target_width, usable_w)
        height = min(target_height, usable_h)

        # Ensure absolute minimums
        width = max(width, 700)
        height = max(height, 560)

        # Set resizable bounds
        min_width = max(int(target_width * 0.85), 650)
        min_height = max(int(target_height * 0.90), 430)
        max_width = int(target_width * 1.20)
        max_height = int(target_height * 1.15)

        # Center on screen, but shift UP to avoid taskbar
        x = max((screen_w - width) // 2, 0)
        y = max((screen_h - height - 100) // 2, 0)  # Shift 100px higher

        self.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")
        self.minsize(int(min_width), int(min_height))
        self.maxsize(int(max_width), int(max_height))

        self._geometry_initialized = True
        log.info(
            "custom_regex.geometry_initialized",
            size=f"{int(width)}×{int(height)}",
            screen=f"{screen_w}×{screen_h}",
            position=f"+{int(x)}+{int(y)}",
        )

    # ------------------------------------------------------------------
    # Live preview helpers

    def _on_pattern_change(self, *_args):
        self._schedule_live_update()

    def _schedule_live_update(self, *, immediate: bool = False):
        if self._live_update_job is not None:
            try:
                self.after_cancel(self._live_update_job)
            except Exception:
                pass
            self._live_update_job = None

        delay = 0 if immediate else 150
        self._live_update_job = self.after(delay, self._refresh_live_previews)

    def _refresh_live_previews(self):
        self._live_update_job = None
        compiled, errors = self._compile_patterns()
        self._compiled_patterns = compiled
        self._pattern_errors = errors

        self._render_test_feedback()
        self._update_live_preview()

    def _compile_patterns(self) -> tuple[dict[str, re.Pattern], dict[str, str]]:
        compiled: dict[str, re.Pattern] = {}
        errors: dict[str, str] = {}

        for key, var in (
            ("group", self.group_pattern_var),
            ("day", self.day_pattern_var),
            ("subject", self.subject_pattern_var),
        ):
            pattern = var.get().strip()
            if not pattern:
                continue
            try:
                compiled[key] = re.compile(pattern)
            except re.error as exc:  # pragma: no cover - defensive
                errors[key] = str(exc)

        return compiled, errors

    def _render_test_feedback(self, preset_results: list[str] | None = None):
        if preset_results is None:
            test_path = self.test_path_var.get().strip()
            results = self._evaluate_path(test_path)
        else:
            results = preset_results

        self.test_results_text.config(state="normal")
        self.test_results_text.delete("1.0", "end")
        self.test_results_text.insert("1.0", "\n".join(results))
        self.test_results_text.config(state="disabled")

    def _evaluate_path(self, path: str) -> list[str]:
        if not path:
            return ["✗ Informe um caminho para testar"]

        lines: list[str] = []

        for label, key in (
            ("Grupo", "group"),
            ("Dia", "day"),
            ("Sujeito", "subject"),
        ):
            pattern_str = getattr(self, f"{key}_pattern_var").get().strip()
            if not pattern_str:
                lines.append(f"○ {label}: Padrão não definido")
                continue

            error = self._pattern_errors.get(key)
            if error:
                lines.append(f"✗ {label}: Regex inválido - {error}")
                continue

            pattern = self._compiled_patterns.get(key)
            if not pattern:
                lines.append(f"✗ {label}: Regex inválido")
                continue

            match = pattern.search(path)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                lines.append(f"✓ {label}: '{value}'")
            else:
                lines.append(f"✗ {label}: Nenhuma correspondência")

        return lines

    def _update_live_preview(self):
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)

        if not self.sample_paths:
            self.preview_tree.insert(
                "",
                "end",
                values=(
                    "Adicione vídeos na etapa anterior",
                    "-",
                    "-",
                    "-",
                ),
            )
            return

        display_paths = self.sample_paths[:15]
        for path in display_paths:
            results = self._match_path(path)
            self.preview_tree.insert(
                "",
                "end",
                values=(
                    results["path"],
                    results["group"],
                    results["day"],
                    results["subject"],
                ),
            )

        if len(self.sample_paths) > len(display_paths):
            remaining = len(self.sample_paths) - len(display_paths)
            self.preview_tree.insert(
                "",
                "end",
                values=(f"… {remaining} caminho(s) adicionais", "", "", ""),
            )

    def _match_path(self, path: str) -> dict[str, str]:
        display_path = path
        if len(path) > 65:
            display_path = f"…{path[-64:]}"

        result = {"path": display_path, "group": "-", "day": "-", "subject": "-"}

        for label, key in (
            ("group", "group"),
            ("day", "day"),
            ("subject", "subject"),
        ):
            error = self._pattern_errors.get(key)
            if error:
                result[label] = "Erro"
                continue

            pattern = self._compiled_patterns.get(key)
            if not pattern:
                continue

            match = pattern.search(path)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                result[label] = value

        return result
