# Live Camera Implementation Guide

**Status:** Implementation Reference
**Target:** Developers
**Category:** How-To Guide (Diátaxis)

## 1. Threading Model

Live camera capture runs in a dedicated `LiveCameraService` thread (daemon=True). To maintain GUI responsiveness:
- **Capture Thread:** Pulls raw frames from hardware.
- **Analysis Thread:** (Optional) If recording+analyzing, a pool or separate worker handles detection.
- **Main Thread:** Tkinter draws the result using `canvas.itemconfig(image_id, image=...)`.

## 2. Shared Buffer Logic

To prevent frame drops during recording, the `LiveCameraService` uses a `collections.deque` with a fixed `maxlen`.
```python
# capture loop snippet
frame = self.source.read()
if frame is not None:
    self.buffer.append(frame)
    self.event_bus.publish(Events.UI_DISPLAY_FRAME, {'frame': frame})
```

## 3. Handling Multi-Aquarium in Live Mode

When multi-aquarium is active:
1. `DetectorService` receives the full frame.
2. It uses `_crop_aquarium_region` to generate slices.
3. `detect_partitioned_parallel` is called.
4. Coordinates are translated back to global canvas space.

## 4. Troubleshooting Hacks

- **High Latency:** Reduce `opencv_buffer_size` in `config.yaml`.
- **System Freeze:** Ensure `root.after()` is used for ALL UI updates originating from the service thread of the camera.
- **Lost Frames:** Increase parity between capture rate and disk write speed (check SSD throughput).
