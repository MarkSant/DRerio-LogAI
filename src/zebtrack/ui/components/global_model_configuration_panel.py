"""Global model configuration panel extracted from CalibrationDialog."""

from __future__ import annotations

import contextlib
import os
import unicodedata
from collections.abc import Callable
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, messagebox, simpledialog, ttk

import structlog

from zebtrack.i18n import _
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

log = structlog.get_logger()

_CONVERSION_POLL_INTERVAL_MS = 1500

# The four label maps below are functions, not module constants: a dict built at
# import time would freeze whatever language happened to be installed then --
# usually none at all. See docs/guides/developer/i18n.md.


def _target_labels() -> dict[str, str]:
    """Human-readable names for the stored ``target`` tokens."""
    return {"aquarium": _("Aquarium"), "zebrafish": _("Zebrafish")}


def _method_labels() -> dict[str, str]:
    """Human-readable names for the stored ``type`` tokens."""
    return {"seg": _("Segmentation"), "det": _("Detection")}


def _perspective_labels() -> dict[str, str]:
    """Human-readable names for the stored ``perspective`` tokens."""
    return {"lateral": _("Lateral"), "top_down": _("Top (top-down)")}


def _openvino_status_labels() -> dict[str, str]:
    """Human-readable names for the stored OpenVINO conversion states."""
    return {
        "ready": _("✓ Ready"),
        "converting": _("⏳ Converting"),
        "failed": _("✗ Failed"),
        "not_converted": "—",
    }


def _strip_accents(text: str) -> str:
    """Fold accents away so typed input matches regardless of spelling.

    The target prompt accepts the word in either language; "aquário" and
    "aquario" must both work, and comparing against a folded form avoids
    carrying an accented literal that the i18n scanner would flag as copy.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


class GlobalModelConfigurationPanel(ttk.Frame):
    """Global model catalog, OpenVINO, maintenance, and hardware tools."""

    def __init__(self, parent, controller) -> None:
        super().__init__(parent)
        self.controller = controller

        self.use_openvino_var = BooleanVar(master=self)
        self.openvino_status_var = StringVar(master=self)
        self.device_var = StringVar(master=self, value="AUTO")
        self.slot_vars: dict[tuple[str, str], StringVar] = {
            ("det", "aquarium"): StringVar(master=self),
            ("seg", "aquarium"): StringVar(master=self),
            ("det", "zebrafish"): StringVar(master=self),
            ("seg", "zebrafish"): StringVar(master=self),
        }
        self.slot_comboboxes: dict[tuple[str, str], ttk.Combobox] = {}

        self.weights_treeview: ttk.Treeview | None = None
        self.openvino_checkbox: ttk.Checkbutton | None = None
        self.openvino_status_label: ttk.Label | None = None
        self.device_combobox: ttk.Combobox | None = None
        self._weights_validation: dict[str, bool] = {}
        self._conversion_poller_id: str | None = None
        self._refresh_weight_choices: Callable[[], None] | None = None

        self._build()

    def set_weight_refresh_callback(self, callback: Callable[[], None] | None) -> None:
        """Refresh external weight selectors after catalog changes."""
        self._refresh_weight_choices = callback

    def refresh_view(self) -> None:
        """Reload catalog, slots, and OpenVINO status from current state."""
        self._populate_slot_comboboxes()
        self._populate_weights_treeview()
        self._populate_device_combobox()
        self.use_openvino_var.set(self.controller.hardware_vm.use_openvino)
        self.update_openvino_status_label(self.controller.hardware_vm.get_openvino_status())
        if self.device_combobox is not None:
            state = "readonly" if self.use_openvino_var.get() else "disabled"
            self.device_combobox.configure(state=state)

    def _build(self) -> None:
        model_frame = ttk.LabelFrame(self, text=_("Model Configuration"), padding=10)
        model_frame.pack(fill="both", expand=True, pady=5, padx=5)

        top_row = ttk.Frame(model_frame)
        top_row.pack(fill="both", expand=True)
        top_row.columnconfigure(0, weight=2, minsize=360)
        top_row.columnconfigure(1, weight=3, minsize=520)

        left_col = ttk.Frame(top_row)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right_col = ttk.Frame(top_row)
        right_col.grid(row=0, column=1, sticky="nsew")

        self._build_default_slots_section(left_col)
        ttk.Separator(left_col, orient="horizontal").pack(fill="x", pady=10)
        self._build_openvino_section(left_col)

        self._build_weights_catalog_section(right_col)

        ttk.Separator(model_frame, orient="horizontal").pack(fill="x", pady=10)

        bottom_row = ttk.Frame(model_frame)
        bottom_row.pack(fill="x")
        bottom_row.columnconfigure(0, weight=3, minsize=480)
        bottom_row.columnconfigure(1, weight=2, minsize=320)

        maint_col = ttk.Frame(bottom_row)
        maint_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        sys_col = ttk.Frame(bottom_row)
        sys_col.grid(row=0, column=1, sticky="nsew")

        self._build_maintenance_section(maint_col)
        self._build_system_section(sys_col)

    def _build_default_slots_section(self, parent: ttk.Widget) -> None:
        ttk.Label(parent, text=_("Default weights per slot"), font=("Segoe UI", 10, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            parent,
            text=_(
                "Each combination (method × target) uses a default weight. "
                "The detector looks up the right slot at runtime."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=340,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        slot_specs = [
            (_("🐠 Aquarium (Detection)"), "det", "aquarium"),
            (_("🐠 Aquarium (Segmentation)"), "seg", "aquarium"),
            (_("🐟 Animal (Detection)"), "det", "zebrafish"),
            (_("🐟 Animal (Segmentation)"), "seg", "zebrafish"),
        ]
        for row, (label, method, target) in enumerate(slot_specs):
            ttk.Label(grid, text=f"{label}:").grid(row=row, column=0, sticky="w", padx=4, pady=2)
            combo = ttk.Combobox(
                grid,
                textvariable=self.slot_vars[(method, target)],
                state="readonly",
            )
            combo.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, m=method, t=target: self._on_slot_default_selected(m, t),  # type: ignore[misc]
            )
            self.slot_comboboxes[(method, target)] = combo

        self._populate_slot_comboboxes()

    def _build_weights_catalog_section(self, parent: ttk.Widget) -> None:
        ttk.Label(parent, text=_("Weight catalogue"), font=("Segoe UI", 10, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            parent,
            text=_(
                "Ctrl/Shift-click to select several. Type = how the model operates "
                "(segmentation or detection); Target = what it identifies "
                "(aquarium or zebrafish)."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ("name", "type", "target", "perspective", "defaults", "openvino")
        self.weights_treeview = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=10,
            selectmode="extended",
        )
        self.weights_treeview.heading("name", text=_("Weight Name"))
        self.weights_treeview.heading("type", text=_("Type"))
        self.weights_treeview.heading("target", text=_("Target"))
        self.weights_treeview.heading("perspective", text=_("Perspective"))
        self.weights_treeview.heading("defaults", text=_("Default?"))
        self.weights_treeview.heading("openvino", text="OpenVINO")

        self.weights_treeview.column("name", width=180, stretch=True, minwidth=120)
        self.weights_treeview.column("type", width=80, anchor="center", stretch=False)
        self.weights_treeview.column("target", width=70, anchor="center", stretch=False)
        self.weights_treeview.column("perspective", width=90, anchor="center", stretch=False)
        self.weights_treeview.column("defaults", width=110, anchor="center", stretch=False)
        self.weights_treeview.column("openvino", width=90, anchor="center", stretch=False)
        self.weights_treeview.tag_configure("missing", foreground="#b00020")

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.weights_treeview.yview,
        )
        self.weights_treeview.configure(yscrollcommand=scrollbar.set)
        self.weights_treeview.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        button_grid = ttk.Frame(parent)
        button_grid.pack(fill="x", pady=(6, 0))
        for col in range(3):
            button_grid.columnconfigure(col, weight=1, uniform="catalog_btns")

        ttk.Button(button_grid, text=_("Add Weight..."), command=self._on_add_weight).grid(
            row=0, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(button_grid, text=_("Delete Selected"), command=self._on_delete_weight).grid(
            row=0, column=1, sticky="ew", padx=2, pady=2
        )
        ttk.Button(button_grid, text=_("Change Target..."), command=self._on_change_target).grid(
            row=0, column=2, sticky="ew", padx=2, pady=2
        )
        ttk.Button(button_grid, text=_("Validate Paths"), command=self._on_validate_paths).grid(
            row=1, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(
            button_grid,
            text=_("Convert to OpenVINO"),
            command=self._on_convert_openvino,
        ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=2, pady=2)

        self._populate_weights_treeview()

    def _build_openvino_section(self, parent: ttk.Widget) -> None:
        ttk.Label(parent, text="OpenVINO", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.openvino_checkbox = ttk.Checkbutton(
            parent,
            text=_("Optimise with OpenVINO (for Intel hardware)"),
            variable=self.use_openvino_var,
            command=self._on_openvino_toggled_local,
        )
        self.openvino_checkbox.pack(anchor="w", padx=4, pady=(2, 2))

        self.openvino_status_label = ttk.Label(
            parent,
            textvariable=self.openvino_status_var,
            font=("Segoe UI", 8),
        )
        self.openvino_status_label.pack(anchor="w", padx=20, pady=(0, 4))

        device_row = ttk.Frame(parent)
        device_row.pack(anchor="w", padx=4, pady=2)
        ttk.Label(device_row, text=_("OpenVINO device:")).pack(side="left")
        self.device_combobox = ttk.Combobox(
            device_row,
            textvariable=self.device_var,
            state="readonly",
            width=20,
        )
        self.device_combobox.pack(side="left", padx=(6, 0))
        self.device_combobox.bind("<<ComboboxSelected>>", self._on_device_selected)

        self.refresh_view()

    def _build_maintenance_section(self, parent: ttk.Widget) -> None:
        ttk.Label(parent, text=_("Cache maintenance"), font=("Segoe UI", 10, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            parent,
            text=_(
                "OpenVINO caches speed detection up but stay tied to the original "
                ".pt file. Clear them when replacing weights with the same name or "
                "after retraining."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        for col in range(2):
            grid.columnconfigure(col, weight=1, uniform="maint_btns")

        ttk.Button(
            grid,
            text=_("Delete OpenVINO Cache (Selected)"),
            command=self._on_clear_cache_selected,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text=_("Delete ALL OpenVINO Caches"),
            command=self._on_clear_cache_all,
        ).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text=_("Rescan Weights Folder"),
            command=self._on_rescan_folder,
        ).grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text=_("Reset Weight List (factory)"),
            command=self._on_reset_registry,
        ).grid(row=1, column=1, sticky="ew", padx=2, pady=2)

    def _build_system_section(self, parent: ttk.Widget) -> None:
        ttk.Label(parent, text=_("System & Hardware"), font=("Segoe UI", 10, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            parent,
            text=_(
                "Re-running the benchmark recalculates the optimal OpenVINO settings "
                "(device, precision, hint) for your current hardware."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="sys_btns")
        grid.columnconfigure(1, weight=1, uniform="sys_btns")
        ttk.Button(
            grid,
            text=_("Re-run Hardware Benchmark"),
            command=self._on_force_benchmark,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text=_("Open Cache Folder"),
            command=self._on_open_cache_folder,
        ).grid(row=0, column=1, sticky="ew", padx=2, pady=2)

    def _publish_model_event(self, event_type: UIEvents, payload) -> None:
        bus = getattr(self.controller, "ui_event_bus", None)
        if bus is None:
            log.error("global_model_config.no_event_bus", event=event_type.name)
            return
        bus.publish(Event(type=event_type, data=payload))

    def _selected_weight_names(self) -> list[str]:
        if not self.weights_treeview:
            return []
        selection = self.weights_treeview.selection()
        if not selection:
            messagebox.showwarning(
                _("No Selection"),
                _("Please select at least one weight first."),
                parent=self,
            )
            return []
        return [self.weights_treeview.item(iid)["values"][0] for iid in selection]

    def _selected_weight_name(self) -> str | None:
        names = self._selected_weight_names()
        return names[0] if names else None

    def _selected_weight_details(self) -> tuple[str, dict] | None:
        name = self._selected_weight_name()
        if not name:
            return None
        wm = self.controller.weight_manager
        details = wm.get_weight_details(name) if wm else None
        if not details:
            messagebox.showerror(
                _("Weight not found"),
                _("Could not find data for '{name}'.").format(name=name),
                parent=self,
            )
            return None
        return name, details

    def _populate_slot_comboboxes(self) -> None:
        wm = self.controller.weight_manager
        if not wm:
            return
        for (method, target), combo in self.slot_comboboxes.items():
            options = [
                name for name, details in wm.weights.items() if details.get("type") == method
            ]
            combo["values"] = sorted(options)
            current_name, _default_path = wm.get_default_weight_for(method, target)
            self.slot_vars[(method, target)].set(current_name or "")

    def _populate_weights_treeview(self) -> None:
        if not self.weights_treeview:
            return
        for item in self.weights_treeview.get_children():
            self.weights_treeview.delete(item)

        wm = self.controller.weight_manager
        if not wm:
            return
        weights = self.controller.hardware_vm.get_all_weight_names()
        self._weights_validation = wm.validate_weight_files()

        method_labels = _method_labels()
        target_labels = _target_labels()
        perspective_labels = _perspective_labels()
        status_labels = _openvino_status_labels()

        for name in sorted(weights):
            details = wm.get_weight_details(name)
            if not details:
                continue

            weight_type = details.get("type", "seg")
            target = details.get("target", "zebrafish" if weight_type == "seg" else "aquarium")
            perspective = details.get("perspective")
            type_label = method_labels.get(weight_type, weight_type)
            target_label = target_labels.get(target, target)
            perspective_label = perspective_labels.get(perspective, "—") if perspective else "—"
            defaults = self._format_default_slots(details, weight_type)
            openvino_status = status_labels.get(
                details.get("openvino_status", "not_converted"), "—"
            )

            tags: tuple[str, ...] = ()
            if not self._weights_validation.get(name, True):
                tags = ("missing",)
                openvino_status = _("⚠ File missing")

            self.weights_treeview.insert(
                "",
                "end",
                iid=name,
                values=(
                    name,
                    type_label,
                    target_label,
                    perspective_label,
                    defaults,
                    openvino_status,
                ),
                tags=tags,
            )

    @staticmethod
    def _format_default_slots(details: dict, weight_type: str) -> str:
        slots: list[str] = []
        if details.get("is_default_seg_aquarium"):
            slots.append("Seg-Aq")
        if details.get("is_default_seg_zebrafish"):
            slots.append("Seg-Zb")
        if details.get("is_default_det_aquarium"):
            slots.append("Det-Aq")
        if details.get("is_default_det_zebrafish"):
            slots.append("Det-Zb")
        if not slots:
            if details.get("is_default_seg") and weight_type == "seg":
                slots.append(_("Seg (legacy)"))
            if details.get("is_default_det") and weight_type == "det":
                slots.append(_("Det (legacy)"))
        return ", ".join(slots) if slots else "—"

    def _refresh_weights_catalog(self) -> None:
        self._populate_weights_treeview()
        self._populate_slot_comboboxes()
        if self._refresh_weight_choices is not None:
            self._refresh_weight_choices()

        gui = getattr(getattr(self.controller, "view", None), "gui", None)
        if gui is None:
            gui = getattr(self.controller, "view", None)
        weight_hw = getattr(gui, "weight_hardware_manager", None) if gui else None
        if weight_hw is not None:
            weight_hw.refresh_weights_summary()

    def _on_slot_default_selected(self, method: str, target: str) -> None:
        chosen_name = self.slot_vars[(method, target)].get()
        if not chosen_name:
            return
        self._publish_model_event(
            UIEvents.MODEL_SET_DEFAULT_FOR,
            payloads.ModelSetDefaultForPayload(name=chosen_name, method=method, target=target),
        )
        self.after(150, self._refresh_weights_catalog)

    def _on_add_weight(self) -> None:
        path = filedialog.askopenfilename(
            title=_("Select weight file"),
            filetypes=[(_("YOLO models"), "*.pt"), (_("All files"), "*.*")],
            parent=self,
        )
        if not path:
            return
        self._publish_model_event(
            UIEvents.MODEL_LOAD_NEW_WEIGHT,
            payloads.ModelLoadNewWeightPayload(weight_path=path, weight_type=None),
        )
        self.after(250, self._refresh_weights_catalog)

    def _on_delete_weight(self) -> None:
        name = self._selected_weight_name()
        if not name:
            return
        if not messagebox.askyesno(
            _("Confirm Deletion"),
            _(
                "Delete the registry entry for weight '{name}'?\n\n"
                "(The .pt file on disk will not be deleted.)"
            ).format(name=name),
            parent=self,
        ):
            return
        self._publish_model_event(
            UIEvents.MODEL_DELETE_WEIGHT,
            payloads.ModelDeleteWeightPayload(name=name),
        )
        self.after(150, self._refresh_weights_catalog)

    def _on_change_target(self) -> None:
        selected = self._selected_weight_details()
        if not selected:
            return
        name, details = selected
        current = details.get("target", "zebrafish")
        new_label = simpledialog.askstring(
            _("Change Target"),
            _(
                "Current target of '{name}': {target}\n\n"
                "Type the new target: 'aquarium' or 'zebrafish'"
            ).format(name=name, target=_target_labels().get(current, current)),
            parent=self,
        )
        if not new_label:
            return
        normalized = _strip_accents(new_label.strip().lower())
        if normalized in ("aquario", "aquarium", "tank"):
            new_target = "aquarium"
        elif normalized in ("zebrafish", "fish", "animal", "peixe"):
            new_target = "zebrafish"
        else:
            messagebox.showerror(
                _("Invalid target"),
                _("Target '{value}' not recognised. Use 'aquarium' or 'zebrafish'.").format(
                    value=new_label
                ),
                parent=self,
            )
            return
        if new_target == current:
            return
        self._publish_model_event(
            UIEvents.MODEL_RECLASSIFY_TARGET,
            payloads.ModelReclassifyTargetPayload(name=name, target=new_target),
        )
        self.after(150, self._refresh_weights_catalog)

    def _on_validate_paths(self) -> None:
        wm = self.controller.weight_manager
        if not wm:
            return
        self._weights_validation = wm.validate_weight_files()
        missing = [name for name, ok in self._weights_validation.items() if not ok]
        self._populate_weights_treeview()
        if missing:
            messagebox.showwarning(
                _("Weights with a missing file"),
                _("The following weights reference .pt files that were not found on disk:\n\n  • ")
                + "\n  • ".join(missing),
                parent=self,
            )
            return
        messagebox.showinfo(
            _("Validation finished"),
            _("Every registered .pt file exists on disk."),
            parent=self,
        )

    def _on_convert_openvino(self) -> None:
        names = self._selected_weight_names()
        if not names:
            return
        wm = self.controller.weight_manager
        candidates: list[str] = []
        already_ready: list[str] = []
        for name in names:
            details = wm.get_weight_details(name) if wm else None
            if not details:
                continue
            if details.get("openvino_status") == "ready":
                already_ready.append(name)
            else:
                candidates.append(name)

        if not candidates:
            messagebox.showinfo(
                _("Nothing to convert"),
                _(
                    "The selected weights are already converted to OpenVINO. "
                    "Use 'Delete OpenVINO Cache' first to force a reconversion."
                ),
                parent=self,
            )
            return

        plural = len(candidates) > 1
        msg = (
            _("Convert {count} weights to OpenVINO now?\n\n  • ").format(count=len(candidates))
            + "\n  • ".join(candidates)
            if plural
            else _("Convert '{name}' to OpenVINO now?").format(name=candidates[0])
        )
        msg += _(
            "\n\nThe conversion runs in the background; the status in the 'OpenVINO' "
            "column is refreshed every ~1.5s until it finishes."
        )
        if already_ready:
            msg += _("\n\n({count} weight(s) are already ready and were skipped.)").format(
                count=len(already_ready)
            )
        if not messagebox.askyesno(_("OpenVINO Conversion"), msg, parent=self):
            return

        for name in candidates:
            self._publish_model_event(
                UIEvents.MODEL_CONVERT_OPENVINO,
                payloads.ModelConvertOpenVinoPayload(weight_name=name),
            )
        self.after(150, self._populate_weights_treeview)
        self._start_conversion_poller()

    def _on_clear_cache_selected(self) -> None:
        name = self._selected_weight_name()
        if not name:
            return
        if not messagebox.askyesno(
            _("Delete OpenVINO cache"),
            _("Delete the OpenVINO cache of '{name}'?").format(name=name),
            parent=self,
        ):
            return
        report = self.controller.hardware_vm.clear_openvino_cache(name)
        self._show_cache_clear_report(report, scope=name)
        self._populate_weights_treeview()

    def _on_clear_cache_all(self) -> None:
        if not messagebox.askyesno(
            _("Delete ALL caches"),
            _(
                "This action removes ALL converted OpenVINO models.\n\n"
                "They will be regenerated on the next detection. Continue?"
            ),
            parent=self,
            icon="warning",
        ):
            return
        if not messagebox.askyesno(
            _("Additional confirmation"),
            _("Confirm the removal of every OpenVINO cache?"),
            parent=self,
            icon="warning",
        ):
            return
        report = self.controller.hardware_vm.clear_openvino_cache(None)
        self._show_cache_clear_report(report, scope=None)
        self._populate_weights_treeview()

    def _show_cache_clear_report(
        self,
        report: dict[str, list[str]] | None,
        *,
        scope: str | None,
    ) -> None:
        if not report:
            return
        cleared = report.get("cleared", [])
        locked = report.get("locked", [])
        orphans_locked = report.get("orphans_locked", [])

        if not locked and not orphans_locked:
            scope_label = (
                _("of weight '{name}'").format(name=scope) if scope else _("of every weight")
            )
            messagebox.showinfo(
                _("OpenVINO caches deleted"),
                _(
                    "OpenVINO cache {scope} removed successfully "
                    "({count} entry/entries processed).\n\n"
                    "The status in the list is back to '—'; the next detection will "
                    "regenerate the cache."
                ).format(scope=scope_label, count=len(cleared)),
                parent=self,
            )
            return

        parts: list[str] = []
        if cleared:
            parts.append(_("✓ {count} cache(s) deleted successfully.").format(count=len(cleared)))
        if locked:
            parts.append(
                _("⚠ Could not delete the cache of the following weights:\n  • ")
                + "\n  • ".join(locked)
            )
        if orphans_locked:
            parts.append(
                _("⚠ Orphan folders that resisted removal:\n  • ") + "\n  • ".join(orphans_locked)
            )
        parts.append(
            _(
                "\nLikely cause: the running detector still has the model loaded in "
                "memory (open handle), or OneDrive is syncing the files.\n\n"
                "Fixes:\n"
                "  1. Close and reopen DRerio LogAI (releases the model handle);\n"
                "  2. Pause OneDrive temporarily and try again;\n"
                "  3. Use 'poetry run zebtrack --reset-openvino-cache' before starting "
                "the app — it clears the cache while nothing is loaded."
            )
        )
        messagebox.showwarning(_("Caches partially deleted"), "\n\n".join(parts), parent=self)

    def _on_rescan_folder(self) -> None:
        wm = self.controller.weight_manager
        before = set(wm.weights.keys()) if wm else set()
        self._publish_model_event(UIEvents.MODEL_RESCAN_WEIGHTS, payloads.EmptyPayload())
        self.after(180, self._refresh_weights_catalog)
        if not wm:
            return

        after = set(wm.weights.keys())
        new = after - before
        if new:
            messagebox.showinfo(
                _("Rescan"),
                _("{count} new weight(s) detected:\n  • ").format(count=len(new))
                + "\n  • ".join(sorted(new)),
                parent=self,
            )
            return
        messagebox.showinfo(
            _("Rescan"),
            _("No new weight found in '{folder}'.").format(folder=wm.weights_dir),
            parent=self,
        )

    def _on_reset_registry(self) -> None:
        if not messagebox.askyesno(
            _("Factory reset"),
            _(
                "This action deletes 'weights_config.json' and rebuilds the registry "
                "from the settings + a scan of the 'weights/' folder.\n\n"
                "Custom defaults will be lost. Continue?"
            ),
            parent=self,
            icon="warning",
        ):
            return
        if not messagebox.askyesno(
            _("Additional confirmation"),
            _("Confirm resetting the weight list to the factory state?"),
            parent=self,
            icon="warning",
        ):
            return
        self._publish_model_event(UIEvents.MODEL_RESET_REGISTRY, payloads.EmptyPayload())
        self.after(200, self._refresh_weights_catalog)

    def _on_force_benchmark(self) -> None:
        if not messagebox.askyesno(
            _("Re-run benchmark"),
            _(
                "The benchmark will take ~10-30 seconds and will update the optimal "
                "OpenVINO settings. Continue?"
            ),
            parent=self,
        ):
            return
        self._publish_model_event(UIEvents.MODEL_FORCE_BENCHMARK, payloads.EmptyPayload())
        messagebox.showinfo(
            _("Benchmark running"),
            _(
                "The benchmark is running in the background. The settings will be "
                "applied automatically when it finishes."
            ),
            parent=self,
        )

    def _on_open_cache_folder(self) -> None:
        wm = self.controller.weight_manager
        if not wm:
            return
        cache_dir = Path(wm.config_dir) / "openvino_model_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(cache_dir))  # type: ignore[attr-defined]
            else:
                import subprocess

                opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"  # type: ignore[attr-defined]
                subprocess.Popen([opener, str(cache_dir)])
        except Exception as exc:
            messagebox.showwarning(
                _("Failed to open folder"),
                _("Could not open the file explorer at:\n{path}\n\n{error}").format(
                    path=cache_dir, error=exc
                ),
                parent=self,
            )

    def _start_conversion_poller(self) -> None:
        if self._conversion_poller_id is not None:
            return
        self._conversion_poller_id = self.after(
            _CONVERSION_POLL_INTERVAL_MS,
            self._poll_conversion_status,
        )

    def _poll_conversion_status(self) -> None:
        self._conversion_poller_id = None
        wm = self.controller.weight_manager
        if not wm:
            return
        converting = [
            name
            for name, details in wm.weights.items()
            if details.get("openvino_status") == "converting"
        ]
        try:
            self._populate_weights_treeview()
        except Exception as exc:
            log.debug("global_model_config.poll.populate_failed", error=str(exc))
            return
        if converting:
            self._conversion_poller_id = self.after(
                _CONVERSION_POLL_INTERVAL_MS,
                self._poll_conversion_status,
            )

    def update_openvino_status_label(self, status: str) -> None:
        self.openvino_status_var.set(status)

    def _on_openvino_toggled_local(self) -> None:
        self._publish_model_event(
            UIEvents.MODEL_SET_OPENVINO,
            payloads.ModelSetOpenVinoPayload(
                use_openvino=self.use_openvino_var.get(),
                dialog=self,
            ),
        )
        if self.device_combobox is not None:
            state = "readonly" if self.use_openvino_var.get() else "disabled"
            self.device_combobox.configure(state=state)

    def _populate_device_combobox(self) -> None:
        if self.device_combobox is None:
            return

        from zebtrack.utils.hardware_detection import get_openvino_devices

        devices = list(get_openvino_devices())
        options = ["AUTO"]
        for device in ("CPU", "GPU", "NPU"):
            if any(device in detected for detected in devices):
                options.append(device)
        self.device_combobox["values"] = options

        settings_obj = getattr(self.controller, "settings_obj", None)
        current = getattr(getattr(settings_obj, "openvino", None), "device", "AUTO")
        self.device_var.set(current if current in options else "AUTO")

    def _on_device_selected(self, _event=None) -> None:
        selected_device = self.device_var.get()
        log.info("global_model_config.device_selected", device=selected_device)
        self._publish_model_event(
            UIEvents.MODEL_SET_OPENVINO,
            payloads.ModelSetOpenVinoPayload(
                use_openvino=self.use_openvino_var.get(),
                device=selected_device,
                dialog=self,
            ),
        )

    def destroy(self):
        poller_id = self._conversion_poller_id
        if poller_id is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(poller_id)
            self._conversion_poller_id = None
        super().destroy()
