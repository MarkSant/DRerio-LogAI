"""Interface vocabulary that follows the project's animal model (Barnes v8.1, stage 3).

DRerio LogAI began as a zebrafish tracker, so its labels say "aquarium" and "fish".
That is wrong on a rat's Barnes table. This module is the ONE place that decides
which noun a screen shows, from the animal model of the experiment profile
(:func:`zebtrack.core.services.experiment_profile.resolve_experiment_profile`).

Rules (see ``docs/tasks/v8.1/barnes/TERMINOLOGY.md``):

* **Display only.** ``num_aquariums``, ``animals_per_aquarium``,
  ``aquarium_width_cm``, ``aquarium_id``, the ``aquarium_N/`` folders and every other
  persisted key stay as they are (ADR-012); only the text a person reads changes.
* **A zebrafish or legacy project shows exactly today's text.** The ``zebrafish``
  variant of every key is the original msgid, byte for byte, so the existing
  translations keep applying.
* **One complete msgid per animal variant.** Portuguese inflects ("o aquário" /
  "a arena", "peixe" / "rato"): a noun interpolated into a translated sentence cannot be
  made to agree. Every variant below is a whole sentence a translator can read.
* **Resolved at CALL time.** Each entry is a thunk; ``_()`` runs inside
  :func:`term`, never at import (``tests/i18n/test_no_import_time_translation.py``).
* **Never branch on displayed text.** Callers pass the animal model (a token), never
  compare what :func:`term` returned.

``other`` (any species that is neither zebrafish nor rodent) reads like ``rodent``
unless an entry gives it a variant of its own (only the emoji differ today).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any

from zebtrack.core.services.experiment_profile import AnimalModel, resolve_experiment_profile
from zebtrack.i18n import _

__all__ = [
    "AnimalLike",
    "animal_model_of",
    "animal_model_of_gui",
    "animal_model_of_project_manager",
    "term",
    "term_keys",
    "variants",
]

#: What a caller may hold: the enum, its persisted token, or nothing (legacy project).
AnimalLike = AnimalModel | str | None


@dataclass(frozen=True, slots=True)
class _Entry:
    """The text of one key per animal model.

    ``zebrafish`` is the legacy wording (today's msgid); ``rodent`` is the neutral
    "arena"/"animal" wording; ``other`` defaults to ``rodent``.
    """

    zebrafish: str
    rodent: str
    other: str | None = None

    def for_model(self, model: AnimalModel) -> str:
        if model is AnimalModel.ZEBRAFISH:
            return self.zebrafish
        if model is AnimalModel.OTHER and self.other is not None:
            return self.other
        return self.rodent


def _coerce(animal_model: AnimalLike) -> AnimalModel:
    """The :class:`AnimalModel` behind ``animal_model``; missing or zebrafish stay legacy.

    A string goes through the single resolver, so an unknown token degrades to
    ``other`` exactly as it does everywhere else; ``None`` (no profile) is the
    legacy zebrafish project.
    """
    if animal_model is None:
        return AnimalModel.ZEBRAFISH
    if isinstance(animal_model, AnimalModel):
        return animal_model
    return resolve_experiment_profile(behavioral_config={"animal_model": animal_model}).animal_model


def animal_model_of(
    project_data: Mapping[str, Any] | None = None,
    behavioral_config: Mapping[str, Any] | None = None,
) -> AnimalModel:
    """The animal model of a project / run, through the single profile resolver."""
    return resolve_experiment_profile(project_data, behavioral_config).animal_model


def animal_model_of_project_manager(project_manager: Any) -> AnimalModel:
    """The animal model of ``project_manager``'s open project (legacy when none).

    For the coordinators, which hold the project manager directly. Anything that
    is not a mapping (no manager, no project, a test double) reads as no project.
    """
    return animal_model_of(getattr(project_manager, "project_data", None))


def animal_model_of_gui(gui: Any) -> AnimalModel:
    """The animal model of the project the main window has open (legacy when none).

    ``gui.controller.project_manager.project_data`` is where every other UI reader
    of the profile looks; anything that is not a mapping reads as no project.
    """
    controller = getattr(gui, "controller", None)
    return animal_model_of_project_manager(getattr(controller, "project_manager", None))


# ---------------------------------------------------------------------------
# The vocabulary. Thunks, not strings: ``_()`` must run when asked, not on import.
# Naming: ``<surface>.<what>``. Keep a key's variants side by side.
# ---------------------------------------------------------------------------
@cache
def _entries() -> dict[str, Callable[[], _Entry]]:
    """The key -> thunk table. Built inside a function so ``_()`` never sits in module scope."""
    return {
        # -- Wizard: Calibration step ------------------------------------------------
        "calibration.count_label": lambda: _Entry(
            _("Number of aquariums (videos):"),
            _("Number of arenas (videos):"),
        ),
        "calibration.count_help": lambda: _Entry(
            _(
                "🎬 Number of Aquariums (Videos)\n\n"
                "How many independent videos will be analyzed in this project.\n\n"
                "• Each aquarium = 1 separate video\n"
                "• LIVE project: typically 1 (a single recording)\n"
                "• PRE-RECORDED project: may be several videos\n\n"
                "Examples:\n"
                "  • 1 aquarium: a single experiment/recording\n"
                "  • 6 aquariums: 6 different recordings (e.g. 3 groups x 2 days)\n"
                "  • 24 aquariums: a full battery of experiments\n\n"
                "💡 Tip: if you are unsure, start with 1 and add more videos later."
            ),
            _(
                "🎬 Number of Arenas (Videos)\n\n"
                "How many independent videos will be analyzed in this project.\n\n"
                "• Each arena = 1 separate video\n"
                "• LIVE project: typically 1 (a single recording)\n"
                "• PRE-RECORDED project: may be several videos\n\n"
                "Examples:\n"
                "  • 1 arena: a single experiment/recording\n"
                "  • 6 arenas: 6 different recordings (e.g. 3 groups x 2 days)\n"
                "  • 24 arenas: a full battery of experiments\n\n"
                "💡 Tip: if you are unsure, start with 1 and add more videos later."
            ),
        ),
        "calibration.animals_label": lambda: _Entry(
            _("Animals per aquarium:"),
            _("Animals per arena:"),
        ),
        "calibration.animals_help": lambda: _Entry(
            _(
                "🐾 Animals per Aquarium\n\n"
                "How many animals will be present in EACH video/aquarium.\n\n"
                "Impact on the analysis:\n"
                "  • 1 animal: simplified individual tracking\n"
                "    → Ideal for: individual behavioural studies\n"
                "    → Recommended method: detection (det)\n\n"
                "  • 2-5 animals: moderate multi-animal tracking\n"
                "    → Ideal for: social interaction, small-group behaviour\n"
                "    → Recommended method: segmentation (seg)\n\n"
                "  • 6+ animals: group tracking (e.g. a zebrafish shoal)\n"
                "    → Ideal for: group dynamics, collective behaviour\n"
                "    → Recommended method: segmentation (seg) with high confidence\n\n"
                "⚠️ IMPORTANT: this value must be the SAME for every video in the project.\n"
                "If you have videos with different animal counts, "
                "create separate projects.\n\n"
                "💡 Tip: for several animals, prefer segmentation (seg) in the "
                "model selection step."
            ),
            _(
                "🐾 Animals per Arena\n\n"
                "How many animals will be present in EACH video/arena.\n\n"
                "Impact on the analysis:\n"
                "  • 1 animal: simplified individual tracking\n"
                "    → Ideal for: individual behavioural studies\n"
                "    → Recommended method: detection (det)\n\n"
                "  • 2-5 animals: moderate multi-animal tracking\n"
                "    → Ideal for: social interaction, small-group behaviour\n"
                "    → Recommended method: segmentation (seg)\n\n"
                "  • 6+ animals: group tracking (e.g. a large social group)\n"
                "    → Ideal for: group dynamics, collective behaviour\n"
                "    → Recommended method: segmentation (seg) with high confidence\n\n"
                "⚠️ IMPORTANT: this value must be the SAME for every video in the project.\n"
                "If you have videos with different animal counts, "
                "create separate projects.\n\n"
                "💡 Tip: for several animals, prefer segmentation (seg) in the "
                "model selection step."
            ),
        ),
        # -- Wizard: Discovery glossary and the confirmation / detection summaries ----
        "discovery.glossary": lambda: _Entry(
            _(
                "• Parquet: an efficient file format for storing data\n\n"
                "• Arena: the area of the tank where the animals move "
                "(a bounding polygon)\n\n"
                "• ROI (Region of Interest): specific regions such as 'Centre', "
                "'Edge', 'Escape Zone'\n\n"
                "• Trajectory: frame-by-frame coordinates of the animals' "
                "movement\n\n"
                "Importing this data from previous analyses avoids "
                "reprocessing."
            ),
            _(
                "• Parquet: an efficient file format for storing data\n\n"
                "• Arena: the area where the animals move, such as a table or a box "
                "(a bounding polygon)\n\n"
                "• ROI (Region of Interest): specific regions such as 'Centre', "
                "'Edge', 'Escape Zone'\n\n"
                "• Trajectory: frame-by-frame coordinates of the animals' "
                "movement\n\n"
                "Importing this data from previous analyses avoids "
                "reprocessing."
            ),
        ),
        "wizard.count_summary": lambda: _Entry(
            _("  • Aquariums: {count}"),
            _("  • Arenas: {count}"),
        ),
        "wizard.animals_summary": lambda: _Entry(
            _("  • Animals per aquarium: {count}"),
            _("  • Animals per arena: {count}"),
        ),
        "wizard.arena_method_summary": lambda: _Entry(
            _("  • Aquarium method: {method}"),
            _("  • Arena method: {method}"),
        ),
        "wizard.arena_weight_summary": lambda: _Entry(
            _("  • Aquarium weight: {weight}"),
            _("  • Arena weight: {weight}"),
        ),
        # -- Behavioural configuration widget ----------------------------------------
        "behavioral.perspective_title": lambda: _Entry(
            _("Aquarium Perspective *"),
            _("Arena Perspective *"),
        ),
        "behavioral.perspective_help": lambda: _Entry(
            _("Select how the camera sees the aquarium:"),
            _("Select how the camera sees the arena:"),
        ),
        "behavioral.thigmotaxis_help": lambda: _Entry(
            _("Distance threshold for considering the fish close to the aquarium walls:"),
            _("Distance threshold for considering the animal close to the arena walls:"),
        ),
        "behavioral.zones_split": lambda: _Entry(
            _("Split the aquarium into:"),
            _("Split the arena into:"),
        ),
        # -- Zones tab ---------------------------------------------------------------
        "zones.detect_button": lambda: _Entry(
            _("Detect Aquarium (Auto)"),
            _("Detect Arena (Auto)"),
        ),
        "zones.active_frame": lambda: _Entry(
            _("🐟 Active Aquarium"),
            _("🐀 Active Arena"),
            _("🐾 Active Arena"),
        ),
        "zones.radio_left": lambda: _Entry(
            _("Aquarium 1 (Left)"),
            _("Arena 1 (Left)"),
        ),
        "zones.radio_right": lambda: _Entry(
            _("Aquarium 2 (Right)"),
            _("Arena 2 (Right)"),
        ),
        "zones.sequential_radio": lambda: _Entry(
            _("Sequential (2 passes, 1 aquarium at a time)"),
            _("Sequential (2 passes, 1 arena at a time)"),
        ),
        "zones.sequential_help": lambda: _Entry(
            _("Sequential: processes the whole video for each aquarium separately"),
            _("Sequential: processes the whole video for each arena separately"),
        ),
        # Messages that quote the Detect button: each variant quotes ITS button's label
        # (a unit test keeps the two in step; retyping a label is how help text rots).
        "zones.no_frame": lambda: _Entry(
            _("Could not load a frame. Please load a video or use 'Detect Aquarium (Auto)' first."),
            _("Could not load a frame. Please load a video or use 'Detect Arena (Auto)' first."),
        ),
        "zones.no_arena_live_prompt": lambda: _Entry(
            _(
                "No main arena has been defined for this live project.\n\n"
                "Do you want to set the calibration up automatically now?\n\n"
                "• The Zone Configuration tab will open\n"
                "• You can use 'Detect Aquarium (Auto)' or draw manually\n"
                "• The configuration is saved automatically"
            ),
            _(
                "No main arena has been defined for this live project.\n\n"
                "Do you want to set the calibration up automatically now?\n\n"
                "• The Zone Configuration tab will open\n"
                "• You can use 'Detect Arena (Auto)' or draw manually\n"
                "• The configuration is saved automatically"
            ),
        ),
        "zones.no_arena_live_steps": lambda: _Entry(
            _(
                "Set the main arena up using:\n\n"
                "1. 'Detect Aquarium (Auto)' - for automatic detection\n"
                "2. 'Draw Main Polygon' - for manual drawing\n\n"
                "The configuration is saved automatically."
            ),
            _(
                "Set the main arena up using:\n\n"
                "1. 'Detect Arena (Auto)' - for automatic detection\n"
                "2. 'Draw Main Polygon' - for manual drawing\n\n"
                "The configuration is saved automatically."
            ),
        ),
        # -- Coordinators: arena detection / definition prompts -----------------------
        "coordinator.arena_missing_batch": lambda: _Entry(
            _(
                "The main aquarium polygon has not been defined.\n\n"
                "The main arena is required for an accurate analysis.\n"
                "Do you want to define it now, before processing?"
            ),
            _(
                "The main arena polygon has not been defined.\n\n"
                "The main arena is required for an accurate analysis.\n"
                "Do you want to define it now, before processing?"
            ),
        ),
        "coordinator.define_arena_steps_videos": lambda: _Entry(
            _(
                "Please:\n"
                "1. Use 'Detect Aquarium (Auto)' or\n"
                "2. Draw the main polygon manually\n"
                "3. Then come back to add videos"
            ),
            _(
                "Please:\n"
                "1. Use 'Detect Arena (Auto)' or\n"
                "2. Draw the main polygon manually\n"
                "3. Then come back to add videos"
            ),
        ),
        "calibration.arena_missing_live": lambda: _Entry(
            _(
                "The main aquarium polygon has not been defined.\n\n"
                "Defining the arena before starting the recording is recommended.\n"
                "Do you want to define it now?"
            ),
            _(
                "The main arena polygon has not been defined.\n\n"
                "Defining the arena before starting the recording is recommended.\n"
                "Do you want to define it now?"
            ),
        ),
        "calibration.define_arena_steps_live": lambda: _Entry(
            _(
                "Please:\n"
                "1. Use the live camera to calibrate\n"
                "2. Use 'Detect Aquarium (Auto)' or\n"
                "3. Draw the main polygon manually\n"
                "4. Then come back to start the recording"
            ),
            _(
                "Please:\n"
                "1. Use the live camera to calibrate\n"
                "2. Use 'Detect Arena (Auto)' or\n"
                "3. Draw the main polygon manually\n"
                "4. Then come back to start the recording"
            ),
        ),
        "calibration.detecting_status": lambda: _Entry(
            _("Detecting the aquarium..."),
            _("Detecting the arena..."),
        ),
        "calibration.detected_title": lambda: _Entry(
            _("Aquarium Detected"),
            _("Arena Detected"),
        ),
        "calibration.detected_message": lambda: _Entry(
            _(
                "Aquarium detected successfully!\n\n"
                "You can adjust the vertices or add ROIs.\n"
                "Click 'Finish' when you are ready."
            ),
            _(
                "Arena detected successfully!\n\n"
                "You can adjust the vertices or add ROIs.\n"
                "Click 'Finish' when you are ready."
            ),
        ),
        "calibration.detect_failed_zones": lambda: _Entry(
            _(
                "Could not detect the aquarium automatically.\n\n"
                "You will be taken to the zones tab to draw it manually."
            ),
            _(
                "Could not detect the arena automatically.\n\n"
                "You will be taken to the zones tab to draw it manually."
            ),
        ),
        "calibration.detect_failed_manual": lambda: _Entry(
            _(
                "Could not detect the aquarium automatically.\n\n"
                "The captured image was loaded for manual drawing.\n"
                "Please use the 'Main Polygon' tool to define the arena."
            ),
            _(
                "Could not detect the arena automatically.\n\n"
                "The captured image was loaded for manual drawing.\n"
                "Please use the 'Main Polygon' tool to define the arena."
            ),
        ),
        "calibration.draw_title": lambda: _Entry(
            _("Draw the Aquarium"),
            _("Draw the Arena"),
        ),
        "calibration.draw_message": lambda: _Entry(
            _(
                "Draw the aquarium polygon and ROIs (if needed).\n\n"
                "Click 'Finish' when you are ready."
            ),
            _("Draw the arena polygon and ROIs (if needed).\n\nClick 'Finish' when you are ready."),
        ),
        # -- Ad-hoc dialogs (live analysis, single video) ----------------------------
        "live.count_label": lambda: _Entry(
            _("No. of aquariums:"),
            _("No. of arenas:"),
        ),
        "live.count_help": lambda: _Entry(
            _(
                "Live analysis handles ONE aquarium at a time.\n"
                "For multiple aquariums, create a live project."
            ),
            _(
                "Live analysis handles ONE arena at a time.\n"
                "For multiple arenas, create a live project."
            ),
        ),
        "live.animals_label": lambda: _Entry(
            _("Animals/aquarium:"),
            _("Animals/arena:"),
        ),
        "live.animals_help": lambda: _Entry(
            _("Number of animals inside each aquarium."),
            _("Number of animals inside each arena."),
        ),
        "live.one_arena_notice": lambda: _Entry(
            _(
                "ℹ️ Live analysis covers ONE aquarium at a time. "
                "To record several aquariums at once, create a live project."
            ),
            _(
                "ℹ️ Live analysis covers ONE arena at a time. "
                "To record several arenas at once, create a live project."
            ),
        ),
        "live.count_error": lambda: _Entry(
            _("The number of aquariums and animals must be >= 1"),
            _("The number of arenas and animals must be >= 1"),
        ),
        "single.count_label": lambda: _Entry(
            _("Number of Aquariums:"),
            _("Number of Arenas:"),
        ),
        "single.count_help": lambda: _Entry(
            _(
                "Number of Aquariums\n\n"
                "Sets whether the video contains 1 or 2 independent arenas (e.g. tanks).\n"
                "• 1: standard analysis.\n"
                "• 2: lets you draw two arenas and process them together."
            ),
            _(
                "Number of Arenas\n\n"
                "Sets whether the video contains 1 or 2 independent arenas.\n"
                "• 1: standard analysis.\n"
                "• 2: lets you draw two arenas and process them together."
            ),
        ),
        "single.animals_label": lambda: _Entry(
            _("Animals per Aquarium:"),
            _("Animals per Arena:"),
        ),
        "single.animals_help": lambda: _Entry(
            _(
                "Animals per Aquarium\n\n"
                "How many animals are in each arena.\n"
                "• 1: enables the tracker optimized for a single subject.\n"
                "• >1: requires Segmentation (seg) mode to avoid ID swaps."
            ),
            _(
                "Animals per Arena\n\n"
                "How many animals are in each arena.\n"
                "• 1: enables the tracker optimized for a single subject.\n"
                "• >1: requires Segmentation (seg) mode to avoid ID swaps."
            ),
        ),
        # -- Aquarium assignment dialog (two arenas in one video) --------------------
        "assignment.title": lambda: _Entry(
            _("Aquarium Configuration"),
            _("Arena Configuration"),
        ),
        "assignment.header": lambda: _Entry(
            _("Assign groups and identifiers to each aquarium"),
            _("Assign groups and identifiers to each arena"),
        ),
        "assignment.excess_matches": lambda: _Entry(
            _(
                "Found {count} matches in the file name,\n"
                "but only 2 aquariums are supported.\n\n"
                "Using the first 2 matches."
            ),
            _(
                "Found {count} matches in the file name,\n"
                "but only 2 arenas are supported.\n\n"
                "Using the first 2 matches."
            ),
        ),
        "assignment.panel_title": lambda: _Entry(
            _("Aquarium {number} ({position})"),
            _("Arena {number} ({position})"),
        ),
        "assignment.group_empty": lambda: _Entry(
            _("The group of Aquarium {number} cannot be empty"),
            _("The group of Arena {number} cannot be empty"),
        ),
        "assignment.subject_empty": lambda: _Entry(
            _("The subject of Aquarium {number} cannot be empty"),
            _("The subject of Arena {number} cannot be empty"),
        ),
        # -- Subject nodes of the project trees --------------------------------------
        "subject.label": lambda: _Entry(
            _("🐟 Subject {label}"),
            _("🐀 Subject {label}"),
            _("🐾 Subject {label}"),
        ),
        "subject.video_node": lambda: _Entry(
            _("🐟 {label}"),
            _("🐀 {label}"),
            _("🐾 {label}"),
        ),
        "subject.list_title": lambda: _Entry(
            _("🐟 Subjects"),
            _("🐀 Subjects"),
            _("🐾 Subjects"),
        ),
    }


def term_keys() -> tuple[str, ...]:
    """Every key :func:`term` knows, in definition order."""
    return tuple(_entries())


def variants(key: str) -> dict[AnimalModel, str]:
    """The text of ``key`` for every animal model (for tests and the inventory doc)."""
    entry = _entries()[key]()
    return {model: entry.for_model(model) for model in AnimalModel}


def term(key: str, animal_model: AnimalLike = None, /, **fmt: Any) -> str:
    """The text of ``key`` for ``animal_model``, translated at this very call.

    Args:
        key: One of :func:`term_keys`.
        animal_model: The project's animal model (enum or persisted token). ``None``
            or ``zebrafish`` returns today's exact (legacy) text.
        **fmt: ``str.format`` arguments; applied only when given, so a msgid that
            carries ``{braces}`` of its own is returned untouched without them.

    Raises:
        KeyError: ``key`` is not in the vocabulary (a typo must not read as legacy).
    """
    text = _entries()[key]().for_model(_coerce(animal_model))
    return text.format(**fmt) if fmt else text
