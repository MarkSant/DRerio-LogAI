"""
AquariumAssignmentDialog - Dialog for assigning groups to each aquarium.

Displayed when:
- Auto-detection finds 2 aquariums
- User draws the 2nd aquarium manually

Allows assigning group, subject_id, and day to each aquarium.
"""

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import simpledialog, ttk

import structlog

from zebtrack.ui.wizard.models import AquariumConfig, MultiAquariumData

log = structlog.get_logger()


class AquariumAssignmentDialog(simpledialog.Dialog):
    """Dialog for assigning experimental groups to each aquarium.

    Layout:
    ┌──────────────────────────────────────────────┐
    │  Configuração dos Aquários                   │
    ├──────────────────────────────────────────────┤
    │  ┌─ Aquário 1 (Esquerda) ─────────────────┐  │
    │  │ Grupo:    [Combobox: Controle     ▼]  │  │
    │  │ Sujeito:  [Entry: S01              ]  │  │
    │  │ Dia:      [Spinbox: 1        ▲▼   ]  │  │
    │  └───────────────────────────────────────┘  │
    │                                              │
    │  ┌─ Aquário 2 (Direita) ──────────────────┐  │
    │  │ Grupo:    [Combobox: Tratamento   ▼]  │  │
    │  │ Sujeito:  [Entry: S02              ]  │  │
    │  │ Dia:      [Spinbox: 1        ▲▼   ]  │  │
    │  └───────────────────────────────────────┘  │
    │                                              │
    │  ☑ Aplicar para todos os vídeos do batch    │
    │                                              │
    │           [Cancelar]  [Confirmar]           │
    └──────────────────────────────────────────────┘
    """

    def __init__(
        self,
        parent: tk.Toplevel | tk.Tk,
        available_groups: list[str],
        video_path: Path | str | None = None,
        multi_aquarium_config: "MultiAquariumData | None" = None,
        entry_metadata: dict | None = None,
        on_confirm: Callable[[list[AquariumConfig], bool], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ):
        """Initialize the aquarium assignment dialog.

        Args:
            parent: Parent widget.
            available_groups: List of available group names.
            video_path: Path to the video being configured.
            multi_aquarium_config: Config object with regex patterns.
            entry_metadata: Pre-existing metadata from project entry (group, subject, day).
            on_confirm: Callback with (configs, apply_to_all) when confirmed.
            on_cancel: Callback when cancelled.
        """
        self.available_groups = available_groups or ["Controle", "Tratamento"]
        self.video_path = video_path
        self.multi_aquarium_config = multi_aquarium_config
        self.entry_metadata = entry_metadata or {}
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self.result: list[AquariumConfig] | None = None
        self.apply_to_all: bool = False

        # Variables for form fields
        self._group_vars: list[tk.StringVar] = []
        self._group_combos: list[ttk.Combobox] = []  # Store comboboxes for dynamic updates
        self._subject_vars: list[tk.StringVar] = []
        self._day_vars: list[tk.IntVar] = []
        self._apply_all_var: tk.BooleanVar | None = None

        print("[DIAGNOSTIC] AquariumAssignmentDialog.__init__ called")
        print(f"[DIAGNOSTIC] video_path={video_path}")
        print(f"[DIAGNOSTIC] has_multi_aquarium_config={bool(multi_aquarium_config)}")
        if multi_aquarium_config:
            print(
                f"[DIAGNOSTIC] regex_pattern="
                f"{getattr(multi_aquarium_config, 'regex_pattern', 'NONE')}"
            )

        log.debug(
            "aquarium_assignment.dialog.init",
            video_path=video_path,
            groups=available_groups,
        )

        super().__init__(parent, "Configuração dos Aquários")

    def body(self, master: tk.Frame) -> tk.Widget | None:
        """Create dialog body with aquarium configuration forms.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        master.config(padx=20, pady=15)

        # Header
        header_label = ttk.Label(
            master,
            text="Atribua grupos e identificadores para cada aquário",
            font=("Helvetica", 11, "bold"),
        )
        header_label.pack(pady=(0, 5))

        # Show current filename if available
        if self.video_path:
            import os

            filename = os.path.basename(self.video_path)
            ttk.Label(
                master, text=f"Arquivo: {filename}", font=("Helvetica", 9), foreground="#666666"
            ).pack(pady=(0, 15))

        # Auto-fill button (only if config and regex available)
        if self.multi_aquarium_config and self.multi_aquarium_config.regex_pattern:
            auto_frame = ttk.Frame(master)
            auto_frame.pack(fill=tk.X, pady=(0, 10))

            if self.video_path:
                # Pre-check if regex matches to enable/disable button visual hint?
                # For now just always show it enabled.
                pass

            ttk.Button(
                auto_frame,
                text="✨ Auto-Preencher com Regex",
                command=self._on_auto_fill_click,
                width=25,
            ).pack(anchor=tk.W)

        # Create config frames for each aquarium
        first_combo = None
        for aquarium_id in range(2):
            frame, combo = self._create_aquarium_frame(master, aquarium_id)
            frame.pack(fill=tk.X, pady=8)
            if first_combo is None:
                first_combo = combo

        # Apply to all checkbox
        self._apply_all_var = tk.BooleanVar(value=False)
        apply_all_check = ttk.Checkbutton(
            master,
            text="Aplicar para todos os vídeos do batch",
            variable=self._apply_all_var,
        )
        apply_all_check.pack(anchor=tk.W, pady=(15, 0))

        # Pre-populate from project entry metadata (regex-derived during project creation)
        # Applied BEFORE regex auto-fill so that regex can override with per-aquarium data
        self._apply_entry_metadata_defaults()

        # Auto-fill automatically when dialog opens if regex pattern is available
        if self.multi_aquarium_config and self.multi_aquarium_config.regex_pattern:
            self._perform_auto_fill_silent()

        return first_combo  # Initial focus

    def _apply_entry_metadata_defaults(self) -> None:
        """Apply pre-existing project metadata as defaults for all aquarium fields.

        Uses group/subject/day from the video entry metadata (extracted during
        project creation via regex). This runs before regex auto-fill, so regex
        can override with per-aquarium specifics when available.
        """
        if not self.entry_metadata:
            return

        group = self.entry_metadata.get("group", "")
        subject = self.entry_metadata.get("subject", "")
        day = self.entry_metadata.get("day")

        log.info(
            "aquarium_assignment.apply_entry_metadata",
            group=group,
            subject=subject,
            day=day,
        )

        for i in range(len(self._group_vars)):
            if group:
                group_value = self._resolve_group_name(group)
                self._ensure_group_in_combobox(i, group_value)
                self._group_vars[i].set(group_value)
            if subject:
                self._subject_vars[i].set(subject)
            if day is not None:
                try:
                    self._day_vars[i].set(int(day))
                except (ValueError, TypeError):
                    pass

    def _on_auto_fill_click(self):
        """Auto-fill fields using regex pattern from filename."""
        if not self.video_path or not self.multi_aquarium_config:
            return

        import os
        from tkinter import messagebox

        filename = os.path.basename(self.video_path)
        matches = self.multi_aquarium_config.extract_metadata(filename)

        if not matches:
            messagebox.showinfo(
                "Auto-Preencher",
                "Nenhuma correspondência encontrada com o padrão regex atual:\n"
                f"{self.multi_aquarium_config.regex_pattern}",
                parent=self,
            )
            return

        log.info("aquarium_assignment.auto_fill", matches=matches)

        # Logic for mapping matches to aquariums
        # If 2 matches, assign 1 to each aquarium
        # If 1 match, assign to both or ask? Current logic: assign to first, duplicate for second?
        # Better: If 1 match, maybe it contains info for the whole video (like Group/Day), set both.

        count = len(matches)

        # Warn user if more matches than aquariums
        if count > 2:
            messagebox.showwarning(
                "Aviso",
                f"Encontradas {count} correspondências no nome do arquivo,\n"
                "mas apenas 2 aquários são suportados.\n\n"
                "Usando as 2 primeiras correspondências.",
                parent=self,
            )
            log.warning(
                "aquarium_assignment.excess_matches",
                count=count,
                used=2,
                filename=os.path.basename(self.video_path) if self.video_path else None,
            )

        for i in range(2):
            if i < count:
                match = matches[i]

                # Update vars
                if match.get("group"):
                    # Use the same resolution logic as silent auto-fill
                    group_value = self._resolve_group_name(match["group"])
                    # Dynamically add to combobox values if not present
                    self._ensure_group_in_combobox(i, group_value)
                    self._group_vars[i].set(group_value)

                if match.get("subject"):
                    self._subject_vars[i].set(match["subject"])

                if match.get("day"):
                    try:
                        self._day_vars[i].set(int(match["day"]))
                    except ValueError:
                        log.debug(
                            "aquarium_dialog.day_parse_error",
                            day=match["day"],
                            aquarium=i,
                            exc_info=True,
                        )
            elif count == 1 and i == 1:
                # Fallback for 2nd aquarium if only 1 match found
                # Copy Group and Day from first match, keep Subject different or empty?
                # Usually single match means shared metadata like Group/Day.
                match = matches[0]
                if match.get("group"):
                    group_value = match["group"]
                    self._ensure_group_in_combobox(i, group_value)
                    self._group_vars[i].set(group_value)
                if match.get("day"):
                    try:
                        self._day_vars[i].set(int(match["day"]))
                    except ValueError:
                        log.debug(
                            "aquarium_dialog.day_fallback_error",
                            day=match["day"],
                            aquarium=i,
                            exc_info=True,
                        )
                # Don't overwrite subject of 2nd aquarium with 1st subject ID if it's specific

        messagebox.showinfo(
            "Auto-Preencher",
            f"Preenchido com sucesso ({count} correspondências encontradas).",
            parent=self,
        )

    def _perform_auto_fill_silent(self) -> None:
        """Perform auto-fill silently (no messagebox) when dialog opens.

        This is called automatically if a regex pattern is configured.
        """
        print("[DIAGNOSTIC] _perform_auto_fill_silent called")
        print(f"[DIAGNOSTIC] has_video_path={bool(self.video_path)}")
        print(f"[DIAGNOSTIC] has_multi_aquarium_config={bool(self.multi_aquarium_config)}")

        if not self.video_path or not self.multi_aquarium_config:
            print("[DIAGNOSTIC] auto_fill SKIPPED - missing video_path or config")
            log.debug(
                "aquarium_assignment.auto_fill_silent.skipped",
                has_video_path=bool(self.video_path),
                has_config=bool(self.multi_aquarium_config),
            )
            return

        import os

        filename = os.path.basename(self.video_path)
        regex_pattern = getattr(self.multi_aquarium_config, "regex_pattern", "")
        print(f"[DIAGNOSTIC] filename={filename}")
        print(f"[DIAGNOSTIC] regex_pattern={regex_pattern}")

        log.info(
            "aquarium_assignment.auto_fill_silent.starting",
            filename=filename,
            regex_pattern=regex_pattern[:80] if regex_pattern else "EMPTY",
        )

        matches = self.multi_aquarium_config.extract_metadata(filename)
        print(f"[DIAGNOSTIC] matches={matches}")

        if not matches:
            log.warning(
                "aquarium_assignment.auto_fill_silent.no_matches",
                filename=filename,
                regex_pattern=regex_pattern[:80] if regex_pattern else "EMPTY",
                hint="Regex pattern did not match the filename. Defaults will be used.",
            )
            return

        log.info(
            "aquarium_assignment.auto_fill_silent.matches_found",
            matches=matches,
            filename=filename,
            count=len(matches),
        )

        count = len(matches)

        for i in range(2):
            if i < count:
                match = matches[i]

                # Update vars
                if match.get("group"):
                    # CRITICAL FIX: Match regex value to available_groups
                    # Regex captures '1', but available_groups has 'G01'
                    group_value = self._resolve_group_name(match["group"])
                    self._ensure_group_in_combobox(i, group_value)
                    self._group_vars[i].set(group_value)

                if match.get("subject"):
                    self._subject_vars[i].set(match["subject"])

                if match.get("day"):
                    try:
                        self._day_vars[i].set(int(match["day"]))
                    except ValueError:
                        log.debug(
                            "aquarium_dialog.regex_day_error",
                            day=match["day"],
                            aquarium=i,
                            exc_info=True,
                        )
            elif count == 1 and i == 1:
                # Fallback for 2nd aquarium if only 1 match found
                match = matches[0]
                if match.get("group"):
                    # CRITICAL FIX: Match regex value to available_groups (same as above)
                    group_value = self._resolve_group_name(match["group"])
                    self._ensure_group_in_combobox(i, group_value)
                    self._group_vars[i].set(group_value)
                if match.get("day"):
                    try:
                        self._day_vars[i].set(int(match["day"]))
                    except ValueError:
                        log.debug(
                            "aquarium_dialog.regex_fallback_error",
                            day=match["day"],
                            aquarium=i,
                            exc_info=True,
                        )

    def _resolve_group_name(self, regex_value: str) -> str:
        """Resolve regex group name using ProjectManager helper."""
        from zebtrack.core.project.project_manager import ProjectManager

        return ProjectManager.resolve_group_name(regex_value, self.available_groups)

    def _ensure_group_in_combobox(self, index: int, group: str) -> None:
        """Ensure a group value is available in the combobox values.

        If the regex extraction returns a group not in the predefined list,
        dynamically add it so the user can see and select it.
        """
        if index >= len(self._group_combos):
            return

        combo = self._group_combos[index]
        current_values = list(combo["values"])

        if group and group not in current_values:
            current_values.append(group)
            combo["values"] = current_values
            log.debug(
                "aquarium_assignment.group_added_to_combobox",
                group=group,
                aquarium_index=index,
            )

    def _create_aquarium_frame(
        self, parent: tk.Frame, aquarium_id: int
    ) -> tuple[ttk.LabelFrame, ttk.Combobox]:
        """Create configuration frame for a single aquarium.

        Args:
            parent: Parent widget.
            aquarium_id: ID of the aquarium (0 or 1).

        Returns:
            Tuple of (frame, group_combobox).
        """
        position = "Esquerda" if aquarium_id == 0 else "Direita"
        frame = ttk.LabelFrame(parent, text=f"Aquário {aquarium_id + 1} ({position})", padding=10)

        # Group selection
        group_label = ttk.Label(frame, text="Grupo:")
        group_label.grid(row=0, column=0, sticky=tk.W, pady=3)

        group_var = tk.StringVar(value=self._get_default_group(aquarium_id))
        self._group_vars.append(group_var)

        group_combo = ttk.Combobox(
            frame,
            textvariable=group_var,
            values=self.available_groups,
            width=20,
            # Restrict to predefined groups for data integrity
            # Note: If regex extracts a group not in the list, the StringVar can still
            # be set programmatically, but user cannot type arbitrary values.
            state="readonly",
        )
        self._group_combos.append(group_combo)  # Store for dynamic updates
        group_combo.grid(row=0, column=1, sticky=tk.W, pady=3, padx=(10, 0))

        # Subject ID
        subject_label = ttk.Label(frame, text="Sujeito:")
        subject_label.grid(row=1, column=0, sticky=tk.W, pady=3)

        subject_var = tk.StringVar(value=f"S{aquarium_id + 1:02d}")
        self._subject_vars.append(subject_var)

        subject_entry = ttk.Entry(frame, textvariable=subject_var, width=22)
        subject_entry.grid(row=1, column=1, sticky=tk.W, pady=3, padx=(10, 0))

        # Day
        day_label = ttk.Label(frame, text="Dia:")
        day_label.grid(row=2, column=0, sticky=tk.W, pady=3)

        day_var = tk.IntVar(value=1)
        self._day_vars.append(day_var)

        day_spinbox = ttk.Spinbox(
            frame,
            from_=1,
            to=365,
            textvariable=day_var,
            width=20,
        )
        day_spinbox.grid(row=2, column=1, sticky=tk.W, pady=3, padx=(10, 0))

        return frame, group_combo

    def _get_default_group(self, aquarium_id: int) -> str:
        """Get default group for an aquarium.

        Args:
            aquarium_id: ID of the aquarium.

        Returns:
            Default group name.
        """
        if not self.available_groups:
            return "Controle" if aquarium_id == 0 else "Tratamento"

        # Try to assign different groups by default
        if len(self.available_groups) >= 2:
            return self.available_groups[aquarium_id % len(self.available_groups)]
        return self.available_groups[0]

    def buttonbox(self) -> None:
        """Create custom button box with Confirm and Cancel buttons."""
        box = ttk.Frame(self)
        box.pack(pady=(15, 0))

        confirm_btn = ttk.Button(
            box,
            text="Confirmar",
            width=12,
            command=self._on_confirm_click,
        )
        confirm_btn.pack(side=tk.LEFT, padx=5)

        cancel_btn = ttk.Button(
            box,
            text="Cancelar",
            width=12,
            command=self.cancel,
        )
        cancel_btn.pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._on_confirm_click())
        self.bind("<Escape>", lambda e: self.cancel())

    def _on_confirm_click(self) -> None:
        """Handle confirmation and validate inputs."""
        print("[DIAGNOSTIC] _on_confirm_click called")

        try:
            configs = self.get_configs()
            print(f"[DIAGNOSTIC] configs={configs}")

            self.result = configs
            self.apply_to_all = self._apply_all_var.get() if self._apply_all_var else False
            print(f"[DIAGNOSTIC] apply_to_all={self.apply_to_all}")

            log.info(
                "aquarium_assignment.dialog.confirmed",
                configs=[
                    {"id": c.aquarium_id, "group": c.group, "subject": c.subject_id}
                    for c in configs
                ],
                apply_to_all=self.apply_to_all,
            )

            if self._on_confirm:
                print("[DIAGNOSTIC] calling on_confirm callback")
                self._on_confirm(configs, self.apply_to_all)
            else:
                print("[DIAGNOSTIC] no on_confirm callback provided")

            print("[DIAGNOSTIC] calling self.ok()")
            self.ok()

        except ValueError as e:
            log.warning("aquarium_assignment.dialog.validation_error", error=str(e))
            # Show error in dialog
            from tkinter import messagebox

            messagebox.showerror("Erro de Validação", str(e), parent=self)

    def cancel(self, event=None) -> None:
        """Handle dialog cancellation.

        Note: This is also called by the base Dialog.ok() after validation succeeds.
        We only reset self.result if it hasn't been set yet (user cancelled).
        """
        print(f"[DIAGNOSTIC] cancel called, current result={self.result}")

        # Only reset result if user is actually cancelling (not coming from ok())
        if self.result is None:
            log.debug("aquarium_assignment.dialog.cancelled")
            if self._on_cancel:
                print("[DIAGNOSTIC] calling on_cancel callback")
                self._on_cancel()
            else:
                print("[DIAGNOSTIC] no on_cancel callback provided")

        super().cancel()

    def get_configs(self) -> list[AquariumConfig]:
        """Return the configured AquariumConfig objects.

        Returns:
            List of 2 AquariumConfig objects.

        Raises:
            ValueError: If validation fails.
        """
        configs = []

        for i in range(2):
            group_raw = self._group_vars[i].get().strip()
            subject = self._subject_vars[i].get().strip()
            day = self._day_vars[i].get()

            if not group_raw:
                raise ValueError(f"Grupo do Aquário {i + 1} não pode estar vazio")

            # CRITICAL FIX: Resolve group name to match available_groups format
            # The StringVar might have '1', but we need 'G01'
            group = self._resolve_group_name(group_raw)

            print(f"[DIAGNOSTIC] get_configs[{i}]: '{group_raw}' → '{group}'")

            config = AquariumConfig(
                aquarium_id=i,
                group=group,
                subject_id=subject,
                day=day,
            )
            configs.append(config)

        return configs

    def get_result(self) -> tuple[list[AquariumConfig] | None, bool]:
        """Return the dialog result.

        Returns:
            Tuple of (configs, apply_to_all) or (None, False) if cancelled.
        """
        return self.result, self.apply_to_all
