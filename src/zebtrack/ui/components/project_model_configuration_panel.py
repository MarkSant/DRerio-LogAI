"""Project-scoped model configuration panel."""

from __future__ import annotations

from tkinter import StringVar, messagebox, ttk

import structlog

from zebtrack.core.exceptions import ZebTrackError
from zebtrack.i18n import _
from zebtrack.ui.wizard.tooltip import ToolTip

log = structlog.get_logger()


def weight_inherit_label() -> str:
    """Dropdown entry meaning "no project override for this slot".

    A function, not a class attribute: ``_()`` resolves the catalogue when it is
    called, and a class-body call would freeze the label into whatever language
    was installed at import time. The value doubles as the sentinel compared in
    :meth:`ProjectModelConfigurationPanel._get_preferences_overrides`, so both
    sides must come from this one source.
    """
    return _("Inherit (global default)")


class ProjectModelConfigurationPanel(ttk.Frame):
    """Project-only overrides for model selection and OpenVINO usage."""

    SLOT_SEPARATOR = ":"
    OPENVINO_INHERIT = "inherit"
    OPENVINO_ON = "on"
    OPENVINO_OFF = "off"

    def __init__(self, parent, controller) -> None:
        super().__init__(parent, padding=10)
        self.controller = controller
        self.project_manager = controller.project_manager
        self.scope_info = controller.project_vm.get_calibration_scope_info()

        self.openvino_choice = StringVar(master=self, value=self.OPENVINO_INHERIT)
        self.defaults_summary_var = StringVar(master=self)
        self.effective_weight_var = StringVar(master=self)
        self.effective_openvino_var = StringVar(master=self)
        self.slot_weight_choices: dict[str, StringVar] = {}
        self.slot_weight_dropdowns: dict[str, ttk.Combobox] = {}
        self.project_slots: list[dict[str, str | None]] = []
        self.slot_controls_frame: ttk.LabelFrame | None = None

        self._build()

    def refresh_from_project(self) -> None:
        """Reload project overrides and available weights into the current form."""
        self.scope_info = self.controller.project_vm.get_calibration_scope_info()
        self.project_slots = self._get_project_slots()
        self._refresh_slot_dropdown_values()
        self._restore_project_preferences()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)

        heading = ttk.Label(
            self,
            text=_("Project Model Configuration"),
            font=("Segoe UI", 11, "bold"),
        )
        heading.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        if not self.scope_info.get("project_loaded"):
            ttk.Label(
                self,
                text=_(
                    "Open a project to adjust project-specific weights and OpenVINO. "
                    "The preferences applied here do not affect the global default."
                ),
                wraplength=640,
                justify="left",
                foreground="#555555",
            ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=12)
            return

        ttk.Label(
            self,
            text=_(
                "Set only this project's overrides. To edit the weight catalogue, the "
                "per-slot defaults or OpenVINO maintenance, use Global Model Configuration."
            ),
            wraplength=700,
            justify="left",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 10))

        self.slot_controls_frame = ttk.LabelFrame(
            self,
            text=_("Weights specific to this project"),
            padding=8,
        )
        self.slot_controls_frame.grid(
            row=2,
            column=0,
            columnspan=2,
            padx=12,
            pady=(0, 4),
            sticky="ew",
        )
        self.slot_controls_frame.columnconfigure(1, weight=1)
        self.project_slots = self._get_project_slots()
        self._build_slot_override_controls()

        openvino_frame = ttk.LabelFrame(self, text="OpenVINO", padding=8)
        openvino_frame.grid(row=3, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="ew")
        openvino_frame.columnconfigure(0, weight=1)

        inherit_radio = ttk.Radiobutton(
            openvino_frame,
            text=_("Inherit the global configuration"),
            value=self.OPENVINO_INHERIT,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        inherit_radio.grid(row=0, column=0, sticky="w")
        ToolTip(
            inherit_radio, _("Uses exactly the global OpenVINO configuration for this project.")
        )

        force_on_radio = ttk.Radiobutton(
            openvino_frame,
            text=_("Force enabled"),
            value=self.OPENVINO_ON,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        force_on_radio.grid(row=1, column=0, sticky="w", pady=(2, 0))
        ToolTip(
            force_on_radio,
            _("Always uses OpenVINO in this project, regardless of the global default."),
        )

        force_off_radio = ttk.Radiobutton(
            openvino_frame,
            text=_("Force disabled"),
            value=self.OPENVINO_OFF,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        force_off_radio.grid(row=2, column=0, sticky="w", pady=(2, 0))
        ToolTip(
            force_off_radio,
            _("Prevents OpenVINO use in this project, even when it is globally enabled."),
        )

        ttk.Label(
            openvino_frame,
            text=_(
                "Choose how to apply OpenVINO in this project:\n"
                "• Inherit: follows the current global state.\n"
                "• Force enabled: always uses OpenVINO here.\n"
                "• Force disabled: keeps PyTorch even when the global state is enabled."
            ),
            justify="left",
            font=("TkDefaultFont", 9),
            foreground="#555555",
        ).grid(row=3, column=0, sticky="w", pady=(6, 0))

        preview = ttk.LabelFrame(self, text=_("Effective Result"), padding=8)
        preview.grid(row=4, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="ew")
        preview.columnconfigure(1, weight=1)

        ttk.Label(preview, text=_("Weights in use:")).grid(row=0, column=0, sticky="nw")
        ttk.Label(preview, textvariable=self.effective_weight_var, justify="left").grid(
            row=0,
            column=1,
            sticky="w",
        )
        ttk.Label(preview, text="OpenVINO:").grid(row=1, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.effective_openvino_var).grid(
            row=1, column=1, sticky="w"
        )

        defaults_frame = ttk.LabelFrame(self, text=_("Global Defaults"), padding=8)
        defaults_frame.grid(row=5, column=0, columnspan=2, padx=12, pady=(6, 4), sticky="ew")
        ttk.Label(
            defaults_frame,
            textvariable=self.defaults_summary_var,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            defaults_frame,
            text=_("Global OpenVINO: {state}").format(
                state=(
                    _("Enabled")
                    if self._get_detector_defaults().get("use_openvino")
                    else _("Disabled")
                )
            ),
        ).pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(self)
        actions.grid(row=6, column=0, columnspan=2, sticky="e", padx=12, pady=(10, 12))
        ttk.Button(
            actions,
            text=_("Save Preferences"),
            command=self._save_project_preferences,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions,
            text=_("Copy Globals to the Project"),
            command=self._copy_globals_to_project,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions,
            text=_("Reload From Project"),
            command=self._restore_project_preferences,
        ).pack(side="left")

        self._restore_project_preferences()

    @classmethod
    def _slot_key(cls, method: str, target: str) -> str:
        return f"{method}{cls.SLOT_SEPARATOR}{target}"

    def _get_project_slots(self) -> list[dict[str, str | None]]:
        summary_getter = getattr(self.controller.hardware_vm, "get_default_weights_summary", None)
        if not callable(summary_getter):
            return []

        slots: list[dict[str, str | None]] = []
        for label, method, target, global_weight in summary_getter(scope="project"):
            slots.append(
                {
                    "key": self._slot_key(method, target),
                    "label": label,
                    "method": method,
                    "target": target,
                    "global_weight": global_weight,
                }
            )
        return slots

    def _build_slot_override_controls(self) -> None:
        if self.slot_controls_frame is None:
            return

        for child in self.slot_controls_frame.winfo_children():
            child.destroy()

        self.slot_weight_dropdowns = {}

        if not self.project_slots:
            ttk.Label(
                self.slot_controls_frame,
                text=_("No active project slot was identified."),
                foreground="#555555",
            ).grid(row=0, column=0, sticky="w")
            return

        for row, slot in enumerate(self.project_slots):
            slot_key = str(slot["key"])
            slot_var = self.slot_weight_choices.setdefault(
                slot_key,
                StringVar(master=self, value=weight_inherit_label()),
            )
            ttk.Label(self.slot_controls_frame, text=f"{slot['label']}:").grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=2,
            )
            dropdown = ttk.Combobox(
                self.slot_controls_frame,
                state="readonly",
                textvariable=slot_var,
            )
            dropdown.grid(row=row, column=1, sticky="ew", pady=2)
            dropdown.bind("<<ComboboxSelected>>", lambda *_a: self._update_preferences_preview())
            self.slot_weight_dropdowns[slot_key] = dropdown

        self._refresh_slot_dropdown_values()

    def _get_detector_defaults(self) -> dict[str, object]:
        detector_state = self.controller.state_manager.get_detector_state()
        if hasattr(detector_state, "active_weight_name"):
            active_weight = detector_state.active_weight_name
            use_openvino = detector_state.use_openvino
        else:
            active_weight = detector_state.get("active_weight_name")
            use_openvino = detector_state.get("use_openvino", False)
        return {
            "active_weight": active_weight,
            "use_openvino": bool(use_openvino),
        }

    def _get_current_overrides(self) -> dict:
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        return project_data.get("model_overrides", {}) or {}

    def _get_current_slot_overrides(self) -> dict[str, str]:
        overrides = self._get_current_overrides()
        slot_weights = overrides.get("slot_weights") or {}
        normalized: dict[str, str] = {}
        if isinstance(slot_weights, dict):
            for key, value in slot_weights.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    continue
                candidate = value.strip()
                if candidate:
                    normalized[key] = candidate

        legacy_weight = overrides.get("active_weight")
        if isinstance(legacy_weight, str) and legacy_weight.strip():
            for slot in self.project_slots:
                if slot["target"] == "zebrafish":
                    normalized.setdefault(str(slot["key"]), legacy_weight.strip())
                    break
        return normalized

    def _refresh_slot_dropdown_values(self) -> None:
        slot_overrides = self._get_current_slot_overrides()
        for slot in self.project_slots:
            slot_key = str(slot["key"])
            dropdown = self.slot_weight_dropdowns.get(slot_key)
            if dropdown is None:
                continue

            weight_getter = getattr(self.controller.hardware_vm, "get_weight_names_for_slot", None)
            if callable(weight_getter):
                weights = weight_getter(str(slot["method"]), str(slot["target"]))
            else:
                weights = self.controller.hardware_vm.get_all_weight_names()

            display_values = [weight_inherit_label(), *weights]
            current_override = slot_overrides.get(slot_key)
            if current_override and current_override not in display_values:
                display_values.append(current_override)
            dropdown["values"] = display_values

    def _get_preferences_overrides(self) -> tuple[dict[str, str], bool | None]:
        slot_overrides: dict[str, str] = {}
        for slot_key, variable in self.slot_weight_choices.items():
            selection = variable.get().strip()
            if selection and selection != weight_inherit_label():
                slot_overrides[slot_key] = selection

        openvino_selection = self.openvino_choice.get()
        if openvino_selection == self.OPENVINO_INHERIT:
            openvino_override = None
        elif openvino_selection == self.OPENVINO_ON:
            openvino_override = True
        else:
            openvino_override = False

        return slot_overrides, openvino_override

    def _update_preferences_preview(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        slot_overrides, openvino_override = self._get_preferences_overrides()
        effective_lines: list[str] = []
        global_lines: list[str] = []
        for slot in self.project_slots:
            slot_key = str(slot["key"])
            label = str(slot["label"])
            global_weight = slot.get("global_weight")
            effective_weight = slot_overrides.get(slot_key) or global_weight
            none_label = _("None")
            effective_lines.append(f"{label}: {effective_weight or none_label}")
            global_lines.append(f"{label}: {global_weight or none_label}")

        self.effective_weight_var.set("\n".join(effective_lines) or _("No weight available"))
        self.defaults_summary_var.set("\n".join(global_lines) or _("No global default available"))

        defaults = self._get_detector_defaults()
        resolved_openvino = (
            bool(defaults.get("use_openvino"))
            if openvino_override is None
            else bool(openvino_override)
        )
        self.effective_openvino_var.set(_("Enabled") if resolved_openvino else _("Disabled"))

    def _save_project_preferences(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        slot_overrides, openvino_override = self._get_preferences_overrides()
        try:
            self.controller.project_vm.save_project_model_slot_overrides(
                slot_overrides,
                openvino_override,
            )
        # ZebTrackError, not pydantic's ValidationError: nothing in this chain
        # (project_vm -> lifecycle coordinator -> model override service ->
        # project workflow service) validates a pydantic model, so the old
        # handler could never fire. What that chain CAN raise is the
        # application hierarchy, which now includes the coordinator errors.
        except ZebTrackError as exc:
            log.error("project_model_config.save_preferences.failed", error=str(exc))
            messagebox.showerror(_("Error"), str(exc), parent=self)
            return

        messagebox.showinfo(
            _("Preferences updated"),
            _("The project preferences have been saved."),
            parent=self,
        )
        self._restore_project_preferences()
        self._refresh_related_project_panels()

    def _copy_globals_to_project(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        self.controller.project_vm.handle_calibration_copy_to_project()
        self._restore_project_preferences()
        self._refresh_related_project_panels()
        messagebox.showinfo(
            _("Project updated"),
            _("The current global settings have been copied into this project."),
            parent=self,
        )

    def _restore_project_preferences(self) -> None:
        self.project_slots = self._get_project_slots()
        self._build_slot_override_controls()

        slot_overrides = self._get_current_slot_overrides()
        for slot in self.project_slots:
            slot_key = str(slot["key"])
            variable = self.slot_weight_choices.get(slot_key)
            if variable is None:
                continue
            variable.set(slot_overrides.get(slot_key, weight_inherit_label()))

        overrides = self._get_current_overrides()
        openvino_override = overrides.get("use_openvino")
        if openvino_override is None:
            self.openvino_choice.set(self.OPENVINO_INHERIT)
        elif bool(openvino_override):
            self.openvino_choice.set(self.OPENVINO_ON)
        else:
            self.openvino_choice.set(self.OPENVINO_OFF)

        self._update_preferences_preview()

    def _refresh_related_project_panels(self) -> None:
        view = getattr(self.controller, "view", None)
        diagnostics_panel = getattr(view, "project_diagnostics_panel", None)
        if diagnostics_panel is not None and hasattr(diagnostics_panel, "refresh_weight_options"):
            diagnostics_panel.refresh_weight_options()
