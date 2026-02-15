# Live Camera & Analysis Reference

**Status:** Canonical Reference
**Last Updated:** February 2, 2026
**Category:** Reference (Diátaxis)

## 1. Overview

The Live Camera system handles real-time video streaming, recording, and analysis. In v2.2+, it was unified to support both single-aquarium and multi-aquarium configurations with shared frame-buffering logic.

## 2. Hardware Interface

- **VideoSource (`io/video_source.py`):** The abstraction layer for OpenCV/Camera captures. Handles exposure, white balance, and resolution settings.
- **Recording (`io/recorder.py`):** Synchronous frame writing to MP4 while simultaneously persisting detection coordinates to Parquet.

## 3. Live Analysis Pipeline

Live analysis operates in two modes:

1. **Preview Only:** Standard 30/60 FPS stream for setup.
2. **Analysis Mode:** Frames are processed by `DetectorService` before display.

### 3.1. Multi-Aquarium Partitioning

For multi-aquarium live analysis, the system:

- Crops the full frame into $N$ sub-regions based on assigned aquariums.
- Parallelizes detection using a `ThreadPoolExecutor` to maintain frame rates.
- Re-maps local IDs to global IDs (`aquarium_id * 1000 + id`).

## 4. Operational Parameters

| Parameter      | Default | Description                                    |
| -------------- | ------- | ---------------------------------------------- |
| `fps_limit`    | 30      | Target capture rate to prevent CPU saturation. |
| `buffer_size`  | 5       | Shared memory buffer for frame stabilization.  |
| `use_openvino` | Auto    | Enables hardware acceleration if available.    |

---

**Developer Tip:** UI updates during live streaming **must** use `UIScheduler.schedule_update()` to avoid blocking the capture thread.
