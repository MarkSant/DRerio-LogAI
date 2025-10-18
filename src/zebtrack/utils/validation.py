import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

def validate_calibration(pixel_per_cm_ratio: tuple[float, float] | None) -> None:
    """
    Validates calibration ratio.

    Args:
        pixel_per_cm_ratio: Tuple of (x_ratio, y_ratio) or None

    Raises:
        TypeError: If ratios are not numeric
        ValueError: If ratios are invalid (<=0, NaN, inf)

    Returns:
        None if validation passes
    """
    if pixel_per_cm_ratio is None:
        return  # Calibration optional

    if not isinstance(pixel_per_cm_ratio, tuple) or len(pixel_per_cm_ratio) != 2:
        # This check is good practice, though the type hint should catch it.
        raise TypeError("pixel_per_cm_ratio must be a tuple of two floats or None")

    x_ratio, y_ratio = pixel_per_cm_ratio

    if not (isinstance(x_ratio, (int, float)) and isinstance(y_ratio, (int, float))):
        raise TypeError("Calibration ratios must be numeric")

    if not (math.isfinite(x_ratio) and math.isfinite(y_ratio)):
        raise ValueError(f"Calibration ratios must be finite, got ({x_ratio}, {y_ratio})")

    if not (x_ratio > 0 and y_ratio > 0):
        raise ValueError(f"Calibration ratios must be positive, got ({x_ratio}, {y_ratio})")