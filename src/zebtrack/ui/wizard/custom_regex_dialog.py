"""
Custom Regex Patterns Dialog.

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
        self.day_pattern_var = StringVar(value=self.current_patterns.get("day_pattern", "") or "")
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

        # Title (full width)
        title_font = tkfont.Font(size=10, weight="bold")
        Label(
            master,
            text="Padrões Regex Personalizados",
            font=title_font,
        ).pack(pady=(0, 2))

        subtitle = Label(
            master,
            text=(
                "Defina regex para detectar grupos, dias e sujeitos. "
                "Use grupos de captura () ou nomeados (?P<nome>) para extrair os valores."
            ),
            fg="gray",
            wraplength=760,
            justify="left",
            font=("TkDefaultFont", 8),
        )
        subtitle.pack(pady=(0, 5))

        # HORIZONTAL 2-COLUMN LAYOUT
        content_frame = Frame(master)
        content_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        content_frame.columnconfigure(0, weight=11, minsize=440)  # Left 55%
        content_frame.columnconfigure(1, weight=9, minsize=360)   # Right 45%
        content_frame.rowconfigure(0, weight=1)

        # LEFT COLUMN: Tips + Examples + Pattern fields
        left_panel = Frame(content_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        tips_frame = ttk.LabelFrame(left_panel, text="Dicas rápidas", padding=(6, 4))
        tips_frame.pack(fill="x", pady=(0, 5))
        Label(
            tips_frame,
            text=(
                "• Campos vazios permanecem inalterados no design.\n"
                "• \\d captura dígitos (0-9); \\w cobre letras, números e _.\n"
                "• Âncoras ^ (início) e $ (fim) fixam o padrão completo.\n"
                "• A pré-visualização calcula automaticamente após cada edição."
            ),
            justify="left",
            wraplength=420,
            fg="#4a4a4a",
            font=("TkDefaultFont", 8),
        ).pack(anchor="w")

        # Examples section
        examples_frame = ttk.LabelFrame(left_panel, text="📚 Exemplos Comuns", padding=(6, 4))
        examples_frame.pack(fill="x", pady=(0, 5))

        # Define common examples
        examples = [
            {
                "desc": "Grupo no nome do arquivo",
                "pattern": r"(Control|Treatment)",
                "example": "Video_Control_Day1.mp4",
                "field": "group",
            },
            {
                "desc": "Dia com número",
                "pattern": r"Day(\d+)",
                "example": "Day01_Subject_S1.mp4",
                "field": "day",
            },
            {
                "desc": "Sujeito com prefixo S",
                "pattern": r"S(\d+)",
                "example": "Group1_Day2_S03.mp4",
                "field": "subject",
            },
            {
                "desc": "Grupo em pasta (qualquer palavra)",
                "pattern": r"(\w+)",
                "example": "/Control/Day1/Video.mp4",
                "field": "group",
            },
        ]

        for i, ex in enumerate(examples):
            row = Frame(examples_frame)
            row.pack(fill="x", pady=1)

            # Description
            desc_label = Label(
                row,
                text=f"{ex['desc']}:",
                width=22,
                anchor="w",
                font=("TkDefaultFont", 8),
            )
            desc_label.pack(side="left", padx=(0, 3))

            # Pattern display
            pattern_label = Label(
                row,
                text=ex["pattern"],
                fg="#0066cc",
                font=("Courier", 8),
                anchor="w",
                width=18,
            )
            pattern_label.pack(side="left", padx=(0, 3))

            # Use button
            use_btn = Button(
                row,
                text="Usar",
                command=lambda p=ex["pattern"], f=ex["field"]: self._apply_example_pattern(f, p),
                width=5,
                font=("TkDefaultFont", 8),
            )
            use_btn.pack(side="left", padx=(0, 3))

            # Example filename
            ex_label = Label(
                row,
                text=f"Ex: {ex['example']}",
                fg="gray",
                font=("TkDefaultFont", 7),
                anchor="w",
            )
            ex_label.pack(side="left")

        # Group pattern
        group_frame = Frame(left_panel)
        group_frame.pack(fill="x", pady=(0, 4))

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
            width=42,
            textvariable=self.group_pattern_var,
        )
        self.group_pattern_entry.pack(fill="x", pady=2)

        # Day pattern
        day_frame = Frame(left_panel)
        day_frame.pack(fill="x", pady=(0, 4))

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
            width=42,
            textvariable=self.day_pattern_var,
        )
        self.day_pattern_entry.pack(fill="x", pady=2)

        # Subject pattern
        subject_frame = Frame(left_panel)
        subject_frame.pack(fill="x", pady=(0, 0))

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
            width=42,
            textvariable=self.subject_pattern_var,
        )
        self.subject_pattern_entry.pack(fill="x", pady=2)

        # RIGHT COLUMN: Test + Results + Preview
        right_panel = Frame(content_frame)
        right_panel.grid(row=0, column=1, sticky="nsew")

        # Test section
        test_frame = Frame(right_panel)
        test_frame.pack(fill="both", expand=True)

        Label(
            test_frame,
            text="Testar Padrões:",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w")

        test_input_frame = Frame(test_frame)
        test_input_frame.pack(fill="x", pady=2)

        self.test_path_entry = Entry(
            test_input_frame,
            width=28,
            textvariable=self.test_path_var,
        )
        self.test_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 3))

        Button(
            test_input_frame,
            text="Testar",
            command=self._test_patterns,
        ).pack(side="left")

        # Test results displayed side by side
        results_container = ttk.Frame(test_frame)
        results_container.pack(fill="x", pady=(4, 2))
        results_container.columnconfigure(0, weight=1)
        results_container.columnconfigure(1, weight=1)
        results_container.columnconfigure(2, weight=1)

        self._test_result_vars: dict[str, StringVar] = {}
        for idx, (key, label_text) in enumerate(
            (("group", "Grupo"), ("day", "Dia"), ("subject", "Sujeito"))
        ):
            slot = ttk.Frame(results_container, padding=(6, 4))
            slot.grid(row=0, column=idx, sticky="nsew")
            ttk.Label(slot, text=label_text, font=("TkDefaultFont", 8, "bold")).pack(anchor="w")
            value_var = StringVar(value=f"○ {label_text}: aguardando")
            Label(
                slot,
                textvariable=value_var,
                justify="left",
                wraplength=160,
                fg="#333333",
                font=("TkDefaultFont", 8),
            ).pack(anchor="w")
            self._test_result_vars[key] = value_var

        self._test_summary_var = StringVar(value="")
        Label(
            test_frame,
            textvariable=self._test_summary_var,
            fg="#666666",
            font=("TkDefaultFont", 8),
            justify="left",
            wraplength=340,
        ).pack(anchor="w", pady=(0, 2))
        Label(
            test_frame,
            text="Legenda: ✓ correspondeu • ✗ falhou • ○ não definido",
            fg="gray",
            font=("TkDefaultFont", 8),
        ).pack(anchor="w", pady=(0, 2))

        # Live preview (in right panel)
        preview_frame = Frame(right_panel)
        preview_frame.pack(fill="both", expand=True, pady=(5, 0))

        Label(
            preview_frame,
            text="Pré-visualização automática (até 15 caminhos)",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w")

        tree_outer = Frame(preview_frame)
        tree_outer.pack(fill="both", expand=True, pady=(2, 0))

        self.preview_tree = ttk.Treeview(
            tree_outer,
            columns=("path", "group", "day", "subject"),
            show="headings",
            height=7,
        )
        self.preview_tree.heading("path", text="Caminho")
        self.preview_tree.heading("group", text="Grupo")
        self.preview_tree.heading("day", text="Dia")
        self.preview_tree.heading("subject", text="Sujeito")
        self.preview_tree.column("path", width=160, anchor="w")
        self.preview_tree.column("group", width=70, anchor="center")
        self.preview_tree.column("day", width=60, anchor="center")
        self.preview_tree.column("subject", width=60, anchor="center")
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

    def _apply_example_pattern(self, field: str, pattern: str):
        """
        Apply an example pattern to the corresponding field.

        Args:
            field: Field name ('group', 'day', or 'subject')
            pattern: Regex pattern to apply
        """
        if field == "group":
            self.group_pattern_var.set(pattern)
            self.group_pattern_entry.focus_set()
        elif field == "day":
            self.day_pattern_var.set(pattern)
            self.day_pattern_entry.focus_set()
        elif field == "subject":
            self.subject_pattern_var.set(pattern)
            self.subject_pattern_entry.focus_set()

        # Trigger live update
        self._schedule_live_update()

        log.info(
            "custom_regex.example_applied",
            field=field,
            pattern=pattern,
        )

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
        self._schedule_live_update(immediate=True)

    def _clear_all(self):
        """Clear all pattern entries."""
        self.group_pattern_entry.delete(0, "end")
        self.day_pattern_entry.delete(0, "end")
        self.subject_pattern_entry.delete(0, "end")
        self.test_path_entry.delete(0, "end")
        default_preview_path = (
            self.sample_paths[0] if self.sample_paths else "/Control/Day01/Subject_S01.mp4"
        )
        self.test_path_entry.insert(0, default_preview_path)
        for key, var in self._test_result_vars.items():
            label_name = {"group": "Grupo", "day": "Dia", "subject": "Sujeito"}.get(key, key)
            var.set(f"○ {label_name}: aguardando")
        self._test_summary_var.set("")
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
        usable_h = screen_h - 160

        # Target size: Reduced to fit 1080p screens with taskbar/scaling
        # Previous: 800×960 (too tall for 1080p)
        # New: 800×780 (fits comfortably with taskbar)
        target_width = 800
        target_height = 780

        # Don't exceed available space on smaller screens
        width = min(target_width, usable_w)
        height = min(target_height, usable_h)

        # Ensure absolute minimums
        width = max(width, 700)
        height = max(height, 580)

        # Set resizable bounds
        min_width = max(int(target_width * 0.85), 650)
        min_height = max(int(target_height * 0.75), 550)
        max_width = int(target_width * 1.25)
        max_height = min(int(target_height * 1.15), max(usable_h, height))

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

    def _render_test_feedback(self, preset_results: dict[str, str] | None = None):
        if preset_results is None:
            test_path = self.test_path_var.get().strip()
            results = self._evaluate_path(test_path)
        else:
            results = preset_results

        label_map = {"group": "Grupo", "day": "Dia", "subject": "Sujeito"}
        for key, label_name in label_map.items():
            value = results.get(key) or f"○ {label_name}: aguardando"
            var = self._test_result_vars.get(key)
            if var is not None:
                var.set(value)

        summary_text = results.get("summary", "")
        self._test_summary_var.set(summary_text)

    def _evaluate_path(self, path: str) -> dict[str, str]:
        label_map = {"group": "Grupo", "day": "Dia", "subject": "Sujeito"}
        results: dict[str, str] = {}

        summary = "" if path else "✗ Informe um caminho para testar"

        for key, label in label_map.items():
            pattern_str = getattr(self, f"{key}_pattern_var").get().strip()
            if not pattern_str:
                results[key] = f"○ {label}: Padrão não definido"
                continue

            error = self._pattern_errors.get(key)
            if error:
                results[key] = f"✗ {label}: Regex inválido - {error}"
                continue

            pattern = self._compiled_patterns.get(key)
            if not pattern:
                try:
                    pattern = re.compile(pattern_str)
                except re.error as exc:
                    results[key] = f"✗ {label}: Regex inválido - {exc}"
                    continue

            if not path:
                results[key] = f"✗ {label}: Informe um caminho"
                continue

            match = pattern.search(path)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                results[key] = f"✓ {label}: '{value}'"
            else:
                results[key] = f"✗ {label}: Nenhuma correspondência"

        results["summary"] = summary
        return results

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
            matches = self._match_path_all(path)
            for result in matches:
                self.preview_tree.insert(
                    "",
                    "end",
                    values=(
                        result["path"],
                        result["group"],
                        result["day"],
                        result["subject"],
                    ),
                )

        if len(self.sample_paths) > len(display_paths):
            remaining = len(self.sample_paths) - len(display_paths)
            self.preview_tree.insert(
                "",
                "end",
                values=(f"… {remaining} caminho(s) adicionais", "", "", ""),
            )

    def _match_path_all(self, path: str) -> list[dict[str, str]]:
        """Match all occurrences of the patterns in the path.

        Returns a list of dictionaries, one per match found.
        If patterns match multiple times (e.g., G1_D1_S1--G1_D1_S2),
        returns multiple results.
        """
        display_path = path
        if len(path) > 65:
            display_path = f"…{path[-64:]}"

        # Collect all matches for each pattern
        all_group_matches = []
        all_day_matches = []
        all_subject_matches = []

        for key, match_list in [
            ("group", all_group_matches),
            ("day", all_day_matches),
            ("subject", all_subject_matches),
        ]:
            error = self._pattern_errors.get(key)
            if error:
                match_list.append("Erro")
                continue

            pattern = self._compiled_patterns.get(key)
            if not pattern:
                match_list.append("-")
                continue

            # Use finditer to get ALL matches
            matches = list(pattern.finditer(path))
            if matches:
                for m in matches:
                    value = m.group(1) if m.groups() else m.group(0)
                    match_list.append(value)
            else:
                match_list.append("-")

        # Determine how many rows to create (max matches across all fields)
        max_matches = max(
            len(all_group_matches),
            len(all_day_matches),
            len(all_subject_matches),
        )

        if max_matches <= 1:
            # Single or no match - return as before
            return [
                {
                    "path": display_path,
                    "group": all_group_matches[0] if all_group_matches else "-",
                    "day": all_day_matches[0] if all_day_matches else "-",
                    "subject": all_subject_matches[0] if all_subject_matches else "-",
                }
            ]

        # Multiple matches - create one row per match
        results = []
        for i in range(max_matches):
            group_val = all_group_matches[i] if i < len(all_group_matches) else "-"
            day_val = all_day_matches[i] if i < len(all_day_matches) else "-"
            subject_val = all_subject_matches[i] if i < len(all_subject_matches) else "-"

            # Add match indicator to path for clarity
            if i == 0:
                path_display = f"{display_path} (match {i + 1})"
            else:
                path_display = f"  └─ (match {i + 1})"

            results.append(
                {
                    "path": path_display,
                    "group": group_val,
                    "day": day_val,
                    "subject": subject_val,
                }
            )

        return results

    def _match_path(self, path: str) -> dict[str, str]:
        """Legacy method - returns first match only."""
        results = self._match_path_all(path)
        return (
            results[0]
            if results
            else {
                "path": path[:65] if len(path) <= 65 else f"…{path[-64:]}",
                "group": "-",
                "day": "-",
                "subject": "-",
            }
        )
