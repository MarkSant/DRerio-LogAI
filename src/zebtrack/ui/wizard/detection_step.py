"""Wizard detection step (design auto-detection and confirmation)."""

import os
import re
from pathlib import Path
from tkinter import (
    Button,
    Frame,
    Label,
    LabelFrame,
    StringVar,
    Text,
    messagebox,
)
from tkinter import (
    font as tkfont,
)

import structlog

from zebtrack.core.project_manager import ProjectManager
from zebtrack.ui.window_utils import create_scrollbar
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.custom_regex_dialog import CustomRegexDialog
from zebtrack.ui.wizard.design_editor_dialog import DesignEditorDialog
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner

log = structlog.get_logger()


_METHOD_LABELS = {
    "seg": "Segmentação (seg)",
    "det": "Detecção (det)",
}


class DetectionStep(WizardStep):
    """
    Detection & Validation step - auto-detect design and scan parquets.

    Processing:
        1. Scan video paths using ProjectManager.scan_input_paths()
        2. Auto-detect experimental design from folder structure
        3. Calculate confidence score
        4. Show parquet summary (if any exist)

    Output:
        {
            "scanned_videos": list[dict],  # Results from scan_input_paths()
            "detected_design": {
                "groups": list[str],
                "days": list[str] | None,  # Only for experimental
                "subjects_per_group": dict[str, list[str]],
                "confidence": float,  # 0.0 to 1.0
                "pattern_used": str,  # e.g., "groups_as_folders"
            } | None,  # None if detection failed or exploratory project
            "video_count": int,
            "parquet_summary": {
                "total_arena": int,
                "total_rois": int,
                "total_trajectory": int,
                "total_complete": int,  # Videos with all 3 parquets
            }
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize detection step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.DETECTION_VALIDATION

        # State
        self.scanned_videos = []
        self.detected_design = None
        self.status_var = StringVar(value="Aguardando análise...")
        self.custom_regex_patterns = None  # User-defined regex patterns
        self.design_editor_confirmed = False
        self.template_info_var = StringVar(value="")
        self.template_info_label = None

    def build_ui(self):
        """Build detection step UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text="Detecção Automática de Design", font=title_font)
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text="Analisando estrutura de pastas e arquivos parquet...",
            fg="gray",
            wraplength=500,
        )
        subtitle.pack(pady=(0, 20))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=500,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # Status message
        status_frame = Frame(self)
        status_frame.pack(fill="x", pady=(0, 15))

        Label(status_frame, text="Status: ").pack(side="left")
        Label(status_frame, textvariable=self.status_var, fg="blue").pack(side="left")

        # Detection results
        results_frame = LabelFrame(self, text="Resultados da Detecção", padx=10, pady=10)
        results_frame.pack(fill="both", expand=True, pady=(0, 15))

        # Scrollable text widget for results
        scrollbar = create_scrollbar(results_frame)
        scrollbar.pack(side="right", fill="y")

        self.results_text = Text(
            results_frame,
            height=15,
            width=60,
            wrap="word",
            yscrollcommand=scrollbar.set,
            state="disabled",  # Read-only
        )
        self.results_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.results_text.yview)

        # Action buttons
        button_frame = Frame(self)
        button_frame.pack(pady=(0, 10))

        Button(
            button_frame,
            text="🔄 Re-analisar",
            command=self._run_detection,
            width=15,
        ).pack(side="left", padx=5)

        self.edit_design_btn = Button(
            button_frame,
            text="✏️ Editar Design",
            command=self._edit_design,
            width=15,
            state="disabled",  # Enable only after detection
        )
        self.edit_design_btn.pack(side="left", padx=5)

        Button(
            button_frame,
            text="🔧 Regex Customizado",
            command=self._configure_custom_regex,
            width=18,
        ).pack(side="left", padx=5)

        # Help text
        help_text = Label(
            self,
            text=(
                "💡 Dica: A detecção automática identifica grupos, dias e sujeitos "
                "baseando-se na estrutura de pastas."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack(pady=(15, 0))
        self._update_template_banner()

    def on_show(self):
        """Called when step becomes visible - run detection automatically."""
        self._update_template_banner()
        if self.wizard_data.get("custom_regex_patterns"):
            self.custom_regex_patterns = self.wizard_data.get("custom_regex_patterns")
        self._run_detection()

    def _run_detection(self):
        """Run file scanning and design detection."""
        if self.custom_regex_patterns:
            self.status_var.set("Analisando (usando regex personalizada)...")
        else:
            self.status_var.set("Analisando...")

        # Get video paths from previous step
        video_paths = self.wizard_data.get("video_paths", [])

        if not video_paths:
            self._show_error("Nenhum vídeo selecionado.")
            return

        try:
            # 1. Scan files using ProjectManager
            log.info("wizard.detection.scan_started", path_count=len(video_paths))
            self.scanned_videos = ProjectManager.scan_input_paths(video_paths)

            # 2. Auto-detect design (only for experimental projects)
            project_type = self.wizard_data.get("project_type")
            if project_type == ProjectType.EXPERIMENTAL.value:
                log.info("wizard.detection.design_detection_started")
                # CRITICAL FIX: Use scanned video paths instead of folder inputs
                scanned_video_paths = [v["path"] for v in self.scanned_videos]
                self.detected_design = self._detect_design(scanned_video_paths)
                if self.detected_design:
                    log.info(
                        "wizard.detection.design_detected",
                        pattern=self.detected_design.get("pattern_used"),
                        confidence=self.detected_design.get("confidence"),
                    )
                    self._ensure_group_display_names()
                    if self.wizard_data.get("auto_confirm_design"):
                        self.design_editor_confirmed = True
                        log.info("wizard.design.auto_confirmed")
                    else:
                        self.design_editor_confirmed = False
                        self._open_design_editor_for_confirmation(auto_invoked=True)
                else:
                    log.warning(
                        "wizard.detection.design_not_detected",
                        reason="No pattern matched",
                    )
                    self.design_editor_confirmed = True
            else:
                self.detected_design = None
                log.info(
                    "wizard.detection.design_skipped",
                    reason=f"Project type is {project_type}, not experimental",
                )
                self.design_editor_confirmed = True

            # 3. Calculate parquet summary
            parquet_summary = self._calculate_parquet_summary()

            # 4. Update UI
            self._display_results(parquet_summary)

            # Enable edit button (available for both detected and non-detected designs)
            self.edit_design_btn.config(state="normal")

            self.status_var.set("Análise concluída!")
            log.info(
                "wizard.detection.completed",
                video_count=len(self.scanned_videos),
                design_detected=self.detected_design is not None,
            )
        except Exception as exc:
            log.exception("wizard.detection.run_failed", error=str(exc))
            self.scanned_videos = self.scanned_videos if self.scanned_videos else []
            self.detected_design = None
            self.design_editor_confirmed = False
            self.edit_design_btn.config(state="disabled")
            self._show_error(f"Falha ao concluir a detecção: {exc}")

    def _ensure_group_display_names(self) -> None:
        """Ensure detected design carries a friendly-name mapping."""

        if not self.detected_design:
            return

        groups = self.detected_design.get("groups") or []
        mapping = dict(self.detected_design.get("group_display_names") or {})

        for group in groups:
            if isinstance(group, str):
                mapping.setdefault(group, group)

        self.detected_design["group_display_names"] = mapping

    def _open_design_editor_for_confirmation(self, auto_invoked: bool = False) -> None:
        """Open the design editor dialog to force friendly-name confirmation."""

        if not self.detected_design:
            return

        self._ensure_group_display_names()

        groups = self.detected_design.get("groups") or []
        if not groups:
            self.design_editor_confirmed = True
            return

        wizard_flag = False
        if isinstance(self.wizard_data, dict):
            wizard_flag = bool(self.wizard_data.get("suppress_dialogs"))

        suppress_dialogs = bool(
            os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("ZEBTRACK_SUPPRESS_WIZARD_DIALOGS")
            or wizard_flag
            or getattr(self, "suppress_dialogs", False)
        )

        if suppress_dialogs:
            self.design_editor_confirmed = True
            log.info("wizard.design.confirmation.auto_suppressed")
            return

        if auto_invoked:
            message = (
                "Design experimental detectado!\n\n"
                f"Grupos encontrados: {len(groups)}\n"
                f"Dias: {len(self.detected_design.get('days') or [])}\n\n"
                "Revise ou personalize os nomes antes de continuar."
            )
            messagebox.showinfo("Design Detectado", message, parent=self)

        editor = DesignEditorDialog(
            self,
            self.detected_design,
            custom_regex_patterns=self.custom_regex_patterns,
            on_custom_regex_configured=self._handle_custom_regex_from_editor,
            sample_paths=self._get_sample_paths_for_regex(),
        )
        edited_design = editor.get_result()

        if edited_design:
            self.detected_design = edited_design
            self._ensure_group_display_names()
            self.design_editor_confirmed = True
            log.info(
                "wizard.design.edited_by_user",
                groups=len(self.detected_design.get("groups") or []),
                has_display_names=bool(self.detected_design.get("group_display_names")),
            )
        else:
            if auto_invoked:
                messagebox.showwarning(
                    "Confirmação Necessária",
                    "Confirme os nomes dos grupos antes de avançar.",
                    parent=self,
                )
            self.design_editor_confirmed = False
            log.info("wizard.design.editor_cancelled", auto_invoked=auto_invoked)

    def _detect_design(self, video_paths: list[str]) -> dict | None:
        """
        Auto-detect experimental design from folder structure.

        Args:
            video_paths: List of video file paths

        Returns:
            dict | None: Detected design with confidence score, or None if failed
        """
        # Convert to Path objects
        paths = [Path(p) if isinstance(p, str) else p for p in video_paths]

        # Try custom regex patterns first (if configured)
        if self.custom_regex_patterns:
            custom_result = self._pattern_custom_regex(paths, self.custom_regex_patterns)
            if custom_result:
                log.info(
                    "wizard.detection.custom_regex_used",
                    confidence=custom_result.get("confidence"),
                )
                return custom_result

        # Try built-in patterns (v1.0: 4 patterns)
        patterns = [
            self._pattern_groups_as_folders,
            self._pattern_days_as_folders,
            self._pattern_mixed_folders,
            self._pattern_filename_based,
        ]

        best_result = None
        best_confidence = 0.0

        for pattern_func in patterns:
            result = pattern_func(paths)
            if result and result.get("confidence", 0) > best_confidence:
                best_result = result
                best_confidence = result["confidence"]

        return best_result

    def _pattern_custom_regex(self, paths: list[Path], patterns: dict) -> dict | None:
        """
        Pattern: User-defined custom regex patterns.

        Args:
            paths: List of video file paths
            patterns: Dict with keys: group_pattern, day_pattern, subject_pattern

        Returns:
            dict | None: Detected design or None if patterns don't match
        """
        group_pattern = patterns.get("group_pattern")
        day_pattern = patterns.get("day_pattern")
        subject_pattern = patterns.get("subject_pattern")

        if not group_pattern:
            log.warning("wizard.detection.custom_regex.no_group_pattern")
            return None

        groups_found = set()
        days_found = set()
        subjects_per_group = {}
        match_count = 0

        for path in paths:
            # Search in full path string
            path_str = str(path)

            # Extract group (required)
            group = None
            if group_pattern:
                try:
                    match = re.search(group_pattern, path_str)
                    if match:
                        # Use first capture group if available, otherwise full match
                        group = match.group(1) if match.groups() else match.group(0)
                        groups_found.add(group)
                        match_count += 1

                        if group not in subjects_per_group:
                            subjects_per_group[group] = set()
                except re.error as e:
                    log.error("wizard.detection.custom_regex.group_error", error=str(e))
                    return None

            # Extract day (optional)
            if day_pattern:
                try:
                    match = re.search(day_pattern, path_str)
                    if match:
                        day = match.group(1) if match.groups() else match.group(0)
                        # Normalize day format (add leading zeros if numeric)
                        if day.isdigit():
                            day = f"Day{day.zfill(2)}"
                        days_found.add(day)
                except re.error as e:
                    log.error("wizard.detection.custom_regex.day_error", error=str(e))

            # Extract subject (optional)
            if subject_pattern and group:
                try:
                    match = re.search(subject_pattern, path_str)
                    if match:
                        subject = match.group(1) if match.groups() else match.group(0)
                        # Normalize subject format (add leading zeros if numeric)
                        if subject.isdigit():
                            subject = f"S{subject.zfill(2)}"
                        subjects_per_group[group].add(subject)
                except re.error as e:
                    log.error("wizard.detection.custom_regex.subject_error", error=str(e))

        # Must have at least 2 groups to be valid
        if len(groups_found) < 2:
            log.debug(
                "wizard.detection.custom_regex.insufficient_groups",
                count=len(groups_found),
            )
            return None

        # Convert sets to sorted lists
        subjects_per_group_sorted = {
            group: sorted(list(subjects)) for group, subjects in subjects_per_group.items()
        }

        # Calculate confidence based on match coverage
        coverage = match_count / len(paths)
        confidence = coverage * 0.9  # High confidence for custom patterns

        return {
            "groups": sorted(list(groups_found)),
            "days": sorted(list(days_found)) if days_found else None,
            "subjects_per_group": subjects_per_group_sorted,
            "confidence": confidence,
            "pattern_used": "custom_regex",
        }

    def _pattern_groups_as_folders(self, paths: list[Path]) -> dict | None:
        """Pattern 1: Groups as folders (e.g., /Control/Day1/video.mp4)."""
        if len(paths) < 2:
            log.debug("pattern_groups_as_folders.skipped", reason="Less than 2 videos")
            return None

        # Find common ancestor directory
        common_ancestor = Path(paths[0]).parent
        for path in paths[1:]:
            while not str(Path(path)).startswith(str(common_ancestor)):
                common_ancestor = common_ancestor.parent
                if len(common_ancestor.parts) == 0:
                    break

        log.debug("pattern_groups_as_folders.common_ancestor", path=str(common_ancestor))

        # Extract relative paths from common ancestor
        group_candidates = {}

        for path in paths:
            try:
                rel_parts = Path(path).relative_to(common_ancestor).parts
                # Look at first-level folder under common ancestor
                if len(rel_parts) >= 2:  # At least folder/file.mp4
                    folder = rel_parts[0]
                    if folder not in group_candidates:
                        group_candidates[folder] = []
                    group_candidates[folder].append(path)
            except ValueError:
                # Path not relative to common ancestor
                log.debug("pattern_groups_as_folders.path_not_relative", path=str(path))
                continue

        # Find groups (should have 2+ distinct values, each with at least 1 video)
        groups = [g for g in group_candidates.keys() if len(group_candidates[g]) >= 1]

        log.debug("pattern_groups_as_folders.groups_found", groups=groups, count=len(groups))

        if len(groups) < 2:
            log.debug("pattern_groups_as_folders.insufficient_groups", count=len(groups))
            return None  # Need at least 2 groups

        # Extract days and subjects
        days_found = set()
        subjects_per_group = {}

        for group in groups:
            subjects_per_group[group] = set()  # Use set to avoid duplicates
            for path in group_candidates[group]:
                # Look for day pattern in filename or parent folders
                day_match = re.search(r"[Dd](?:ay)?[\s_-]?(\d+)", str(path))
                if day_match:
                    days_found.add(f"Day{day_match.group(1).zfill(2)}")

                # Look for subject in filename
                subject_match = re.search(r"[Ss](?:ubject)?[\s_-]?(\d+)", path.stem)
                if subject_match:
                    subjects_per_group[group].add(f"S{subject_match.group(1).zfill(2)}")

        # Convert sets to sorted lists for display
        subjects_per_group_sorted = {
            group: sorted(list(subjects)) for group, subjects in subjects_per_group.items()
        }

        # Calculate confidence with penalty when no group shows repetition
        total_grouped_videos = sum(len(group_candidates[g]) for g in groups)
        coverage = total_grouped_videos / len(paths)

        group_sizes = [len(group_candidates[g]) for g in groups]
        max_group_size = max(group_sizes) if group_sizes else 0
        repetition_factor = 1.0 if max_group_size >= 2 else 0.5

        confidence = coverage * 0.8 * repetition_factor  # Base confidence scaled by repetition

        return {
            "groups": sorted(groups),
            "days": sorted(list(days_found)) if days_found else None,
            "subjects_per_group": subjects_per_group_sorted,
            "confidence": confidence,
            "pattern_used": "groups_as_folders",
        }

    def _pattern_days_as_folders(self, paths: list[Path]) -> dict | None:
        """Pattern 2: Days as folders (e.g., /Day1/Control/video.mp4)."""
        # Similar logic but prioritize day detection
        return None  # Simplified for MVP - implement if needed

    def _pattern_mixed_folders(self, paths: list[Path]) -> dict | None:
        """Pattern 3: Mixed folders (e.g., /Exp1/Control/D01/video.mp4)."""
        return None  # Simplified for MVP

    def _pattern_filename_based(self, paths: list[Path]) -> dict | None:
        """Pattern 4: Filename-based (e.g., Control_Day1_S01.mp4)."""
        # Extract from filenames only
        groups_found = set()
        days_found = set()
        subjects_per_group = {}

        for path in paths:
            filename = path.stem

            # Look for group in filename
            # (common prefixes: Control, Treatment, Exp, Group)
            group_value = None
            group_match = re.search(r"(Control|Treatment|Exp\d+|Group\d+)", filename, re.IGNORECASE)
            if group_match:
                group_value = group_match.group(1).capitalize()
                groups_found.add(group_value)

                if group_value not in subjects_per_group:
                    subjects_per_group[group_value] = set()
                    # Use set to avoid duplicate entries for the same subject

            # Look for day
            day_match = re.search(r"[Dd](?:ay)?[\s_-]?(\d+)", filename)
            if day_match:
                days_found.add(f"Day{day_match.group(1).zfill(2)}")

            # Look for subject
            subject_match = re.search(r"[Ss](?:ubject)?[\s_-]?(\d+)", filename)
            if subject_match and group_value:
                subjects_per_group[group_value].add(f"S{subject_match.group(1).zfill(2)}")

        if len(groups_found) < 2:
            return None

        # Convert sets to sorted lists for display
        subjects_per_group_sorted = {
            group: sorted(list(subjects)) for group, subjects in subjects_per_group.items()
        }

        # Calculate confidence based on pattern consistency
        confidence = min(len(groups_found) / 5.0, 1.0) * 0.6  # Lower confidence for filename-based

        return {
            "groups": sorted(list(groups_found)),
            "days": sorted(list(days_found)) if days_found else None,
            "subjects_per_group": subjects_per_group_sorted,
            "confidence": confidence,
            "pattern_used": "filename_based",
        }

    def _calculate_parquet_summary(self) -> dict:
        """Calculate summary of existing parquet files."""
        total_arena = sum(1 for v in self.scanned_videos if v.get("has_arena", False))
        total_rois = sum(1 for v in self.scanned_videos if v.get("has_rois", False))
        total_trajectory = sum(1 for v in self.scanned_videos if v.get("has_trajectory", False))
        total_complete = sum(1 for v in self.scanned_videos if v.get("has_complete_data", False))

        return {
            "total_arena": total_arena,
            "total_rois": total_rois,
            "total_trajectory": total_trajectory,
            "total_complete": total_complete,
        }

    def _display_results(self, parquet_summary: dict):
        """Display detection results in text widget."""
        self.results_text.config(state="normal")
        self.results_text.delete("1.0", "end")

        # Video count
        text = f"📊 Vídeos Encontrados: {len(self.scanned_videos)}\n\n"

        # Parquet summary
        text += "📦 Arquivos Parquet Existentes:\n"
        text += f"  • Arena: {parquet_summary['total_arena']}\n"
        text += f"  • ROIs: {parquet_summary['total_rois']}\n"
        text += f"  • Trajetória: {parquet_summary['total_trajectory']}\n"
        text += f"  • Completos (todos 3): {parquet_summary['total_complete']}\n\n"

        # Design detection
        if self.detected_design:
            text += "🎯 Design Experimental Detectado:\n"
            groups = self.detected_design.get("groups") or []
            friendly_names = self.detected_design.get("group_display_names") or {}
            group_descriptions = []
            for group in groups:
                display = friendly_names.get(group)
                if display and display != group:
                    group_descriptions.append(f"{group} → {display}")
                else:
                    group_descriptions.append(group)

            text += f"  • Grupos: {', '.join(group_descriptions)}\n"

            if self.detected_design.get("days"):
                text += f"  • Dias: {', '.join(self.detected_design['days'])}\n"

            text += f"  • Padrão: {self.detected_design['pattern_used']}\n"
            text += f"  • Confiança: {self.detected_design['confidence']:.0%}\n\n"

            # Subjects per group
            if self.detected_design.get("subjects_per_group"):
                text += "  📋 Sujeitos por Grupo:\n"
                for group, subjects in self.detected_design["subjects_per_group"].items():
                    if subjects:
                        display = friendly_names.get(group, group)
                        label = f"{group} ({display})" if display != group else group
                        text += f"    - {label}: {len(subjects)} sujeito(s)\n"
        else:
            project_type = self.wizard_data.get("project_type")
            if project_type == ProjectType.EXPERIMENTAL.value:
                text += "⚠️ Design experimental não detectado automaticamente.\n\n"
                text += "Possíveis causas:\n"
                text += "  • Estrutura de pastas não segue padrões reconhecidos\n"
                text += "  • Nomes de grupos/dias não são detectáveis (ex: Grupo1, Day01)\n\n"
                text += "Você pode prosseguir sem design detectado ou reorganizar os arquivos.\n"
            else:
                text += "ℹ️ Detecção de design desativada (projeto exploratório).\n"

        # Detector configuration snapshot (helps confirm template application)
        detection_section = self._format_detector_configuration()
        if detection_section:
            text += f"\n{detection_section}\n"

        if self.custom_regex_patterns:
            text += "\n🧩 Regex personalizada em uso:\n"
            for key, label in (
                ("group_pattern", "Grupos"),
                ("day_pattern", "Dias"),
                ("subject_pattern", "Sujeitos"),
            ):
                pattern_value = self.custom_regex_patterns.get(key)
                if pattern_value:
                    text += f"  • {label}: {pattern_value}\n"
                else:
                    text += f"  • {label}: —\n"

        self.results_text.insert("1.0", text)
        self.results_text.config(state="disabled")

    def _format_detector_configuration(self) -> str:
        """Build textual summary of detector/model selections."""

        model_selection = self.wizard_data.get("model_selection") or {}
        weight_assignments = self.wizard_data.get("weight_assignments") or {}
        detector_params = self.wizard_data.get("detector_parameters") or {}
        use_openvino = self.wizard_data.get("use_openvino")

        if not (
            model_selection or weight_assignments or detector_params or use_openvino is not None
        ):
            return ""

        lines = ["⚙️ Configuração Atual do Detector:"]

        aquarium_method = model_selection.get("aquarium_method")
        animal_method = model_selection.get("animal_method")
        if aquarium_method or animal_method:
            aquarium_label = (
                _METHOD_LABELS.get(aquarium_method, aquarium_method)
                if isinstance(aquarium_method, str)
                else None
            )
            animal_label = (
                _METHOD_LABELS.get(animal_method, animal_method)
                if isinstance(animal_method, str)
                else None
            )
            if aquarium_label:
                lines.append(f"  • Método aquário: {aquarium_label}")
            if animal_label:
                lines.append(f"  • Método animais: {animal_label}")

        aquarium_weight = weight_assignments.get("aquarium")
        animal_weight = weight_assignments.get("animal")
        if aquarium_weight or animal_weight:
            if aquarium_weight:
                lines.append(f"  • Peso aquário: {aquarium_weight}")
            if animal_weight:
                lines.append(f"  • Peso animais: {animal_weight}")

        if use_openvino is not None:
            status = "Ativado" if use_openvino else "Desativado"
            lines.append(f"  • OpenVINO: {status}")

        conf = detector_params.get("confidence_threshold")
        nms = detector_params.get("nms_threshold")
        track = detector_params.get("track_threshold")
        match = detector_params.get("match_threshold")
        threshold_bits = []
        if conf is not None:
            threshold_bits.append(f"conf={conf:.2f}")
        if nms is not None:
            threshold_bits.append(f"NMS={nms:.2f}")
        if track is not None:
            threshold_bits.append(f"track={track:.2f}")
        if match is not None:
            threshold_bits.append(f"match={match:.2f}")
        if threshold_bits:
            lines.append(f"  • Thresholds: {', '.join(threshold_bits)}")

        return "\n".join(lines)

    def _show_error(self, message: str):
        """Display error message."""
        self.status_var.set("Erro!")
        self.results_text.config(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("1.0", f"❌ Erro: {message}")
        self.results_text.config(state="disabled")

    def _configure_custom_regex(self):
        """Open custom regex dialog to configure detection patterns."""
        # Open dialog with current patterns
        dialog = CustomRegexDialog(
            self,
            self.custom_regex_patterns or {},
            sample_paths=self._get_sample_paths_for_regex(),
        )
        result_patterns = dialog.get_result()

        if result_patterns is None:
            return

        self._set_custom_regex_patterns(result_patterns, source="detection_step")
        self._run_detection()

    def _get_sample_paths_for_regex(self) -> list[str]:
        """Collect sample paths for live regex preview."""
        samples: list[str] = []

        for video in self.scanned_videos or []:
            path = video.get("path") if isinstance(video, dict) else None
            if isinstance(path, str):
                samples.append(path)

        if not samples:
            raw_paths = self.wizard_data.get("video_paths", [])
            for raw in raw_paths:
                if isinstance(raw, str):
                    samples.append(raw)

        return samples

    def _handle_custom_regex_from_editor(self, patterns: dict | None) -> dict | None:
        """Receive custom regex updates triggered from the design editor."""
        if patterns is None:
            return None

        self._set_custom_regex_patterns(patterns, source="design_editor")
        new_design = self._recalculate_detected_design(
            update_results=True,
            source="design_editor",
        )

        self.design_editor_confirmed = False

        if self.custom_regex_patterns:
            if new_design:
                self.status_var.set("Regex personalizado aplicado ✓")
            else:
                self.status_var.set(
                    "Regex personalizado não encontrou design; "
                    "ajuste os padrões ou edite manualmente."
                )
        else:
            if new_design:
                self.status_var.set("Regex personalizado removido. Detecção padrão reaplicada ✓")
            else:
                self.status_var.set("Detecção padrão reaplicada, mas nenhum design foi encontrado.")

        return new_design

    def _set_custom_regex_patterns(self, patterns: dict, *, source: str) -> None:
        """Persist custom regex patterns and record origin."""
        active_patterns = {key: value for key, value in patterns.items() if value}

        if active_patterns:
            self.custom_regex_patterns = patterns.copy()
            log.info(
                "wizard.detection.custom_regex_configured",
                source=source,
                patterns=list(active_patterns),
            )
        else:
            self.custom_regex_patterns = None
            log.info(
                "wizard.detection.custom_regex_cleared",
                source=source,
            )

    def _recalculate_detected_design(
        self,
        *,
        update_results: bool,
        source: str,
    ) -> dict | None:
        """Re-run design detection using the current regex configuration."""
        if not self.scanned_videos:
            log.warning(
                "wizard.detection.design_recalculation_skipped",
                source=source,
                reason="no_scanned_videos",
            )
            return self.detected_design

        project_type = self.wizard_data.get("project_type")
        if project_type != ProjectType.EXPERIMENTAL.value:
            log.info(
                "wizard.detection.design_recalculation_skipped",
                source=source,
                reason="non_experimental_project",
            )
            return self.detected_design

        scanned_video_paths: list[str] = []
        for video in self.scanned_videos:
            path = video.get("path")
            if isinstance(path, str):
                scanned_video_paths.append(path)

        if not scanned_video_paths:
            log.warning(
                "wizard.detection.design_recalculation_skipped",
                source=source,
                reason="no_paths",
            )
            return self.detected_design

        new_design = self._detect_design(scanned_video_paths)
        self.detected_design = new_design
        self._ensure_group_display_names()

        if update_results:
            parquet_summary = self._calculate_parquet_summary()
            self._display_results(parquet_summary)

        log.info(
            "wizard.detection.design_recalculated",
            source=source,
            has_design=bool(new_design),
            groups=len(new_design.get("groups", [])) if new_design else 0,
        )

        return new_design

    def _edit_design(self):
        """Open design editor dialog for manual editing."""
        if not self.detected_design:
            # If no design detected, create empty template for user to fill
            self.detected_design = {
                "groups": [],
                "days": [],
                "subjects_per_group": {},
                "pattern_used": "none",
                "confidence": 0.0,
                "group_display_names": {},
            }

        self._ensure_group_display_names()

        # Open editor dialog
        editor = DesignEditorDialog(
            self,
            self.detected_design,
            custom_regex_patterns=self.custom_regex_patterns,
            on_custom_regex_configured=self._handle_custom_regex_from_editor,
            sample_paths=self._get_sample_paths_for_regex(),
        )
        edited_design = editor.get_result()

        if edited_design:
            # User saved changes
            self.detected_design = edited_design
            self._ensure_group_display_names()
            self.design_editor_confirmed = True
            log.info(
                "wizard.design.manually_edited",
                groups=len(edited_design["groups"]),
                days=len(edited_design["days"]) if edited_design.get("days") else 0,
            )

            # Refresh display
            parquet_summary = self._calculate_parquet_summary()
            self._display_results(parquet_summary)
            if self.custom_regex_patterns:
                self.status_var.set("Design editado manualmente ✓ (regex personalizado aplicado)")
            else:
                self.status_var.set("Design editado manualmente ✓ (regex padrão)")

    def validate(self) -> tuple[bool, str]:
        """
        Validate detection results.

        Returns:
            tuple[bool, str]: (True, "") if scan completed successfully
        """
        if not self.scanned_videos:
            return (
                False,
                "Nenhum vídeo foi encontrado. Volte e selecione vídeos válidos.",
            )

        project_type = self.wizard_data.get("project_type")
        if (
            project_type == ProjectType.EXPERIMENTAL.value
            and self.detected_design
            and (self.detected_design.get("groups") or [])
            and not self.design_editor_confirmed
        ):
            return (
                False,
                "Confirme os nomes dos grupos no editor antes de avançar.",
            )

        return (True, "")

    def get_data(self) -> dict:
        """
        Extract detection step data.

        Returns:
            dict: Detection data with keys:
                - scanned_videos (list)
                - detected_design (dict | None)
                - video_count (int)
                - parquet_summary (dict)
                - custom_regex_patterns (dict | None)
        """
        return {
            "scanned_videos": self.scanned_videos,
            "detected_design": self.detected_design,
            "video_count": len(self.scanned_videos),
            "parquet_summary": self._calculate_parquet_summary(),
            "custom_regex_patterns": self.custom_regex_patterns,
        }

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected detection data
        """
        if "scanned_videos" in data:
            self.scanned_videos = data["scanned_videos"]

        if "detected_design" in data:
            self.detected_design = data["detected_design"]
            self._ensure_group_display_names()
            self.design_editor_confirmed = True

        if "custom_regex_patterns" in data:
            self.custom_regex_patterns = data["custom_regex_patterns"]

        # Re-display results
        if self.scanned_videos:
            parquet_summary = data.get("parquet_summary", self._calculate_parquet_summary())
            self._display_results(parquet_summary)
            self.status_var.set("Resultados anteriores (use Re-analisar para atualizar)")
        self._update_template_banner()

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(pady=(0, 10))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()
