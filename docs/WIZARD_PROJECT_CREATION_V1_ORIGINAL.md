# 5-Step Wizard: Intelligent Project Creation System

**Status**: Detailed Specification (Not Yet Implemented)
**Created**: 2025-10-03
**Estimated Implementation Time**: 2-3 weeks
**Priority**: High - Fundamental UX improvement

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Solution Overview](#solution-overview)
3. [Step-by-Step Wizard Flow](#step-by-step-wizard-flow)
4. [Architecture Changes](#architecture-changes)
5. [Implementation Phases](#implementation-phases)
6. [Data Structures](#data-structures)
7. [Test Scenarios](#test-scenarios)
8. [Migration Strategy](#migration-strategy)
9. [Open Questions](#open-questions)

---

## Problem Statement

### Current Workflow Issues

The existing `CreateProjectDialog` has fundamental UX problems:

1. **Information Asymmetry**: System asks for 15+ configuration fields BEFORE knowing what the user actually has:
   - Experimental design (groups, days, subjects)
   - Folder organization patterns
   - Existing parquet files (arena, ROIs, trajectory)
   - Video naming conventions

2. **Wasted User Effort**: Users must manually configure design even when it's already encoded in:
   - Folder structure: `GrupoControle/Dia1/Sujeito1.mp4`
   - File names: `D1_GControle_S1.mp4`
   - Existing parquet files with zone definitions

3. **Missed Import Opportunities**: Users cannot:
   - Import zones from previous analyses
   - Selectively reprocess (keep zones, regenerate trajectory)
   - Merge zones from multiple sources

4. **Rigid Workflow**: System assumes all videos need the same processing:
   - Some videos may have complete data (skip processing)
   - Some may only need zone definition
   - Some may need full tracking from scratch

### User Expectations

Users expect the system to:
1. **Discover** what they have (folder structure, parquets, naming patterns)
2. **Detect** experimental design automatically
3. **Validate** detections with the user
4. **Adapt** configuration based on context
5. **Import** existing work when available

---

## Solution Overview

### 5-Step Wizard Architecture

Replace the monolithic `CreateProjectDialog` with a progressive disclosure wizard:

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Discovery Dialog                                   │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ What best describes your project?                     │  │
│ │ ○ Experimental Design (groups, days, subjects)        │  │
│ │ ○ Exploratory Analysis (no experimental structure)    │  │
│ │                                                        │  │
│ │ Are your videos organized in folders?                 │  │
│ │ ○ Yes - folders represent experimental structure     │  │
│ │ ○ Yes - but just for organization                    │  │
│ │ ○ No - all videos in single directory                │  │
│ │                                                        │  │
│ │ Do you have existing parquet files?                   │  │
│ │ ○ Yes - want to import zones (arena/ROIs)            │  │
│ │ ○ Yes - want to import everything                    │  │
│ │ ○ No - starting from scratch                         │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│                        [Next >]                             │
└─────────────────────────────────────────────────────────────┘

↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 2: File Selection                                      │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Select videos and folders:                            │  │
│ │                                                        │  │
│ │ [Selecionar Vídeos...]  [Selecionar Pasta...]        │  │
│ │                                                        │  │
│ │ Selected:                                             │  │
│ │ • C:\Videos\GrupoControle\                            │  │
│ │ • C:\Videos\GrupoTratamento\                          │  │
│ │ • C:\Videos\extra_video.mp4                           │  │
│ │                                                        │  │
│ │ Total: 12 videos found                                │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│                  [< Back]    [Next >]                       │
└─────────────────────────────────────────────────────────────┘

↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Automatic Detection & Validation                    │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ 🔍 Detected Experimental Design (Confidence: 95%)     │  │
│ │                                                        │  │
│ │ Folder Structure Analysis:                            │  │
│ │ ✓ Pattern: {Group}/{Day}/{Subject}.mp4               │  │
│ │   Groups: GrupoControle, GrupoTratamento              │  │
│ │   Days: Dia1, Dia2, Dia3                              │  │
│ │   Subjects: 8 per group                               │  │
│ │                                                        │  │
│ │ Parquet Files:                                        │  │
│ │ ✓ 8 videos have arena definitions                     │  │
│ │ ✓ 8 videos have ROIs (Top, Bottom)                    │  │
│ │ ⚠ 4 videos have complete trajectory data              │  │
│ │   (these will be skipped unless you choose reprocess)│  │
│ │                                                        │  │
│ │ [✓] Use detected design                               │  │
│ │ [Edit Design Manually...]                             │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│                  [< Back]    [Next >]                       │
└─────────────────────────────────────────────────────────────┘

↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Import Configuration                                │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Configure what to import for each video:             │  │
│ │                                                        │  │
│ │ Video                  Arena  ROIs  Trajectory Action │  │
│ │ ────────────────────── ───── ───── ────────── ────── │  │
│ │ GC_D1_S1.mp4            [✓]   [✓]     [ ]     Import │  │
│ │ GC_D1_S2.mp4            [✓]   [✓]     [✓]     Skip   │  │
│ │ GC_D1_S3.mp4            [ ]   [ ]     [ ]     Full   │  │
│ │ GC_D2_S1.mp4            [✓]   [ ]     [ ]     Partial│  │
│ │                                                        │  │
│ │ Import Actions:                                       │  │
│ │ • Skip: Video has complete data, no processing        │  │
│ │ • Import: Load zones, regenerate trajectory           │  │
│ │ • Partial: Import arena, define ROIs, track           │  │
│ │ • Full: Define all zones, then track                  │  │
│ │                                                        │  │
│ │ ROI Merge Strategy:                                   │  │
│ │ ○ Replace existing ROIs with imported ones            │  │
│ │ ○ Merge (keep both, rename conflicts)                │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│                  [< Back]    [Next >]                       │
└─────────────────────────────────────────────────────────────┘

↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Confirmation & Summary                              │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Project Summary:                                       │  │
│ │                                                        │  │
│ │ Name: Experimento_Canabidiol_2025                     │  │
│ │ Type: Experimental (2 groups, 3 days, 8 subjects/grp) │  │
│ │ Videos: 12 total                                       │  │
│ │                                                        │  │
│ │ Processing Plan:                                       │  │
│ │ • 4 videos: Skip (complete data exists)               │  │
│ │ • 6 videos: Import zones + track                      │  │
│ │ • 2 videos: Full processing from scratch              │  │
│ │                                                        │  │
│ │ Detection Settings:                                    │  │
│ │ • Model: YOLOv8n (OpenVINO)                           │  │
│ │ • Interval: 10 frames                                 │  │
│ │ • Animals per aquarium: 1                             │  │
│ │                                                        │  │
│ │ Project will be saved to:                             │  │
│ │ C:\Projects\Experimento_Canabidiol_2025\              │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│            [< Back]    [Create Project]                     │
└─────────────────────────────────────────────────────────────┘
```

### Key Features

1. **Progressive Disclosure**: Only show relevant options based on previous answers
2. **Automatic Detection**: Analyze folder structure, file names, and parquet files
3. **Confidence Scoring**: Show how confident the system is in its detections
4. **Validation Loop**: User can review and edit detected design
5. **Selective Import**: Per-video control over what to import
6. **Smart Defaults**: Pre-select most common options based on context

---

## Step-by-Step Wizard Flow

### Step 1: Discovery Dialog

**Purpose**: Understand user's context before showing file selection.

**UI Components**:
```python
class DiscoveryDialog(simpledialog.Dialog):
    """
    First step: Gather context about project type and existing data.

    Attributes:
        project_type: 'experimental' | 'exploratory'
        has_folder_structure: bool
        folder_meaning: 'experimental' | 'organizational' | None
        has_parquets: bool
        parquet_import_scope: 'zones' | 'all' | None
    """
```

**Questions**:

1. **Project Type**:
   - Radio buttons: `Experimental Design` vs `Exploratory Analysis`
   - Help text: "Experimental = grupos, dias, sujeitos. Exploratory = análise livre sem design."
   - Default: `Experimental` (most common)

2. **Folder Organization** (only if project_type == 'experimental'):
   - Radio buttons:
     - `Yes - folders represent experimental structure` (e.g., Grupo/Dia/)
     - `Yes - but just for organization` (arbitrary folders)
     - `No - all videos in single directory`
   - Default: `Yes - folders represent structure` (most common)

3. **Existing Parquet Files**:
   - Radio buttons:
     - `Yes - want to import zones (arena/ROIs)`
     - `Yes - want to import everything (zones + trajectory)`
     - `No - starting from scratch`
   - Help text: "Parquet files from previous analyses can be reused."
   - Default: `No` (safest assumption)

**Output Data**:
```python
{
    "project_type": "experimental",
    "has_folder_structure": True,
    "folder_meaning": "experimental",
    "has_parquets": True,
    "parquet_import_scope": "zones"
}
```

---

### Step 2: File Selection

**Purpose**: Let user select videos/folders (existing functionality, enhanced UI).

**UI Components**:
```python
class FileSelectionPanel(Frame):
    """
    Second step: Select videos and folders.

    Uses existing logic from CreateProjectDialog Phase 2.

    Enhancements:
        - Shows preview of folder structure
        - Displays video count in real-time
        - Warns if no videos found in selected folders
    """
```

**Layout**:
```
┌────────────────────────────────────────────┐
│ Select videos and folders:                 │
│                                             │
│ [Selecionar Vídeos...]  [Selecionar Pasta]│
│                                             │
│ Selected Paths:                             │
│ ┌─────────────────────────────────────────┐│
│ │ 📁 C:\Videos\GrupoControle\             ││
│ │ 📁 C:\Videos\GrupoTratamento\           ││
│ │ 📄 C:\Videos\extra_video.mp4            ││
│ └─────────────────────────────────────────┘│
│                                             │
│ 📊 Summary:                                 │
│    • 12 videos found (.mp4)                │
│    • 2 folders                              │
│    • 1 individual file                      │
│                                             │
│ [Clear Selection]                           │
└────────────────────────────────────────────┘
```

**Validation**:
- At least 1 video must be found
- Warn if folders contain no .mp4 files
- Warn if same video appears in multiple selections

**Output Data**:
```python
{
    "selected_paths": [
        "C:\\Videos\\GrupoControle\\",
        "C:\\Videos\\GrupoTratamento\\",
        "C:\\Videos\\extra_video.mp4"
    ],
    "discovered_videos": [
        "C:\\Videos\\GrupoControle\\Dia1\\Sujeito1.mp4",
        "C:\\Videos\\GrupoControle\\Dia1\\Sujeito2.mp4",
        # ... (12 total)
    ]
}
```

---

### Step 3: Automatic Detection & Validation

**Purpose**: Analyze selected videos and detect experimental design + parquet availability.

**UI Components**:
```python
class DetectionPanel(Frame):
    """
    Third step: Show detected design and parquet analysis.

    Components:
        - DesignDetector: Analyzes folder structure and filenames
        - ParquetAnalyzer: Scans for existing parquet files
        - ConfidenceDisplay: Shows detection confidence with visual indicator
        - ManualEditButton: Opens dialog to manually correct design
    """
```

**Detection Algorithms**:

#### 3.1. Folder Structure Detection

```python
class FolderStructureDetector:
    """
    Analyzes folder hierarchy to detect experimental design.

    Patterns Supported:
        - {Group}/{Day}/{Subject}.mp4
        - {Day}/{Group}/{Subject}.mp4
        - {Group}/{Subject}_{Day}.mp4
        - Custom patterns (user-defined regex)

    Confidence Scoring:
        - 100%: All videos follow same pattern, clear naming
        - 80-99%: Most videos follow pattern, some outliers
        - 50-79%: Partial pattern detected, needs validation
        - <50%: No clear pattern, suggest manual config
    """

    def detect_pattern(self, video_paths: list[str]) -> DetectionResult:
        """
        1. Build directory tree
        2. Count depth levels (1, 2, 3+)
        3. Extract unique folder names at each level
        4. Attempt to classify each level as Group/Day/Subject
        5. Calculate confidence based on:
           - Naming consistency (e.g., all start with "Grupo", "Dia")
           - Numeric patterns (D1, D2 vs Dia1, Dia2)
           - Folder count matches expected design
        """
        pass
```

**Example Detection Output**:
```python
{
    "pattern": "{Group}/{Day}/{Subject}.mp4",
    "confidence": 0.95,
    "groups": ["GrupoControle", "GrupoTratamento"],
    "days": ["Dia1", "Dia2", "Dia3"],
    "subjects_per_group": 8,
    "total_videos": 48,  # 2 groups * 3 days * 8 subjects
    "outliers": [],  # Videos that don't fit pattern
    "warnings": []
}
```

#### 3.2. Filename Pattern Detection

```python
class FilenamePatternDetector:
    """
    Analyzes filenames for experimental design encoding.

    Common Patterns:
        - D{day}_G{group}_S{subject}.mp4
        - {group}_{day}_{subject}.mp4
        - {subject}_{group}_D{day}.mp4

    Regex Templates:
        - Day: r'D?(\d+)'
        - Group: r'G(Controle|Tratamento|[A-Z])'
        - Subject: r'S(\d+)'
    """

    def detect_pattern(self, filenames: list[str]) -> DetectionResult:
        """
        1. Extract all filenames (without extension)
        2. Try each regex template
        3. For each match, extract group/day/subject
        4. Calculate confidence based on:
           - Percentage of files matching pattern
           - Consistency of extracted values
           - Logical ranges (days 1-N, subjects 1-M)
        """
        pass
```

#### 3.3. Parquet Availability Analysis

```python
class ParquetAnalyzer:
    """
    Uses enhanced scan_input_paths() from Phase 1.

    For each video, determine:
        - has_arena: bool
        - has_rois: bool
        - has_trajectory: bool
        - has_complete_data: bool
        - parquet_files: dict (paths to each type)

    Aggregate Statistics:
        - How many videos have arena?
        - How many have ROIs?
        - How many have complete data?
        - Are ROI names consistent across videos?
    """

    def analyze(self, video_paths: list[str]) -> ParquetAnalysisResult:
        """
        1. Call scan_input_paths() for all videos
        2. Aggregate results
        3. Check ROI consistency:
           - Extract all unique ROI names
           - Check if same ROIs appear in all files
           - Warn if ROI schemas differ
        """
        pass
```

**UI Layout**:
```
┌──────────────────────────────────────────────────┐
│ 🔍 Detection Results                             │
│                                                  │
│ ┌──────────────────────────────────────────────┐│
│ │ Experimental Design                          ││
│ │ Confidence: ████████░░ 85%                   ││
│ │                                              ││
│ │ Detected Pattern: {Group}/{Day}/{Subject}   ││
│ │                                              ││
│ │ Groups (2):                                  ││
│ │   • GrupoControle                            ││
│ │   • GrupoTratamento                          ││
│ │                                              ││
│ │ Days (3): Dia1, Dia2, Dia3                   ││
│ │ Subjects per Group: 8                        ││
│ │                                              ││
│ │ [✓] Use this design                          ││
│ │ [Edit Manually...]                           ││
│ └──────────────────────────────────────────────┘│
│                                                  │
│ ┌──────────────────────────────────────────────┐│
│ │ Parquet Files Found                          ││
│ │                                              ││
│ │ Arena Definitions:  12/12 videos (100%)      ││
│ │ ROI Definitions:    10/12 videos (83%)       ││
│ │ Trajectory Data:     4/12 videos (33%)       ││
│ │                                              ││
│ │ ROI Names Detected:                          ││
│ │   • Top (appears in 10 videos)               ││
│ │   • Bottom (appears in 10 videos)            ││
│ │                                              ││
│ │ ⚠ 4 videos have complete data and will      ││
│ │   be skipped unless you choose to reprocess ││
│ └──────────────────────────────────────────────┘│
│                                                  │
│ ┌──────────────────────────────────────────────┐│
│ │ ⚠ Warnings                                   ││
│ │                                              ││
│ │ • 2 videos don't match folder pattern:       ││
│ │   - extra_video.mp4                          ││
│ │   - test_recording.mp4                       ││
│ │                                              ││
│ │ These will be treated as ungrouped.          ││
│ └──────────────────────────────────────────────┘│
└──────────────────────────────────────────────────┘
```

**Manual Edit Dialog**:

If user clicks "Edit Manually", open a dialog to override detection:

```python
class ManualDesignEditor(simpledialog.Dialog):
    """
    Allows user to manually specify experimental design.

    Fields:
        - Number of groups (spinbox)
        - Group names (entry list)
        - Number of days (spinbox)
        - Number of subjects per group (spinbox)
        - Video-to-design mapping table (editable grid)
    """
```

**Output Data**:
```python
{
    "design_detected": True,
    "design_confidence": 0.85,
    "design": {
        "pattern": "{Group}/{Day}/{Subject}",
        "groups": ["GrupoControle", "GrupoTratamento"],
        "days": ["Dia1", "Dia2", "Dia3"],
        "subjects_per_group": 8
    },
    "parquet_analysis": {
        "videos_with_arena": 12,
        "videos_with_rois": 10,
        "videos_with_trajectory": 4,
        "roi_names": ["Top", "Bottom"],
        "details": [
            {
                "video": "GC_D1_S1.mp4",
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": False
            },
            # ... (one per video)
        ]
    },
    "warnings": [
        "2 videos don't match pattern: extra_video.mp4, test_recording.mp4"
    ]
}
```

---

### Step 4: Import Configuration

**Purpose**: Let user decide what to import for each video.

**UI Components**:
```python
class ImportConfigPanel(Frame):
    """
    Fourth step: Configure import strategy per video.

    Components:
        - Video table (scrollable)
        - Per-video checkboxes for arena/ROIs/trajectory
        - Action dropdown (Skip/Import/Partial/Full)
        - Bulk actions toolbar
        - ROI merge strategy selector
    """
```

**Video Table Columns**:
1. **Video Name**: Basename of video file
2. **Arena**: Checkbox (enabled if parquet exists)
3. **ROIs**: Checkbox (enabled if parquet exists)
4. **Trajectory**: Checkbox (enabled if parquet exists)
5. **Action**: Computed based on checkboxes
   - `Skip`: All 3 checked (has complete data, no processing needed)
   - `Import Zones`: Arena/ROIs checked, trajectory unchecked
   - `Partial`: Only arena checked
   - `Full`: None checked (process from scratch)

**Bulk Actions Toolbar**:
```
[Select All Arena] [Select All ROIs] [Deselect All Trajectory]
[Skip All Complete] [Import All Zones]
```

**ROI Merge Strategy**:

When importing ROIs from parquet files:
- **Replace**: Delete any manually-defined ROIs, use imported ones only
- **Merge**: Keep both, rename conflicts (e.g., `Top` → `Top_imported`)
- **Manual**: Show conflict resolution dialog for each video

**UI Layout**:
```
┌────────────────────────────────────────────────────────────┐
│ Configure Import Strategy                                  │
│                                                            │
│ Bulk Actions:                                              │
│ [Select All Arena] [Deselect All Trajectory]              │
│                                                            │
│ ┌────────────────────────────────────────────────────────┐│
│ │Video            Arena ROIs Traj  Action     Group/Day  ││
│ │──────────────── ───── ──── ──── ────────── ────────────││
│ │GC_D1_S1.mp4      [✓]  [✓]  [ ]  Import     GC / D1    ││
│ │GC_D1_S2.mp4      [✓]  [✓]  [✓]  Skip       GC / D1    ││
│ │GC_D1_S3.mp4      [ ]  [ ]  [ ]  Full       GC / D1    ││
│ │GC_D2_S1.mp4      [✓]  [ ]  [ ]  Partial    GC / D2    ││
│ │GT_D1_S1.mp4      [✓]  [✓]  [ ]  Import     GT / D1    ││
│ │...                                                      ││
│ └────────────────────────────────────────────────────────┘│
│                                                            │
│ ROI Import Strategy:                                       │
│ ○ Replace existing ROIs with imported ones                │
│ ○ Merge (keep both, rename conflicts)                     │
│ ○ Manual resolution (ask for each conflict)               │
│                                                            │
│ Summary:                                                   │
│ • 4 videos: Skip (complete data)                          │
│ • 6 videos: Import zones + track                          │
│ • 1 video: Partial import (arena only)                    │
│ • 1 video: Full processing from scratch                   │
└────────────────────────────────────────────────────────────┘
```

**Smart Defaults**:
- If video has all 3 parquets AND user said "import everything" in Step 1 → check all 3
- If video has arena+ROIs AND user said "import zones" in Step 1 → check arena+ROIs only
- If user said "starting from scratch" in Step 1 → uncheck all

**Output Data**:
```python
{
    "import_config": [
        {
            "video": "GC_D1_S1.mp4",
            "import_arena": True,
            "import_rois": True,
            "import_trajectory": False,
            "action": "import_zones"
        },
        {
            "video": "GC_D1_S2.mp4",
            "import_arena": True,
            "import_rois": True,
            "import_trajectory": True,
            "action": "skip"
        },
        # ... (one per video)
    ],
    "roi_merge_strategy": "replace"
}
```

---

### Step 5: Confirmation & Summary

**Purpose**: Show final summary before creating project.

**UI Components**:
```python
class ConfirmationPanel(Frame):
    """
    Fifth step: Final review and project creation.

    Components:
        - Project name entry (editable)
        - Project location entry + browse button
        - Read-only summary of all previous steps
        - Estimated processing time
        - Create Project button
    """
```

**UI Layout**:
```
┌──────────────────────────────────────────────┐
│ Project Summary                              │
│                                              │
│ Project Name:                                │
│ ┌──────────────────────────────────────────┐│
│ │ Experimento_Canabidiol_2025              ││
│ └──────────────────────────────────────────┘│
│                                              │
│ Location:                                    │
│ ┌──────────────────────────────────────────┐│
│ │ C:\Projects\Experimento_...   [Browse]   ││
│ └──────────────────────────────────────────┘│
│                                              │
│ ┌──────────────────────────────────────────┐│
│ │ Design:                                  ││
│ │ • Type: Experimental                     ││
│ │ • Groups: 2 (GrupoControle, GrupoTrat..) ││
│ │ • Days: 3                                ││
│ │ • Subjects per Group: 8                  ││
│ │ • Total Videos: 12                       ││
│ └──────────────────────────────────────────┘│
│                                              │
│ ┌──────────────────────────────────────────┐│
│ │ Processing Plan:                         ││
│ │ • 4 videos: Skip (complete data)         ││
│ │ • 6 videos: Import zones + track         ││
│ │ • 1 video: Partial (arena only)          ││
│ │ • 1 video: Full processing               ││
│ │                                          ││
│ │ Estimated Time: ~45 minutes              ││
│ │   (based on 8 videos to process)         ││
│ └──────────────────────────────────────────┘│
│                                              │
│ ┌──────────────────────────────────────────┐│
│ │ Detection Settings:                      ││
│ │ • Model: YOLOv8n (OpenVINO)             ││
│ │ • Analysis Interval: 10 frames           ││
│ │ • Display Interval: 10 frames            ││
│ │ • Animals per Aquarium: 1                ││
│ └──────────────────────────────────────────┘│
│                                              │
│           [< Back]    [Create Project]       │
└──────────────────────────────────────────────┘
```

**Validation**:
- Project name must not be empty
- Project location must be writable
- Warn if project folder already exists

**On Create Project**:
1. Create project directory structure
2. Call `ProjectManager.create_new_project()` with full config
3. For each video with import_arena/import_rois:
   - Call `load_zones_from_parquet()`
   - Store ZoneData in project
4. Close wizard
5. Open main application with loaded project

**Output Data** (passed to `AppController.create_new_project()`):
```python
{
    "project_path": "C:\\Projects\\Experimento_Canabidiol_2025",
    "project_type": "experimental",
    "use_openvino": True,
    "active_weight": "yolov8n",
    "video_files": [
        "C:\\Videos\\GrupoControle\\Dia1\\Sujeito1.mp4",
        # ... (all 12 videos)
    ],
    "num_groups": 2,
    "group_names": ["GrupoControle", "GrupoTratamento"],
    "experiment_days": 3,
    "subjects_per_group": 8,
    "animals_per_aquarium": 1,
    "analysis_interval_frames": 10,
    "display_interval_frames": 10,

    # NEW: Import configuration
    "import_config": [
        {
            "video": "GC_D1_S1.mp4",
            "import_arena": True,
            "import_rois": True,
            "import_trajectory": False,
            "zone_data": ZoneData(...)  # Loaded from parquet
        },
        # ... (one per video)
    ],
    "roi_merge_strategy": "replace"
}
```

---

## Architecture Changes

### New Modules

#### 1. `src/zebtrack/ui/wizard/`

New package for wizard components:

```
src/zebtrack/ui/wizard/
├── __init__.py
├── wizard_dialog.py         # Main WizardDialog class (orchestrates 5 steps)
├── discovery_step.py         # Step 1: DiscoveryDialog
├── file_selection_step.py    # Step 2: FileSelectionPanel
├── detection_step.py         # Step 3: DetectionPanel + ManualDesignEditor
├── import_config_step.py     # Step 4: ImportConfigPanel
├── confirmation_step.py      # Step 5: ConfirmationPanel
└── base.py                   # WizardStep base class
```

**WizardDialog Structure**:
```python
class WizardDialog(simpledialog.Dialog):
    """
    Main wizard orchestrator.

    Attributes:
        steps: list[WizardStep]  # 5 step instances
        current_step: int
        wizard_data: dict  # Accumulated data from all steps

    Methods:
        next_step(): Validate current step, move to next
        previous_step(): Go back, preserve data
        finish(): Call create_project with wizard_data
    """
```

**WizardStep Base Class**:
```python
class WizardStep(Frame):
    """
    Base class for wizard steps.

    Methods:
        build_ui(parent): Create UI widgets
        validate() -> bool: Check if step data is valid
        get_data() -> dict: Return step's data
        set_data(data: dict): Populate UI from data (for Back button)
        on_show(): Called when step becomes visible
        on_hide(): Called when leaving step
    """
```

#### 2. `src/zebtrack/analysis/design_detector.py`

New module for design detection:

```python
class DesignDetector:
    """
    Detects experimental design from folder structure and filenames.

    Methods:
        detect_from_folders(video_paths) -> DetectionResult
        detect_from_filenames(video_paths) -> DetectionResult
        merge_results(folder_result, filename_result) -> DetectionResult
        calculate_confidence(result) -> float
    """

class DetectionResult:
    """
    Data class for detection results.

    Attributes:
        pattern: str  # "{Group}/{Day}/{Subject}"
        groups: list[str]
        days: list[str]
        subjects_per_group: int
        confidence: float  # 0.0 to 1.0
        outliers: list[str]  # Videos that don't fit
        warnings: list[str]
    """
```

**Detection Strategy**:
1. Try folder structure detection first
2. If confidence < 0.8, try filename detection
3. If both available, merge results (use higher confidence)
4. Allow user to override with manual edit

#### 3. `src/zebtrack/analysis/parquet_analyzer.py`

New module for parquet analysis (builds on Phase 1):

```python
class ParquetAnalyzer:
    """
    Analyzes parquet file availability and consistency.

    Uses ProjectManager.scan_input_paths() from Phase 1.

    Methods:
        analyze(video_paths) -> ParquetAnalysisResult
        check_roi_consistency(video_infos) -> ROIConsistencyReport
        estimate_processing_time(import_config) -> int  # seconds
    """

class ParquetAnalysisResult:
    """
    Data class for parquet analysis.

    Attributes:
        videos_with_arena: int
        videos_with_rois: int
        videos_with_trajectory: int
        roi_names: list[str]  # All unique ROI names found
        details: list[VideoParquetInfo]  # Per-video breakdown
    """

class ROIConsistencyReport:
    """
    Reports on ROI naming consistency.

    Attributes:
        is_consistent: bool
        common_roi_names: list[str]  # ROIs present in >50% of videos
        conflicts: list[ROIConflict]
    """
```

### Modified Modules

#### 1. `src/zebtrack/core/controller.py`

**Changes**:
```python
class AppController:
    def create_new_project(self, **kwargs):
        # NEW: Handle import_config parameter
        import_config = kwargs.pop("import_config", None)
        roi_merge_strategy = kwargs.pop("roi_merge_strategy", "replace")

        # Existing: Whitelist filtering
        allowed_params = {...}
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}

        # Create project
        if self.project_manager.create_new_project(**filtered_kwargs):
            # NEW: Import zones for each video
            if import_config:
                self._import_zones_from_config(import_config, roi_merge_strategy)

            # Existing: Setup detector
            if self.setup_detector(temp_animal_method=animal_method):
                self.view._load_project_view()
                return True
        return False

    def _import_zones_from_config(self, import_config: list[dict],
                                  merge_strategy: str):
        """
        Import zones from parquet files based on wizard configuration.

        For each video in import_config:
            1. If zone_data provided, use it directly
            2. Otherwise, call load_zones_from_parquet()
            3. Store in project_data
            4. Handle ROI merge conflicts based on strategy
        """
        for video_config in import_config:
            video_path = video_config["video"]

            if video_config.get("import_arena") or video_config.get("import_rois"):
                zone_data = video_config.get("zone_data")
                if not zone_data:
                    # Load from parquet
                    video_info = self.project_manager.get_video_info(video_path)
                    zone_data = self.project_manager.load_zones_from_parquet(video_info)

                if zone_data:
                    # Store in project
                    self._apply_zones_to_video(video_path, zone_data, merge_strategy)
```

#### 2. `src/zebtrack/ui/gui.py`

**Changes**:
```python
class ApplicationGUI:
    def _create_new_project(self):
        # REPLACE: Old CreateProjectDialog
        # with: New WizardDialog

        from zebtrack.ui.wizard import WizardDialog

        dialog = WizardDialog(self.root)
        if dialog.result:
            self.controller.create_new_project(**dialog.result)

    # KEEP: Existing CreateProjectDialog as fallback/legacy
    # Rename to CreateProjectDialogLegacy
```

#### 3. `src/zebtrack/core/project_manager.py`

**Changes**:
```python
class ProjectManager:
    # EXISTING: scan_input_paths() from Phase 1 (no changes)
    # EXISTING: load_zones_from_parquet() from Phase 1 (no changes)

    # NEW: Helper methods for wizard
    def get_video_info(self, video_path: str) -> dict:
        """
        Get parquet info for a single video.
        Wrapper around scan_input_paths([video_path])[0].
        """
        results = self.scan_input_paths([video_path])
        return results[0] if results else None

    def estimate_processing_time(self, video_paths: list[str],
                                 import_config: list[dict]) -> int:
        """
        Estimate total processing time in seconds.

        Assumptions:
            - Videos to skip: 0 seconds
            - Videos with imported zones: 80% of full processing time
            - Full processing: 100% of time
            - Base time: 5 minutes per video (conservative estimate)
        """
        base_time_per_video = 300  # 5 minutes
        total_time = 0

        for config in import_config:
            if config["action"] == "skip":
                continue
            elif config["action"] == "import_zones":
                total_time += base_time_per_video * 0.8
            elif config["action"] == "partial":
                total_time += base_time_per_video * 0.9
            else:  # full
                total_time += base_time_per_video

        return int(total_time)
```

### Data Flow

```
WizardDialog (orchestrator)
    ↓
Step 1: DiscoveryDialog
    → wizard_data["discovery"] = {project_type, has_folder_structure, ...}
    ↓
Step 2: FileSelectionPanel
    → wizard_data["file_selection"] = {selected_paths, discovered_videos}
    ↓
Step 3: DetectionPanel
    → DesignDetector.detect() + ParquetAnalyzer.analyze()
    → wizard_data["detection"] = {design, parquet_analysis, warnings}
    ↓
Step 4: ImportConfigPanel
    → wizard_data["import_config"] = [{video, import_arena, ...}, ...]
    ↓
Step 5: ConfirmationPanel
    → wizard_data["project_name"] = "..."
    → wizard_data["project_path"] = "..."
    ↓
WizardDialog.finish()
    → AppController.create_new_project(**wizard_data)
        → ProjectManager.create_new_project()
        → AppController._import_zones_from_config()
```

---

## Implementation Phases

### Phase W1: Foundation (3-4 days)

**Goal**: Set up wizard infrastructure and Step 1.

**Tasks**:
1. Create `src/zebtrack/ui/wizard/` package structure
2. Implement `WizardStep` base class and `WizardDialog` orchestrator
3. Implement `DiscoveryDialog` (Step 1)
4. Add navigation buttons (Back/Next) with state management
5. Write unit tests for wizard state transitions

**Deliverables**:
- Working Step 1 (Discovery) with proper data output
- Wizard can be launched from GUI (even if incomplete)
- Tests: `tests/test_wizard_foundation.py`

**Acceptance Criteria**:
- User can answer 3 questions in Step 1
- Data is correctly stored in `wizard_data`
- Next button advances to Step 2 (placeholder for now)

---

### Phase W2: File Selection (2 days)

**Goal**: Integrate existing file/folder selection logic into Step 2.

**Tasks**:
1. Extract file selection logic from `CreateProjectDialog` (Phase 2 work)
2. Refactor into `FileSelectionPanel` (reusable component)
3. Add video count summary and folder structure preview
4. Implement validation (at least 1 video required)
5. Update tests

**Deliverables**:
- Working Step 2 with file/folder selection
- Summary shows video count and folder breakdown
- Tests: `tests/test_wizard_file_selection.py`

**Acceptance Criteria**:
- User can select files and folders
- Back button returns to Step 1 with preserved data
- Video list is correctly populated in `wizard_data`

---

### Phase W3: Design Detection (5-6 days)

**Goal**: Implement automatic design detection algorithms.

**Tasks**:
1. Create `src/zebtrack/analysis/design_detector.py`
2. Implement `FolderStructureDetector` with pattern matching
3. Implement `FilenamePatternDetector` with regex templates
4. Add confidence scoring algorithm
5. Implement `ManualDesignEditor` dialog for overrides
6. Create `DetectionPanel` UI (Step 3)
7. Integrate `ParquetAnalyzer` (uses existing `scan_input_paths()`)
8. Write comprehensive tests for detection edge cases

**Deliverables**:
- Working Step 3 with automatic detection
- Confidence scores displayed visually
- Manual edit option available
- Parquet analysis integrated
- Tests: `tests/test_design_detector.py`, `tests/test_wizard_detection.py`

**Acceptance Criteria**:
- Correctly detects {Group}/{Day}/{Subject} pattern with 90%+ confidence
- Handles flat directory structure gracefully (confidence < 50%)
- Shows parquet availability for all videos
- Manual edit allows overriding detected design

**Test Scenarios**:
```python
# test_design_detector.py
def test_detect_perfect_folder_structure():
    # GrupoControle/Dia1/Sujeito1.mp4
    # GrupoControle/Dia1/Sujeito2.mp4
    # ...
    assert result.confidence > 0.95
    assert result.groups == ["GrupoControle", "GrupoTratamento"]

def test_detect_filename_pattern():
    # Flat directory with D1_GC_S1.mp4, D1_GC_S2.mp4, ...
    assert result.confidence > 0.85
    assert result.pattern == "D{day}_G{group}_S{subject}"

def test_detect_no_pattern():
    # Random filenames: video1.mp4, test.mp4, ...
    assert result.confidence < 0.3
    assert result.warnings == ["No clear pattern detected"]
```

---

### Phase W4: Import Configuration (3-4 days)

**Goal**: Implement per-video import strategy configuration.

**Tasks**:
1. Create `ImportConfigPanel` with video table
2. Implement checkbox logic (arena/ROIs/trajectory)
3. Auto-compute action based on checkboxes
4. Add bulk actions toolbar
5. Implement ROI merge strategy selector
6. Add smart defaults based on Step 1 choices
7. Write tests for import logic

**Deliverables**:
- Working Step 4 with video table
- Checkboxes correctly enabled/disabled based on parquet availability
- Bulk actions work correctly
- Tests: `tests/test_wizard_import_config.py`

**Acceptance Criteria**:
- Videos with parquets show checked boxes by default
- Action column updates when checkboxes change
- Bulk "Skip All Complete" correctly checks all 3 boxes for videos with complete data
- ROI merge strategy is stored in `wizard_data`

---

### Phase W5: Confirmation & Integration (3-4 days)

**Goal**: Implement final confirmation and integrate with existing project creation.

**Tasks**:
1. Create `ConfirmationPanel` (Step 5) with summary display
2. Implement project name/location selection
3. Add processing time estimation
4. Modify `AppController.create_new_project()` to handle `import_config`
5. Implement `_import_zones_from_config()` method
6. Add `ProjectManager.estimate_processing_time()`
7. Write end-to-end integration tests

**Deliverables**:
- Working Step 5 with all data summarized
- Create Project button calls controller with full config
- Zones are imported from parquet files
- Tests: `tests/test_wizard_integration.py`

**Acceptance Criteria**:
- Summary shows all wizard choices correctly
- Project is created with correct structure
- Videos with `import_arena=True` have arena loaded from parquet
- Videos with `import_rois=True` have ROIs loaded with correct names

**Integration Test Scenario**:
```python
def test_wizard_end_to_end_with_parquet_import():
    """
    Simulates full wizard flow:
    1. Answer discovery questions (experimental, folder structure, import zones)
    2. Select test folder with parquet files
    3. Verify detection (should detect 2 groups, 3 days)
    4. Configure import (import arena+ROIs for 6 videos)
    5. Confirm and create project
    6. Verify project has zones loaded from parquet
    """
    # Create test data
    test_folder = create_test_videos_with_parquets()

    # Launch wizard
    wizard = WizardDialog(root)

    # Step 1
    wizard.steps[0].set_project_type("experimental")
    wizard.steps[0].set_folder_structure("experimental")
    wizard.steps[0].set_parquet_import("zones")
    wizard.next_step()

    # Step 2
    wizard.steps[1].add_folder(test_folder)
    assert len(wizard.steps[1].discovered_videos) == 12
    wizard.next_step()

    # Step 3 (auto-detection)
    detection = wizard.steps[2].get_detection_result()
    assert detection["confidence"] > 0.9
    assert len(detection["groups"]) == 2
    wizard.next_step()

    # Step 4 (import config)
    # Verify smart defaults (arena+ROIs checked, trajectory unchecked)
    config = wizard.steps[3].get_import_config()
    assert sum(1 for c in config if c["import_arena"]) == 12
    assert sum(1 for c in config if c["import_rois"]) == 12
    wizard.next_step()

    # Step 5 (confirm)
    wizard.steps[4].set_project_name("Test_Project")
    wizard.finish()

    # Verify project created
    pm = ProjectManager()
    pm.load_project(wizard.result["project_path"])

    # Check that zones were imported
    video_data = pm.project_data["videos"][0]
    assert video_data["zone_data"] is not None
    assert len(video_data["zone_data"].polygon) == 4  # Rectangle
    assert len(video_data["zone_data"].roi_names) == 2  # Top, Bottom
```

---

### Phase W6: Polish & Documentation (2-3 days)

**Goal**: Improve UX, add help text, update documentation.

**Tasks**:
1. Add tooltips and help icons to all wizard steps
2. Improve visual design (colors, spacing, fonts)
3. Add progress indicator (Step 1 of 5, Step 2 of 5, ...)
4. Handle edge cases (empty folders, corrupted parquets, etc.)
5. Update `docs/PROJECT_WORKFLOW.md` with wizard documentation
6. Create user guide with screenshots
7. Record demo video

**Deliverables**:
- Polished wizard UI with help text
- Updated documentation
- User guide with examples
- Demo video showing wizard flow

**Acceptance Criteria**:
- All edge cases handled gracefully with user-friendly error messages
- Tooltips explain each option clearly
- Progress indicator shows current step
- Documentation includes screenshots of each step

---

### Phase W7: Migration & Rollout (1-2 days)

**Goal**: Deploy wizard and provide migration path from old dialog.

**Tasks**:
1. Add feature flag `use_wizard_dialog` to `config.yaml`
2. Implement toggle in preferences/settings
3. Keep old `CreateProjectDialog` as fallback
4. Add banner: "New wizard available! [Try it] [Learn more]"
5. Monitor for bugs in production
6. Prepare rollback plan

**Deliverables**:
- Feature flag to enable/disable wizard
- Both old and new dialogs available
- Migration guide for users

**Acceptance Criteria**:
- Users can switch between old and new dialog
- Default is wizard (unless feature flag disabled)
- No breaking changes to existing projects

---

### Timeline Summary

| Phase | Duration | Cumulative |
|-------|----------|------------|
| W1: Foundation | 3-4 days | 4 days |
| W2: File Selection | 2 days | 6 days |
| W3: Design Detection | 5-6 days | 12 days |
| W4: Import Config | 3-4 days | 16 days |
| W5: Confirmation | 3-4 days | 20 days |
| W6: Polish | 2-3 days | 23 days |
| W7: Migration | 1-2 days | 25 days |

**Total: ~5 weeks** (accounting for testing, bug fixes, and iteration)

---

## Data Structures

### WizardData (accumulated across all steps)

```python
{
    # Step 1: Discovery
    "discovery": {
        "project_type": "experimental",  # or "exploratory"
        "has_folder_structure": True,
        "folder_meaning": "experimental",  # or "organizational", None
        "has_parquets": True,
        "parquet_import_scope": "zones"  # or "all", None
    },

    # Step 2: File Selection
    "file_selection": {
        "selected_paths": [
            "C:\\Videos\\GrupoControle\\",
            "C:\\Videos\\GrupoTratamento\\"
        ],
        "discovered_videos": [
            "C:\\Videos\\GrupoControle\\Dia1\\Sujeito1.mp4",
            # ... (12 total)
        ]
    },

    # Step 3: Detection
    "detection": {
        "design_detected": True,
        "design_confidence": 0.85,
        "design": {
            "pattern": "{Group}/{Day}/{Subject}",
            "groups": ["GrupoControle", "GrupoTratamento"],
            "days": ["Dia1", "Dia2", "Dia3"],
            "subjects_per_group": 8
        },
        "parquet_analysis": {
            "videos_with_arena": 12,
            "videos_with_rois": 10,
            "videos_with_trajectory": 4,
            "roi_names": ["Top", "Bottom"],
            "details": [
                {
                    "video": "GC_D1_S1.mp4",
                    "video_path": "C:\\Videos\\GrupoControle\\Dia1\\Sujeito1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": False,
                    "parquet_files": {
                        "arena": "C:\\Videos\\...\\1_ProcessingArea_GC_D1_S1.parquet",
                        "rois": "C:\\Videos\\...\\2_AreasOfInterest_GC_D1_S1.parquet",
                        "trajectory": None
                    }
                },
                # ... (one per video)
            ]
        },
        "warnings": [
            "2 videos don't match pattern: extra_video.mp4, test.mp4"
        ]
    },

    # Step 4: Import Configuration
    "import_config": [
        {
            "video": "GC_D1_S1.mp4",
            "video_path": "C:\\Videos\\GrupoControle\\Dia1\\Sujeito1.mp4",
            "import_arena": True,
            "import_rois": True,
            "import_trajectory": False,
            "action": "import_zones",  # or "skip", "partial", "full"
            "zone_data": None  # Will be loaded when needed
        },
        # ... (one per video)
    ],
    "roi_merge_strategy": "replace",  # or "merge", "manual"

    # Step 5: Confirmation
    "project_name": "Experimento_Canabidiol_2025",
    "project_path": "C:\\Projects\\Experimento_Canabidiol_2025",

    # Additional config (from existing CreateProjectDialog)
    "use_openvino": True,
    "active_weight": "yolov8n",
    "animals_per_aquarium": 1,
    "analysis_interval_frames": 10,
    "display_interval_frames": 10,

    # Computed from detection
    "num_groups": 2,
    "group_names": ["GrupoControle", "GrupoTratamento"],
    "experiment_days": 3,
    "subjects_per_group": 8,
    "video_files": [
        "C:\\Videos\\GrupoControle\\Dia1\\Sujeito1.mp4",
        # ... (all discovered videos)
    ]
}
```

### DetectionResult (from DesignDetector)

```python
@dataclass
class DetectionResult:
    """Result from experimental design detection."""

    pattern: str  # "{Group}/{Day}/{Subject}" or custom regex
    confidence: float  # 0.0 to 1.0

    # Detected design components
    groups: list[str]
    days: list[str]
    subjects_per_group: int

    # Quality metrics
    videos_matched: int
    videos_total: int
    outliers: list[str]  # Videos that don't fit pattern
    warnings: list[str]

    # Detailed mapping
    video_to_design: dict[str, dict]
    # Example: {
    #   "GC_D1_S1.mp4": {"group": "GrupoControle", "day": "Dia1", "subject": 1},
    #   ...
    # }
```

### ParquetAnalysisResult (from ParquetAnalyzer)

```python
@dataclass
class ParquetAnalysisResult:
    """Result from parquet availability analysis."""

    videos_with_arena: int
    videos_with_rois: int
    videos_with_trajectory: int
    videos_with_complete_data: int

    roi_names: list[str]  # All unique ROI names found
    roi_consistency: ROIConsistencyReport

    details: list[VideoParquetInfo]
    # One VideoParquetInfo per video (from scan_input_paths)

@dataclass
class ROIConsistencyReport:
    """Reports on ROI naming consistency across videos."""

    is_consistent: bool  # True if all videos have same ROI names
    common_roi_names: list[str]  # ROIs present in >50% of videos
    conflicts: list[dict]
    # Example conflicts:
    # [
    #   {"video": "GC_D1_S1.mp4", "roi_names": ["Top", "Bottom"]},
    #   {"video": "GC_D2_S1.mp4", "roi_names": ["Top", "Center", "Bottom"]}
    # ]
```

---

## Test Scenarios

### Manual Test Scenarios (for QA)

#### Scenario 1: Perfect Experimental Design
- **Setup**: Create folder structure:
  ```
  TestVideos/
    GrupoControle/
      Dia1/
        Sujeito1.mp4, Sujeito2.mp4, ...
      Dia2/
        Sujeito1.mp4, Sujeito2.mp4, ...
    GrupoTratamento/
      Dia1/
        Sujeito1.mp4, Sujeito2.mp4, ...
      Dia2/
        Sujeito1.mp4, Sujeito2.mp4, ...
  ```
- **Expected**:
  - Step 3 detects pattern with 95%+ confidence
  - Shows 2 groups, 2 days, X subjects per group
  - No warnings

#### Scenario 2: Filename-Based Design (Flat Directory)
- **Setup**: Single folder with files:
  ```
  D1_GC_S1.mp4, D1_GC_S2.mp4, ..., D3_GT_S8.mp4
  ```
- **Expected**:
  - Step 3 detects pattern `D{day}_G{group}_S{subject}`
  - Shows 2 groups, 3 days, 8 subjects
  - Confidence 85%+

#### Scenario 3: Mixed (Folders + Outliers)
- **Setup**: Folders like Scenario 1 + 2 extra videos in root
- **Expected**:
  - Step 3 detects main pattern
  - Warns about 2 outlier videos
  - User can still proceed

#### Scenario 4: Existing Parquet Files (Import Zones)
- **Setup**: Use `generate_test_parquets.py` Scenario 5 (mixed states)
- **Expected**:
  - Step 3 shows parquet availability (12 arena, 10 ROIs, 4 trajectory)
  - Step 4 defaults to importing arena+ROIs for videos that have them
  - Videos with complete data default to "Skip" action

#### Scenario 5: No Pattern (Exploratory)
- **Setup**: Random video names in single folder
- **Expected**:
  - Step 3 shows "No pattern detected" (confidence <30%)
  - User can proceed with exploratory project
  - No experimental design fields required

#### Scenario 6: Corrupted Parquet (Invalid Schema)
- **Setup**: Use `generate_test_parquets.py` Scenario 7 (invalid ROI schema)
- **Expected**:
  - Step 3 detects arena but flags ROI as invalid
  - Warning: "ROI file for video_invalido.mp4 has invalid schema"
  - User can still import arena, skip ROI

#### Scenario 7: Back Navigation Preserves Data
- **Setup**: Complete wizard through Step 4, then click Back repeatedly
- **Expected**:
  - Each step shows previously entered data
  - File selection preserved
  - Import checkboxes preserved
  - No data loss

#### Scenario 8: Bulk Actions
- **Setup**: Wizard with 12 videos (6 have parquets, 6 don't)
- **Expected**:
  - Click "Select All Arena" → checks all available
  - Click "Deselect All Trajectory" → unchecks all
  - Click "Skip All Complete" → finds videos with all 3 parquets, checks all boxes

---

### Automated Test Coverage

#### Unit Tests

```python
# tests/test_design_detector.py
def test_detect_folder_structure_2_groups_3_days():
    """Test perfect folder structure detection."""

def test_detect_filename_pattern_standard():
    """Test D{day}_G{group}_S{subject} pattern."""

def test_confidence_scoring_perfect():
    """Confidence = 1.0 when all videos match."""

def test_confidence_scoring_with_outliers():
    """Confidence decreases with outliers."""

def test_no_pattern_detected():
    """Returns low confidence for random filenames."""

# tests/test_parquet_analyzer.py
def test_analyze_all_videos_have_arena():
    """All videos have arena parquet."""

def test_analyze_mixed_parquet_availability():
    """Some videos have arena, some ROIs, some trajectory."""

def test_roi_consistency_all_same():
    """All videos have identical ROI names."""

def test_roi_consistency_conflicts():
    """Videos have different ROI names."""

# tests/test_wizard_foundation.py
def test_wizard_navigation_forward():
    """Next button advances through steps."""

def test_wizard_navigation_backward():
    """Back button returns to previous step."""

def test_wizard_data_accumulation():
    """Data from each step is preserved in wizard_data."""

def test_step_validation():
    """Cannot advance if current step is invalid."""
```

#### Integration Tests

```python
# tests/test_wizard_integration.py
def test_wizard_end_to_end_experimental():
    """Full wizard flow for experimental project."""

def test_wizard_end_to_end_exploratory():
    """Full wizard flow for exploratory project."""

def test_wizard_with_parquet_import():
    """Wizard imports zones from parquet files."""

def test_wizard_creates_valid_project():
    """Created project can be loaded and used."""

def test_wizard_back_navigation_preserves_data():
    """Back button doesn't lose data."""
```

---

## Migration Strategy

### Coexistence Period

For first 2-3 months:
1. **Default**: New wizard is shown
2. **Opt-out**: Settings → "Use legacy project creation dialog"
3. **A/B Testing**: Track usage metrics (completion rate, time spent, errors)

### Feature Flag

```yaml
# config.yaml
ui:
  use_wizard_dialog: true  # Set to false to use legacy dialog
  wizard_show_intro_banner: true  # Show "New wizard!" banner
```

### User Communication

**In-app banner** (first time user creates project after update):
```
┌────────────────────────────────────────────────────┐
│ 🎉 New: Intelligent Project Creation Wizard!      │
│                                                    │
│ • Automatically detects experimental design        │
│ • Imports zones from existing parquet files        │
│ • Selective reprocessing (keep zones, rerun track)│
│                                                    │
│          [Try New Wizard]    [Use Old Dialog]     │
│                                                    │
│ You can always change this in Settings.           │
└────────────────────────────────────────────────────┘
```

### Rollback Plan

If critical bugs found:
1. Set `use_wizard_dialog: false` in default config
2. Push hotfix update
3. Fix bugs in wizard
4. Re-enable in next version

### Data Compatibility

- Projects created with wizard are **identical** to legacy dialog projects
- `project_data` schema unchanged (only adds optional `import_config` metadata)
- No migration needed for existing projects

---

## Open Questions

### 1. Design Detection Accuracy

**Question**: What if detection confidence is medium (60-70%)? Should we:
- Show detected design and ask for confirmation?
- Show "Low confidence" warning and suggest manual edit?
- Skip detection and go straight to manual entry?

**Proposed Solution**:
- Confidence ≥80%: Auto-populate, allow edit
- Confidence 50-79%: Show warning, require user validation
- Confidence <50%: Skip auto-detection, manual entry only

---

### 2. ROI Merge Conflicts

**Question**: If importing ROIs with names that conflict with manually-defined ones:
- Replace all (lose manual work)?
- Merge and rename (e.g., `Top` → `Top_imported`)?
- Show conflict resolution dialog per video?

**Proposed Solution**:
- Default: Replace (safest for most users)
- Advanced: Merge with rename
- Power users: Manual resolution dialog

---

### 3. Partial Experimental Design

**Question**: What if only 50% of videos fit the pattern? Should we:
- Apply design to matching videos, treat rest as ungrouped?
- Force user to manually assign group/day/subject for outliers?
- Create two separate projects (one experimental, one exploratory)?

**Proposed Solution**:
- Apply design to matching videos
- Outliers go into special group: "Ungrouped"
- User can manually reassign outliers in Step 4

---

### 4. Performance with Large Projects

**Question**: What if user selects 500 videos across 50 folders?
- Detection might take 10-30 seconds
- Parquet analysis could take minutes

**Proposed Solution**:
- Show progress bar during detection
- Run detection in background thread
- Allow user to cancel if taking too long
- Cache detection results (reuse if user clicks Back)

---

### 5. Custom Pattern Support

**Question**: Should we support user-defined regex patterns for design detection?

**Proposed Solution** (Future Enhancement):
- v1.0: Support 3-4 built-in patterns only
- v1.1: Add "Custom Pattern" option with regex builder
- v2.0: Learn patterns from user corrections (ML-based)

---

## Next Steps (Implementation Kickoff)

### Before Starting Implementation

1. **Review this document** with stakeholders
2. **Prioritize open questions** and make decisions
3. **Create GitHub issues** for each phase (W1-W7)
4. **Set up project board** with columns: Backlog, In Progress, Review, Done
5. **Create feature branch**: `feature/wizard-project-creation`

### Phase W1 Kickoff Checklist

- [ ] Create `src/zebtrack/ui/wizard/` package
- [ ] Implement `WizardStep` base class
- [ ] Implement `WizardDialog` orchestrator (with dummy steps)
- [ ] Implement `DiscoveryDialog` (Step 1)
- [ ] Write tests for Step 1
- [ ] Manual test: Launch wizard from GUI, complete Step 1
- [ ] Commit: "feat(wizard): implement foundation and Step 1 (Discovery)"

---

## Appendix: Design Mockups

### Step 3: Detection Panel (Detailed View)

```
┌────────────────────────────────────────────────────────────┐
│ 🔍 Automatic Detection Results                             │
│                                                            │
│ ┌────────────────────────────────────────────────────────┐│
│ │ Experimental Design                                    ││
│ │                                                        ││
│ │ Confidence: ████████░░ 85%  [What does this mean?]    ││
│ │                                                        ││
│ │ Detection Method:                                      ││
│ │ • Folder Structure ✓ (90% confidence)                  ││
│ │   Pattern: {Group}/{Day}/{Subject}.mp4                ││
│ │   Detected: 2 groups, 3 days, 8 subjects/group        ││
│ │                                                        ││
│ │ Groups (2):                                            ││
│ │   🟦 GrupoControle     (24 videos)                     ││
│ │   🟩 GrupoTratamento   (24 videos)                     ││
│ │                                                        ││
│ │ Days (3): Dia1, Dia2, Dia3                             ││
│ │ Subjects per Group: 8                                  ││
│ │                                                        ││
│ │ Total Videos: 48                                       ││
│ │ Videos Matching Pattern: 46 (96%)                      ││
│ │                                                        ││
│ │ [✓] Use detected design                                ││
│ │ [Edit Design Manually...]                              ││
│ │                                                        ││
│ │ Video-to-Design Mapping: [Show Details ▼]             ││
│ └────────────────────────────────────────────────────────┘│
│                                                            │
│ ┌────────────────────────────────────────────────────────┐│
│ │ Parquet Files Analysis                                 ││
│ │                                                        ││
│ │ Arena Definitions:    48/48 videos (100%) ✓           ││
│ │ ROI Definitions:      46/48 videos (96%)  ⚠           ││
│ │ Trajectory Data:      12/48 videos (25%)              ││
│ │ Complete Data:        12/48 videos (25%)              ││
│ │                                                        ││
│ │ ROI Analysis:                                          ││
│ │ ┌──────────────────────────────────────────────────┐  ││
│ │ │ ROI Name     Videos  Consistency                  │  ││
│ │ │ ─────────── ─────── ───────────────────────────── │  ││
│ │ │ Top          46/46   ✓ Consistent                 │  ││
│ │ │ Bottom       46/46   ✓ Consistent                 │  ││
│ │ │ Center        2/46   ⚠ Only in 2 videos           │  ││
│ │ └──────────────────────────────────────────────────┘  ││
│ │                                                        ││
│ │ ℹ Most videos have 2 ROIs (Top, Bottom).              ││
│ │   2 videos have an additional "Center" ROI.           ││
│ │                                                        ││
│ │ [Show Per-Video Breakdown...]                          ││
│ └────────────────────────────────────────────────────────┘│
│                                                            │
│ ┌────────────────────────────────────────────────────────┐│
│ │ ⚠ Warnings (2)                                         ││
│ │                                                        ││
│ │ 1. 2 videos don't match folder pattern:                ││
│ │    • extra_video.mp4 (in root directory)              ││
│ │    • test_recording.mp4 (in root directory)           ││
│ │    → These will be assigned to "Ungrouped"            ││
│ │                                                        ││
│ │ 2. ROI names inconsistent for 2 videos:                ││
│ │    • GC_D1_S1.mp4 has extra "Center" ROI              ││
│ │    • GC_D2_S1.mp4 has extra "Center" ROI              ││
│ │    → You can choose to ignore or merge these in Step 4││
│ └────────────────────────────────────────────────────────┘│
│                                                            │
│                      [< Back]    [Next >]                  │
└────────────────────────────────────────────────────────────┘
```

---

**End of Specification**

This document serves as the complete blueprint for implementing the 5-Step Wizard project creation system. Implementation should proceed phase by phase (W1 through W7) with rigorous testing at each stage.
