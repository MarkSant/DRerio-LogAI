"""Behavioral analysis configuration widget component.

Reusable widget for configuring thigmotaxis and geotaxis behavioral analysis parameters.
Used in Wizard CalibrationStep, SingleVideoConfigDialog, and LiveAnalysisDialog.
"""

from collections.abc import Callable
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, ttk
from typing import Any

import structlog

from zebtrack.analysis.behavioral_policy import animal_behavior_defaults
from zebtrack.core.services.experiment_profile import (
    ANIMAL_MODEL_KEY,
    PROTOCOL_KEY,
    PROTOCOL_PARAMS_KEY,
    AnimalModel,
    ExperimentProfile,
    ProtocolId,
    forced_animal_model,
    resolve_experiment_profile,
)
from zebtrack.i18n import _
from zebtrack.settings import (
    DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S,
    MAX_PLAUSIBLE_SPEED_LIMIT_CM_S,
    THIGMOTAXIS_MAX_DISTANCE_CM,
)
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus_v2 import EventBusV2
from zebtrack.ui.wizard.models import AquariumPerspective, GeotaxisMode

log = structlog.get_logger()

#: ``protocol_params[<protocol>]`` key of the trial type a session defaults to
#: (``BarnesParams.default_trial_type``). Persisted token: never translated.
DEFAULT_TRIAL_TYPE_KEY = "default_trial_type"
_TRIAL_TYPES = ("training", "probe")


def animal_model_choices() -> list[tuple[str, str]]:
    """``(label, token)`` for the animal-model combo. Labels resolve at call time."""
    return [
        (_("Zebrafish (aquarium)"), AnimalModel.ZEBRAFISH.value),
        (_("Rodent (rat or mouse)"), AnimalModel.RODENT.value),
        (_("Other species"), AnimalModel.OTHER.value),
    ]


def protocol_choices() -> list[tuple[str, str]]:
    """``(label, token)`` for the protocol combo. Labels resolve at call time."""
    return [
        (_("Generic (no protocol)"), ProtocolId.GENERIC.value),
        (_("Barnes maze (rodents)"), ProtocolId.BARNES.value),
    ]


def trial_type_choices() -> list[tuple[str, str]]:
    """``(label, token)`` for the Barnes trial-type combo."""
    return [
        (_("Training trial"), _TRIAL_TYPES[0]),
        (_("Probe trial"), _TRIAL_TYPES[1]),
    ]


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
    - Plausible speed ceiling (cm/s), above which the trajectory validator flags
      a frame (#695). 50 cm/s suits adult zebrafish; rodents sprint faster.

    Events emitted:
    - behavioral_config.perspective_changed: Perspective selection changed
    - behavioral_config.geotaxis_toggled: Geotaxis enabled/disabled
    - behavioral_config.values_changed: Any configuration value changed
    """

    @staticmethod
    def _coerce_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(fallback)

    @staticmethod
    def _coerce_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(fallback)

    def __init__(
        self,
        parent,
        event_bus: EventBusV2 | None = None,
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
            default_max_speed_cm_s: Default plausible speed ceiling (cm/s); callers pass
                ``settings.behavioral_analysis.max_plausible_speed_cm_s``
            **kwargs: Additional arguments passed to BaseWidget
        """
        # Store defaults before super().__init__ calls _build_ui
        self._default_thigmotaxis_cm = self._coerce_float(default_thigmotaxis_cm, 1.5)
        self._default_geotaxis_cm = self._coerce_float(default_geotaxis_cm, 1.5)
        self._default_num_zones = self._coerce_int(default_num_zones, 3)
        self._default_bottom_zones = self._coerce_int(default_bottom_zones, 1)
        self._default_perspective = kwargs.pop(
            "default_perspective", AquariumPerspective.LATERAL.value
        )
        self._default_geotaxis_mode = kwargs.pop("default_geotaxis_mode", GeotaxisMode.ZONES.value)
        self._default_max_speed_cm_s = self._coerce_float(
            kwargs.pop("default_max_speed_cm_s", DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S),
            DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S,
        )
        # Experiment profile (ADR-014). The combos are opt-in: the wizard asks the
        # question in its Discovery step and the config editor edits global
        # settings that have no profile, so only the ad-hoc dialogs show them.
        self._show_profile = bool(kwargs.pop("show_profile", False))
        self._show_trial_type = bool(kwargs.pop("show_trial_type", False))
        self._on_profile_changed: Callable[[ExperimentProfile], None] | None = kwargs.pop(
            "on_profile_changed", None
        )
        self.animal_model_var = StringVar(value=AnimalModel.ZEBRAFISH.value)
        self.protocol_var = StringVar(value=ProtocolId.GENERIC.value)
        self.trial_type_var = StringVar(value=_TRIAL_TYPES[0])
        #: ``protocol_params[<protocol>]`` carried through untouched (a template or
        #: project may hold thresholds this widget has no field for).
        self._protocol_params: dict[str, Any] = {}

        # State variables - initialized before _build_ui
        self.perspective_var = StringVar(value=self._default_perspective)
        self.thigmotaxis_distance_var = DoubleVar(value=self._default_thigmotaxis_cm)
        self.geotaxis_enabled_var = BooleanVar(
            value=True if self._default_perspective == AquariumPerspective.LATERAL.value else False
        )
        self.geotaxis_mode_var = StringVar(value=self._default_geotaxis_mode)
        self.geotaxis_distance_var = DoubleVar(value=self._default_geotaxis_cm)
        self.geotaxis_num_zones_var = IntVar(value=self._default_num_zones)
        self.geotaxis_bottom_zones_var = IntVar(value=self._default_bottom_zones)
        self.max_speed_var = DoubleVar(value=self._default_max_speed_cm_s)

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
        self.max_speed_spinbox: ttk.Spinbox | None = None
        self.animal_model_combo: ttk.Combobox | None = None
        self.protocol_combo: ttk.Combobox | None = None
        self.trial_type_combo: ttk.Combobox | None = None
        self._trial_type_row: ttk.Frame | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the behavioral configuration widget UI."""
        # Main container with padding
        self.configure(padding=10)

        # Section title
        title_label = ttk.Label(
            self,
            text=_("Behavioural Analysis Configuration"),
            font=("TkDefaultFont", 10, "bold"),
        )
        title_label.pack(fill="x", pady=(0, 10))

        # Experiment profile (animal model + protocol), only where the caller asks
        if self._show_profile:
            self._build_profile_section()

        # Aquarium Perspective Section
        self._build_perspective_section()

        # Thigmotaxis Section
        self._build_thigmotaxis_section()

        # Geotaxis Section (conditional on lateral perspective)
        self._build_geotaxis_section()

        # Plausible speed ceiling (trajectory validation)
        self._build_speed_ceiling_section()

        # Initial state update
        self._on_perspective_changed()
        self._enforce_profile_locks()

    def _build_profile_section(self) -> None:
        """Build the experiment-profile section: animal model and protocol combos."""
        profile_frame = ttk.LabelFrame(self, text=_("Experiment Profile"), padding=5)
        profile_frame.pack(fill="x", pady=(0, 10))

        animal_row = ttk.Frame(profile_frame)
        animal_row.pack(fill="x", pady=(0, 3))
        ttk.Label(animal_row, text=_("Animal model:"), width=14).pack(side="left", padx=(0, 5))
        self.animal_model_combo = ttk.Combobox(
            animal_row,
            values=[label for label, _token in animal_model_choices()],
            state="readonly",
            width=25,
        )
        self.animal_model_combo.pack(side="left")
        self.animal_model_combo.bind("<<ComboboxSelected>>", self._on_animal_model_selected)

        protocol_row = ttk.Frame(profile_frame)
        protocol_row.pack(fill="x", pady=(0, 3))
        ttk.Label(protocol_row, text=_("Protocol:"), width=14).pack(side="left", padx=(0, 5))
        self.protocol_combo = ttk.Combobox(
            protocol_row,
            values=[label for label, _token in protocol_choices()],
            state="readonly",
            width=25,
        )
        self.protocol_combo.pack(side="left")
        self.protocol_combo.bind("<<ComboboxSelected>>", self._on_protocol_selected)

        if self._show_trial_type:
            self._trial_type_row = ttk.Frame(profile_frame)
            ttk.Label(self._trial_type_row, text=_("Trial type:"), width=14).pack(
                side="left", padx=(0, 5)
            )
            self.trial_type_combo = ttk.Combobox(
                self._trial_type_row,
                values=[label for label, _token in trial_type_choices()],
                state="readonly",
                width=25,
            )
            self.trial_type_combo.pack(side="left")
            self.trial_type_combo.bind("<<ComboboxSelected>>", self._on_trial_type_selected)

        ttk.Label(
            profile_frame,
            text=_(
                "The Barnes maze is run with rodents: choosing it sets the animal model, the "
                "top-down view and the analysis interval for you."
            ),
            wraplength=500,
            foreground="gray",
        ).pack(fill="x", pady=(3, 0))

        self._refresh_profile_combos()

    def _build_perspective_section(self) -> None:
        """Build the aquarium perspective selection section."""
        perspective_frame = ttk.LabelFrame(self, text=_("Aquarium Perspective *"), padding=5)
        perspective_frame.pack(fill="x", pady=(0, 10))

        # Description
        desc_label = ttk.Label(
            perspective_frame,
            text=_("Select how the camera sees the aquarium:"),
            wraplength=500,
        )
        desc_label.pack(fill="x", pady=(0, 5))

        # Combobox for perspective selection
        perspective_values = [
            (_("Top-Down View"), AquariumPerspective.TOP_DOWN.value),
            (_("Side View"), AquariumPerspective.LATERAL.value),
        ]
        display_values = [v[0] for v in perspective_values]
        self._perspective_mapping = {v[0]: v[1] for v in perspective_values}
        self._perspective_reverse = {v[1]: v[0] for v in perspective_values}

        combo_frame = ttk.Frame(perspective_frame)
        combo_frame.pack(fill="x")

        ttk.Label(combo_frame, text=_("Perspective:")).pack(side="left", padx=(0, 5))

        self.perspective_combo = ttk.Combobox(
            combo_frame,
            values=display_values,
            state="readonly",
            width=25,
        )
        self.perspective_combo.pack(side="left")
        # Show the perspective the caller actually asked for. Hardcoding "Side
        # View" here let the combobox disagree with ``perspective_var``: a widget
        # built with ``default_perspective="top_down"`` displayed "Side View"
        # while reporting ``top_down``, so the operator could not tell which one
        # the run would use — and the perspective is what selects the arena weight.
        self.perspective_combo.set(
            self._perspective_reverse.get(self._default_perspective, display_values[1])
        )
        self.perspective_combo.bind("<<ComboboxSelected>>", self._on_perspective_combo_changed)

    def _build_thigmotaxis_section(self) -> None:
        """Build the thigmotaxis configuration section."""
        thigmotaxis_frame = ttk.LabelFrame(
            self, text=_("Thigmotaxis (Proximity to the Walls)"), padding=5
        )
        thigmotaxis_frame.pack(fill="x", pady=(0, 10))

        # Description
        desc_label = ttk.Label(
            thigmotaxis_frame,
            text=_("Distance threshold for considering the fish close to the aquarium walls:"),
            wraplength=500,
        )
        desc_label.pack(fill="x", pady=(0, 5))

        # Spinbox for distance threshold
        input_frame = ttk.Frame(thigmotaxis_frame)
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text=_("Distance (cm):")).pack(side="left", padx=(0, 5))

        self.thigmotaxis_spinbox = ttk.Spinbox(
            input_frame,
            from_=0.1,
            to=THIGMOTAXIS_MAX_DISTANCE_CM,
            increment=0.1,
            textvariable=self.thigmotaxis_distance_var,
            width=8,
            format="%.1f",
        )
        self.thigmotaxis_spinbox.pack(side="left")

        ttk.Label(input_frame, text=_("(default: 1.5 cm)")).pack(side="left", padx=(10, 0))

    def _build_geotaxis_section(self) -> None:
        """Build the geotaxis configuration section."""
        self.geotaxis_frame = ttk.LabelFrame(
            self, text=_("Geotaxis (Proximity to the Bottom) - Side View Only"), padding=5
        )
        self.geotaxis_frame.pack(fill="x", pady=(0, 10))

        # Enable checkbox
        self.geotaxis_check = ttk.Checkbutton(
            self.geotaxis_frame,
            text=_("Enable geotaxis analysis"),
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

        ttk.Label(mode_frame, text=_("Calculation mode:")).pack(side="left", padx=(0, 10))

        self.distance_radio = ttk.Radiobutton(
            mode_frame,
            text=_("By Distance"),
            variable=self.geotaxis_mode_var,
            value=GeotaxisMode.DISTANCE.value,
            command=self._on_mode_changed,
        )
        self.distance_radio.pack(side="left", padx=(0, 10))

        self.zones_radio = ttk.Radiobutton(
            mode_frame,
            text=_("By Vertical Zones"),
            variable=self.geotaxis_mode_var,
            value=GeotaxisMode.ZONES.value,
            command=self._on_mode_changed,
        )
        self.zones_radio.pack(side="left")

        # Distance mode options
        self.distance_frame = ttk.Frame(self.geotaxis_options_frame)
        self.distance_frame.pack(fill="x", pady=(5, 0))

        ttk.Label(self.distance_frame, text=_("Distance from the bottom (cm):")).pack(
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

        # Zones mode options
        self.zones_frame = ttk.Frame(self.geotaxis_options_frame)
        self.zones_frame.pack(fill="x", pady=(5, 0))

        # Number of zones
        zones_row1 = ttk.Frame(self.zones_frame)
        zones_row1.pack(fill="x", pady=(0, 5))

        ttk.Label(zones_row1, text=_("Split the aquarium into:")).pack(side="left", padx=(0, 5))

        self.num_zones_spinbox = ttk.Spinbox(
            zones_row1,
            from_=2,
            to=10,
            increment=1,
            textvariable=self.geotaxis_num_zones_var,
            width=5,
        )
        self.num_zones_spinbox.pack(side="left")

        ttk.Label(zones_row1, text=_("vertical zones")).pack(side="left", padx=(5, 0))

        # Bottom zones to consider
        zones_row2 = ttk.Frame(self.zones_frame)
        zones_row2.pack(fill="x")

        ttk.Label(zones_row2, text=_("Consider as 'bottom':")).pack(side="left", padx=(0, 5))

        self.bottom_zones_spinbox = ttk.Spinbox(
            zones_row2,
            from_=1,
            to=2,
            increment=1,
            textvariable=self.geotaxis_bottom_zones_var,
            width=5,
        )
        self.bottom_zones_spinbox.pack(side="left")

        ttk.Label(zones_row2, text=_("lowest zone(s)")).pack(side="left", padx=(5, 0))

        # Initial visibility
        self._update_geotaxis_visibility()

    def _build_speed_ceiling_section(self) -> None:
        """Build the plausible speed ceiling section (#695)."""
        speed_frame = ttk.LabelFrame(self, text=_("Plausible Speed"), padding=5)
        speed_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(
            speed_frame,
            text=_(
                "Frames faster than this are flagged as implausible. 50 cm/s suits adult "
                "zebrafish; rodents sprint faster."
            ),
            wraplength=500,
        ).pack(fill="x", pady=(0, 5))

        input_frame = ttk.Frame(speed_frame)
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text=_("Maximum speed (cm/s):")).pack(side="left", padx=(0, 5))

        self.max_speed_spinbox = ttk.Spinbox(
            input_frame,
            from_=1.0,
            to=MAX_PLAUSIBLE_SPEED_LIMIT_CM_S,
            increment=5.0,
            textvariable=self.max_speed_var,
            width=8,
            format="%.1f",
        )
        self.max_speed_spinbox.pack(side="left")

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

    # Experiment profile

    @staticmethod
    def _label_of(choices: list[tuple[str, str]], token: str) -> str:
        return next((label for label, value in choices if value == token), token)

    @staticmethod
    def _token_of(choices: list[tuple[str, str]], label: str, fallback: str) -> str:
        return next((value for text, value in choices if text == label), fallback)

    def current_profile(self) -> ExperimentProfile:
        """The profile the combos currently describe, through the single resolver."""
        return resolve_experiment_profile(
            behavioral_config={
                ANIMAL_MODEL_KEY: self.animal_model_var.get(),
                PROTOCOL_KEY: self.protocol_var.get(),
            }
        )

    def _on_animal_model_selected(self, event=None) -> None:
        """The user picked another animal model: its behavioural defaults apply."""
        if not self.animal_model_combo:
            return
        token = self._token_of(
            animal_model_choices(), self.animal_model_combo.get(), AnimalModel.ZEBRAFISH.value
        )
        self._apply_profile(token, self.protocol_var.get())

    def _on_protocol_selected(self, event=None) -> None:
        """The user picked another protocol: its parameters start over."""
        if not self.protocol_combo:
            return
        token = self._token_of(
            protocol_choices(), self.protocol_combo.get(), ProtocolId.GENERIC.value
        )
        if token != self.protocol_var.get():
            self._protocol_params = {}
        self._apply_profile(self.animal_model_var.get(), token)

    def _on_trial_type_selected(self, event=None) -> None:
        if not self.trial_type_combo:
            return
        self.trial_type_var.set(
            self._token_of(trial_type_choices(), self.trial_type_combo.get(), _TRIAL_TYPES[0])
        )

    def _apply_profile(self, animal_token: str, protocol_token: str) -> None:
        """Make ``(animal model, protocol)`` the widget's profile and propagate it.

        The protocol may force the animal model (Barnes => rodent) and, through
        :meth:`_enforce_profile_locks`, the perspective. When the animal model
        ends up different from what it was, the speed ceiling and the wall band
        are reset to that animal's defaults. Only a user action calls this:
        :meth:`set_values` restores a saved profile without touching the fields.
        """
        before = self.animal_model_var.get()
        profile = resolve_experiment_profile(
            behavioral_config={ANIMAL_MODEL_KEY: animal_token, PROTOCOL_KEY: protocol_token}
        )
        self.animal_model_var.set(profile.animal_model.value)
        self.protocol_var.set(profile.protocol.value)
        if profile.animal_model.value != before:
            self._reset_animal_defaults(profile.animal_model)
        self._refresh_profile_combos()
        self._enforce_profile_locks()
        if self._on_profile_changed is not None:
            self._on_profile_changed(profile)

    def _reset_animal_defaults(self, animal_model: AnimalModel) -> None:
        """Put the animal's speed ceiling and wall band in their fields."""
        defaults = animal_behavior_defaults(animal_model)
        if defaults is None:
            self.max_speed_var.set(self._default_max_speed_cm_s)
            self.thigmotaxis_distance_var.set(self._default_thigmotaxis_cm)
        else:
            self.max_speed_var.set(defaults.max_plausible_speed_cm_s)
            self.thigmotaxis_distance_var.set(defaults.thigmotaxis_distance_cm)

    def _refresh_profile_combos(self) -> None:
        """Show the combos' labels for the current tokens (no-op when hidden)."""
        if self.animal_model_combo:
            self.animal_model_combo.set(
                self._label_of(animal_model_choices(), self.animal_model_var.get())
            )
        if self.protocol_combo:
            self.protocol_combo.set(self._label_of(protocol_choices(), self.protocol_var.get()))
        if self.trial_type_combo:
            self.trial_type_combo.set(
                self._label_of(trial_type_choices(), self.trial_type_var.get())
            )
        if self._trial_type_row is not None:
            if self.protocol_var.get() == ProtocolId.BARNES.value:
                self._trial_type_row.pack(fill="x", pady=(0, 3))
            else:
                self._trial_type_row.pack_forget()

    def _enforce_profile_locks(self) -> None:
        """Lock what the protocol decides: the animal model and the perspective.

        Runs whether or not the combos are shown, so a wizard that asked the
        question in Discovery still gets a top-down view for a Barnes project.
        """
        protocol = ProtocolId(self.protocol_var.get())
        forced = forced_animal_model(protocol)
        if forced is not None:
            self.animal_model_var.set(forced.value)
        if self.animal_model_combo:
            self.animal_model_combo.configure(
                state="disabled" if forced is not None else "readonly"
            )
        if forced is not None:
            self.perspective_var.set(AquariumPerspective.TOP_DOWN.value)
            if self.perspective_combo:
                self.perspective_combo.set(
                    self._perspective_reverse.get(AquariumPerspective.TOP_DOWN.value, "")
                )
        if self.perspective_combo:
            self.perspective_combo.configure(state="disabled" if forced is not None else "readonly")
        self._on_perspective_changed()

    def set_protocol_param(self, name: str, value: Any) -> None:
        """Set one parameter of the effective protocol (``protocol_params[<protocol>]``)."""
        self._protocol_params[name] = value

    def get_protocol_params(self) -> dict[str, Any]:
        """A copy of the effective protocol's parameters (``{}`` for generic)."""
        if self.protocol_var.get() == ProtocolId.GENERIC.value:
            return {}
        return dict(self._protocol_params)

    def _on_geotaxis_toggled(self, event=None) -> None:
        """Handle geotaxis enable/disable toggle."""
        self._update_geotaxis_visibility()

    def _on_mode_changed(self, event=None) -> None:
        """Handle geotaxis mode change (distance vs zones)."""
        self._update_geotaxis_visibility()

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
            "max_plausible_speed_cm_s": self.max_speed_var.get(),
            **self._profile_values(),
        }

    def _profile_values(self) -> dict[str, Any]:
        """The experiment-profile keys of :meth:`get_values` (writers build the dict)."""
        values: dict[str, Any] = {
            ANIMAL_MODEL_KEY: self.animal_model_var.get(),
            PROTOCOL_KEY: self.protocol_var.get(),
        }
        protocol = self.protocol_var.get()
        params = self.get_protocol_params()
        if protocol == ProtocolId.BARNES.value and self._show_trial_type:
            params[DEFAULT_TRIAL_TYPE_KEY] = self.trial_type_var.get()
        if params:
            values[PROTOCOL_PARAMS_KEY] = {protocol: params}
        return values

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
                - max_plausible_speed_cm_s: float
                - animal_model / protocol / protocol_params: the experiment profile
                  (ADR-014), restored through ``resolve_experiment_profile``
        """
        self._restore_profile(config)
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

        if config.get("max_plausible_speed_cm_s") is not None:
            self.max_speed_var.set(config["max_plausible_speed_cm_s"])

        # Update UI state (and re-impose what the protocol decides over the above)
        self._on_perspective_changed()
        self._enforce_profile_locks()

    def _restore_profile(self, config: dict) -> None:
        """Take the profile out of ``config`` when it declares one.

        A configuration that mentions none of the profile keys (a legacy project,
        a partial update) leaves the combos alone. Unlike a user pick, restoring
        never resets the speed ceiling or the wall band: the saved values win.
        """
        if not any(key in config for key in (ANIMAL_MODEL_KEY, PROTOCOL_KEY, PROTOCOL_PARAMS_KEY)):
            return
        profile = resolve_experiment_profile(behavioral_config=config)
        self.animal_model_var.set(profile.animal_model.value)
        self.protocol_var.set(profile.protocol.value)
        self._protocol_params = dict(profile.protocol_params)
        trial_type = self._protocol_params.get(DEFAULT_TRIAL_TYPE_KEY)
        if trial_type in _TRIAL_TYPES:
            self.trial_type_var.set(trial_type)
        self._refresh_profile_combos()
        if self._on_profile_changed is not None:
            self._on_profile_changed(profile)

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
                "max_plausible_speed_cm_s": self._default_max_speed_cm_s,
                ANIMAL_MODEL_KEY: AnimalModel.ZEBRAFISH.value,
                PROTOCOL_KEY: ProtocolId.GENERIC.value,
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
        if thigmotaxis < 0.1 or thigmotaxis > THIGMOTAXIS_MAX_DISTANCE_CM:
            errors.append(
                _("Thigmotaxis distance must be between {minimum} and {maximum} cm").format(
                    minimum=0.1, maximum=THIGMOTAXIS_MAX_DISTANCE_CM
                )
            )

        max_speed = self.max_speed_var.get()
        if max_speed <= 0 or max_speed > MAX_PLAUSIBLE_SPEED_LIMIT_CM_S:
            errors.append(
                _(
                    "The maximum plausible speed must be greater than 0 and at most {maximum} cm/s"
                ).format(maximum=MAX_PLAUSIBLE_SPEED_LIMIT_CM_S)
            )

        # Validate geotaxis if enabled
        if self.geotaxis_enabled_var.get():
            perspective = self.perspective_var.get()
            if perspective != AquariumPerspective.LATERAL.value:
                errors.append(_("Geotaxis can only be enabled for the side perspective"))

            mode = self.geotaxis_mode_var.get()
            if mode == GeotaxisMode.DISTANCE.value:
                geotaxis_dist = self.geotaxis_distance_var.get()
                if geotaxis_dist < 0.1 or geotaxis_dist > 10.0:
                    errors.append(_("Geotaxis distance must be between 0.1 and 10.0 cm"))
            else:
                num_zones = self.geotaxis_num_zones_var.get()
                bottom_zones = self.geotaxis_bottom_zones_var.get()

                if num_zones < 2 or num_zones > 10:
                    errors.append(_("The number of zones must be between 2 and 10"))

                if bottom_zones < 1 or bottom_zones > 2:
                    errors.append(_("The number of bottom zones must be 1 or 2"))

                if bottom_zones > num_zones:
                    errors.append(_("Bottom zones cannot exceed the total number of zones"))

        return (len(errors) == 0, errors)
