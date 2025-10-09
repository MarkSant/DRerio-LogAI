#!/usr/bin/env python3
"""Build wizard template distribution artifacts.

The CI pipeline calls this script to produce a distributable ZIP archive that
bundles the curated wizard templates stored under ``resources/wizard_templates``.

Running the script locally is safe and idempotent – artefacts are written to the
``dist`` directory (ignored by git).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_SOURCE = REPO_ROOT / "resources" / "wizard_templates"
OUTPUT_DIR = REPO_ROOT / "dist"
ARCHIVE_NAME = "wizard_templates.zip"
MANIFEST_NAME = "wizard_templates_manifest.json"


def build_archive(output_dir: Path) -> Path:
    """Package the curated wizard templates as a ZIP archive.

    Args:
        output_dir: Directory where the artefacts will be written.

    Returns:
        Path to the generated archive.
    """
    if not TEMPLATES_SOURCE.exists():
        raise SystemExit(
            f"Template source directory '{TEMPLATES_SOURCE}' is missing. "
            "Ensure resources are generated before building the archive."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / ARCHIVE_NAME

    template_files = sorted(TEMPLATES_SOURCE.glob("*.json"))
    if not template_files:
        raise SystemExit(
            f"No template JSON files were found in '{TEMPLATES_SOURCE}'."
        )

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for template_file in template_files:
            zf.write(template_file, arcname=template_file.name)

    manifest = {
        "archive": archive_path.name,
        "template_count": len(template_files),
        "templates": [
            {
                "filename": path.name,
                "name": json.loads(path.read_text(encoding="utf-8")).get(
                    "name", path.stem
                ),
            }
            for path in template_files
        ],
    }
    (output_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return archive_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Destination directory (defaults to dist/).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    archive_path = build_archive(args.output_dir)
    print(f"✅ Wizard templates archive generated at: {archive_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
