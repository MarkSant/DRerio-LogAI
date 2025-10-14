# UI Component Architecture (Step 6 Refactoring)

## Overview

The ZebTrack-AI GUI has been refactored from a monolithic `ApplicationGUI` class (11,000+ lines) into **modular, reusable, and testable UI components**. This refactoring improves maintainability, testability, and code organization by separating UI display logic from application logic.

## Architecture Principles

### 1. Component-Based Design
- Each UI section is a **self-contained `ttk.Frame` subclass**
- Components are **composable** - they can be combined to build complex UIs
- Components are **reusable** - they can be instantiated multiple times or used in different contexts

### 2. Separation of Concerns
- **UI Logic**: Components handle only display and user interaction
- **Application Logic**: Controller handles business logic, state management, and data processing
- **Communication**: Event bus for decoupled component-to-controller communication

### 3. Event-Driven Communication
- Components **emit events** when users interact with them
- Controller **subscribes to events** and handles the application logic
- Components **do not** directly call controller methods (except via events)

### 4. Testability
- Components can be **tested in isolation** without the full GUI
- Mock event buses allow testing event emission
- Public API methods allow testing state changes

---

## Component Hierarchy

```
BaseWidget (abstract)
├── VideoDisplayWidget - Canvas for video frame display
├── ZoneControlsWidget - Zone drawing and ROI management
├── ControlPanelWidget - Recording and processing controls
├── ProjectOverviewWidget - Project status and video tree
└── AnalysisControlsWidget - Analysis metadata and track controls
```

---

## Component Catalog

### 1. BaseWidget

**Location**: `src/zebtrack/ui/components/base.py`

**Purpose**: Abstract base class providing common functionality for all components.

**Features**:
- Event bus integration (`emit_event`, `bind_callback`)
- Logging support with component-specific context
- Common state management (`set_enabled`)
- Abstract `_build_ui()` method that subclasses must implement

**Usage**:
```python
class MyWidget(BaseWidget):
    def _build_ui(self):
        # Create your UI widgets here
        self.button = ttk.Button(self, text="Click Me", command=self._on_click)
        self.button.pack()
    
    def _on_click(self):
        # Emit event instead of calling controller directly
        self.emit_event("my_widget.button_clicked", {"timestamp": time.time()})
```

---

### 2. VideoDisplayWidget

**Location**: `src/zebtrack/ui/components/video_display.py`

**Purpose**: Display video frames with automatic scaling and coordinate transformation.

**Key Features**:
- Canvas-based frame display with automatic aspect ratio preservation
- Coordinate conversion between video and canvas space
- Frame loading from video files
- Image scaling and centering

**Events Emitted**:
- `frame.loaded` - Frame successfully loaded
- `frame.error` - Frame loading failed

**Public API**:
```python
widget = VideoDisplayWidget(parent, event_bus=bus, width=800, height=600)

# Load a video frame
success = widget.load_frame("/path/to/video.mp4", frame_number=100)

# Set an image directly
widget.set_image(pil_image)

# Coordinate conversion
canvas_x, canvas_y = widget.video_to_canvas(video_x, video_y)
video_x, video_y = widget.canvas_to_video(canvas_x, canvas_y)

# Clear display
widget.clear()
```

**Use Cases**:
- Zone configuration tab (displaying background frame for drawing)
- Analysis tab (showing live analysis frames)
- Any view requiring video frame display

---

### 3. ZoneControlsWidget

**Location**: `src/zebtrack/ui/components/zone_controls.py`

**Purpose**: Comprehensive controls for zone/ROI drawing and management.

**Key Features**:
- Drawing action buttons (auto-detect, manual polygon, ROI)
- Zone list (Treeview) showing all defined zones
- ROI template management (save/load/apply)
- Video selector for choosing which video to draw on
- ROI inclusion rule configuration
- Interactive editing buttons (save/discard)

**Events Emitted**:
- `zone.auto_detect_clicked` - Auto-detect aquarium clicked
- `zone.draw_main_polygon` - Draw main arena polygon
- `zone.draw_roi` - Draw ROI clicked
- `zone.template_apply` - Apply ROI template
- `zone.template_save` - Save current zones as template
- `zone.template_import` - Import template from file
- `zone.video_selected` - Video selected from tree
- `zone.video_frame_load` - Load frame from selected video
- `zone.list_item_right_click` - Right-click on zone in list
- `zone.roi_rule_changed` - ROI inclusion rule changed
- `zone.roi_settings_apply` - Apply ROI settings

**Public API**:
```python
widget = ZoneControlsWidget(parent, event_bus=bus)

# Enable/disable controls
widget.set_draw_roi_enabled(True)
widget.set_toggle_view_enabled(True)

# Show/hide sections
widget.show_single_analysis_options()
widget.hide_single_analysis_options()
widget.show_interactive_buttons()
widget.hide_interactive_buttons()

# Update lists
widget.update_template_list(["Template 1", "Template 2"])
widget.clear_zone_list()
widget.add_zone_to_list("zone_1", "Main Arena", "arena", "#00FF00")
```

**Use Cases**:
- Zone configuration tab
- Single video analysis setup

---

### 4. ControlPanelWidget

**Location**: `src/zebtrack/ui/components/control_panel.py`

**Purpose**: Recording and video processing controls.

**Key Features**:
- Start/Stop recording buttons
- Process video button
- Preview toggle checkbox
- Processing interval configuration

**Events Emitted**:
- `control.start_recording` - Start recording clicked
- `control.stop_recording` - Stop recording clicked
- `control.process_video` - Process video clicked
- `control.preview_toggled` - Preview checkbox toggled
- `control.interval_changed` - Processing interval changed

**Public API**:
```python
widget = ControlPanelWidget(parent, event_bus=bus)

# Update button states
widget.set_recording_state(is_recording=True)  # Disable start, enable stop
widget.set_processing_enabled(enabled=False)   # Disable process button
```

**Use Cases**:
- Main controls tab
- Project recording interface

---

### 5. ProjectOverviewWidget

**Location**: `src/zebtrack/ui/components/project_overview.py`

**Purpose**: Display project status and video hierarchy.

**Key Features**:
- Status summary cards (total, pending, processing, processed, complete, failed)
- Hierarchical video tree (Group > Day > Subject)
- Video status indicators
- Refresh button

**Events Emitted**:
- `project.video_selected` - Video selected in tree
- `project.video_double_click` - Video double-clicked
- `project.video_right_click` - Video right-clicked (for context menu)
- `project.refresh_requested` - Refresh button clicked

**Public API**:
```python
widget = ProjectOverviewWidget(parent, event_bus=bus)

# Update status counts
widget.update_status_counts({
    "total": 100,
    "pending": 20,
    "processed": 60,
    "complete": 15,
    "failed": 5
})

# Populate tree
widget.clear_tree()
widget.add_tree_item("group_1", "Group A", parent="", values=("", "10 videos"))
widget.add_tree_item("day_1", "Day 1", parent="group_1", values=("", "5 videos"))
widget.add_tree_item("video_1", "video.mp4", parent="day_1", values=("✅", "metadata"))
widget.expand_tree_item("group_1")
```

**Use Cases**:
- Project overview tab
- Video status dashboard

---

### 6. AnalysisControlsWidget

**Location**: `src/zebtrack/ui/components/analysis_controls.py`

**Purpose**: Analysis status display and track selection controls.

**Key Features**:
- Analysis status label
- Metadata display (group, day, subject, task)
- Tracking mode indicator
- Track selector combobox
- Social proximity summary
- Video display label

**Events Emitted**:
- `analysis.track_selected` - User selected a track ID

**Public API**:
```python
widget = AnalysisControlsWidget(parent, event_bus=bus)

# Update metadata
widget.set_metadata(group="Group A", day="Day 1", subject="Subject 01", task="Test")
widget.set_tracking_mode("Multi-indivíduos")
widget.set_profile("default")
widget.set_status("Processando frame 150/500...")
widget.set_social_summary("Interações sociais: 5 eventos detectados")

# Update track options
widget.update_track_options(["Todos", "1", "2", "3"])

# Display frame
widget.display_frame(pil_image)
widget.clear_frame()
```

**Use Cases**:
- Analysis tab
- Real-time analysis display

---

## Integration Pattern

### How to Use Components in ApplicationGUI

**Before (Monolithic)**:
```python
class ApplicationGUI:
    def _create_zone_tab(self):
        # 500+ lines of UI creation code here
        self.zone_listbox = ttk.Treeview(...)
        self.draw_roi_button = ttk.Button(...)
        # ... hundreds more lines
```

**After (Component-Based)**:
```python
class ApplicationGUI:
    def _create_zone_tab(self):
        # Create the component
        self.zone_controls = ZoneControlsWidget(
            self.zone_tab_frame,
            event_bus=self.event_bus
        )
        self.zone_controls.pack(fill="both", expand=True)
        
        # Subscribe to events
        self._subscribe_zone_events()
    
    def _subscribe_zone_events(self):
        """Subscribe to zone control events."""
        if self.event_bus:
            self.event_bus.subscribe("zone.draw_main_polygon", 
                                     self._handle_draw_main_polygon)
            self.event_bus.subscribe("zone.draw_roi", 
                                     self._handle_draw_roi)
            # ... subscribe to other events
    
    def _handle_draw_main_polygon(self, data: dict):
        """Handle draw main polygon event."""
        self.controller.start_zone_drawing("main_arena")
```

---

## Testing Components

### Unit Test Pattern

```python
def test_zone_controls_emits_auto_detect_event(root, event_bus):
    """Test that ZoneControlsWidget emits correct event."""
    widget = ZoneControlsWidget(root, event_bus=event_bus)
    widget.stabilization_frames_var.set("20")
    
    # Simulate button click
    widget._on_auto_detect_clicked()
    
    # Verify event was emitted
    event_bus.publish.assert_called_once()
    call_args = event_bus.publish.call_args[0][0]
    assert call_args.event_name == "zone.auto_detect_clicked"
    assert call_args.data["stabilization_frames"] == 20
```

### Integration Test Pattern

```python
def test_gui_uses_zone_controls_widget(controller):
    """Test that ApplicationGUI properly integrates ZoneControlsWidget."""
    root = tk.Tk()
    event_bus = EventBus()
    gui = ApplicationGUI(root, controller, event_bus)
    
    # Verify component was created
    assert hasattr(gui, 'zone_controls')
    assert isinstance(gui.zone_controls, ZoneControlsWidget)
    
    # Verify event subscriptions
    # ... test that events are properly handled
```

---

## Migration Guide

### For Adding New UI Features

**Before**: Find the 11,000-line `gui.py` and add UI code inline.

**After**: 
1. Identify which component the feature belongs to
2. Add the UI element to the component's `_build_ui()` method
3. Create an event handler that emits an event
4. Update the component's docstring with the new event
5. Subscribe to the event in ApplicationGUI or controller
6. Write a unit test for the new feature

### For Modifying Existing UI

**Before**: Search through 11,000 lines to find the widget.

**After**:
1. Identify which component contains the widget
2. Modify the component file (typically < 500 lines)
3. Update the component's public API if needed
4. Update tests

### For Testing UI Logic

**Before**: Create entire ApplicationGUI in tests (heavyweight).

**After**:
1. Import only the specific component
2. Create a minimal Tkinter root
3. Instantiate the component
4. Test in isolation

---

## Benefits of This Refactoring

### ✅ Maintainability
- **11,000+ lines → 5 focused components** (~200-600 lines each)
- Clear separation of concerns
- Easier to locate and modify specific UI sections

### ✅ Testability
- Components can be tested in isolation
- Mock event buses simplify testing
- No need to instantiate the entire GUI for unit tests

### ✅ Reusability
- Components can be used in multiple places
- `VideoDisplayWidget` can be used in zone tab AND analysis tab
- Components can be composed to create new UIs

### ✅ Extensibility
- Adding new features is straightforward
- New components follow established patterns
- Event-driven architecture allows loose coupling

### ✅ Debugging
- Smaller files are easier to navigate
- Component boundaries make it clear where bugs originate
- Event logging helps trace user interactions

---

## Future Work

### Phase 2: Complete Migration
- Incrementally refactor remaining ApplicationGUI methods to use components
- Extract welcome frame, configuration tab, reports tab into components
- Create integration tests verifying end-to-end workflows

### Phase 3: Advanced Components
- Create composite "smart" widgets that combine multiple base components
- Add component-level state management for complex interactions
- Implement component lifecycle hooks (on_show, on_hide, on_destroy)

### Phase 4: Component Library
- Document all components in a style guide
- Create visual component gallery/showcase
- Provide Tkinter best practices guide

---

## Related Documentation

- **Event Bus Guide**: `docs/PHASE1_EVENT_BUS_IMPLEMENTATION.md`
- **State Manager Guide**: `docs/STATE_MANAGER_GUIDE.md`
- **Architecture Overview**: `docs/ARCHITECTURE.md`
- **Testing Guide**: `tests/ui/test_components.py`

---

## Contact & Contribution

When adding new UI components:
1. Extend `BaseWidget`
2. Implement `_build_ui()`
3. Emit events for user actions
4. Provide a clean public API
5. Write unit tests
6. Update this documentation

For questions or issues, refer to the component source code - each file is heavily documented with docstrings and inline comments.
