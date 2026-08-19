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
from typing import Any

import structlog

from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.i18n import _
from zebtrack.ui.window_utils import create_scrollbar
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.custom_regex_dialog import CustomRegexDialog
from zebtrack.ui.wizard.design_editor_dialog import DesignEditorDialog
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner

log = structlog.get_logger()


def _method_labels() -> dict[str, str]:
    """Map a detector method key to the label shown to the operator.

    This is a function, not a module-level dict, because a dict literal would
    call _() at import time and freeze whatever language happened to be
    installed then -- see docs/guides/developer/i18n.md.
    """
    return {
        "seg": _("Segmentation (seg)"),
        "det": _("Detection (det)"),
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
            } | None,  # None when detection failed or was not run
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
        # State
        self.scanned_videos: list[dict] = []
        self.detected_design: dict[str, Any] | None = None
        self.status_var = StringVar(value=_("Waiting for analysis..."))
        self.custom_regex_patterns: dict[str, str] | None = None  # User-defined regex patterns
        self.design_editor_confirmed = False
        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None

    def build_ui(self):
        """Build detection step UI - horizontal 2-column layout for better space usage."""
        # Title (full width)
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text=_("Automatic Design Detection"), font=title_font)
        title.pack(pady=(0, 5))

        subtitle = Label(
            self,
            text=_("Analyzing folder structure and parquet files..."),
            fg="gray",
            wraplength=700,
        )
        subtitle.pack(pady=(0, 10))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=700,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # HORIZONTAL 2-COLUMN LAYOUT: Results (left) + Controls (right)
        content_frame = Frame(self)
        content_frame.pack(fill="both", expand=True, pady=(5, 0))
        content_frame.columnconfigure(0, weight=3, minsize=650)  # Results column (70%)
        content_frame.columnconfigure(1, weight=1, minsize=280)  # Controls column (30%)
        content_frame.rowconfigure(0, weight=1)

        # LEFT COLUMN: Detection results
        results_frame = LabelFrame(content_frame, text=_("Detection Results"), padx=10, pady=10)
        results_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Scrollable text widget for results (REDUCED height from 15 to 12)
        scrollbar = create_scrollbar(results_frame)
        scrollbar.pack(side="right", fill="y")

        self.results_text = Text(
            results_frame,
            height=12,  # Reduced from 15 to save vertical space
            width=50,  # Reduced from 60 to fit horizontal layout
            wrap="word",
            yscrollcommand=scrollbar.set,
            state="disabled",
        )
        self.results_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.results_text.yview)

        # RIGHT COLUMN: Controls and status
        right_panel = Frame(content_frame)
        right_panel.grid(row=0, column=1, sticky="nsew")

        # Status message (top of right panel)
        status_label_frame = LabelFrame(right_panel, text=_("Status"), padx=10, pady=10)
        status_label_frame.pack(fill="x", pady=(0, 10))

        Label(
            status_label_frame,
            textvariable=self.status_var,
            fg="blue",
            wraplength=240,
            justify="left",
        ).pack()

        # Action buttons (vertical stack in right panel)
        button_frame = LabelFrame(right_panel, text=_("Actions"), padx=10, pady=10)
        button_frame.pack(fill="x", pady=(0, 10))

        Button(
            button_frame,
            text=_("🔄 Re-analyze"),
            command=self._run_detection,
            width=22,
        ).pack(pady=3, fill="x")

        self.edit_design_btn = Button(
            button_frame,
            text=_("✏️ Edit Design"),
            command=self._edit_design,
            width=22,
            state="disabled",
        )
        self.edit_design_btn.pack(pady=3, fill="x")

        Button(
            button_frame,
            text=_("🔧 Custom Regex"),
            command=self._configure_custom_regex,
            width=22,
        ).pack(pady=3, fill="x")

        # Help text (bottom of right panel)
        help_frame = LabelFrame(right_panel, text=_("💡 Tip"), padx=10, pady=10)
        help_frame.pack(fill="both", expand=True)

        help_text = Label(
            help_frame,
            text=_(
                "Automatic detection identifies groups, days and subjects "
                "from the folder structure."
            ),
            fg="gray",
            wraplength=240,
            justify="left",
        )
        help_text.pack()

        self._update_template_banner()

    def on_show(self):
        """Execute actions when step becomes visible - run detection automatically."""
        self._update_template_banner()
        if self.wizard_data.get("custom_regex_patterns"):
            self.custom_regex_patterns = self.wizard_data.get("custom_regex_patterns")
        self._run_detection()

    def _run_detection(self):
        """Run file scanning and design detection."""
        if self.custom_regex_patterns:
            self.status_var.set(_("Analyzing (using custom regex)..."))
        else:
            self.status_var.set(_("Analyzing..."))

        # Get video paths from previous step
        video_paths = self.wizard_data.get("video_paths", [])

        if not video_paths:
            self._show_error(_("No video selected."))
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

            self.status_var.set(_("Analysis complete!"))
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
            self._show_error(_("Failed to complete detection: {error}").format(error=exc))

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
            message = _(
                "Experimental design detected!\n\n"
                "Groups found: {groups}\n"
                "Days: {days}\n\n"
                "Review or customize the names before continuing."
            ).format(
                groups=len(groups),
                days=len(self.detected_design.get("days") or []),
            )
            messagebox.showinfo(_("Design Detected"), message, parent=self)

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
                    _("Confirmation Required"),
                    _("Confirm the group names before moving on."),
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

        # DEBUG: Log custom_regex_patterns state
        log.info(
            "wizard.detection._detect_design.start",
            has_custom_regex=bool(self.custom_regex_patterns),
            custom_patterns_keys=list(self.custom_regex_patterns.keys())
            if self.custom_regex_patterns
            else [],
            video_count=len(paths),
        )

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

        Supports multi-subject files.
        """
        from zebtrack.ui.wizard.models import MultiAquariumData

        if not patterns.get("group_pattern"):
            log.warning("wizard.detection.custom_regex.no_group_pattern")
            return None

        groups_found: set[str] = set()
        days_found: set[str] = set()
        subjects_per_group: dict[str, set[str]] = {}
        match_count = 0
        subject_mappings: dict[str, list[dict]] = {}

        combined_pattern = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=patterns.get("group_pattern"),
            day_pattern=patterns.get("day_pattern"),
            subject_pattern=patterns.get("subject_pattern"),
        )

        for path in paths:
            file_subjects = []
            matched = False

            # Try combined pattern first
            if combined_pattern:
                file_subjects = self._process_path_with_combined_pattern(
                    str(path), combined_pattern, groups_found, days_found, subjects_per_group
                )
                if file_subjects:
                    matched = True
                    match_count += 1

            # Fallback: individual patterns (returns list of dicts)
            if not matched:
                fallback_results = self._process_path_with_individual_patterns(
                    str(path), patterns, groups_found, days_found, subjects_per_group
                )
                if fallback_results:
                    file_subjects.extend(fallback_results)
                    match_count += 1

            if file_subjects:
                subject_mappings[str(path)] = file_subjects

        return self._build_custom_regex_result(
            paths, groups_found, days_found, subjects_per_group, match_count, subject_mappings
        )

    def _process_path_with_combined_pattern(
        self, path_str: Path | str, pattern, groups_found, days_found, subjects_per_group
    ):
        """Process path using combined regex pattern."""
        file_subjects = []
        try:
            compiled = re.compile(pattern)
            matches = list(compiled.finditer(path_str))

            if len(matches) >= 1:
                for m in matches:
                    data = self._extract_match_data(m.groupdict())
                    if not data["group"]:
                        continue

                    self._update_detected_sets(data, groups_found, days_found, subjects_per_group)
                    file_subjects.append(data)
        except re.error as e:
            log.error("wizard.detection.custom_regex.combined_error", error=str(e))

        return file_subjects

    def _process_path_with_individual_patterns(
        self, path_str: Path | str, patterns, groups_found, days_found, subjects_per_group
    ):
        """Process path using individual regex patterns as fallback.

        Uses ``findall`` on each individual pattern to detect ALL occurrences
        in the filename/path.  When the subject pattern matches more than once
        (multi-subject file), a list with one dict per subject is returned so
        the caller can populate ``subject_mappings`` correctly.

        Returns:
            list[dict] | None: A list of ``{"group", "day", "subject"}`` dicts,
            one per detected subject.  ``None`` if the group pattern did not
            match at all (the file is not recognised).
        """
        # --- groups ----------------------------------------------------------
        group_pattern = patterns.get("group_pattern")
        if not group_pattern:
            return None

        try:
            group_match = re.search(group_pattern, str(path_str))
        except re.error as e:
            log.error("wizard.detection.custom_regex.group_error", error=str(e))
            return None

        if not group_match:
            return None

        group = group_match.group(1) if group_match.groups() else group_match.group(0)

        # --- days ------------------------------------------------------------
        day = None
        day_pattern = patterns.get("day_pattern")
        if day_pattern:
            try:
                day_match = re.search(day_pattern, str(path_str))
                if day_match:
                    day = day_match.group(1) if day_match.groups() else day_match.group(0)
                    if day.isdigit():
                        day = f"Day{day.zfill(2)}"
            except re.error as e:
                log.error("wizard.detection.custom_regex.day_error", error=str(e))

        # --- subjects (finditer → ALL matches) -------------------------------
        subjects: list[str] = []
        subject_pattern = patterns.get("subject_pattern")
        if subject_pattern:
            try:
                for sub_match in re.finditer(subject_pattern, str(path_str)):
                    val = sub_match.group(1) if sub_match.groups() else sub_match.group(0)
                    if val.isdigit():
                        val = f"S{val.zfill(2)}"
                    if val not in subjects:
                        subjects.append(val)
            except re.error as e:
                log.error("wizard.detection.custom_regex.subject_error", error=str(e))

        if not subjects:
            subjects = [""]

        # Build one entry per subject and register in detection sets
        results: list[dict] = []
        for subject in subjects:
            data = {"group": group, "day": day or "", "subject": subject}
            self._update_detected_sets(data, groups_found, days_found, subjects_per_group)
            results.append(data)

        return results

    def _extract_match_data(self, groups_dict):
        """Extract and normalize data from regex match dict."""
        group_val = groups_dict.get("group", "")
        day_val = groups_dict.get("day", "")
        subject_val = groups_dict.get("subject", "")

        if group_val and group_val.isdigit():
            group_val = f"G{group_val.zfill(2)}"
        if day_val and day_val.isdigit():
            day_val = f"Day{day_val.zfill(2)}"
        if subject_val and subject_val.isdigit():
            subject_val = f"S{subject_val.zfill(2)}"

        return {"group": group_val, "day": day_val, "subject": subject_val}

    def _update_detected_sets(self, data, groups_found, days_found, subjects_per_group):
        """Update detection sets with found data."""
        if data["group"]:
            groups_found.add(data["group"])
            if data["group"] not in subjects_per_group:
                subjects_per_group[data["group"]] = set()
            if data["subject"]:
                subjects_per_group[data["group"]].add(data["subject"])

        if data["day"]:
            days_found.add(data["day"])

    def _build_custom_regex_result(
        self,
        paths: list[Path],
        groups_found,
        days_found,
        subjects_per_group,
        match_count,
        subject_mappings,
    ):
        """Validate and build final result dict."""
        total_subjects = sum(len(subs) for subs in subjects_per_group.values())

        if len(groups_found) < 2 and total_subjects < 2:
            log.debug(
                "wizard.detection.custom_regex.insufficient_data",
                groups=len(groups_found),
                subjects=total_subjects,
            )
            return None

        subjects_per_group_sorted = {
            group: sorted(list(subjects)) for group, subjects in subjects_per_group.items()
        }

        coverage = match_count / len(paths) if paths else 0
        confidence = coverage * 0.9

        return {
            "groups": sorted(list(groups_found)),
            "days": sorted(list(days_found)) if days_found else None,
            "subjects_per_group": subjects_per_group_sorted,
            "confidence": confidence,
            "pattern_used": "custom_regex",
            "subject_mappings": subject_mappings,
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
        group_candidates: dict[str, list[Path]] = {}

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
        subjects_per_group: dict[str, set[str]] = {}

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
        total_grouped_videos = sum([len(group_candidates[g]) for g in groups])
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
        subjects_per_group: dict[str, set[str]] = {}

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
        text = _("📊 Videos found: {count}").format(count=len(self.scanned_videos)) + "\n\n"

        # Parquet summary
        text += _("📦 Existing Parquet Files:") + "\n"
        text += _("  • Arena: {count}").format(count=parquet_summary["total_arena"]) + "\n"
        text += _("  • ROIs: {count}").format(count=parquet_summary["total_rois"]) + "\n"
        text += (
            _("  • Trajectory: {count}").format(count=parquet_summary["total_trajectory"]) + "\n"
        )
        text += (
            _("  • Complete (all 3): {count}").format(count=parquet_summary["total_complete"])
            + "\n\n"
        )

        # Design detection
        if self.detected_design:
            text += _("🎯 Experimental Design Detected:") + "\n"
            groups = self.detected_design.get("groups") or []
            friendly_names = self.detected_design.get("group_display_names") or {}
            group_descriptions = []
            for group in groups:
                display = friendly_names.get(group)
                if display and display != group:
                    group_descriptions.append(f"{group} → {display}")
                else:
                    group_descriptions.append(group)

            text += _("  • Groups: {groups}").format(groups=", ".join(group_descriptions)) + "\n"

            if self.detected_design.get("days"):
                text += (
                    _("  • Days: {days}").format(days=", ".join(self.detected_design["days"]))
                    + "\n"
                )

            text += (
                _("  • Pattern: {pattern}").format(pattern=self.detected_design["pattern_used"])
                + "\n"
            )
            text += (
                _("  • Confidence: {value}").format(
                    value=f"{self.detected_design['confidence']:.0%}"
                )
                + "\n\n"
            )

            # Subjects per group
            if self.detected_design.get("subjects_per_group"):
                text += _("  📋 Subjects per Group:") + "\n"
                for group, subjects in self.detected_design["subjects_per_group"].items():
                    if subjects:
                        display = friendly_names.get(group, group)
                        label = f"{group} ({display})" if display != group else group
                        text += (
                            _("    - {label}: 1 subject").format(label=label)
                            if len(subjects) == 1
                            else _("    - {label}: {count} subjects").format(
                                label=label, count=len(subjects)
                            )
                        ) + "\n"
        else:
            project_type = self.wizard_data.get("project_type")
            if project_type == ProjectType.EXPERIMENTAL.value:
                text += _(
                    "⚠️ Experimental design was not detected automatically.\n\n"
                    "Possible causes:\n"
                    "  • The folder structure does not follow a recognized pattern\n"
                    "  • Group/day names are not detectable (e.g. Grupo1, Day01)\n\n"
                    "You can continue without a detected design, or reorganize the files.\n"
                )
            else:
                text += _("ℹ️ Automatic design detection was not run.") + "\n"

        # Detector configuration snapshot (helps confirm template application)
        detection_section = self._format_detector_configuration()
        if detection_section:
            text += f"\n{detection_section}\n"

        if self.custom_regex_patterns:
            text += "\n" + _("🧩 Custom regex in use:") + "\n"
            for key, label in (
                ("group_pattern", _("Groups")),
                ("day_pattern", _("Days")),
                ("subject_pattern", _("Subjects")),
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

        lines = [_("⚙️ Current Detector Configuration:")]

        aquarium_method = model_selection.get("aquarium_method")
        animal_method = model_selection.get("animal_method")
        if aquarium_method or animal_method:
            method_labels = _method_labels()
            aquarium_label = (
                method_labels.get(aquarium_method, aquarium_method)
                if isinstance(aquarium_method, str)
                else None
            )
            animal_label = (
                method_labels.get(animal_method, animal_method)
                if isinstance(animal_method, str)
                else None
            )
            if aquarium_label:
                lines.append(_("  • Aquarium method: {method}").format(method=aquarium_label))
            if animal_label:
                lines.append(_("  • Animal method: {method}").format(method=animal_label))

        aquarium_weight = weight_assignments.get("aquarium")
        animal_weight = weight_assignments.get("animal")
        if aquarium_weight or animal_weight:
            if aquarium_weight:
                lines.append(_("  • Aquarium weight: {weight}").format(weight=aquarium_weight))
            if animal_weight:
                lines.append(_("  • Animal weight: {weight}").format(weight=animal_weight))

        if use_openvino is not None:
            status = _("Enabled") if use_openvino else _("Disabled")
            lines.append(_("  • OpenVINO: {status}").format(status=status))

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
        self.status_var.set(_("Error!"))
        self.results_text.config(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("1.0", _("❌ Error: {message}").format(message=message))
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
                self.status_var.set(_("Custom regex applied ✓"))
            else:
                self.status_var.set(
                    _("The custom regex found no design; adjust the patterns or edit manually.")
                )
        else:
            if new_design:
                self.status_var.set(_("Custom regex removed. Default detection reapplied ✓"))
            else:
                self.status_var.set(_("Default detection reapplied, but no design was found."))

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
                self.status_var.set(_("Design edited manually ✓ (custom regex applied)"))
            else:
                self.status_var.set(_("Design edited manually ✓ (default regex)"))

    def validate(self) -> tuple[bool, str]:
        """
        Validate detection results.

        Returns:
            tuple[bool, str]: (True, "") if scan completed successfully
        """
        if not self.scanned_videos:
            return (
                False,
                _("No video was found. Go back and select valid videos."),
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
                _("Confirm the group names in the editor before moving on."),
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
            self.status_var.set(
                _("Previous results (use '{button}' to refresh)").format(button=_("🔄 Re-analyze"))
            )
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
