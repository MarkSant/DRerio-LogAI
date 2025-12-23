# Multi-Aquarium Workflow Analysis & Gap Report

**Date:** December 2025
**Topic:** Subject Definition in Multi-Aquarium Projects

## 1. Current Workflow Overview

The current workflow for processing video files containing multiple aquariums (e.g., side-by-side tanks) relies on a combination of Project Wizard configuration and automated detection, but currently lacks a specific step for assigning distinct metadata (Group/Subject) to each detected aquarium.

### Step 1: Project Creation (Wizard)
*   **Experimental Design**: The user defines the *total* pool of subjects and groups (e.g., "Group A", "Group B", "10 animals per group").
*   **Calibration**: The user specifies `Number of Aquariums per Video` = 2.
*   **Result**: The project metadata knows there are 2 aquariums per video frame, and it knows the list of available groups.

### Step 2: Automated Detection
*   **Mechanism**: `ProcessingCoordinator` checks `num_aquariums` setting.
*   **Action**: If > 1, it calls `AquariumDetector.detect_multiple_aquariums()`.
*   **Outcome**: Successfully detects 2 polygons (Zone 0 and Zone 1).
*   **Data Structure**: A `MultiAquariumZoneData` object is created and saved. Importantly, the `AquariumData` objects inside it are initialized with **empty** metadata:
    *   `group = ""`
    *   `subject_id = ""`
    *   `day = 0`

### Step 3: Analysis & Output
*   **Processing**: `ProcessingCoordinator` iterates through the detected aquariums.
*   **Output Generation**: It generates result folders. Because metadata is empty, it bypasses the hierarchical folder structure (`Group/Day/Subject`) and instead creates flat folders:
    *   `{video_name}_results/aquarium_0`
    *   `{video_name}_results/aquarium_1`

## 2. Identified Gap: Subject Assignment

A mechanism exists in the codebase codebase (`AquariumAssignmentDialog.py`) to bridge the gap between "Detection" and "Analysis" by asking the user to map specific aquariums to specific subjects/groups, but it is **not currently connected**.

### Missing Components
1.  **Event Trigger**: The event `ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG` is defined in the system map but is never published by `ZoneControls` or `CanvasManager` after detection.
2.  **Dialog Usage**: The `AquariumAssignmentDialog`, which allows selecting "Aquarium 1 = Group Control, Subject S01" and "Aquarium 2 = Group Treatment, Subject S02", is effectively orphaned code.

### Impact
*   **Organization**: Output files for multi-aquarium videos are not organized into the standard "Experimental Design" hierarchy.
*   **Analysis**: Group-based statistical analysis may fail to distinguish between the two animals in the same video unless manually corrected downstream.

## 3. Recommended Adaptation

To fully support the workflow, the following adaptation is required:

1.  **Hook up the Dialog**: Modify `CanvasManager.on_multi_auto_detect_success` (or the corresponding `EventDispatcher` handler) to trigger the `AquariumAssignmentDialog` immediately after 2 zones are detected and confirmed.
2.  **Persist Metadata**: Save the user's selection (Group/Subject for each aquarium) into the `MultiAquariumZoneData` object.
3.  **Update Processing**: Ensure `ProcessingCoordinator` reads this metadata from `MultiAquariumZoneData` to correctly resolve the hierarchical output directories using `ProjectManager.resolve_multi_aquarium_results_directories`.
