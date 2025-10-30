"""
Update gui.py to import dialogs from separate modules and remove old definitions.
"""

import ast
from pathlib import Path


def find_class_positions(source_code: str, class_names: list[str]) -> dict[str, tuple[int, int]]:
    """Find start and end positions of classes in source code."""
    tree = ast.parse(source_code)
    lines = source_code.split("\n")

    positions = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in class_names:
            start_line = node.lineno - 1  # 0-indexed
            end_line = node.end_lineno  # 1-indexed, so this is exclusive

            positions[node.name] = (start_line, end_line)

    return positions


def main():
    repo_root = Path(__file__).parent.parent
    gui_file = repo_root / "src" / "zebtrack" / "ui" / "gui.py"

    print(f"Updating {gui_file}...")

    with open(gui_file, encoding="utf-8") as f:
        source_code = f.read()

    lines = source_code.split("\n")

    # Find all dialog classes to remove
    dialog_classes = [
        "DiagnosticProgressDialog",
        "CalibrationDialog",
        "ManageWeightsDialog",
        "PendingVideosDialog",
        "CreateProjectDialog",
        "SingleVideoConfigDialog",
        "StartRecordingDialog",
        "MissingMetadataDialog",
        "SubjectSelectionDialog",
        "SaveROITemplateDialog",
        "TemplateDialog",
        "CenterPeripheryDialog",
        "ColorSelectionDialog",
    ]

    positions = find_class_positions(source_code, dialog_classes)

    # Sort by start line (descending) so we can remove from bottom to top
    sorted_positions = sorted(positions.items(), key=lambda x: x[1][0], reverse=True)

    # Remove classes from bottom to top (so line numbers don't shift)
    for class_name, (start, end) in sorted_positions:
        print(f"Removing {class_name} (lines {start+1}-{end})")
        # Remove the lines
        del lines[start:end]

    # Now add the import statement
    # Find where to insert (after log = structlog.get_logger())
    import_lines = [
        "",
        "# Import dialogs from separate modules",
        "from zebtrack.ui.dialogs import (",
        "    CalibrationDialog,",
        "    CenterPeripheryDialog,",
        "    ColorSelectionDialog,",
        "    CreateProjectDialog,",
        "    DiagnosticProgressDialog,",
        "    ManageWeightsDialog,",
        "    MissingMetadataDialog,",
        "    PendingVideosDialog,",
        "    SaveROITemplateDialog,",
        "    SingleVideoConfigDialog,",
        "    StartRecordingDialog,",
        "    SubjectSelectionDialog,",
        "    TemplateDialog,",
        ")",
        "",
    ]

    # Find insertion point
    for i, line in enumerate(lines):
        if "log = structlog.get_logger()" in line:
            # Insert after this line
            lines = lines[: i + 1] + import_lines + lines[i + 1 :]
            print(f"[OK] Added imports after line {i+1}")
            break

    # Write back
    updated_code = "\n".join(lines)

    with open(gui_file, "w", encoding="utf-8") as f:
        f.write(updated_code)

    print("\n[SUCCESS] gui.py updated!")
    print("\nNext: Run tests to verify no regressions")


if __name__ == "__main__":
    main()
