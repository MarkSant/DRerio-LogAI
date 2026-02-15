# ZebTrack UI Widgets Catalog

This document catalogs reusable UI widgets in ZebTrack-AI, providing API documentation and usage examples.

## Table of Contents

<!-- markdownlint-disable MD051 --><!-- justification: TOC anchors validated by renderer -->

- [CollapsibleFrame](#collapsibleframe)
- [NumberInput](#numberinput)
- [Standard Widgets](#standard-widgets)

<!-- markdownlint-enable MD051 -->

---

## CollapsibleFrame

**Location**: `src/zebtrack/ui/collapsible_frame.py`
**Added**: v2.0 (Phase 4, October 2025)
**Purpose**: Expandable/collapsible section with clickable header

### CollapsibleFrame Features

- ✅ Click-to-toggle: Entire header area is clickable
- ✅ Visual indicator: ▼ (expanded) / ▶ (collapsed)
- ✅ Hover effect: Header highlights on mouse-over
- ✅ Configurable initial state
- ✅ Clean API: `get_content_frame()` for content access

### CollapsibleFrame API

```python
from zebtrack.ui.collapsible_frame import CollapsibleFrame

# Create collapsible section
frame = CollapsibleFrame(
    parent,
    title="Section Title",        # Header text
    start_collapsed=False,         # Initial state (default: False)
    **kwargs                       # Additional Frame options
)
frame.pack(fill="both", expand=False, pady=5)

# Add content to the collapsible area
content = frame.get_content_frame()
Label(content, text="Content goes here").pack()

# Programmatic control
frame.collapse()  # Hide content
frame.expand()    # Show content
frame.toggle()    # Toggle current state

# Check state
if frame.is_collapsed:
    print("Frame is collapsed")
```

### CollapsibleFrame Usage Example

**CalibrationDialog** (gui.py:298-320):

```python
# Calibration section
calibration_collapsible = CollapsibleFrame(
    container,
    title="📐 Calibração e Diagnóstico",
    start_collapsed=False,
)
calibration_collapsible.pack(fill="both", expand=False, pady=(0, 5))
calibration_section = calibration_collapsible.get_content_frame()

# Add widgets to calibration_section
Label(calibration_section, text="Calibration controls...").pack()
```

### CollapsibleFrame Styling

**Colors**:

- Header default: SystemButtonFace (matches OS)
- Header hover: `#e8e8e8` (light gray)
- Header border: raised, borderwidth=1

**Fonts**:

- Indicator: Segoe UI, 10pt
- Title: Segoe UI, 10pt bold

### CollapsibleFrame Best Practices

✅ **Do**:

- Use for logically grouped settings
- Start with most important section expanded
- Keep titles concise (< 40 characters)
- Use emojis for visual categorization (📐, ⚙️, 🎯)

❌ **Don't**:

- Nest CollapsibleFrames (causes layout issues)
- Use for single widgets (overhead not justified)
- Change state programmatically during user interaction

---

## NumberInput

**Location**: `src/zebtrack/ui/wizard/experimental_design_step.py:24-118`
**Added**: v2.0 (Phase 4, October 2025)
**Purpose**: Numeric input with direct typing + increment/decrement buttons

### NumberInput Features

- ✅ Direct keyboard input (faster than Scale)
- ✅ Mouse increment/decrement buttons (− / +)
- ✅ Automatic validation and clamping to range
- ✅ Visual feedback: Buttons disabled at limits
- ✅ Works with IntVar (reactive)

### API

```python
from zebtrack.ui.wizard.experimental_design_step import NumberInput
from tkinter import IntVar

# Create NumberInput
var = IntVar(value=5)
number_input = NumberInput(
    parent,
    variable=var,               # IntVar to bind
    min_val=1,                  # Minimum value (default: 1)
    max_val=100,                # Maximum value (default: 100)
    width=5,                    # Entry width in characters (default: 5)
    **kwargs                    # Additional Frame options
)
number_input.pack()

# Value is automatically clamped
var.set(150)  # Will be clamped to 100
var.set(-5)   # Will be clamped to 1

# Read current value
current = var.get()
```

### NumberInput Usage Example

**ExperimentalDesignStep** (experimental_design_step.py:188-197):

```python
# Days input (1-30)
days_input = NumberInput(
    days_frame,
    variable=self.num_days_var,
    min_val=1,
    max_val=30,
    width=5,
)
days_input.pack(side="left")
Label(days_frame, text="dias", fg="gray").pack(side="left", padx=5)
```

### NumberInput Internal Structure

```text
┌─────────────────────────────┐
│ [−]  [ 15 ]  [+]           │  ← NumberInput
│  ↑     ↑      ↑            │
│  │     │      │            │
│  │     │      └─ Increase button
│  │     └──────── Entry (editable)
│  └────────────── Decrease button
└─────────────────────────────┘
```

### NumberInput Validation Logic

1. User types value → `trace_add("write")` triggered
2. Try to convert to int
3. If valid:
   - Clamp to [min_val, max_val]
   - Update button states
4. If invalid:
   - Reset to min_val
   - Visual feedback via button states

### NumberInput Best Practices

✅ **Do**:

- Use for numeric settings with clear min/max
- Provide visual label explaining unit (e.g., "dias", "animais/grupo")
- Set reasonable ranges (avoid 1-1000)
- Combine with ToolTip for guidance

❌ **Don't**:

- Use for unbounded ranges (Entry alone is better)
- Set max_val > 1000 (too many clicks)
- Forget validation in parent form

---

## Standard Widgets

### create_scrollbar()

**Location**: `src/zebtrack/ui/window_utils.py`
**Purpose**: Factory for ttkbootstrap-compatible scrollbars

```python
from zebtrack.ui.window_utils import create_scrollbar

scrollbar = create_scrollbar(
    parent,
    orient="vertical",          # "vertical" or "horizontal"
    command=text_widget.yview
)
text_widget.configure(yscrollcommand=scrollbar.set)
scrollbar.pack(side="right", fill="y")
```

### ToolTip

**Location**: `src/zebtrack/ui/wizard/tooltip.py`
**Purpose**: Hover tooltips for form fields

```python
from zebtrack.ui.wizard.tooltip import ToolTip

button = Button(parent, text="Help")
ToolTip(
    button,
    "This is a helpful tooltip\n\n"
    "Multiple lines supported\n"
    "• Bullet points\n"
    "• Work well"
)
```

**Best Practices**:

- Start with brief description
- Use blank line before details
- Use emojis for emphasis: 📏, ⚠️, 💡
- Include examples when relevant

---

## Widget Comparison

### When to Use Each

| Widget               | Use Case                      | Example              |
| -------------------- | ----------------------------- | -------------------- |
| **NumberInput**      | Bounded numeric input (1-100) | Days, groups, counts |
| **Entry**            | Text or unbounded numbers     | Names, file paths    |
| **Scale**            | Visual range selection        | Opacity (0.0-1.0)    |
| **Spinbox**          | List of discrete values       | Font sizes           |
| **Combobox**         | Choice from list              | Ports, weights       |
| **CollapsibleFrame** | Grouped settings              | Dialog sections      |

### Migration Guide

**Scale → NumberInput**:

```python
# OLD (Scale)
scale = Scale(parent, from_=1, to=30, variable=var, orient="horizontal")
scale.pack(side="left")
value_label = Label(parent, textvariable=var)
value_label.pack(side="left")

# NEW (NumberInput)
number_input = NumberInput(parent, variable=var, min_val=1, max_val=30)
number_input.pack(side="left")
Label(parent, text="units", fg="gray").pack(side="left", padx=5)
```

**Benefits**:

- ✅ 50% less code
- ✅ Direct keyboard input
- ✅ No separate label needed
- ✅ Better accessibility

---

## Creating New Widgets

### Widget Checklist

When creating a new reusable widget:

1. **Inheritance**:
   - Inherit from Frame or ttk.Frame
   - Use `super().__init__(parent, **kwargs)`

2. **API Design**:
   - Accept parent as first arg
   - Use kwargs for Frame options
   - Provide simple getter/setter if needed

3. **Validation**:
   - Use `trace_add("write")` for reactive validation
   - Provide visual feedback (colors, icons)
   - Don't block invalid input, just highlight

4. **Documentation**:
   - Add docstring with example
   - Document all parameters
   - Include in this WIDGETS.md

5. **Testing**:
   - Add unit tests in tests/ui/
   - Test with different parent types
   - Verify keyboard/mouse interaction

### Template

```python
"""
MyWidget - Brief description

Example:
    widget = MyWidget(parent, option="value")
    widget.pack()
"""
from tkinter import Frame

class MyWidget(Frame):
    """Widget description."""

    def __init__(self, parent, option="default", **kwargs):
        """
        Initialize widget.

        Args:
            parent: Parent widget
            option: Some option
            **kwargs: Additional Frame options
        """
        super().__init__(parent, **kwargs)
        # Build UI here

    def get_value(self):
        """Get current value."""
        return self._value

    def set_value(self, value):
        """Set value with validation."""
        # Validate and set
        self._value = value
```

---

## Widget Gallery

Visual reference of common widgets:

```text
CollapsibleFrame (expanded):
┌─────────────────────────────┐
│ ▼ Section Title             │ ← Clickable header
├─────────────────────────────┤
│                             │
│  Content area (ttk.Frame)   │
│  Add widgets here           │
│                             │
└─────────────────────────────┘

CollapsibleFrame (collapsed):
┌─────────────────────────────┐
│ ▶ Section Title             │ ← Clickable header
└─────────────────────────────┘

NumberInput:
┌─────────────────────────────┐
│ [−]  [ 15 ]  [+]  units     │
└─────────────────────────────┘

Standard Form Layout:
┌─────────────────────────────┐
│ Label:  [Entry Field     ]  │ ← Horizontal
│                             │
│ Label:  [Entry] units       │ ← With unit
│                             │
│ Label:  [NumberInput] units │ ← NumberInput
│                             │
│ Label:  [Combobox       ▼]  │ ← Dropdown
└─────────────────────────────┘
```

---

## References

- **CLAUDE.md**: Main development guide
- **Wizard guide**: `docs/guides/developer/wizard.md`
- **Architecture overview**: `docs/explanation/architecture.md`
- **Code Examples**: See wizard steps in `src/zebtrack/ui/wizard/`

---

**Maintained by**: ZebTrack-AI Team
**Last Updated**: October 29, 2025
**Version**: 1.0
