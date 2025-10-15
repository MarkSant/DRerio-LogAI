"""
Video display widget component - handles canvas rendering and video frame display.
"""

import os
from tkinter import Canvas

import cv2
import structlog
from PIL import Image, ImageTk

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class VideoDisplayWidget(BaseWidget):
    """
    Reusable video display widget with canvas for rendering video frames.

    Provides:
    - Canvas for displaying video frames
    - Automatic scaling and centering
    - Coordinate transformation (video <-> canvas)
    - Background image rendering

    Events emitted:
    - frame.loaded: When a video frame is successfully loaded
    - frame.error: When frame loading fails
    """

    DEFAULT_WIDTH = 800
    DEFAULT_HEIGHT = 600

    def __init__(
        self,
        parent,
        event_bus: EventBus | None = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        bg: str = "gray",
        **kwargs,
    ):
        """
        Initialize the video display widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            width: Canvas width in pixels
            height: Canvas height in pixels
            bg: Background color for canvas
            **kwargs: Additional arguments passed to BaseWidget
        """
        self._canvas_width = width
        self._canvas_height = height
        self._canvas_bg = bg

        # Canvas and image state
        self.canvas: Canvas | None = None
        self._original_image: Image.Image | None = None
        self._raw_bg_image: Image.Image | None = None
        self._canvas_bg_image: ImageTk.PhotoImage | None = None
        self._canvas_bg_position: tuple[int, int, str] | None = None

        # Coordinate transformation state
        self._bg_scale: float = 1.0
        self._bg_offset: tuple[int, int] = (0, 0)
        self._bg_img_size: tuple[int, int] = (width, height)

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the video display widget UI."""
        self.canvas = Canvas(
            self,
            width=self._canvas_width,
            height=self._canvas_height,
            bg=self._canvas_bg,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Bind canvas resize to redraw
        self.canvas.bind("<Configure>", self._on_canvas_resize)

    def _on_canvas_resize(self, event) -> None:
        """Handle canvas resize events by redrawing the background."""
        if self._raw_bg_image or self._original_image:
            # Defer redraw to avoid multiple redraws during resize
            if hasattr(self, "_redraw_job") and self._redraw_job:
                self.after_cancel(self._redraw_job)
            self._redraw_job = self.after(100, self._draw_bg_image_to_canvas)

    def load_frame(self, video_path: str, frame_number: int = 0) -> bool:
        """
        Load a specific frame from a video file.

        Args:
            video_path: Path to the video file
            frame_number: Frame index to load (0-based)

        Returns:
            True if frame was loaded successfully, False otherwise

        Emits:
            - frame.loaded on success
            - frame.error on failure
        """
        if not video_path or not os.path.exists(video_path):
            self._log.error("video_display.load_frame.no_video", path=video_path)
            self.emit_event("frame.error", {"reason": "video_not_found", "path": video_path})
            return False

        try:
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                self._log.error(
                    "video_display.load_frame.failed",
                    path=video_path,
                    frame=frame_number,
                )
                self.emit_event(
                    "frame.error",
                    {
                        "reason": "read_failed",
                        "path": video_path,
                        "frame": frame_number,
                    },
                )
                return False

            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._original_image = Image.fromarray(frame_rgb)
            self._raw_bg_image = self._original_image

            # Display the frame
            self._draw_bg_image_to_canvas()

            self._log.info("video_display.frame_loaded", path=video_path, frame=frame_number)

            self.emit_event(
                "frame.loaded",
                {
                    "path": video_path,
                    "frame": frame_number,
                    "width": frame.shape[1],
                    "height": frame.shape[0],
                },
            )

            return True

        except Exception as e:
            self._log.error(
                "video_display.load_frame.error",
                path=video_path,
                frame=frame_number,
                error=str(e),
            )
            self.emit_event(
                "frame.error",
                {
                    "reason": "exception",
                    "path": video_path,
                    "frame": frame_number,
                    "error": str(e),
                },
            )
            return False

    def set_image(self, image: Image.Image) -> None:
        """
        Set an image directly (without loading from video).

        Args:
            image: PIL Image to display
        """
        self._original_image = image
        self._raw_bg_image = image
        self._draw_bg_image_to_canvas()

    def clear(self) -> None:
        """Clear the canvas and reset image state."""
        if self.canvas:
            self.canvas.delete("all")
        self._original_image = None
        self._raw_bg_image = None
        self._canvas_bg_image = None
        self._canvas_bg_position = None

    def _draw_bg_image_to_canvas(self) -> None:
        """Draw the background image to canvas with proper scaling and centering."""
        if not self._raw_bg_image and not self._original_image:
            return

        # Use raw_bg_image if available, otherwise use original_image
        image_to_draw = self._raw_bg_image or self._original_image

        # Get actual canvas dimensions
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not ready yet, try again
            self.after(10, self._draw_bg_image_to_canvas)
            return

        # Calculate scaling to fit image while maintaining aspect ratio
        img_w, img_h = image_to_draw.size
        scale = min(canvas_width / img_w, canvas_height / img_h, 1.0)
        new_width = int(img_w * scale)
        new_height = int(img_h * scale)

        # Store scaling information for coordinate conversion
        self._bg_scale = scale
        self._bg_img_size = (img_w, img_h)

        # Calculate offset (top-left position of scaled image in canvas)
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        offset_x = center_x - new_width // 2
        offset_y = center_y - new_height // 2
        self._bg_offset = (offset_x, offset_y)

        # Choose a resampling filter compatible with multiple Pillow versions
        try:
            RESAMPLING_LANCZOS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
        except Exception:
            try:
                RESAMPLING_LANCZOS = Image.LANCZOS  # type: ignore[attr-defined]
            except Exception:
                RESAMPLING_LANCZOS = Image.BICUBIC

        # Scale the image
        scaled_image = image_to_draw.resize((new_width, new_height), RESAMPLING_LANCZOS)

        # Clear canvas and display centered image
        self.canvas.delete("all")
        self._canvas_bg_image = ImageTk.PhotoImage(scaled_image)

        # Store positioning for reference
        self._canvas_bg_position = (center_x, center_y, "center")

        self.canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

    def video_to_canvas(self, video_x: float, video_y: float) -> tuple[float, float]:
        """
        Convert video frame coordinates to canvas coordinates.

        Args:
            video_x: X coordinate in video frame
            video_y: Y coordinate in video frame

        Returns:
            Tuple of (canvas_x, canvas_y)
        """
        if not hasattr(self, "_bg_scale") or not hasattr(self, "_bg_offset"):
            # Fallback: return video coordinates if scaling info not available
            return (float(video_x), float(video_y))

        scale = self._bg_scale
        offset_x, offset_y = self._bg_offset

        # Convert video coordinates to canvas coordinates
        canvas_x = video_x * scale + offset_x
        canvas_y = video_y * scale + offset_y

        return (float(canvas_x), float(canvas_y))

    def canvas_to_video(self, canvas_x: float, canvas_y: float) -> tuple[float, float]:
        """
        Convert canvas coordinates to video frame coordinates.

        Args:
            canvas_x: X coordinate on canvas
            canvas_y: Y coordinate on canvas

        Returns:
            Tuple of (video_x, video_y)
        """
        if not hasattr(self, "_bg_scale") or not hasattr(self, "_bg_offset"):
            # Fallback: return canvas coordinates if scaling info not available
            return (float(canvas_x), float(canvas_y))

        scale = self._bg_scale
        offset_x, offset_y = self._bg_offset

        # Convert canvas coordinates to video coordinates
        video_x = (canvas_x - offset_x) / scale
        video_y = (canvas_y - offset_y) / scale

        return (float(video_x), float(video_y))

    def get_image_size(self) -> tuple[int, int] | None:
        """Return the size of the currently loaded image (width, height) if any."""
        if self._bg_img_size:
            return self._bg_img_size
        return None

    def get_scale(self) -> float:
        """
        Get the current display scale factor.

        Returns:
            Scale factor (canvas pixels per video pixel)
        """
        return self._bg_scale
