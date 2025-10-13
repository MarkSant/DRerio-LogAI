"""Wizard step for selecting detection models, weights, and detector parameters."""

from __future__ import annotations

from tkinter import BooleanVar, Label, LabelFrame, StringVar, ttk
from tkinter import font as tkfont

import structlog

from zebtrack.core.weight_manager import WeightManager
from zebtrack.settings import settings
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip

log = structlog.get_logger()

DEFAULT_TRACK_THRESHOLD = 0.25
DEFAULT_MATCH_THRESHOLD = 0.15
_METHOD_OPTIONS: dict[str, str] = {
    "seg": "Segmentação (seg)",
    "det": "Detecção (det)",
}


class ModelSelectionStep(WizardStep):
    """Allow users to review or adjust model strategy, weight usage, and thresholds."""

    def __init__(self, parent, wizard_data: dict):
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.MODEL_SELECTION

        self.weight_manager = WeightManager()
        self.seg_weight_names: list[str] = []
        self.det_weight_names: list[str] = []

        # UI state variables
        self.aquarium_method_var = StringVar()
        self.aquarium_weight_var = StringVar()
        self.animal_method_var = StringVar()
        self.animal_weight_var = StringVar()
        self.use_openvino_var = BooleanVar(value=False)

        self.confidence_var = StringVar()
        self.nms_var = StringVar()
        self.track_var = StringVar()
        self.match_var = StringVar()

        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None
        self.animal_method_hint_var = StringVar(value="")

        self._aquarium_weight_combo: ttk.Combobox | None = None
        self._animal_weight_combo: ttk.Combobox | None = None
        self._methods_frame: LabelFrame | None = None

        self._load_weight_catalog()
        self._prefill_from_wizard_data()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_weight_catalog(self) -> None:
        """Populate cached segmentation/detection weight name lists."""

        self.seg_weight_names.clear()
        self.det_weight_names.clear()

        for name in self.weight_manager.get_all_weights():
            details = self.weight_manager.get_weight_details(name) or {}
            weight_type = details.get("type")
            if weight_type == "seg":
                self.seg_weight_names.append(name)
            elif weight_type == "det":
                self.det_weight_names.append(name)

        self.seg_weight_names.sort()
        self.det_weight_names.sort()

        log.info(
            "wizard.model_step.weights_loaded",
            seg=len(self.seg_weight_names),
            det=len(self.det_weight_names),
        )

    def _method_display(self, method_key: str | None) -> str:
        """Helper to format method labels for display."""

        if method_key in _METHOD_OPTIONS:
            return _METHOD_OPTIONS[method_key]
        if method_key:
            return method_key
        return _METHOD_OPTIONS["seg"]

    def _prefill_from_wizard_data(self) -> None:
        """Initialise state variables from wizard data or global defaults."""

        selection = dict(self.wizard_data.get("model_selection", {}) or {})
        weight_assignments = dict(self.wizard_data.get("weight_assignments", {}) or {})
        defaults = settings.model_selection

        aquarium_method = selection.get("aquarium_method", defaults.aquarium_method)
        animal_method = selection.get("animal_method", defaults.animal_method)
        use_openvino = selection.get("use_openvino")
        if use_openvino is None:
            use_openvino = defaults.use_openvino

        self.aquarium_method_var.set(self._method_display(aquarium_method))
        self.animal_method_var.set(self._method_display(animal_method))
        self.use_openvino_var.set(bool(use_openvino))

        aquarium_weight = weight_assignments.get("aquarium")
        animal_weight = weight_assignments.get("animal")

        if aquarium_weight:
            self.aquarium_weight_var.set(aquarium_weight)
        else:
            self.aquarium_weight_var.set(self._default_weight_for_method(aquarium_method))

        if animal_weight:
            self.animal_weight_var.set(animal_weight)
        else:
            self.animal_weight_var.set(self._default_weight_for_method(animal_method))

        detector_params = dict(self.wizard_data.get("detector_parameters", {}) or {})
        confidence_threshold = float(
            detector_params.get(
                "confidence_threshold", settings.yolo_model.confidence_threshold
            )
        )
        self.confidence_var.set(f"{confidence_threshold:.3f}")

        nms_threshold = float(
            detector_params.get("nms_threshold", settings.yolo_model.nms_threshold)
        )
        self.nms_var.set(f"{nms_threshold:.3f}")

        track_threshold = float(
            detector_params.get("track_threshold", DEFAULT_TRACK_THRESHOLD)
        )
        self.track_var.set(f"{track_threshold:.3f}")

        match_threshold = float(
            detector_params.get("match_threshold", DEFAULT_MATCH_THRESHOLD)
        )
        self.match_var.set(f"{match_threshold:.3f}")

    def _default_weight_for_method(self, method_key: str) -> str:
        if method_key == "seg":
            name, _ = self.weight_manager.get_default_seg_weight()
            return name or (self.seg_weight_names[0] if self.seg_weight_names else "")
        if method_key == "det":
            name, _ = self.weight_manager.get_default_det_weight()
            return name or (self.det_weight_names[0] if self.det_weight_names else "")
        return ""

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build_ui(self) -> None:
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text="Modelos e Pesos", font=title_font)
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text=(
                "Ajuste como o ZebTrack utilizará cada modelo de detecção.\n"
                "Se preferir, mantenha os padrões recomendados e avance."
            ),
            fg="gray",
            wraplength=520,
            justify="left",
        )
        subtitle.pack(pady=(0, 15))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=520,
            justify="left",
        )
        self.template_info_label.pack_forget()

        methods_frame = LabelFrame(
            self,
            text="Métodos e Pesos por Função",
            padx=15,
            pady=10,
        )
        methods_frame.pack(fill="x", pady=(0, 15))
        self._methods_frame = methods_frame

        self._build_method_row(
            parent=methods_frame,
            row=0,
            title="Aquário (detecção de arena)",
            method_var=self.aquarium_method_var,
            weight_var=self.aquarium_weight_var,
            combo_attr="_aquarium_weight_combo",
        )

        self._build_method_row(
            parent=methods_frame,
            row=1,
            title="Animais (rastreamento)",
            method_var=self.animal_method_var,
            weight_var=self.animal_weight_var,
            combo_attr="_animal_weight_combo",
        )

        animal_hint = Label(
            methods_frame,
            textvariable=self.animal_method_hint_var,
            fg="#bb6600",
            wraplength=480,
            justify="left",
        )
        animal_hint.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        acceleration_frame = LabelFrame(
            self,
            text="Aceleração / OpenVINO",
            padx=15,
            pady=10,
        )
        acceleration_frame.pack(fill="x", pady=(0, 15))

        openvino_check = ttk.Checkbutton(
            acceleration_frame,
            text="Usar OpenVINO (requer conversão do peso)",
            variable=self.use_openvino_var,
        )
        openvino_check.pack(anchor="w")
        ToolTip(
            openvino_check,
            "Ative quando o modelo OpenVINO correspondente já foi convertido."
            " Permite inferência mais rápida em CPUs compatíveis.",
        )

        detector_frame = LabelFrame(
            self,
            text="Parâmetros do Detector",
            padx=15,
            pady=10,
        )
        detector_frame.pack(fill="x", pady=(0, 15))

        self._build_detector_param_row(
            detector_frame,
            label="Confiança mínima (0-1):",
            var=self.confidence_var,
            column=0,
            tooltip="Detecções abaixo desse valor são descartadas.",
        )
        self._build_detector_param_row(
            detector_frame,
            label="NMS (sobreposição, 0-1):",
            var=self.nms_var,
            column=1,
            tooltip="Filtra caixas muito próximas com a mesma classe.",
        )
        self._build_detector_param_row(
            detector_frame,
            label="ByteTrack - track (0-1):",
            var=self.track_var,
            column=0,
            row=1,
            tooltip=(
                "Pontuação mínima para manter a trajetória ativa. Ajuste quando"
                " houver trocas frequentes de IDs."
            ),
        )
        self._build_detector_param_row(
            detector_frame,
            label="ByteTrack - associação (0-1):",
            var=self.match_var,
            column=1,
            row=1,
            tooltip=(
                "Limiar para associar detecções às trajetórias existentes."
                " Valores mais altos evitam associações erradas."
            ),
        )

        defaults_label = Label(
            detector_frame,
            text=(
                "Padrões atuais: confiança {conf:.2f}, NMS {nms:.2f}, track {trk:.2f},"
                " associação {match:.2f}."
            ).format(
                conf=settings.yolo_model.confidence_threshold,
                nms=settings.yolo_model.nms_threshold,
                trk=DEFAULT_TRACK_THRESHOLD,
                match=DEFAULT_MATCH_THRESHOLD,
            ),
            fg="#555555",
            wraplength=520,
            justify="left",
        )
        defaults_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        footer = Label(
            self,
            text=(
                "Dica: mantenha os padrões se ainda estiver configurando os vídeos."
                " Você pode revisar esses valores depois nas configurações do projeto."
            ),
            fg="#555555",
            wraplength=520,
            justify="left",
        )
        footer.pack(fill="x", pady=(5, 0))

        self.aquarium_method_var.trace_add("write", self._on_aquarium_method_change)
        self.animal_method_var.trace_add("write", self._on_animal_method_change)

        self._update_template_banner()
        self._refresh_weight_dropdowns()
        self._update_animal_method_hint()

    def _build_method_row(
        self,
        parent,
        row: int,
        title: str,
        method_var: StringVar,
        weight_var: StringVar,
        combo_attr: str,
    ) -> None:
        Label(parent, text=title, anchor="w").grid(row=row, column=0, sticky="w")

        method_combo = ttk.Combobox(
            parent,
            textvariable=method_var,
            values=[label for label in _METHOD_OPTIONS.values()],
            state="readonly",
            width=24,
        )
        method_combo.grid(row=row, column=1, padx=(10, 10), pady=5, sticky="w")
        ToolTip(
            method_combo,
            "Segmentação suporta múltiplos animais por aquário.\n"
            "Detecção é otimizada para um animal por aquário e usa ByteTrack.",
        )

        weight_combo = ttk.Combobox(
            parent,
            textvariable=weight_var,
            values=[],
            state="readonly",
            width=28,
        )
        weight_combo.grid(row=row, column=2, pady=5, sticky="w")
        ToolTip(
            weight_combo,
            "Selecione o arquivo de peso carregado para esta função.",
        )
        setattr(self, combo_attr, weight_combo)

    def _build_detector_param_row(
        self,
        parent,
        label: str,
        var: StringVar,
        column: int,
        row: int = 0,
        tooltip: str = "",
    ) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, padx=(0, 12), pady=5, sticky="w")

        Label(frame, text=label).pack(side="left")
        entry = ttk.Entry(frame, textvariable=var, width=8)
        entry.pack(side="left", padx=(5, 0))
        if tooltip:
            ToolTip(entry, tooltip)

    # ------------------------------------------------------------------
    # Event handlers and derived state
    # ------------------------------------------------------------------
    def _on_aquarium_method_change(self, *_):
        self._refresh_weight_dropdowns(role="aquarium")

    def _on_animal_method_change(self, *_):
        self._refresh_weight_dropdowns(role="animal")
        self._update_animal_method_hint()

    def _refresh_weight_dropdowns(self, role: str | None = None) -> None:
        roles = [role] if role else ["aquarium", "animal"]

        for current in roles:
            if current == "aquarium":
                combo = self._aquarium_weight_combo
                method_var = self.aquarium_method_var
                weight_var = self.aquarium_weight_var
            else:
                combo = self._animal_weight_combo
                method_var = self.animal_method_var
                weight_var = self.animal_weight_var

            if combo is None:
                continue

            method_key = self._method_key_from_label(method_var.get())
            if method_key == "seg":
                options = self.seg_weight_names
            else:
                options = self.det_weight_names
            combo.configure(values=options)

            if options:
                current_weight = weight_var.get()
                if current_weight not in options:
                    weight_var.set(options[0])
                combo.configure(state="readonly")
            else:
                weight_var.set("")
                combo.configure(state="disabled")

    def _method_key_from_label(self, label_value: str) -> str:
        for key, label in _METHOD_OPTIONS.items():
            if label_value == label or label_value == key:
                return key
        return label_value or "seg"

    def _update_animal_method_hint(self) -> None:
        method_key = self._method_key_from_label(self.animal_method_var.get())
        animals_per_aquarium = int(self.wizard_data.get("animals_per_aquarium", 1) or 1)

        if method_key == "det" and animals_per_aquarium > 1:
            self.animal_method_hint_var.set(
                "⚠️ Detecção (det) é recomendada para apenas 1 animal por aquário."
                " Considere segmentação (seg) para múltiplos animais."
            )
        else:
            self.animal_method_hint_var.set("")

    # ------------------------------------------------------------------
    # Wizard lifecycle overrides
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._update_template_banner()
        self._refresh_weight_dropdowns()
        self._update_animal_method_hint()

    def set_data(self, data: dict):
        if not data:
            return
        model_selection = self.wizard_data.setdefault("model_selection", {})
        model_selection.update(data.get("model_selection", {}))
        if "aquarium_method" in data:
            model_selection["aquarium_method"] = data["aquarium_method"]
        if "animal_method" in data:
            model_selection["animal_method"] = data["animal_method"]
        if "use_openvino" in data:
            model_selection["use_openvino"] = data["use_openvino"]
        if "weight_assignments" in data:
            self.wizard_data["weight_assignments"] = data.get("weight_assignments")
        if "detector_parameters" in data:
            self.wizard_data["detector_parameters"] = data.get("detector_parameters")
        self._prefill_from_wizard_data()
        self._refresh_weight_dropdowns()
        self._update_animal_method_hint()

    def _update_template_banner(self) -> None:
        metadata = self.wizard_data.get("template_metadata")
        banner = format_template_banner(metadata)
        if banner:
            self.template_info_var.set(banner)
            label = self.template_info_label
            if label and not label.winfo_ismapped():
                target = self._methods_frame
                if target is not None:
                    label.pack(before=target)
                else:
                    label.pack()
        else:
            label = self.template_info_label
            if label and label.winfo_ismapped():
                label.pack_forget()

    # ------------------------------------------------------------------
    # Validation and data extraction
    # ------------------------------------------------------------------
    def validate(self) -> tuple[bool, str]:
        try:
            confidence = float(self.confidence_var.get())
            nms = float(self.nms_var.get())
            track = float(self.track_var.get())
            match = float(self.match_var.get())
        except ValueError:
            return False, "Informe valores decimais entre 0 e 1 para os parâmetros."

        for label, value in (
            ("confiança", confidence),
            ("NMS", nms),
            ("track", track),
            ("associação", match),
        ):
            if not 0.0 < value < 1.0:
                return False, f"O parâmetro de {label} deve estar entre 0 e 1."

        for role, method_var, weight_var in (
            ("aquário", self.aquarium_method_var, self.aquarium_weight_var),
            ("animais", self.animal_method_var, self.animal_weight_var),
        ):
            method_key = self._method_key_from_label(method_var.get())
            if method_key == "seg":
                options = self.seg_weight_names
            else:
                options = self.det_weight_names
            if options and weight_var.get() not in options:
                return False, (
                    f"Selecione um peso válido para {role}."
                    " O arquivo precisa corresponder ao método escolhido."
                )

        return True, ""

    def get_data(self) -> dict:
        aquarium_method = self._method_key_from_label(self.aquarium_method_var.get())
        animal_method = self._method_key_from_label(self.animal_method_var.get())

        return {
            "aquarium_method": aquarium_method,
            "animal_method": animal_method,
            "use_openvino": bool(self.use_openvino_var.get()),
            "weight_assignments": {
                "aquarium": self.aquarium_weight_var.get() or None,
                "animal": self.animal_weight_var.get() or None,
            },
            "detector_parameters": {
                "confidence_threshold": float(self.confidence_var.get()),
                "nms_threshold": float(self.nms_var.get()),
                "track_threshold": float(self.track_var.get()),
                "match_threshold": float(self.match_var.get()),
            },
            "model_selection": {
                "aquarium_method": aquarium_method,
                "animal_method": animal_method,
                "use_openvino": bool(self.use_openvino_var.get()),
            },
        }
