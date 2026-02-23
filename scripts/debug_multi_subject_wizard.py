"""
Debug script to diagnose multi-subject wizard detection issues.

This script adds temporary enhanced logging to track the complete flow
of multi-subject video data from wizard detection to project structure.

Usage:
    poetry run python scripts/debug_multi_subject_wizard.py

Then run the wizard with your multi-aquarium video files and check the logs.
"""

import sys
from pathlib import Path
from typing import Any, cast

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog

log = structlog.get_logger()


def patch_detection_step():
    """Patch detection_step to add enhanced logging."""
    from zebtrack.ui.wizard import detection_step

    original_pattern_custom_regex = detection_step.DetectionStep._pattern_custom_regex

    def patched_pattern_custom_regex(self, paths, patterns):
        """Patched version with enhanced logging."""
        result = original_pattern_custom_regex(self, paths, patterns)

        if result and result.get("subject_mappings"):
            sm = result["subject_mappings"]
            log.warning(
                "🔍 PATCH: detection_step._pattern_custom_regex completed",
                total_files=len(paths),
                subject_mappings_count=len(sm),
                multi_subject_files=[
                    {
                        "file": Path(k).name,
                        "subjects": len(v),
                        "entries": v,
                    }
                    for k, v in sm.items()
                    if len(v) > 1
                ],
            )
        else:
            log.warning(
                "⚠️ PATCH: detection_step._pattern_custom_regex NO subject_mappings!",
                has_result=bool(result),
                result_keys=list(result.keys()) if result else [],
            )

        return result

    attr_name = "_pattern_custom_regex"
    detection_step_class = cast(type[Any], detection_step.DetectionStep)
    type.__setattr__(detection_step_class, attr_name, patched_pattern_custom_regex)
    log.info("✅ Patched detection_step._pattern_custom_regex")


def patch_project_workflow_service():
    """Patch project_workflow_service to add enhanced logging."""
    from zebtrack.core.project import project_workflow_service

    original_enrich = (
        project_workflow_service.ProjectWorkflowService._enrich_videos_with_design_metadata
    )

    def patched_enrich(
        self, scanned_videos, detected_design, custom_patterns=None, group_display_names=None
    ):
        """Patched version with enhanced logging."""
        log.warning(
            "🔍 PATCH: _enrich_videos_with_design_metadata called",
            scanned_videos_count=len(scanned_videos),
            has_detected_design=bool(detected_design),
            detected_design_keys=list(detected_design.keys()) if detected_design else [],
            has_subject_mappings=bool(detected_design and detected_design.get("subject_mappings")),
            subject_mappings_count=len(detected_design.get("subject_mappings", {}))
            if detected_design
            else 0,
        )

        if detected_design and detected_design.get("subject_mappings"):
            sm = detected_design["subject_mappings"]
            log.warning(
                "🔍 PATCH: subject_mappings details",
                sample_paths=[str(k) for k in list(sm.keys())[:3]],
                path_formats={
                    "has_backslashes": any("\\" in k for k in sm.keys()),
                    "has_forward_slashes": any("/" in k for k in sm.keys()),
                },
            )

        result = original_enrich(
            self, scanned_videos, detected_design, custom_patterns, group_display_names
        )

        # Check result
        multi_subject_videos = [
            {
                "path": Path(v.get("path", "")).name,
                "is_multi_subject": v.get("metadata", {}).get("is_multi_subject", False),
                "subject_entries_count": len(v.get("metadata", {}).get("subject_entries", [])),
                "subject_entries": v.get("metadata", {}).get("subject_entries", []),
            }
            for v in result
            if v.get("metadata", {}).get("is_multi_subject")
        ]

        log.warning(
            "🔍 PATCH: _enrich_videos_with_design_metadata completed",
            result_count=len(result),
            multi_subject_videos_count=len(multi_subject_videos),
            multi_subject_videos=multi_subject_videos,
        )

        return result

    attr_name = "_enrich_videos_with_design_metadata"
    workflow_class = cast(type[Any], project_workflow_service.ProjectWorkflowService)
    type.__setattr__(workflow_class, attr_name, patched_enrich)
    log.info("✅ Patched ProjectWorkflowService._enrich_videos_with_design_metadata")


def patch_validation_manager():
    """Patch validation_manager to add enhanced logging."""
    from zebtrack.ui.components import validation_manager

    validation_manager_class = cast(Any, validation_manager.ValidationManager)
    original_build = validation_manager_class._build_video_hierarchy

    def patched_build(self, videos, search_text=""):
        """Patched version with enhanced logging."""
        log.warning(
            "🔍 PATCH: _build_video_hierarchy called",
            total_videos=len(videos),
            multi_subject_videos=[
                {
                    "path": Path(v.get("path", "")).name,
                    "is_multi_subject": v.get("metadata", {}).get("is_multi_subject", False),
                    "subject_entries_count": len(v.get("metadata", {}).get("subject_entries", [])),
                }
                for v in videos
                if v.get("metadata", {}).get("is_multi_subject")
            ],
        )

        result = original_build(self, videos, search_text)

        # Count total entries in hierarchy
        total_entries = 0
        for _group_id, group_data in result.items():
            for _day_id, day_data in group_data.get("days", {}).items():
                total_entries += len(day_data.get("videos", []))

        log.warning(
            "🔍 PATCH: _build_video_hierarchy completed",
            groups_count=len(result),
            total_tree_entries=total_entries,
        )

        return result

    validation_manager_class._build_video_hierarchy = patched_build
    log.info("✅ Patched ValidationManager._build_video_hierarchy")


def main():
    """Apply all patches and run the app."""
    log.warning("=" * 80)
    log.warning("🚨 DIAGNOSTIC MODE: Multi-Subject Wizard Debug 🚨")
    log.warning("=" * 80)
    log.warning("")
    log.warning("This script patches the wizard to add detailed logging.")
    log.warning("Follow these steps:")
    log.warning("")
    log.warning("1. Run the wizard and create a multi-aquarium project")
    log.warning("2. Use custom regex that detects 2 subjects per file")
    log.warning("   Example: G1_D1_S1--G1_D1_S2.mp4")
    log.warning("   Pattern: (?P<group>G\\d+)_(?P<day>D\\d+)_(?P<subject>S\\d+)")
    log.warning("3. Complete the wizard")
    log.warning("4. Check the logs for 🔍 PATCH messages")
    log.warning("")
    log.warning("=" * 80)

    # Apply patches
    patch_detection_step()
    patch_project_workflow_service()
    patch_validation_manager()

    log.warning("")
    log.warning("✅ All patches applied! Starting application...")
    log.warning("")

    # Import and run the application
    from zebtrack.__main__ import main as app_main

    app_main()


if __name__ == "__main__":
    main()
