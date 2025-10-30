"""
Extract dialog classes from gui.py using AST parsing.

This ensures we get complete class definitions with all methods.
"""

import ast
from pathlib import Path


def extract_imports_for_class(class_node: ast.ClassDef, source_code: str) -> list[str]:
    """
    Determine what imports are needed for a class based on its usage.

    This is a simplified version - we'll add common imports for dialogs.
    """
    imports = []

    # Always add these for dialogs
    imports.append("from tkinter import (")
    tk_imports = [
        "BooleanVar",
        "Button",
        "Checkbutton",
        "DoubleVar",
        "Entry",
        "Frame",
        "IntVar",
        "Label",
        "LabelFrame",
        "Listbox",
        "Radiobutton",
        "Scrollbar",
        "Spinbox",
        "StringVar",
        "Text",
        "Toplevel",
        "filedialog",
        "messagebox",
        "simpledialog",
        "ttk",
    ]

    # Check which ones are actually used
    class_source = ast.get_source_segment(source_code, class_node)
    used_imports = []
    for imp in tk_imports:
        if imp in class_source:
            used_imports.append(imp)

    if used_imports:
        imports[0] = "from tkinter import (\n    " + ",\n    ".join(used_imports) + ",\n)"

    # Check for other common imports
    if "structlog" in class_source:
        imports.append("\nimport structlog")
    if "cv2" in class_source:
        imports.append("import cv2")
    if "Path" in class_source:
        imports.append("from pathlib import Path")
    if "yaml" in class_source:
        imports.append("import yaml")
    if "settings" in class_source:
        imports.append("from zebtrack.settings import settings")
    if "schedule_maximize" in class_source:
        imports.append("from zebtrack.ui.window_utils import schedule_maximize")
    if "CollapsibleFrame" in class_source:
        imports.append("from zebtrack.ui.collapsible_frame import CollapsibleFrame")
    if "ToolTip" in class_source:
        imports.append("from zebtrack.ui.wizard.tooltip import ToolTip")
    if "set_window_icon" in class_source:
        imports.append("from zebtrack.ui.icon_utils import set_window_icon")

    return [imp for imp in imports if imp]  # Remove empty


def extract_class_from_ast(source_file: Path, class_name: str) -> str | None:
    """Extract a complete class definition from source file using AST."""
    with open(source_file, encoding="utf-8") as f:
        source_code = f.read()

    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"Syntax error parsing {source_file}: {e}")
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            # Extract the source code for this class
            class_source = ast.get_source_segment(source_code, node)
            if class_source:
                return class_source

    return None


def create_dialog_module(class_name: str, class_source: str, source_code: str, output_file: Path):
    """Create a complete module file for a dialog class."""
    # Get imports
    # For simplicity, we'll parse the class as AST node
    try:
        class_node = ast.parse(class_source).body[0]
        imports = extract_imports_for_class(class_node, class_source)
    except:
        # Fallback: basic imports
        imports = ["from tkinter import simpledialog, ttk, Frame, Label, Button"]

    # Create module
    content = f'''"""
{class_name}

Extracted from gui.py for better modularity.
"""

'''
    content += "\n".join(imports)
    content += "\n\n\n"
    content += class_source
    content += "\n"

    # Write file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[OK] Created {output_file.name}")


def main():
    """Extract all dialog classes."""
    repo_root = Path(__file__).parent.parent
    gui_file = repo_root / "src" / "zebtrack" / "ui" / "gui.py"
    dialogs_dir = repo_root / "src" / "zebtrack" / "ui" / "dialogs"

    # Dialogs to extract (skip DiagnosticProgressDialog - already done)
    dialogs = [
        ("CalibrationDialog", "calibration_dialog.py"),
        ("ManageWeightsDialog", "manage_weights_dialog.py"),
        ("PendingVideosDialog", "pending_videos_dialog.py"),
        ("CreateProjectDialog", "create_project_dialog.py"),
        ("SingleVideoConfigDialog", "single_video_config_dialog.py"),
        ("StartRecordingDialog", "start_recording_dialog.py"),
        ("MissingMetadataDialog", "missing_metadata_dialog.py"),
        ("SubjectSelectionDialog", "subject_selection_dialog.py"),
        ("SaveROITemplateDialog", "save_roi_template_dialog.py"),
        ("TemplateDialog", "template_dialog.py"),
        ("CenterPeripheryDialog", "center_periphery_dialog.py"),
        ("ColorSelectionDialog", "color_selection_dialog.py"),
    ]

    print(f"Extracting dialogs from {gui_file}...\n")

    # Read source once
    with open(gui_file, encoding="utf-8") as f:
        source_code = f.read()

    for class_name, filename in dialogs:
        print(f"Extracting {class_name}...")
        class_source = extract_class_from_ast(gui_file, class_name)

        if class_source:
            output_file = dialogs_dir / filename
            create_dialog_module(class_name, class_source, source_code, output_file)
        else:
            print(f"[ERROR] Could not extract {class_name}")

    print("\n[SUCCESS] Dialog extraction complete!")


if __name__ == "__main__":
    main()
