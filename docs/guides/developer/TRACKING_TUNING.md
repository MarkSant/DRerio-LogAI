# Tracking Parameters and Tuning Guide

This guide explains the tracking parameters available in DRerio LogAI and how to tune them for different experimental setups.

## 1. Tracker Selection

DRerio LogAI offers two tracking strategies:

### ByteTrack (Advanced)

- **Algorithm**: ByteTrack (Kalman Filter + High/Low score association).
- **Best For**: High-density scenarios, multiple animals, or videos with frequent occlusions.
- **Features**: Predicts position using motion modeling, survives short disappearances.
- **Cost**: Higher computational overhead.

### Simple Hybrid Tracker

- **Algorithm**: IoU + Euclidean Distance matching.
- **Best For**: Single animal per aquarium, high frame rates, or low-power hardware.
- **Features**: Stable ID 1 assignment, extremely fast.
- **Note**: When ByteTrack is disabled, this tracker is used automatically.

## 2. Core Parameters

### Confidence Threshold (`conf_threshold`)

- **Range**: 0.0 - 1.0 (Typical: 0.25)
- **Impact**: Minimum certainty for YOLO to report a detection.
- **Tuning**: Decrease if animals are missed; increase if noise (reflections) is detected as animals.

### NMS Threshold (`nms_threshold`)

- **Range**: 0.0 - 1.0 (Typical: 0.45)
- **Impact**: Filters overlapping boxes for the same object.
- **Tuning**: Increase if one animal has multiple boxes; decrease if two close animals are merged into one box.

## 3. ByteTrack Specifics

### Track Threshold (`track_threshold`)

- **Range**: 0.0 - 1.0 (Typical: 0.25)
- **Impact**: Minimum confidence to keep a track active.
- **Tuning**: Decrease to keep tracks of animals that become blurry or low-contrast.

### Match Threshold (`match_threshold`)

- **Range**: 0.0 - 1.0 (Typical: 0.95)
- **Impact**: Tolerância for associating a detection to an existing track.
- **Tuning**: High values (0.9+) are better for zebrafish which move very fast between frames.

### Track Buffer (`track_buffer`)

- **Range**: 10 - 1000 frames (Typical: 90)
- **Impact**: How many frames the tracker "remembers" a lost animal.
- **Tuning**: Increase for videos with intermittent lighting or temporary occlusions.

## 4. Hybrid Matching (Advanced)

### Max Center Distance (`max_center_distance`)

- **Unit**: Pixels (Typical: 400.0)
- **Impact**: Maximum distance an animal can move between processed frames to be considered the same.
- **Tuning**: Increase if IDs jump when processing every N frames (sparse processing).

### IoU Threshold (`iou_threshold`)

- **Range**: 0.0 - 1.0 (Typical: 0.05)
- **Impact**: Minimum overlap required to prefer "Box Match" over "Distance Match".
- **Tuning**: Keep low for small objects (like zebrafish) where even a small movement results in zero box overlap.

## 5. UI Exposure

As of Dec 2025, these parameters are exposed in:

1. **Wizard**: During project creation (Model Selection step).
2. **Calibration Menu**: Accessible via the gear icon or main menu for real-time adjustment and diagnostic testing.
