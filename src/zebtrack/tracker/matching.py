import numpy as np
from cython_bbox import bbox_overlaps as bbox_ious
from scipy.optimize import linear_sum_assignment
from scipy.sparse import csc_matrix
from scipy.spatial.distance import cdist

from zebtrack.tracker import kalman_filter


def merge_matches(m1, m2, shape):
    n_obs, P, Q = shape
    m1 = np.asarray(m1)
    m2 = np.asarray(m2)

    M1 = csc_matrix((np.ones(len(m1)), (m1[:, 0], m1[:, 1])), shape=(n_obs, P))
    M2 = csc_matrix((np.ones(len(m2)), (m2[:, 0], m2[:, 1])), shape=(n_obs, Q))

    mask = M1 * M2
    match = mask.nonzero()
    match = list(zip(match[0], match[1], strict=False))
    unmatched_P = tuple(set(range(P)) - set([i for i, j in match]))
    unmatched_Q = tuple(set(range(Q)) - set([j for i, j in match]))

    return match, unmatched_P, unmatched_Q


def _indices_to_matches(cost_matrix, indices, thresh):
    matched_cost = cost_matrix[tuple(zip(*indices, strict=False))]
    matched_mask = matched_cost <= thresh

    matches = indices[matched_mask]
    unmatched_a = tuple(set(range(cost_matrix.shape[0])) - set(matches[:, 0]))
    unmatched_b = tuple(set(range(cost_matrix.shape[1])) - set(matches[:, 1]))

    return matches, unmatched_a, unmatched_b


def linear_assignment(cost_matrix, thresh):
    if cost_matrix.size == 0:
        return (
            np.empty((0, 2), dtype=int),
            tuple(range(cost_matrix.shape[0])),
            tuple(range(cost_matrix.shape[1])),
        )

    # Handle inf values: scipy's linear_sum_assignment can fail with inf
    # Replace inf with a very large value that will be filtered by threshold
    cost_matrix_safe = cost_matrix.copy()
    inf_mask = np.isinf(cost_matrix_safe)
    if np.any(inf_mask):
        # Use a value larger than any reasonable threshold (thresh is typically < 1)
        cost_matrix_safe[inf_mask] = 1e6

    try:
        row_ind, col_ind = linear_sum_assignment(cost_matrix_safe)
    except ValueError:
        # If still infeasible, return no matches
        return (
            np.empty((0, 2), dtype=int),
            tuple(range(cost_matrix.shape[0])),
            tuple(range(cost_matrix.shape[1])),
        )

    indices = np.array(list(zip(row_ind, col_ind, strict=False)))

    # Use original cost_matrix for threshold comparison (with inf values)
    return _indices_to_matches(cost_matrix, indices, thresh)


def ious(atlbrs, btlbrs):
    """
    Compute cost based on IoU
    :type atlbrs: list[tlbr] | np.ndarray
    :type btlbrs: list[tlbr] | np.ndarray

    :rtype: np.ndarray
    """
    if len(atlbrs) == 0 or len(btlbrs) == 0:
        return np.zeros((len(atlbrs), len(btlbrs)), dtype=np.float64)

    _ious = bbox_ious(
        np.ascontiguousarray(atlbrs, dtype=np.float64),
        np.ascontiguousarray(btlbrs, dtype=np.float64),
    )

    return _ious


def iou_distance(atracks, btracks):
    """
    Compute cost based on IoU
    :type atracks: list[STrack]
    :type btracks: list[STrack]

    :rtype cost_matrix np.ndarray
    """

    if (len(atracks) > 0 and isinstance(atracks[0], np.ndarray)) or (
        len(btracks) > 0 and isinstance(btracks[0], np.ndarray)
    ):
        atlbrs = atracks
        btlbrs = btracks
    else:
        atlbrs = [track.tlbr for track in atracks]
        btlbrs = [track.tlbr for track in btracks]
    _ious = ious(atlbrs, btlbrs)
    cost_matrix = 1 - _ious

    return cost_matrix


def v_iou_distance(atracks, btracks):
    """
    Compute cost based on IoU
    :type atracks: list[STrack]
    :type btracks: list[STrack]

    :rtype cost_matrix np.ndarray
    """

    if (len(atracks) > 0 and isinstance(atracks[0], np.ndarray)) or (
        len(btracks) > 0 and isinstance(btracks[0], np.ndarray)
    ):
        atlbrs = atracks
        btlbrs = btracks
    else:
        atlbrs = [track.tlwh_to_tlbr(track.pred_bbox) for track in atracks]
        btlbrs = [track.tlwh_to_tlbr(track.pred_bbox) for track in btracks]
    _ious = ious(atlbrs, btlbrs)
    cost_matrix = 1 - _ious

    return cost_matrix


def embedding_distance(tracks, detections, metric="cosine"):
    """
    :param tracks: list[STrack]
    :param detections: list[BaseTrack]
    :param metric:
    :return: cost_matrix np.ndarray
    """

    cost_matrix = np.zeros((len(tracks), len(detections)), dtype=np.float64)
    if cost_matrix.size == 0:
        return cost_matrix
    det_features = np.asarray([track.curr_feat for track in detections], dtype=np.float64)
    track_features = np.asarray([track.smooth_feat for track in tracks], dtype=np.float64)
    cost_matrix = np.maximum(0.0, cdist(track_features, det_features, metric))
    return cost_matrix


def gate_cost_matrix(kf, cost_matrix, tracks, detections, only_position=False):
    if cost_matrix.size == 0:
        return cost_matrix
    gating_dim = 2 if only_position else 4
    gating_threshold = kalman_filter.chi2inv95[gating_dim]
    measurements = np.asarray([det.to_xyah() for det in detections])
    for row, track in enumerate(tracks):
        gating_distance = kf.gating_distance(
            track.mean, track.covariance, measurements, only_position
        )
        cost_matrix[row, gating_distance > gating_threshold] = np.inf
    return cost_matrix


def fuse_motion(kf, cost_matrix, tracks, detections, only_position=False, lambda_=0.98):
    if cost_matrix.size == 0:
        return cost_matrix
    gating_dim = 2 if only_position else 4
    gating_threshold = kalman_filter.chi2inv95[gating_dim]
    measurements = np.asarray([det.to_xyah() for det in detections])
    for row, track in enumerate(tracks):
        gating_distance = kf.gating_distance(
            track.mean,
            track.covariance,
            measurements,
            only_position,
            metric="maha",
        )
        cost_matrix[row, gating_distance > gating_threshold] = np.inf
        cost_matrix[row] = lambda_ * cost_matrix[row] + (1 - lambda_) * gating_distance
    return cost_matrix


def fuse_iou(cost_matrix, tracks, detections):
    if cost_matrix.size == 0:
        return cost_matrix
    reid_sim = 1 - cost_matrix
    iou_dist = iou_distance(tracks, detections)
    iou_sim = 1 - iou_dist
    fuse_sim = reid_sim * (1 + iou_sim) / 2
    det_scores = np.array([det.score for det in detections])
    det_scores = np.expand_dims(det_scores, axis=0).repeat(cost_matrix.shape[0], axis=0)
    fuse_sim = fuse_sim * (1 + det_scores) / 2
    fuse_cost = 1 - fuse_sim
    return fuse_cost


def fuse_score(cost_matrix, detections):
    if cost_matrix.size == 0:
        return cost_matrix
    iou_sim = 1 - cost_matrix
    det_scores = np.array([det.score for det in detections])
    det_scores = np.expand_dims(det_scores, axis=0).repeat(cost_matrix.shape[0], axis=0)
    fuse_sim = iou_sim * det_scores
    fuse_cost = 1 - fuse_sim
    return fuse_cost


def center_distance(atracks, btracks, max_distance: float = 200.0):
    """
    Compute cost based on center-to-center Euclidean distance.

    This is useful as a fallback when IoU matching fails due to large
    inter-frame movements (e.g., when processing every N frames).

    Args:
        atracks: List of tracks (STrack objects or np.ndarray of tlbr coords)
        btracks: List of detections (STrack objects or np.ndarray of tlbr coords)
        max_distance: Maximum distance in pixels for matching. Distances beyond
            this are set to inf (no match). Default 200px.

    Returns:
        cost_matrix: Normalized cost matrix [0, 1] where lower = closer.
            Values beyond max_distance are set to inf.

    Note:
        For small objects like zebrafish (~30x30 px), a max_distance of 200px
        allows matching movements of about 6-7 body lengths between frames.
    """
    if len(atracks) == 0 or len(btracks) == 0:
        return np.zeros((len(atracks), len(btracks)), dtype=np.float64)

    # Get centers from tracks/detections
    def get_center(item):
        if isinstance(item, np.ndarray):
            # tlbr format: [x1, y1, x2, y2]
            return np.array([(item[0] + item[2]) / 2, (item[1] + item[3]) / 2])
        else:
            # STrack object with tlbr property
            tlbr = item.tlbr
            return np.array([(tlbr[0] + tlbr[2]) / 2, (tlbr[1] + tlbr[3]) / 2])

    a_centers = np.array([get_center(t) for t in atracks])
    b_centers = np.array([get_center(t) for t in btracks])

    # Compute Euclidean distance matrix
    distances = cdist(a_centers, b_centers, metric="euclidean")

    # Normalize to [0, 1] range based on max_distance
    # Values beyond max_distance get a very high cost (will be filtered by threshold)
    # Using 1e6 instead of inf to avoid scipy linear_sum_assignment issues
    cost_matrix = distances / max_distance
    cost_matrix[distances > max_distance] = 1e6

    return cost_matrix


def hybrid_iou_center_distance(
    atracks, btracks, iou_thresh: float = 0.1, max_center_dist: float = 200.0
):
    """
    Hybrid matching: Use IoU when overlap exists, fall back to center distance otherwise.

    This is designed for scenarios with small, fast-moving objects where:
    1. IoU works well when objects overlap between frames
    2. Center distance provides matching when IoU fails (large movements)

    Args:
        atracks: List of tracks
        btracks: List of detections
        iou_thresh: Minimum IoU to consider valid overlap (below this, use distance)
        max_center_dist: Maximum center distance for fallback matching

    Returns:
        cost_matrix: Combined cost matrix
    """
    if len(atracks) == 0 or len(btracks) == 0:
        return np.zeros((len(atracks), len(btracks)), dtype=np.float64)

    # Compute both IoU and center distance
    iou_cost = iou_distance(atracks, btracks)  # 1 - IoU, so lower = better
    center_cost = center_distance(atracks, btracks, max_center_dist)

    # For each pair, use IoU if there's enough overlap, else use center distance
    # IoU cost < (1 - iou_thresh) means IoU > iou_thresh
    has_iou = iou_cost < (1 - iou_thresh)

    # Combine: prefer IoU when available, else use center distance
    cost_matrix = np.where(has_iou, iou_cost, center_cost)

    return cost_matrix
