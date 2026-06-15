import numpy as np
import pytest

from zebtrack.core.detection.calibration import Calibration


@pytest.fixture
def calibration_setup():
    """Provides a sample polygon and dimensions for testing."""
    polygon = np.array([[105, 105], [495, 100], [505, 395], [100, 405]], dtype=np.int32)
    real_width_cm = 20.0
    real_height_cm = 15.0
    return polygon, real_width_cm, real_height_cm


def test_calibration_initialization_and_processing(calibration_setup):
    """
    Test if the Calibration class initializes correctly and calculates
    the homography matrix and pixel ratio.
    """
    polygon, real_width_cm, real_height_cm = calibration_setup
    calibration = Calibration(polygon, real_width_cm, real_height_cm)

    # 1. Test if homography matrix is calculated and has the correct shape
    assert calibration.homography_matrix is not None
    assert calibration.homography_matrix.shape == (3, 3)

    # 2. Test if the pixel-to-cm ratio is calculated correctly
    # Based on the hardcoded target width of 600px in Calibration class
    target_width_px = 600
    aspect_ratio = real_height_cm / real_width_cm
    target_height_px = int(target_width_px * aspect_ratio)

    expected_ratio_x = target_width_px / real_width_cm
    expected_ratio_y = target_height_px / real_height_cm

    assert calibration.pixel_per_cm_ratio[0] == pytest.approx(expected_ratio_x)
    assert calibration.pixel_per_cm_ratio[1] == pytest.approx(expected_ratio_y)
    assert calibration.target_dims_px == (target_width_px, target_height_px)


def test_warp_frame(calibration_setup):
    """
    Test if the warp_frame method returns a frame with the correct dimensions.
    """
    polygon, real_width_cm, real_height_cm = calibration_setup
    calibration = Calibration(polygon, real_width_cm, real_height_cm)

    # Create a dummy frame
    original_frame = np.zeros((600, 800, 3), dtype=np.uint8)

    warped_frame = calibration.warp_frame(original_frame)

    # The warped frame should have the target dimensions calculated during
    # calibration
    expected_height, expected_width = (
        calibration.target_dims_px[1],
        calibration.target_dims_px[0],
    )

    assert warped_frame.shape[0] == expected_height
    assert warped_frame.shape[1] == expected_width


def test_order_points():
    """
    Test the _order_points static method to ensure it sorts corners correctly.
    """
    pts = np.array(
        [
            (0, 100),  # bottom-left
            (100, 0),  # top-right
            (100, 100),  # bottom-right
            (0, 0),  # top-left
        ],
        dtype="float32",
    )

    ordered = Calibration._order_points(pts)

    # Expected order: top-left, top-right, bottom-right, bottom-left
    expected = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype="float32")

    np.testing.assert_array_equal(ordered, expected)


def test_pixel_to_cm_conversion():
    """
    Test that the pixel-to-cm conversion logic is correct based on the
    calculated ratio.
    """
    # This polygon is not important for the ratio calculation itself, but the
    # class requires it for initialization.
    dummy_polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)
    # If the real-world width is 30cm, and the target warped width is 600px,
    # the ratio should be 20 pixels per cm.
    calibration = Calibration(polygon=dummy_polygon, real_width_cm=30.0, real_height_cm=20.0)

    # 1. Check if the ratio is calculated as expected
    px_per_cm_x, _ = calibration.pixel_per_cm_ratio
    assert px_per_cm_x == pytest.approx(20.0)  # 600px / 30cm

    # 2. Test the conversion as specified in the task description
    # If 100 pixels = 5 cm, then the ratio is 20 px/cm.
    # A value of 200 pixels should convert to 10 cm.
    pixel_value = 200
    expected_cm_value = 10.0
    calculated_cm_value = pixel_value / px_per_cm_x

    assert calculated_cm_value == pytest.approx(expected_cm_value)


# ---------------------------------------------------------------------------
# Edge cases: missing / degenerate polygons and point/bbox transforms
# ---------------------------------------------------------------------------


def test_none_polygon_leaves_matrix_unset():
    """No polygon → no homography; the object must stay in a safe identity state."""
    calibration = Calibration(polygon=None, real_width_cm=20.0, real_height_cm=15.0)
    assert calibration.homography_matrix is None
    assert calibration.pixel_per_cm_ratio == (0.0, 0.0)


def test_find_corners_returns_none_for_too_few_points():
    assert Calibration._find_corners(np.array([[0, 0], [10, 10]], dtype=np.int32)) is None
    assert Calibration._find_corners(None) is None  # type: ignore[arg-type]


def test_warp_frame_without_matrix_is_passthrough():
    calibration = Calibration(polygon=None, real_width_cm=20.0, real_height_cm=15.0)
    frame = np.zeros((10, 12, 3), dtype=np.uint8)
    assert calibration.warp_frame(frame) is frame


def test_transform_points_without_matrix_is_passthrough():
    calibration = Calibration(polygon=None, real_width_cm=20.0, real_height_cm=15.0)
    points = [[1.0, 2.0], [3.0, 4.0]]
    assert calibration.transform_points(points) is points


def test_transform_bbox_without_matrix_is_passthrough():
    calibration = Calibration(polygon=None, real_width_cm=20.0, real_height_cm=15.0)
    assert calibration.transform_bbox(1.0, 2.0, 3.0, 4.0) == (1.0, 2.0, 3.0, 4.0)


def test_transform_bbox_returns_axis_aligned_box(calibration_setup):
    """With a valid homography, transform_bbox returns a well-formed AABB."""
    polygon, w, h = calibration_setup
    calibration = Calibration(polygon, w, h)
    x1_w, y1_w, x2_w, y2_w = calibration.transform_bbox(150.0, 150.0, 300.0, 300.0)
    # The result must be a valid axis-aligned box (min <= max on both axes).
    assert x1_w <= x2_w
    assert y1_w <= y2_w
