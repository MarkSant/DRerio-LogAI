"""Behavioral analysis configuration widget component.

Reusable widget for configuring thigmotaxis and geotaxis behavioral analysis parameters.
Used in Wizard CalibrationStep, SingleVideoConfigDialog, and LiveAnalysisDialog.
"""

from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, ttk

import structlog

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.wizard.models import AquariumPerspective, GeotaxisMode

log = structlog.get_logger()


class BehavioralConfigWidget(BaseWidget):
    """
    Reusable widget for behavioral analysis configuration.

    Provides UI for configuring:
    - Aquarium perspective (top_down / lateral) - Required
    - Thigmotaxis distance threshold (cm)
    - Geotaxis settings (only for lateral perspective):
      - Enable/disable
      - Mode (distance / zones)
      - Distance threshold (cm)
      - Number of zones
      - Bottom zones to consider (1 or 2)

    Events emitted:
    - behavioral_config.perspective_changed: Perspective selection changed
    - behavioral_config.geotaxis_toggled: Geotaxis enabled/disabled
    - behavioral_config.values_changed: Any configuration value changed
    """

    def __init__(
        self,
        parent,
        event_bus: EventBus | None = None,
        default_thigmotaxis_cm: float = 1.5,
        default_geotaxis_cm: float = 1.5,
        default_num_zones: int = 3,
        default_bottom_zones: int = 1,
        **kwargs,
    ):
        """
        Initialize the behavioral configuration widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            default_thigmotaxis_cm: Default thigmotaxis distance threshold
            default_geotaxis_cm: Default geotaxis distance threshold
            default_num_zones: Default number of vertical zones
            default_bottom_zones: Default number of bottom zones (1 or 2)
            default_perspective: Default aquarium perspective (LATERAL or TOP_DOWN)
            default_geotaxis_mode: Default geotaxis calculation mode (DISTANCE or ZONES)
            **kwargs: Additional arguments passed to BaseWidget
        """
        # Store defaults before super().__init__ calls _build_ui
        self._default_thigmotaxis_cm = default_thigmotaxis_cm
        self._default_geotaxis_cm = default_geotaxis_cm
        self._default_num_zones = default_num_zones
        self._default_bottom_zones = default_bottom_zones
        self._default_perspective = kwargs.pop(
            "default_perspective", AquariumPerspective.LATERAL.value
        )
        self._default_geotaxis_mode = kwargs.pop("default_geotaxis_mode", GeotaxisMode.ZONES.value)

        # State variables - initialized before _build_ui
        self.perspective_var = StringVar(value=self._default_perspective)
        self.thigmotaxis_distance_var = DoubleVar(value=default_thigmotaxis_cm)
        self.geotaxis_enabled_var = BooleanVar(
            value=True if self._default_perspective == AquariumPerspective.LATERAL.value else False
        )
        self.geotaxis_mode_var = StringVar(value=self._default_geotaxis_mode)
        self.geotaxis_distance_var = DoubleVar(value=default_geotaxis_cm)
        self.geotaxis_num_zones_var = IntVar(value=default_num_zones)
        self.geotaxis_bottom_zones_var = IntVar(value=default_bottom_zones)

        # Widget references
        self.perspective_combo: ttk.Combobox | None = None
        self.thigmotaxis_spinbox: ttk.Spinbox | None = None
        self.geotaxis_check: ttk.Checkbutton | None = None
        self.geotaxis_frame: ttk.LabelFrame | None = None
        self.distance_radio: ttk.Radiobutton | None = None
        self.zones_radio: ttk.Radiobutton | None = None
        self.distance_frame: ttk.Frame | None = None
        self.zones_frame: ttk.Frame | None = None
        self.geotaxis_distance_spinbox: ttk.Spinbox | None = None
        self.num_zones_spinbox: ttk.Spinbox | None = None
        self.bottom_zones_spinbox: ttk.Spinbox | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the behavioral configuration widget UI."""
        # Main container with padding
        self.configure(padding=10)

        # Section title
        title_label = ttk.Label(
            self,
            text="Configuração de Análise Comportamental",
            font=("TkDefaultFont", 10, "bold"),
        )
        title_label.pack(fill="x", pady=(0, 10))

        # Aquarium Perspective Section
        self._build_perspective_section()

        # Thigmotaxis Section
        self._build_thigmotaxis_section()

        # Geotaxis Section (conditional on lateral perspective)
        self._build_geotaxis_section()

        # Initial state update
        self._on_perspective_changed()

    def _build_perspective_section(self) -> None:
        """Build the aquarium perspective selection section."""
        perspective_frame = ttk.LabelFrame(self, text="Perspectiva do Aquário *", padding=5)
        perspective_frame.pack(fill="x", pady=(0, 10))

        # Description
        desc_label = ttk.Label(
            perspective_frame,
            text="Selecione como a câmera visualiza o aquário:",
            wraplength=500,
        )
        desc_label.pack(fill="x", pady=(0, 5))

        # Combobox for perspective selection
        perspective_values = [
            ("Vista de Cima (Top-Down)", AquariumPerspective.TOP_DOWN.value),
            ("Vista Lateral", AquariumPerspective.LATERAL.value),
        ]
        display_values = [v[0] for v in perspective_values]
        self._perspective_mapping = {v[0]: v[1] for v in perspective_values}
        self._perspective_reverse = {v[1]: v[0] for v in perspective_values}

        combo_frame = ttk.Frame(perspective_frame)
        combo_frame.pack(fill="x")

        ttk.Label(combo_frame, text="Perspectiva:").pack(side="left", padx=(0, 5))

        self.perspective_combo = ttk.Combobox(
            combo_frame,
            values=display_values,
            state="readonly",
            width=25,
        )
        self.perspective_combo.pack(side="left")
        self.perspective_combo.set(display_values[1])  # Default to Lateral
        self.perspective_combo.bind("<<ComboboxSelected>>", self._on_perspective_combo_changed)

    def _build_thigmotaxis_section(self) -> None:
        """Build the thigmotaxis configuration section."""
        thigmotaxis_frame = ttk.LabelFrame(
            self, text="Thigmotaxis (Proximidade às Paredes)", padding=5
        )
        thigmotaxis_frame.pack(fill="x", pady=(0, 10))

        # Description
        desc_label = ttk.Label(
            thigmotaxis_frame,
            text="Distância limite para considerar o peixe próximo às paredes do aquário:",
            wraplength=500,
        )
        desc_label.pack(fill="x", pady=(0, 5))

        # Spinbox for distance threshold
        input_frame = ttk.Frame(thigmotaxis_frame)
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text="Distância (cm):").pack(side="left", padx=(0, 5))

        self.thigmotaxis_spinbox = ttk.Spinbox(
            input_frame,
            from_=0.1,
            to=10.0,
            increment=0.1,
            textvariable=self.thigmotaxis_distance_var,
            width=8,
            format="%.1f",
        )
        self.thigmotaxis_spinbox.pack(side="left")
        self.thigmotaxis_spinbox.bind("<FocusOut>", self._on_value_changed)
        self.thigmotaxis_spinbox.bind("<Return>", self._on_value_changed)

        ttk.Label(input_frame, text="(padrão: 1.5 cm)").pack(side="left", padx=(10, 0))

    def _build_geotaxis_section(self) -> None:
        """Build the geotaxis configuration section."""
        self.geotaxis_frame = ttk.LabelFrame(
            self, text="Geotaxis (Proximidade ao Fundo) - Apenas Vista Lateral", padding=5
        )
        self.geotaxis_frame.pack(fill="x", pady=(0, 10))

        # Enable checkbox
        self.geotaxis_check = ttk.Checkbutton(
            self.geotaxis_frame,
            text="Habilitar análise de geotaxis",
            variable=self.geotaxis_enabled_var,
            command=self._on_geotaxis_toggled,
        )
        self.geotaxis_check.pack(fill="x", pady=(0, 5))

        # Geotaxis options container (shown/hidden based on checkbox)
        self.geotaxis_options_frame = ttk.Frame(self.geotaxis_frame)
        self.geotaxis_options_frame.pack(fill="x", pady=(5, 0))

        # Mode selection (radio buttons)
        mode_frame = ttk.Frame(self.geotaxis_options_frame)
        mode_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(mode_frame, text="Modo de cálculo:").pack(side="left", padx=(0, 10))

        self.distance_radio = ttk.Radiobutton(
            mode_frame,
            text="Por Distância",
            variable=self.geotaxis_mode_var,
            value=GeotaxisMode.DISTANCE.value,
            command=self._on_mode_changed,
        )
        self.distance_radio.pack(side="left", padx=(0, 10))

        self.zones_radio = ttk.Radiobutton(
            mode_frame,
            text="Por Zonas Verticais",
            variable=self.geotaxis_mode_var,
            value=GeotaxisMode.ZONES.value,
            command=self._on_mode_changed,
        )
        self.zones_radio.pack(side="left")

        # Distance mode options
        self.distance_frame = ttk.Frame(self.geotaxis_options_frame)
        self.distance_frame.pack(fill="x", pady=(5, 0))

        ttk.Label(self.distance_frame, text="Distância do fundo (cm):").pack(
            side="left", padx=(0, 5)
        )

        self.geotaxis_distance_spinbox = ttk.Spinbox(
            self.distance_frame,
            from_=0.1,
            to=10.0,
            increment=0.1,
            textvariable=self.geotaxis_distance_var,
            width=8,
            format="%.1f",
        )
        self.geotaxis_distance_spinbox.pack(side="left")
        self.geotaxis_distance_spinbox.bind("<FocusOut>", self._on_value_changed)

        # Zones mode options
        self.zones_frame = ttk.Frame(self.geotaxis_options_frame)
        self.zones_frame.pack(fill="x", pady=(5, 0))

        # Number of zones
        zones_row1 = ttk.Frame(self.zones_frame)
        zones_row1.pack(fill="x", pady=(0, 5))

        ttk.Label(zones_row1, text="Dividir aquário em:").pack(side="left", padx=(0, 5))

        self.num_zones_spinbox = ttk.Spinbox(
            zones_row1,
            from_=2,
            to=10,
            increment=1,
            textvariable=self.geotaxis_num_zones_var,
            width=5,
        )
        self.num_zones_spinbox.pack(side="left")
        self.num_zones_spinbox.bind("<FocusOut>", self._on_value_changed)

        ttk.Label(zones_row1, text="zonas verticais").pack(side="left", padx=(5, 0))

        # Bottom zones to consider
        zones_row2 = ttk.Frame(self.zones_frame)
        zones_row2.pack(fill="x")

        ttk.Label(zones_row2, text="Considerar como 'fundo':").pack(side="left", padx=(0, 5))

        self.bottom_zones_spinbox = ttk.Spinbox(
            zones_row2,
            from_=1,
            to=2,
            increment=1,
            textvariable=self.geotaxis_bottom_zones_var,
            width=5,
        )
        self.bottom_zones_spinbox.pack(side="left")
        self.bottom_zones_spinbox.bind("<FocusOut>", self._on_value_changed)

        ttk.Label(zones_row2, text="zona(s) mais baixa(s)").pack(side="left", padx=(5, 0))

        # Initial visibility
        self._update_geotaxis_visibility()

    # Event handlers

    def _on_perspective_combo_changed(self, event=None) -> None:
        """Handle perspective combobox selection change."""
        if not self.perspective_combo:
            return

        display_value = self.perspective_combo.get()
        actual_value = self._perspective_mapping.get(
            display_value, AquariumPerspective.TOP_DOWN.value
        )
        self.perspective_var.set(actual_value)
        self._on_perspective_changed()

    def _on_perspective_changed(self, event=None) -> None:
        """Handle perspective change - enable/disable geotaxis section."""
        perspective = self.perspective_var.get()
        is_lateral = perspective == AquariumPerspective.LATERAL.value

        # Enable/disable geotaxis section based on perspective
        if is_lateral:
            if self.geotaxis_frame:
                self._set_widget_state(self.geotaxis_frame, "normal")
            if self.geotaxis_check:
                self.geotaxis_check.configure(state="normal")
        else:
            # Disable geotaxis for top-down view
            self.geotaxis_enabled_var.set(False)
            if self.geotaxis_frame:
                self._set_widget_state(self.geotaxis_frame, "disabled")
            if self.geotaxis_check:
                self.geotaxis_check.configure(state="disabled")

        self._update_geotaxis_visibility()
        self.emit_event("behavioral_config.perspective_changed", {"perspective": perspective})
        self._emit_values_changed()

    def _on_geotaxis_toggled(self, event=None) -> None:
        """Handle geotaxis enable/disable toggle."""
        self._update_geotaxis_visibility()
        enabled = self.geotaxis_enabled_var.get()
        self.emit_event("behavioral_config.geotaxis_toggled", {"enabled": enabled})
        self._emit_values_changed()

    def _on_mode_changed(self, event=None) -> None:
        """Handle geotaxis mode change (distance vs zones)."""
        self._update_geotaxis_visibility()
        self._emit_values_changed()

    def _on_value_changed(self, event=None) -> None:
        """Handle any configuration value change."""
        self._emit_values_changed()

    def _emit_values_changed(self) -> None:
        """Emit event with current configuration values."""
        self.emit_event("behavioral_config.values_changed", {"config": self.get_values()})

    def _update_geotaxis_visibility(self) -> None:
        """Update visibility of geotaxis sub-options based on current state."""
        enabled = self.geotaxis_enabled_var.get()
        mode = self.geotaxis_mode_var.get()

        if enabled:
            # Show options frame
            if self.geotaxis_options_frame:
                self.geotaxis_options_frame.pack(fill="x", pady=(5, 0))

            # Show appropriate mode frame
            if mode == GeotaxisMode.DISTANCE.value:
                if self.distance_frame:
                    self.distance_frame.pack(fill="x", pady=(5, 0))
                if self.zones_frame:
                    self.zones_frame.pack_forget()
            else:
                if self.distance_frame:
                    self.distance_frame.pack_forget()
                if self.zones_frame:
                    self.zones_frame.pack(fill="x", pady=(5, 0))
        else:
            # Hide options frame
            if self.geotaxis_options_frame:
                self.geotaxis_options_frame.pack_forget()

    # Public API

    def get_values(self) -> dict:
        """
        Get the current configuration values.

        Returns:
            Dictionary with all behavioral analysis configuration values.
        """
        return {
            "aquarium_perspective": self.perspective_var.get(),
            "thigmotaxis_distance_cm": self.thigmotaxis_distance_var.get(),
            "geotaxis_enabled": self.geotaxis_enabled_var.get(),
            "geotaxis_mode": self.geotaxis_mode_var.get(),
            "geotaxis_distance_cm": self.geotaxis_distance_var.get(),
            "geotaxis_num_zones": self.geotaxis_num_zones_var.get(),
            "geotaxis_bottom_zones": self.geotaxis_bottom_zones_var.get(),
        }

    def set_values(self, config: dict) -> None:
        """
        Set the configuration values from a dictionary.

        Args:
            config: Dictionary with configuration values. Keys:
                - aquarium_perspective: "top_down" or "lateral"
                - thigmotaxis_distance_cm: float
                - geotaxis_enabled: bool
                - geotaxis_mode: "distance" or "zones"
                - geotaxis_distance_cm: float
                - geotaxis_num_zones: int
                - geotaxis_bottom_zones: int (1 or 2)
        """
        if "aquarium_perspective" in config:
            perspective = config["aquarium_perspective"]
            self.perspective_var.set(perspective)
            # Update combobox display
            if self.perspective_combo and perspective in self._perspective_reverse:
                self.perspective_combo.set(self._perspective_reverse[perspective])

        if "thigmotaxis_distance_cm" in config:
            self.thigmotaxis_distance_var.set(config["thigmotaxis_distance_cm"])

        if "geotaxis_enabled" in config:
            self.geotaxis_enabled_var.set(config["geotaxis_enabled"])

        if "geotaxis_mode" in config:
            self.geotaxis_mode_var.set(config["geotaxis_mode"])

        if "geotaxis_distance_cm" in config:
            self.geotaxis_distance_var.set(config["geotaxis_distance_cm"])

        if "geotaxis_num_zones" in config:
            self.geotaxis_num_zones_var.set(config["geotaxis_num_zones"])

        if "geotaxis_bottom_zones" in config:
            self.geotaxis_bottom_zones_var.set(config["geotaxis_bottom_zones"])

        # Update UI state
        self._on_perspective_changed()

    def emit_event(self, event_name: str, data: dict | None = None) -> None:
        """Emit an event through the event bus.

        Safely handles cases where event_bus is not configured (e.g. in standalone dialogs).
        """
        if self.event_bus:
            self.event_bus.publish_event(event_name, data)
        # No else/logging needed - bus is optional for this widget

    def reset_to_defaults(self) -> None:
        """Reset all values to defaults."""
        self.set_values(
            {
                "aquarium_perspective": self._default_perspective,
                "thigmotaxis_distance_cm": self._default_thigmotaxis_cm,
                "geotaxis_enabled": True
                if self._default_perspective == AquariumPerspective.LATERAL.value
                else False,
                "geotaxis_mode": self._default_geotaxis_mode,
                "geotaxis_distance_cm": self._default_geotaxis_cm,
                "geotaxis_num_zones": self._default_num_zones,
                "geotaxis_bottom_zones": self._default_bottom_zones,
            }
        )

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate the current configuration.

        Returns:
            Tuple of (is_valid, list_of_error_messages).
        """
        errors = []

        # Validate thigmotaxis distance
        thigmotaxis = self.thigmotaxis_distance_var.get()
        if thigmotaxis < 0.1 or thigmotaxis > 10.0:
            errors.append("Distância de thigmotaxis deve estar entre 0.1 e 10.0 cm")

        # Validate geotaxis if enabled
        if self.geotaxis_enabled_var.get():
            perspective = self.perspective_var.get()
            if perspective != AquariumPerspective.LATERAL.value:
                errors.append("Geotaxis só pode ser habilitado para perspectiva lateral")

            mode = self.geotaxis_mode_var.get()
            if mode == GeotaxisMode.DISTANCE.value:
                geotaxis_dist = self.geotaxis_distance_var.get()
                if geotaxis_dist < 0.1 or geotaxis_dist > 10.0:
                    errors.append("Distância de geotaxis deve estar entre 0.1 e 10.0 cm")
            else:
                num_zones = self.geotaxis_num_zones_var.get()
                bottom_zones = self.geotaxis_bottom_zones_var.get()

                if num_zones < 2 or num_zones > 10:
                    errors.append("Número de zonas deve estar entre 2 e 10")

                if bottom_zones < 1 or bottom_zones > 2:
                    errors.append("Número de zonas de fundo deve ser 1 ou 2")

                if bottom_zones > num_zones:
                    errors.append("Zonas de fundo não podem exceder o número total de zonas")

        return (len(errors) == 0, errors)
