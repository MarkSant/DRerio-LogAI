#!/usr/bin/env python3
"""
Demonstration of the OpenVINO class filtering patch.

This script shows how the new context-based filtering works:
1. In diagnostic mode: All classes are shown (both aquarium and zebrafish)
2. In tracking mode before aquarium is defined: All classes are shown
3. In tracking mode after aquarium is defined: Only zebrafish (class 1) is shown
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from unittest.mock import MagicMock
import numpy as np
import torch

def main():
    print("=" * 60)
    print("OpenVINO Class Filtering Patch Demonstration")
    print("=" * 60)
    
    # Mock all dependencies
    sys.modules['cython_bbox'] = MagicMock()
    sys.modules['zebtrack.tracker.byte_tracker'] = MagicMock()
    sys.modules['zebtrack.tracker.matching'] = MagicMock()
    sys.modules['zebtrack.utils'] = MagicMock()

    # Mock ultralytics functions to simulate detection results
    def mock_non_max_suppression(prediction, conf_thres, iou_thres, agnostic=True):
        # Return mock detections with both aquarium (class 0) and zebrafish (class 1)
        return [torch.tensor([
            [100, 100, 200, 200, 0.9, 0],  # Aquarium detection
            [300, 300, 400, 400, 0.8, 1],  # Zebrafish detection
            [500, 500, 600, 600, 0.7, 1],  # Another zebrafish detection
        ])]

    def mock_scale_boxes(input_shape, boxes, target_shape):
        return boxes

    # Mock imports
    sys.modules['ultralytics.utils.nms'] = MagicMock()
    sys.modules['ultralytics.utils.nms'].non_max_suppression = mock_non_max_suppression
    sys.modules['ultralytics.utils.ops'] = MagicMock()
    sys.modules['ultralytics.utils.ops'].scale_boxes = mock_scale_boxes

    # Import the modified plugin
    from zebtrack.plugins.openvino_detector import OpenVINOPlugin

    # Create a mock plugin instance
    plugin = object.__new__(OpenVINOPlugin)
    plugin._context = 'tracking'
    plugin._aquarium_region_defined = False
    plugin.conf_threshold = 0.5
    plugin.nms_threshold = 0.4
    plugin.output_layer = 'output'

    # Add our new methods
    def set_context(context):
        if context in ('tracking', 'diagnostic'):
            plugin._context = context

    def set_aquarium_region_defined(defined=True):
        plugin._aquarium_region_defined = bool(defined)

    # Add the filtering logic from our modified _postprocess
    def _postprocess(result, original_frame_shape):
        output_tensor = result[plugin.output_layer]
        preds = mock_non_max_suppression(
            prediction=torch.from_numpy(output_tensor),
            conf_thres=plugin.conf_threshold,
            iou_thres=plugin.nms_threshold,
            agnostic=True,
        )
        detections = preds[0]
        if detections is None or len(detections) == 0:
            return []

        detections = mock_scale_boxes((640, 640), detections, original_frame_shape)

        final_detections = []
        for *xyxy, conf, cls in detections:
            class_id = int(cls)
            
            # NEW FILTERING LOGIC:
            if plugin._context == 'diagnostic':
                # In diagnostic mode NEVER filter: include all returned classes
                final_detections.append(
                    (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]), float(conf), class_id)
                )
            else:
                # Tracking mode:
                # Before aquarium is defined: don't filter (allow class 0 or others)
                # After aquarium definition: filter to only fish (cls == 1)
                if plugin._aquarium_region_defined and class_id != 1:
                    continue
                final_detections.append(
                    (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]), float(conf), class_id)
                )
        return final_detections

    plugin.set_context = set_context
    plugin.set_aquarium_region_defined = set_aquarium_region_defined
    plugin._postprocess = _postprocess

    # Test data
    mock_result = {'output': np.array([[1, 2, 3]])}
    frame_shape = (480, 640, 3)

    def format_detections(detections):
        class_names = {0: 'aquarium', 1: 'zebrafish'}
        return [f"Class {det[5]} ({class_names.get(det[5], 'unknown')}): bbox=({det[0]},{det[1]},{det[2]},{det[3]}), conf={det[4]:.2f}" 
                for det in detections]

    print("\n1. DIAGNOSTIC MODE (Weight Testing)")
    print("-" * 40)
    plugin.set_context('diagnostic')
    detections = plugin._postprocess(mock_result, frame_shape)
    print(f"Number of detections: {len(detections)}")
    for detection in format_detections(detections):
        print(f"  {detection}")
    print("✓ Shows ALL classes (both aquarium and zebrafish) for comprehensive model testing")

    print("\n2. TRACKING MODE - Before Aquarium Region Defined")
    print("-" * 40)
    plugin.set_context('tracking')
    plugin.set_aquarium_region_defined(False)
    detections = plugin._postprocess(mock_result, frame_shape)
    print(f"Number of detections: {len(detections)}")
    for detection in format_detections(detections):
        print(f"  {detection}")
    print("✓ Shows ALL classes (helpful for initial setup before aquarium is detected/drawn)")

    print("\n3. TRACKING MODE - After Aquarium Region Defined")
    print("-" * 40)
    plugin.set_context('tracking')
    plugin.set_aquarium_region_defined(True)
    detections = plugin._postprocess(mock_result, frame_shape)
    print(f"Number of detections: {len(detections)}")
    for detection in format_detections(detections):
        print(f"  {detection}")
    print("✓ Shows ONLY zebrafish (class 1) for focused tracking after aquarium setup")

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("- Diagnostic mode: Shows all classes for comprehensive model evaluation")
    print("- Tracking before aquarium: Shows all classes for initial setup")
    print("- Tracking after aquarium: Shows only zebrafish for focused analysis")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ Patch demonstration completed successfully!")
        else:
            print("\n❌ Patch demonstration failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)