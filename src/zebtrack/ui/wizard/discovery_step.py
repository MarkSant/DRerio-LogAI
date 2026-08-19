"""
Step 1: Discovery Dialog.

Gathers initial context about project type, folder organization, and
existing parquet files before scanning any videos.
"""

from copy import deepcopy
from pathlib import Path
from tkinter import (
    Button,
    Canvas,
    Frame,
    IntVar,
    Label,
    LabelFrame,
    Radiobutton,
    StringVar,
    filedialog,
    messagebox,
)
from tkinter import (
    font as tkfont,
)

from zebtrack.i18n import _
from zebtrack.ui.window_utils import create_scrollbar
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID
from zebtrack.ui.wizard.templates import TemplateManager, format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip


class DiscoveryStep(WizardStep):
    """
    Discovery step - understand user's context.

    Questions:
        1. Project type: Experimental (pre-recorded) vs Live
        2. Folder organization (if experimental)
        3. Existing parquet files

    Output:
        {
            "project_type": "experimental" | "live",
            "has_folder_structure": bool,
            "folder_meaning": "experimental" | "organizational" | None,
            "has_parquets": bool,
            "parquet_import_scope": "zones" | "all" | None
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize discovery step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.DISCOVERY

        # UI state variables
        self.project_type_var = StringVar(value=ProjectType.EXPERIMENTAL.value)
        self.folder_organization_var = IntVar(value=1)  # 1=experimental, 2=org, 3=none
        self.parquet_scope_var = IntVar(value=0)  # 0=none, 1=zones, 2=all
        self.template_manager = TemplateManager()
        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None
        # Last canvas width we reflowed text for. Wrapping is driven solely by
        # the canvas width (a single source of truth), so it cannot feedback-loop
        # the way per-widget <Configure> handlers can.
        self._last_wrap_width: int = -1

    def build_ui(self):
        """Build discovery step UI."""
        background_color = self.cget("background")

        self.scroll_canvas = Canvas(self, highlightthickness=0, bg=background_color, borderwidth=0)
        self.scrollbar = create_scrollbar(self, orient="vertical", command=self.scroll_canvas.yview)
        # Auto-hide the scrollbar when the content already fits the viewport, so
        # it doesn't show needlessly on tall windows.
        self.scroll_canvas.configure(yscrollcommand=self._set_scroll)

        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.content_frame = Frame(self.scroll_canvas, bg=background_color)
        self.content_frame.bind(
            "<Configure>",
            lambda event: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")),
        )
        self._canvas_window = self.scroll_canvas.create_window(
            (0, 0), window=self.content_frame, anchor="nw"
        )

        self.scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self.scroll_canvas.bind("<Enter>", self._bind_mousewheel)
        self.scroll_canvas.bind("<Leave>", self._unbind_mousewheel)

        self.content_container = Frame(self.content_frame, bg=background_color)
        self.content_container.pack(fill="both", expand=True, padx=5, pady=5)

        # Title
        title_font = tkfont.Font(size=13, weight="bold")
        title = Label(
            self.content_container,
            text=_("Welcome to the Project Creation Wizard"),
            font=title_font,
        )
        title.pack(pady=(0, 8))

        subtitle = Label(
            self.content_container,
            text=_("Let's start by understanding the context of your project."),
            fg="gray",
        )
        subtitle.pack(pady=(0, 10))

        actions_frame = Frame(self.content_container, bg=background_color)
        actions_frame.pack(fill="x", pady=(0, 5))

        Button(
            actions_frame,
            text=_("📂 Load Template..."),
            command=self._load_template,
            width=24,
        ).pack(side="right")

        self.template_info_label = Label(
            self.content_container,
            textvariable=self.template_info_var,
            fg="#555555",
            bg=background_color,
            wraplength=520,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # Create horizontal layout container for questions (3 columns).
        # The three columns expand equally; their label texts wrap to a third
        # of the canvas width (driven by _on_canvas_configure), which both keeps
        # every label visible AND equalizes the columns — with single-line text
        # the widest column (Q1) used to stay wider than the others.
        questions_container = Frame(self.content_container, bg=background_color)
        questions_container.pack(fill="both", expand=True, pady=(0, 5))

        # Left column (Q1)
        left_col = Frame(questions_container, bg=background_color)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 3))

        # Middle column (Q2)
        middle_col = Frame(questions_container, bg=background_color)
        middle_col.pack(side="left", fill="both", expand=True, padx=(3, 3))

        # Right column (Q3)
        right_col = Frame(questions_container, bg=background_color)
        right_col.pack(side="left", fill="both", expand=True, padx=(3, 0))

        # Question 1: Project Type (LEFT COLUMN)
        self.q1_frame = LabelFrame(left_col, text=_("1. Project Type"), padx=10, pady=8)
        self.q1_frame.pack(fill="both", expand=True)

        rb1 = Radiobutton(
            self.q1_frame,
            text=_("Experimental (pre-recorded videos with groups, days, subjects)"),
            variable=self.project_type_var,
            value=ProjectType.EXPERIMENTAL.value,
            command=self._on_project_type_change,
        )
        rb1.pack(anchor="w", pady=2)
        experimental_tip = _(
            "Projects with a formal design: treatment groups, controls, time series, etc."
        )
        ToolTip(rb1, experimental_tip)

        rb_live = Radiobutton(
            self.q1_frame,
            text=_("Live (record straight from the camera in real time)"),
            variable=self.project_type_var,
            value=ProjectType.LIVE.value,
            command=self._on_project_type_change,
        )
        rb_live.pack(anchor="w", pady=2)
        live_tip = _("Record experiments in real time using a camera connected to the computer.")
        ToolTip(rb_live, live_tip)

        # Question 2: Folder Organization (MIDDLE COLUMN)
        self.q2_frame = LabelFrame(middle_col, text=_("2. Folder Organization"), padx=10, pady=8)
        self.q2_frame.pack(fill="both", expand=True)

        rb3 = Radiobutton(
            self.q2_frame,
            text=_("Yes - folders represent the experimental structure (e.g. Group/Day/)"),
            variable=self.folder_organization_var,
            value=1,
        )
        rb3.pack(anchor="w", pady=2)
        experimental_structure_tip = _(
            "The wizard will detect groups, days and subjects automatically "
            "from the folder structure (e.g. /Control/Day01/Subject01.mp4)."
        )
        ToolTip(rb3, experimental_structure_tip)

        rb4 = Radiobutton(
            self.q2_frame,
            text=_("Yes - but only for organization (arbitrary names)"),
            variable=self.folder_organization_var,
            value=2,
        )
        rb4.pack(anchor="w", pady=2)
        rb4_tip = _("Folders are used only for organization, with no experimental meaning.")
        ToolTip(rb4, rb4_tip)

        rb5 = Radiobutton(
            self.q2_frame,
            text=_("No - every video is in a single directory"),
            variable=self.folder_organization_var,
            value=3,
        )
        rb5.pack(anchor="w", pady=2)
        rb5_tip = _("Every video is in one flat folder, with no subfolders.")
        ToolTip(rb5, rb5_tip)

        # Question 3: Existing Parquet Files (RIGHT COLUMN)
        self.q3_frame = LabelFrame(
            right_col,
            text=_("3. Existing Parquet Files"),
            padx=10,
            pady=8,
        )
        self.q3_frame.pack(fill="both", expand=True)

        Label(
            self.q3_frame,
            text=_("Do you have .parquet files from previous analyses?"),
            fg="gray",
        ).pack(anchor="w", pady=(0, 8))

        rb6 = Radiobutton(
            self.q3_frame,
            text=_("Yes - I want to import only the arena"),
            variable=self.parquet_scope_var,
            value=1,
        )
        rb6.pack(anchor="w", pady=2)
        ToolTip(
            rb6,
            _(
                "Import only the arena from *_arena.parquet files. "
                "ROIs and trajectories will be defined/generated again."
            ),
        )

        rb7 = Radiobutton(
            self.q3_frame,
            text=_("Yes - I want to import zones (arena and ROIs)"),
            variable=self.parquet_scope_var,
            value=2,
        )
        rb7.pack(anchor="w", pady=2)
        ToolTip(
            rb7,
            _(
                "Import the arena and ROIs from *_arena.parquet and *_rois.parquet files. "
                "Trajectories will be generated again."
            ),
        )

        rb8 = Radiobutton(
            self.q3_frame,
            text=_("Yes - I want to import everything (zones + trajectory)"),
            variable=self.parquet_scope_var,
            value=3,
        )
        rb8.pack(anchor="w", pady=2)
        ToolTip(
            rb8,
            _(
                "Import arenas, ROIs and trajectories from *_arena.parquet, "
                "*_rois.parquet and *_trajectory.parquet files. Saves time by avoiding "
                "reprocessing."
            ),
        )

        rb9 = Radiobutton(
            self.q3_frame,
            text=_("No - start from scratch"),
            variable=self.parquet_scope_var,
            value=0,
        )
        rb9.pack(anchor="w", pady=2)
        ToolTip(
            rb9,
            _(
                "Process everything from the start: draw the arena, define ROIs "
                "and generate trajectories."
            ),
        )

        # Glossary / Help text explaining technical terms
        self.glossary_frame = LabelFrame(
            self.content_container,
            text=_("What do these terms mean?"),
            padx=15,
            pady=10,
        )
        glossary_frame = self.glossary_frame
        glossary_frame.pack(fill="x", pady=(15, 0))

        glossary_text = Label(
            glossary_frame,
            text=_(
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
            fg="gray",
            justify="left",
            font=("TkDefaultFont", 9),
        )
        glossary_text.pack(anchor="w")

        # Update UI state
        self._on_project_type_change()

        self.after(0, self._initialize_scroll_area)
        self._update_template_banner()

    def _set_scroll(self, first, last):
        """yscrollcommand that hides the scrollbar when content fits.

        When the whole content is visible (``first == 0`` and ``last == 1``) the
        vertical scrollbar is unnecessary, so we unmap it; otherwise we re-map it
        and forward the position. Keeps the scrollbar off tall windows where it
        would just be visual noise.
        """
        first_f, last_f = float(first), float(last)
        if first_f <= 0.0 and last_f >= 1.0:
            if self.scrollbar.winfo_manager():
                self.scrollbar.pack_forget()
        elif not self.scrollbar.winfo_manager():
            self.scrollbar.pack(side="right", fill="y")
        self.scrollbar.set(first, last)

    def _on_canvas_configure(self, event):
        self.scroll_canvas.itemconfig(self._canvas_window, width=event.width)
        self._apply_dynamic_wrapping(event.width)

    def _apply_dynamic_wrapping(self, width: int):
        """Reflow long label texts to the current canvas width.

        Long single-line radio/label texts get clipped when the dialog is
        narrower than the text. We set each label's ``wraplength`` so the text
        wraps onto more lines and stays fully visible at any dialog size.

        Wrapping is driven by the canvas width (one source of truth), not each
        widget's own ``<Configure>``: the three question columns wrap to a third
        of the width (which also equalizes their widths — single-line text used
        to leave the widest column, Q1, larger than the others), and the
        full-width glossary wraps to the whole width. Because changing a label's
        wraplength never changes the canvas width, this cannot feedback-loop.
        """
        # The canvas <Configure> can fire mid-build, before the columns/glossary
        # exist. glossary_frame is the last one created, so its presence means
        # all the target frames are ready.
        if not hasattr(self, "glossary_frame"):
            return
        if width <= 1 or width == self._last_wrap_width:
            return
        self._last_wrap_width = width

        # Each column gets a third of the width, minus per-column overhead so
        # the three columns + their paddings never overflow the canvas: the
        # LabelFrame padx (~20), the radio indicator (~22), inter-column padding
        # and the container padx. Be generous here — clipping is worse than a
        # slightly earlier wrap.
        column_target = max(width // 3 - 56, 80)
        for frame in (self.q1_frame, self.q2_frame, self.q3_frame):
            for child in frame.winfo_children():
                if isinstance(child, Radiobutton | Label):
                    child.configure(wraplength=column_target, justify="left")

        # The glossary spans the full content width.
        glossary_target = max(width - 60, 80)
        for child in self.glossary_frame.winfo_children():
            if isinstance(child, Radiobutton | Label):
                child.configure(wraplength=glossary_target, justify="left")

    def _bind_mousewheel(self, _event=None):
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None):
        self.scroll_canvas.unbind_all("<MouseWheel>")
        self.scroll_canvas.unbind_all("<Button-4>")
        self.scroll_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if getattr(event, "delta", 0) != 0:
            delta = -1 * int(event.delta / 120)
            if delta != 0:
                self.scroll_canvas.yview_scroll(delta, "units")
        else:
            num = getattr(event, "num", None)
            if num == 4:
                self.scroll_canvas.yview_scroll(-1, "units")
            elif num == 5:
                self.scroll_canvas.yview_scroll(1, "units")

    def _initialize_scroll_area(self):
        if not hasattr(self, "scroll_canvas"):
            return

        self.update_idletasks()

        requested_width = self.content_container.winfo_reqwidth() + 20
        requested_height = self.content_container.winfo_reqheight() + 20

        screen_width = self.winfo_toplevel().winfo_screenwidth()
        screen_height = self.winfo_toplevel().winfo_screenheight()

        preferred_width = min(max(requested_width, 760), screen_width - 160)
        preferred_height = min(max(requested_height, 520), screen_height - 200)

        # Ensure sane fallbacks when running on very small displays
        preferred_width = max(preferred_width, 520)
        preferred_height = max(preferred_height, 420)

        self.scroll_canvas.configure(width=preferred_width, height=preferred_height)

        toplevel = self.winfo_toplevel()
        if toplevel is not None:
            toplevel.update_idletasks()

            min_width = min(preferred_width + 60, screen_width - 60)
            min_height = min(preferred_height + 160, screen_height - 60)

            toplevel.minsize(min_width, min_height)

    def _on_project_type_change(self):
        """Handle project type change - show/hide questions based on project type."""
        project_type = self.project_type_var.get()

        if project_type == ProjectType.LIVE.value:
            # Live projects: hide both folder organization and parquets questions
            self.q2_frame.pack_forget()
            self.q3_frame.pack_forget()
        else:
            # Pre-recorded (experimental): show both questions.
            # There used to be a third branch here for "exploratory", which hid
            # the folder-organization question. That type is gone: it never
            # survived to disk and produced the same project as an experimental
            # one whose design was not detected.
            if not self.q2_frame.winfo_ismapped():
                self.q2_frame.pack(fill="both", expand=True)
            if not self.q3_frame.winfo_ismapped():
                self.q3_frame.pack(fill="both", expand=True)

    def validate(self) -> tuple[bool, str]:
        """
        Validate discovery step.

        All radio buttons have defaults, so always valid.

        Returns:
            tuple[bool, str]: (True, "")
        """
        return (True, "")

    def get_data(self) -> dict:
        """
        Extract discovery step data.

        Returns:
            dict: Discovery data with keys:
                - project_type
                - has_folder_structure (bool, only if experimental)
                - folder_meaning (str, only if experimental + has folders)
                - has_parquets (bool)
                - parquet_import_scope (str | None)
        """
        project_type = self.project_type_var.get()
        parquet_scope_value = self.parquet_scope_var.get()

        # Map parquet scope value to string
        parquet_scope_map = {
            0: None,  # No parquets
            1: "arena",  # Import arena only
            2: "zones",  # Import zones (arena + ROIs)
            3: "all",  # Import everything
        }

        data = {
            "project_type": project_type,
            "has_parquets": parquet_scope_value > 0,
            "parquet_import_scope": parquet_scope_map[parquet_scope_value],
        }

        # Add folder organization info only for experimental projects
        if project_type == ProjectType.EXPERIMENTAL.value:
            folder_org_value = self.folder_organization_var.get()
            data["has_folder_structure"] = folder_org_value in [1, 2]

            if folder_org_value == 1:
                data["folder_meaning"] = "experimental"
            elif folder_org_value == 2:
                data["folder_meaning"] = "organizational"
            else:
                data["folder_meaning"] = None

        return data

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected discovery data
        """
        if "project_type" in data:
            self.project_type_var.set(ProjectType.normalize(data["project_type"]))

        if "folder_meaning" in data:
            folder_meaning = data["folder_meaning"]
            if folder_meaning == "experimental":
                self.folder_organization_var.set(1)
            elif folder_meaning == "organizational":
                self.folder_organization_var.set(2)
            elif data.get("has_folder_structure") is False:
                self.folder_organization_var.set(3)

        if "parquet_import_scope" in data:
            scope = data["parquet_import_scope"]
            if scope == "arena":
                self.parquet_scope_var.set(1)
            elif scope == "zones":
                self.parquet_scope_var.set(2)
            elif scope == "all":
                self.parquet_scope_var.set(3)
            else:
                self.parquet_scope_var.set(0)

        # Update UI visibility
        self._on_project_type_change()
        self._update_template_banner()

    def on_show(self):
        """Handle step visibility when shown and update UI state."""
        super().on_show()
        self._update_template_banner()
        if hasattr(self, "scroll_canvas"):
            self.scroll_canvas.update_idletasks()
            self.scroll_canvas.yview_moveto(0)

    def on_hide(self):
        """Handle step visibility when hidden and clean up bindings."""
        super().on_hide()
        self._unbind_mousewheel()

    def _load_template(self):
        template_path = filedialog.askopenfilename(
            title=_("Load Wizard Template"),
            filetypes=[(_("Wizard Templates"), "*.json"), ("JSON", "*.json")],
            initialdir=str(self.template_manager.templates_dir),
        )

        if not template_path:
            return

        template = self.template_manager.load_template_from_path(template_path)

        if not template:
            messagebox.showerror(
                _("Load Template"),
                _("Could not load the selected template. Check the file and try again."),
                parent=self,
            )
            return

        self._apply_template_data(template, template_path)

        messagebox.showinfo(
            _("Template Loaded"),
            _("Settings loaded. Review each step before continuing."),
            parent=self,
        )

    def _apply_template_data(self, template: dict, template_path: Path | str):
        template_name = template.get("name") or Path(template_path).stem

        metadata = {
            "name": template_name,
            "path": template_path,
            "created_at": template.get("created_at"),
        }
        if template.get("schema_version") is not None:
            metadata["schema_version"] = template.get("schema_version")
        if template.get("wizard_schema_version") is not None:
            metadata["wizard_schema_version"] = template.get("wizard_schema_version")
        self.wizard_data["template_metadata"] = metadata

        mappings = {
            "project_type": ProjectType.normalize(template.get("project_type")),
            "num_aquariums": template.get("num_aquariums"),
            "animals_per_aquarium": template.get("animals_per_aquarium"),
            "aquarium_width_cm": template.get("aquarium_width_cm"),
            "aquarium_height_cm": template.get("aquarium_height_cm"),
            "analysis_interval_frames": template.get("analysis_interval_frames"),
            "display_interval_frames": template.get("display_interval_frames"),
            "parquet_import_scope": template.get("parquet_import_scope"),
            "detected_design": template.get("detected_design"),
            "custom_regex_patterns": template.get("custom_regex_patterns"),
            "model_selection": template.get("model_selection"),
            "weight_assignments": template.get("weight_assignments"),
            "detector_parameters": template.get("detector_parameters"),
            "use_openvino": template.get("use_openvino"),
            "wizard_schema_version": template.get("wizard_schema_version"),
            "has_folder_structure": template.get("has_folder_structure"),
            "folder_meaning": template.get("folder_meaning"),
            # Experimental design (Step 2 — live projects)
            "experiment_days": template.get("experiment_days"),
            "num_groups": template.get("num_groups"),
            "subjects_per_group": template.get("subjects_per_group"),
            "group_names": template.get("group_names"),
            # Live capture configuration (Step 3). Camera/Arduino are
            # reconciled against host hardware when LiveConfigStep is shown.
            "camera_index": template.get("camera_index"),
            "camera_friendly_name": template.get("camera_friendly_name"),
            "use_arduino": template.get("use_arduino"),
            "arduino_port": template.get("arduino_port"),
            "external_trigger_mode": template.get("external_trigger_mode"),
            "use_timed_recording": template.get("use_timed_recording"),
            "recording_duration_s": template.get("recording_duration_s"),
            "use_countdown": template.get("use_countdown"),
            "countdown_duration_s": template.get("countdown_duration_s"),
            "preserve_real_aquarium_shape": template.get("preserve_real_aquarium_shape"),
            "selected_live_mode": template.get("selected_live_mode"),
            # Behavioral analysis configuration (Step 4)
            "behavioral_analysis": template.get("behavioral_analysis"),
        }

        for key, value in mappings.items():
            if value is not None:
                if isinstance(value, dict):
                    self.wizard_data[key] = deepcopy(value)
                else:
                    self.wizard_data[key] = value

        model_selection = self.wizard_data.get("model_selection")
        if isinstance(model_selection, dict) and "use_openvino" in model_selection:
            self.wizard_data["use_openvino"] = model_selection.get("use_openvino")

        # Update local UI state
        parquet_scope = self.wizard_data.get("parquet_import_scope")
        self.wizard_data["has_parquets"] = bool(parquet_scope)

        discovery_data = {
            "project_type": self.wizard_data.get("project_type"),
            "parquet_import_scope": parquet_scope,
            "has_parquets": bool(parquet_scope),
            "has_folder_structure": self.wizard_data.get("has_folder_structure"),
            "folder_meaning": self.wizard_data.get("folder_meaning"),
        }

        self.set_data(discovery_data)
        self._update_template_banner()

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(fill="x", pady=(0, 15))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()
