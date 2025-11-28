"""
Threading stress tests for BYTETracker to validate Kalman filter race condition fix.

Tests verify that multiple tracker instances can run concurrently without
race conditions on shared state (Issue: shared_kalman class variable).

Run with: pytest tests/test_tracker_threading_stress.py -v
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pytest

from zebtrack.tracker.byte_tracker import BYTETracker, STrack


class Args:
    """Mock arguments for BYTETracker initialization."""

    track_thresh = 0.5
    track_buffer = 30
    match_thresh = 0.8
    mot20 = False


@pytest.fixture
def mock_detections():
    """Generate mock detection data (5 columns: x1, y1, x2, y2, confidence)."""
    return np.array(
        [
            [100, 100, 200, 200, 0.9],
            [300, 300, 400, 400, 0.85],
            [500, 500, 600, 600, 0.95],
        ]
    )


@pytest.fixture
def img_info():
    """Mock image info."""
    return (1920, 1080)


@pytest.fixture
def img_size():
    """Mock image size."""
    return (1920, 1080)


def tracker_worker(tracker_id: int, num_frames: int, detections, img_info, img_size):
    """
    Worker function that runs a tracker instance for multiple frames.

    Args:
        tracker_id: Unique tracker identifier
        num_frames: Number of frames to process
        detections: Detection results to process
        img_info: Image info tuple
        img_size: Image size tuple

    Returns:
        Dict with tracker_id, frames_processed, and final track count
    """
    tracker = BYTETracker(Args(), frame_rate=30)
    track_ids = set()

    for frame_idx in range(num_frames):
        # Slightly vary detections to simulate real tracking
        perturbed_detections = detections.copy()
        perturbed_detections[:, :4] += np.random.randn(*perturbed_detections[:, :4].shape) * 5

        # Update tracker
        online_targets = tracker.update(perturbed_detections, img_info, img_size)

        # Collect track IDs
        for track in online_targets:
            track_ids.add(track.track_id)

    return {
        "tracker_id": tracker_id,
        "frames_processed": num_frames,
        "unique_tracks": len(track_ids),
        "final_track_count": len(tracker.tracked_stracks),
    }


@pytest.mark.slow
def test_single_tracker_baseline(mock_detections, img_info, img_size):
    """Baseline test: single tracker processes frames sequentially."""
    result = tracker_worker(0, 50, mock_detections, img_info, img_size)

    assert result["frames_processed"] == 50
    assert result["unique_tracks"] > 0, "Should have tracked at least one object"
    assert result["final_track_count"] >= 0, "Final track count should be non-negative"


@pytest.mark.slow
def test_parallel_trackers_no_shared_state(mock_detections, img_info, img_size):
    """
    Stress test: Multiple trackers running in parallel threads.

    Validates that each tracker maintains independent state without
    race conditions on the Kalman filter.

    This test would FAIL with the old shared_kalman class variable,
    as concurrent predictions would corrupt covariance matrices.
    """
    num_trackers = 5
    frames_per_tracker = 30

    # Run trackers in parallel
    with ThreadPoolExecutor(max_workers=num_trackers) as executor:
        futures = [
            executor.submit(
                tracker_worker, tracker_id, frames_per_tracker, mock_detections, img_info, img_size
            )
            for tracker_id in range(num_trackers)
        ]

        results = [future.result() for future in as_completed(futures)]

    # Validate all trackers completed successfully
    assert len(results) == num_trackers, "All trackers should complete"

    for result in results:
        assert result["frames_processed"] == frames_per_tracker
        assert result["unique_tracks"] > 0, f"Tracker {result['tracker_id']} should track objects"

    # All trackers should produce similar results (not corrupted)
    track_counts = [r["unique_tracks"] for r in results]
    mean_tracks = np.mean(track_counts)
    std_tracks = np.std(track_counts)

    # If state is corrupted, track counts will vary wildly
    # With independent state, they should be similar
    assert std_tracks < mean_tracks * 0.5, (
        "Track counts should be consistent across trackers (low variance)"
    )


@pytest.mark.slow
def test_rapid_tracker_creation_destruction(mock_detections, img_info, img_size):
    """
    Stress test: Rapidly create and destroy tracker instances.

    Validates that Kalman filter instances are properly isolated
    and don't share state across tracker lifecycles.
    """
    num_iterations = 20

    track_counts = []
    for i in range(num_iterations):
        tracker = BYTETracker(Args(), frame_rate=30)

        # Process a few frames
        for _ in range(5):
            tracker.update(mock_detections, img_info, img_size)

        track_counts.append(len(tracker.tracked_stracks))

        # Tracker goes out of scope - should not affect next iteration

    # All iterations should produce similar results
    assert all(count >= 0 for count in track_counts), "All track counts should be non-negative"
    assert len(set(track_counts)) <= 3, (
        "Track counts should be consistent (not random due to shared state)"
    )


@pytest.mark.slow
def test_strack_multi_predict_thread_safety(mock_detections):
    """
    Unit test: Verify STrack.multi_predict requires kalman_filter parameter.

    This test ensures the API change is enforced and prevents regression
    to the old shared_kalman pattern.
    """
    from zebtrack.tracker.kalman_filter import KalmanFilter

    # Create some tracks
    tracks = [STrack(mock_detections[i, :4], mock_detections[i, 4]) for i in range(3)]

    # Initialize tracks
    kf = KalmanFilter()
    for track in tracks:
        track.activate(kf, frame_id=0)

    # multi_predict should require kalman_filter parameter
    try:
        # Old signature (should fail)
        STrack.multi_predict(tracks)
        pytest.fail("multi_predict should require kalman_filter parameter")
    except TypeError as e:
        # Expected: missing required argument
        assert "kalman_filter" in str(e) or "positional argument" in str(e)

    # New signature (should succeed)
    STrack.multi_predict(tracks, kf)  # Should not raise

    # Verify predictions were applied
    for track in tracks:
        assert track.mean is not None, "Track should have predicted mean"
        assert track.covariance is not None, "Track should have predicted covariance"


@pytest.mark.slow
def test_concurrent_multi_predict_calls(mock_detections):
    """
    Stress test: Multiple threads calling multi_predict with different filters.

    Validates that predictions don't interfere with each other when
    using separate Kalman filter instances.
    """
    from zebtrack.tracker.kalman_filter import KalmanFilter

    def predict_worker(worker_id: int, num_iterations: int):
        """Worker that repeatedly calls multi_predict."""
        kf = KalmanFilter()
        results = []

        for _ in range(num_iterations):
            # Create fresh tracks
            tracks = [STrack(mock_detections[i, :4], mock_detections[i, 4]) for i in range(3)]

            # Initialize
            for track in tracks:
                track.activate(kf, frame_id=0)

            # Predict
            STrack.multi_predict(tracks, kf)

            # Collect covariance diagonal sum (should be consistent)
            cov_sum = sum(np.trace(track.covariance) for track in tracks)
            results.append(cov_sum)

        return {"worker_id": worker_id, "cov_sums": results}

    # Run multiple workers in parallel
    num_workers = 5
    iterations_per_worker = 10

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(predict_worker, worker_id, iterations_per_worker)
            for worker_id in range(num_workers)
        ]

        results = [future.result() for future in as_completed(futures)]

    # Validate results are consistent across workers
    all_cov_sums = [cov for result in results for cov in result["cov_sums"]]

    mean_cov = np.mean(all_cov_sums)
    std_cov = np.std(all_cov_sums)

    # If filters share state, covariances will diverge wildly
    # With independent state, they should be very similar
    assert std_cov < mean_cov * 0.1, (
        "Covariance predictions should be consistent across threads (no shared state corruption)"
    )


@pytest.mark.slow
def test_tracker_reset_independence():
    """
    Test that resetting one tracker doesn't affect others.

    Validates Kalman filter state isolation.
    """
    tracker1 = BYTETracker(Args(), frame_rate=30)
    tracker2 = BYTETracker(Args(), frame_rate=30)

    # Create detections
    detections = np.array([[100, 100, 200, 200, 0.9]])
    img_info = (1920, 1080)
    img_size = (1920, 1080)

    # Process with tracker1
    tracker1.update(detections, img_info, img_size)
    tracker1_count = len(tracker1.tracked_stracks)

    # Process with tracker2 (should be independent)
    tracker2.update(detections, img_info, img_size)
    tracker2_count = len(tracker2.tracked_stracks)

    # Both should have similar results (not affected by each other)
    assert tracker1_count == tracker2_count, "Independent trackers should produce same results"

    # Reset tracker1 (via creating new instance)
    tracker1 = BYTETracker(Args(), frame_rate=30)

    # tracker2 should still work normally
    tracker2.update(detections, img_info, img_size)
    assert len(tracker2.tracked_stracks) > 0, "Tracker2 should not be affected by tracker1 reset"
