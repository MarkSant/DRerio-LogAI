# ROI Snap Indicator Arena Clamping Feature

## Overview

When drawing or editing ROI polygons over the main arena, the visual indicators are now constrained to stay within the arena boundaries. This provides better visual feedback and prevents confusion about where ROI points can be placed.

This feature works in two modes:
1. **Drawing Mode**: The snap indicator (cyan circle) stays within arena boundaries
2. **Editing Mode**: Vertices being dragged are clamped to arena edges, with visual feedback showing clamped vertices

## Behavior

### When Drawing ROIs

- **Snap Indicator Visibility**: The cyan snap indicator circle is always visible when the cursor is near the canvas, even if the actual cursor position is outside the arena.
  
- **Position Clamping**: If the cursor (or snap point) would place the indicator outside the arena boundaries, the indicator is automatically "clamped" to the nearest point on the arena edge.

- **Cursor Movement**: The actual mouse cursor can move freely anywhere on the canvas, including outside the arena. Only the visual indicator is constrained.

- **Snapping Tolerance**: The existing snapping logic (vertices, edges, axes) continues to work as before. If snapping occurs to a point outside the arena, that snap point is also clamped to the arena boundary.

### When Drawing the Arena

- **No Clamping**: When drawing the main arena polygon itself (not ROIs), the indicator is not clamped and moves freely with the cursor.

- **Backward Compatibility**: All existing arena drawing functionality remains unchanged.

## Technical Implementation

### Location
- **File**: `src/zebtrack/ui/gui.py`
- **Method**: `_on_canvas_motion(self, event)`

### Algorithm

1. **Detection Phase**: Check if currently drawing an ROI (`self.current_drawing_type == "roi"`)

2. **Arena Boundary Check**:
   - Retrieve the main arena polygon from project manager
   - Convert arena coordinates to canvas space
   - Use `cv2.pointPolygonTest()` to determine if the display point is inside or outside the arena

3. **Clamping Phase** (if outside):
   - Iterate through each edge of the arena polygon
   - Calculate the closest point on each edge using `_point_to_segment_distance()`
   - Select the overall closest point as the clamped position

4. **Indicator Display**:
   - Draw the cyan snap indicator circle at the clamped position
   - Elastic lines (showing the next polygon edge) automatically use the clamped position

### Key Functions Used

- `cv2.pointPolygonTest()`: Determines if a point is inside/outside a polygon (with signed distance)
- `_point_to_segment_distance()`: Calculates closest point on a line segment
- `_video_to_canvas()`: Coordinate transformation from video to canvas space

## Testing

### Automated Test
- **File**: `tests/test_roi_snap_indicator_arena_clamp.py`
- **Purpose**: Verifies that the clamping logic is present in the code

### Manual Testing Scenarios

#### Drawing Mode Tests

1. **Outside Arena - Top Left**:
   - Create a project with a defined arena
   - Start drawing an ROI
   - Move cursor above and to the left of the arena
   - **Expected**: Indicator stays at arena's top-left corner

2. **Outside Arena - Right Edge**:
   - Move cursor to the right of the arena
   - **Expected**: Indicator clamps to the nearest point on the right edge

3. **Inside Arena**:
   - Move cursor within the arena boundaries
   - **Expected**: Indicator follows cursor normally

4. **Snapping to Arena Vertex**:
   - Move cursor near an arena vertex
   - **Expected**: Indicator snaps to the vertex (existing behavior)

5. **Drawing Arena (Not ROI)**:
   - Start drawing a new arena polygon
   - Move cursor freely
   - **Expected**: No clamping occurs, indicator follows cursor

#### Editing Mode Tests

6. **Edit ROI - Drag Vertex Outside Arena**:
   - Create an ROI within the arena
   - Click "Edit" on the ROI
   - Try to drag a vertex outside the arena boundary
   - **Expected**: Vertex clamps to nearest arena edge; handle turns orange with an extra indicator circle

7. **Edit ROI - Drag Vertex Inside Arena**:
   - While editing, drag a vertex to a different position inside the arena
   - **Expected**: Vertex moves freely; handle remains yellow/gold

8. **Edit ROI - Vertex on Boundary**:
   - Drag a vertex to the arena edge
   - **Expected**: Handle turns orange with indicator circle showing it's on the boundary

## User Experience Benefits

1. **Clear Visual Feedback**: Users can immediately see where their ROI point/vertex will be placed, even if their cursor is outside the valid area.

2. **Prevents Confusion**: The indicator staying within arena boundaries makes it clear that ROIs must be drawn inside the arena.

3. **Preserved Tolerance Logic**: The existing click tolerance for validation remains active, allowing for small positioning errors.

4. **Smooth Drawing**: The cursor can move fluidly without hitting invisible boundaries, while the indicator provides accurate placement feedback.

5. **Edit Mode Visual Cues**: When editing ROI vertices:
   - **Orange handles** with extra circles indicate vertices on the arena boundary
   - **Yellow/gold handles** indicate vertices freely positioned inside the arena
   - Attempting to drag outside results in automatic clamping with immediate visual feedback

## Compatibility Notes

- **Existing ROI Validation**: The `add_roi_polygon()` method in the controller still performs its validation and adjustment of ROI points that are slightly outside the arena.

- **Snapping Logic**: All existing snapping behavior (to vertices, edges, and axes) is preserved and works in combination with arena clamping.

- **Coordinate Systems**: The implementation respects the canvas-to-video coordinate transformation system.

## Future Enhancements

Possible improvements for future versions:

1. **Visual Arena Highlight**: Slightly highlight the arena boundary when drawing ROIs to provide additional context.

2. **Proximity Warning**: Show a different indicator color (e.g., orange) when the cursor is outside the arena but the indicator is clamped.

3. **Configurable Clamping**: Add a setting to disable clamping if users prefer to see the actual cursor position.

## Related Files

- `src/zebtrack/ui/gui.py`: Main implementation
- `src/zebtrack/core/controller.py`: ROI validation logic (`add_roi_polygon`)
- `src/zebtrack/utils/geometry.py`: Geometry helper functions
- `tests/test_roi_snap_indicator_arena_clamp.py`: Automated test
- `.github/copilot-instructions.md`: Updated with feature documentation

## References

- Issue/Request: "Ao desenhar rois sobre a área da arena previamente desenhada, a Bolinha do cursor que representa ação de snapping..."
- Implementation Date: October 14, 2025
- Test Status: ✅ Passing
