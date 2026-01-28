import numpy as np
import structlog

from zebtrack.tracker import matching
from zebtrack.tracker.basetrack import BaseTrack, TrackState
from zebtrack.tracker.kalman_filter import KalmanFilter

log = structlog.get_logger()


class STrack(BaseTrack):
    def __init__(self, tlwh, score):
        # wait activate
        self._tlwh = np.asarray(tlwh, dtype=np.float64)

        self.kalman_filter = None
        self.mean, self.covariance = None, None
        self.is_activated = False

        self.score = score
        self.tracklet_len = 0

    def predict(self):
        mean_state = self.mean.copy()
        if self.state != TrackState.Tracked:
            mean_state[7] = 0

        self.mean, self.covariance = self.kalman_filter.predict(mean_state, self.covariance)

    @staticmethod
    def multi_predict(stracks, kalman_filter):
        """
        Predict next states for multiple tracks using the provided Kalman filter.

        Args:
            stracks: List of STrack instances to predict
            kalman_filter: KalmanFilter instance to use for prediction (thread-safe)

        Note:
            Previously used shared class-level kalman_filter which caused race conditions
            in multi-threaded scenarios. Now requires explicit filter instance.
        """
        if len(stracks) > 0:
            multi_mean = np.asarray([st.mean.copy() for st in stracks])
            multi_covariance = np.asarray([st.covariance for st in stracks])
            for i, st in enumerate(stracks):
                if st.state != TrackState.Tracked:
                    multi_mean[i][7] = 0

            (
                multi_mean,
                multi_covariance,
            ) = kalman_filter.multi_predict(multi_mean, multi_covariance)

            for i, (mean, cov) in enumerate(zip(multi_mean, multi_covariance, strict=False)):
                stracks[i].mean = mean
                stracks[i].covariance = cov

    def activate(self, kalman_filter, frame_id):
        """Start a new tracklet"""
        self.kalman_filter = kalman_filter
        self.track_id = self.next_id()

        self.mean, self.covariance = self.kalman_filter.initiate(self.tlwh_to_xyah(self._tlwh))

        self.tracklet_len = 0
        self.state = TrackState.Tracked
        if frame_id == 1:
            self.is_activated = True

        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, new_track, frame_id, new_id=False):
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_track.tlwh)
        )
        self.tracklet_len = 0
        self.state = TrackState.Tracked
        self.is_activated = True
        self.frame_id = frame_id
        if new_id:
            self.track_id = self.next_id()
        self.score = new_track.score

    def update(self, new_track, frame_id):
        """
        Update a matched track
        :type new_track: STrack
        :type frame_id: int
        :type update_feature: bool
        :return:
        """
        self.frame_id = frame_id
        self.tracklet_len += 1

        new_tlwh = new_track.tlwh
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_tlwh)
        )

        self.state = TrackState.Tracked
        self.is_activated = True

        self.score = new_track.score

    @property
    def tlwh(self):
        """Get current position in bounding box format `(top left x, top left y,
        width, height)`.
        """
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[2] *= ret[3]
        ret[:2] -= ret[2:] / 2
        return ret

    @property
    def tlbr(self):
        """Convert bounding box to format `(min x, min y, max x, max y)`, i.e.,
        `(top left, bottom right)`.
        """
        ret = self.tlwh.copy()
        ret[2:] += ret[:2]
        return ret

    @staticmethod
    def tlwh_to_xyah(tlwh):
        """Convert bounding box to format `(center x, center y, aspect ratio,
        height)`, where the aspect ratio is `width / height`.
        """
        ret = np.asarray(tlwh).copy()
        ret[:2] += ret[2:] / 2
        if ret[3] > 0:
            ret[2] /= ret[3]
        else:
            ret[2] = 1.0
        return ret

    def to_xyah(self):
        return self.tlwh_to_xyah(self.tlwh)

    @staticmethod
    def tlbr_to_tlwh(tlbr):
        ret = np.asarray(tlbr).copy()
        ret[2:] -= ret[:2]
        return ret

    @staticmethod
    def tlwh_to_tlbr(tlwh):
        ret = np.asarray(tlwh).copy()
        ret[2:] += ret[:2]
        return ret

    def __repr__(self):
        return f"OT_{self.track_id}_({self.start_frame}-{self.end_frame})"


class BYTETracker:
    """ByteTrack multi-object tracker with hybrid IoU + center distance matching.

    Enhanced for sparse frame processing scenarios (e.g., analyzing every N frames)
    where small, fast-moving objects like zebrafish can move significantly between
    processed frames, causing IoU-based matching to fail.

    The hybrid matching strategy:
    1. First tries IoU-based matching (standard ByteTrack)
    2. Falls back to center-distance matching when IoU is zero

    Args:
        args: Namespace with track_thresh, match_thresh, track_buffer, mot20
        frame_rate: Video frame rate (default 30)
        use_hybrid_matching: Enable hybrid IoU + center distance (default True)
        max_center_distance: Max pixels for center-distance fallback (default 200)
        processing_interval: Frames between detections (default 1). When > 1,
            the Kalman filter dt is adjusted to correctly predict motion over
            larger time steps, critical for stable track IDs.
    """

    def __init__(
        self,
        args,
        frame_rate=30,
        use_hybrid_matching=True,
        max_center_distance=400.0,  # Default matches config.yaml
        processing_interval=1,
        iou_threshold=0.05,
        single_animal_mode=False,
    ):
        self.tracked_stracks = []
        self.lost_stracks = []
        self.removed_stracks = []

        self.frame_id = 0
        self.args = args

        self.det_thresh = args.track_thresh + 0.1
        # Scale buffer size by processing_interval to maintain equivalent
        # temporal window (e.g., 90 frames @ 30fps with interval=5 = 450 real frames)
        self.buffer_size = int(frame_rate / 30.0 * args.track_buffer * processing_interval)
        self.max_time_lost = self.buffer_size
        # Pass processing_interval as dt to Kalman filter for correct motion prediction
        self.kalman_filter = KalmanFilter(dt=float(processing_interval))

        # Hybrid matching parameters for sparse frame processing
        self.use_hybrid_matching = use_hybrid_matching
        self.max_center_distance = max_center_distance
        self.processing_interval = processing_interval
        self.iou_threshold = iou_threshold  # Min IoU to prefer IoU-based matching

        # Single animal mode: skip fuse_score to avoid confidence penalty
        # When there's only 1 animal, no risk of confusing with others
        self.single_animal_mode = single_animal_mode

        if self.single_animal_mode:
            # In single animal mode, we want to maintain the track as long as possible
            # and recover it even after long disappearances
            self.max_time_lost = self.buffer_size * 3  # Keep the ID alive longer
            self.det_thresh = 0.0  # Accept any detection as a candidate
            self.iou_threshold = 0.0  # Prefer center-distance fallback for big jumps

    def update(self, output_results, img_info, img_size):  # noqa: C901
        self.frame_id += 1

        activated_starcks = []
        refind_stracks = []
        removed_stracks = []

        # Assumes Ultralytics YOLO format (5 columns: x1, y1, x2, y2, confidence)
        # All current detectors provide this format
        if output_results.shape[1] == 5:
            scores = output_results[:, 4]
            bboxes = output_results[:, :4]
        else:
            # Defensive fallback - should not be reached with current detectors
            msg = (
                f"Unexpected detector output format: {output_results.shape[1]} columns (expected 5)"
            )
            raise ValueError(msg)

        img_h, img_w = img_info[0], img_info[1]
        scale = min(img_size[0] / float(img_h), img_size[1] / float(img_w))
        bboxes /= scale

        remain_inds = scores > self.args.track_thresh
        inds_low = scores > 0.1
        inds_high = scores < self.args.track_thresh

        inds_second = np.logical_and(inds_low, inds_high)
        dets_second = bboxes[inds_second]
        dets = bboxes[remain_inds]
        scores_keep = scores[remain_inds]
        scores_second = scores[inds_second]

        if len(dets) > 0:
            """Detections"""
            detections = [
                STrack(STrack.tlbr_to_tlwh(tlbr), s)
                for (tlbr, s) in zip(dets, scores_keep, strict=False)
            ]
        else:
            detections = []

        """ Add newly detected tracklets to tracked_stracks"""
        unconfirmed = []
        tracked_stracks = []

        for track in self.tracked_stracks:
            if not track.is_activated:
                unconfirmed.append(track)
            else:
                tracked_stracks.append(track)

        """ Step 2: First association, with high score detection boxes"""

        strack_pool = joint_stracks(tracked_stracks, self.lost_stracks)
        # Predict the current location with KF
        STrack.multi_predict(strack_pool, self.kalman_filter)

        # Use hybrid matching for better handling of fast-moving small objects
        if self.use_hybrid_matching:
            dists = matching.hybrid_iou_center_distance(
                strack_pool,
                detections,
                iou_thresh=self.iou_threshold,  # Configurable IoU threshold
                max_center_dist=self.max_center_distance,
            )
        else:
            dists = matching.iou_distance(strack_pool, detections)

        # Apply fuse_score only when multiple animals possible
        # In single animal mode, skip to avoid confidence penalty on matching
        if not self.args.mot20 and not self.single_animal_mode:
            dists = matching.fuse_score(dists, detections)

        # DEBUG: Inspect match threshold and cost matrix
        if len(dists) > 0:
            log.debug(
                "detector.bytetrack.association_debug",
                match_thresh=self.args.match_thresh,
                min_cost=float(dists.min()) if dists.size > 0 else -1.0,
                max_cost=float(dists.max()) if dists.size > 0 else -1.0,
                matrix_shape=dists.shape,
            )

        matches, u_track, u_detection = matching.linear_assignment(
            dists, thresh=self.args.match_thresh
        )

        for itracked, idet in matches:
            track = strack_pool[itracked]
            det = detections[idet]
            if track.state == TrackState.Tracked:
                track.update(detections[idet], self.frame_id)
                activated_starcks.append(track)
            else:
                track.re_activate(det, self.frame_id, new_id=False)
                refind_stracks.append(track)

        """ Step 3: Association the unconfirmed to the high score detections"""
        detections_unconfirmed = [detections[i] for i in u_detection]

        # Use hybrid matching for unconfirmed tracks too
        if self.use_hybrid_matching:
            dists = matching.hybrid_iou_center_distance(
                unconfirmed,
                detections_unconfirmed,
                iou_thresh=self.iou_threshold,
                max_center_dist=self.max_center_distance,
            )
        else:
            dists = matching.iou_distance(unconfirmed, detections_unconfirmed)

        matches_unconfirmed, u_unconfirmed, u_detection_rem = matching.linear_assignment(
            dists, thresh=0.7
        )

        for itracked, idet in matches_unconfirmed:
            unconfirmed[itracked].update(detections_unconfirmed[idet], self.frame_id)
            activated_starcks.append(unconfirmed[itracked])

        for it in u_unconfirmed:
            track = unconfirmed[it]
            if self.single_animal_mode:
                # Keep the candidate alive so it can be resurrected instead of discarded
                track.mark_lost()
                self.lost_stracks.append(track)
            else:
                track.mark_removed()
                removed_stracks.append(track)

        """ Step 4: Second association, with low score detection boxes"""
        # association the untrack to the low score detections
        if len(dets_second) > 0:
            """Detections"""
            detections_second = [
                STrack(STrack.tlbr_to_tlwh(tlbr), s)
                for (tlbr, s) in zip(dets_second, scores_second, strict=False)
            ]
        else:
            detections_second = []
        r_tracked_stracks = [
            strack_pool[i] for i in u_track if strack_pool[i].state == TrackState.Tracked
        ]
        # Use hybrid matching for second association as well
        if self.use_hybrid_matching:
            dists = matching.hybrid_iou_center_distance(
                r_tracked_stracks,
                detections_second,
                iou_thresh=self.iou_threshold,
                max_center_dist=self.max_center_distance,
            )
        else:
            dists = matching.iou_distance(r_tracked_stracks, detections_second)
        # DEBUG: Second association details
        if len(dists) > 0:
            log.debug(
                "detector.bytetrack.second_association_debug",
                match_thresh=self.args.match_thresh,
                min_cost=float(dists.min()) if dists.size > 0 else -1.0,
                num_tracks=len(r_tracked_stracks),
                num_dets=len(detections_second),
            )

        matches, u_track, u_detection_second = matching.linear_assignment(
            dists, thresh=self.args.match_thresh
        )

        for itracked, idet in matches:
            track = r_tracked_stracks[itracked]
            det = detections_second[idet]
            if track.state == TrackState.Tracked:
                track.update(det, self.frame_id)
                activated_starcks.append(track)
                # log.debug("detector.bytetrack.match.second_pass",
                #           track_id=track.track_id, reason="matched_low_score_det")
            else:
                track.re_activate(det, self.frame_id, new_id=False)
                refind_stracks.append(track)
                # log.debug("detector.bytetrack.reactivate.second_pass",
                #           track_id=track.track_id, reason="refound_low_score_det")

        for it in u_track:
            track = r_tracked_stracks[it]
            if not track.state == TrackState.Lost:
                track.mark_lost()
                self.lost_stracks.append(track)

        """ Step 5: Init new stracks"""
        # Use the remaining detections from the unconfirmed association step
        # AND the remaining low score detections from the second association step
        # (if single animal mode)

        # Candidates for new tracks (or resurrection)
        candidates = [detections_unconfirmed[i] for i in u_detection_rem]

        if self.single_animal_mode:
            # In single animal mode, we want to consider ALL detections that weren't matched
            # even low score ones that failed association in Step 4
            detections_second_unmatched = [detections_second[i] for i in u_detection_second]
            candidates.extend(detections_second_unmatched)

        for track in candidates:
            if track.score < self.det_thresh and not self.single_animal_mode:
                continue

            # SINGLE ANIMAL MODE: ID RESURRECTION STRATEGY
            # If we are in single animal mode, NEVER create a new ID if we have a lost one.
            # We assume there is only one fish. If we found a detection that didn't match
            # (likely due to a large jump/teleport), we force-match it to the lost track.
            if self.single_animal_mode:
                # Priority 1: Try to find a Lost track to resurrect
                if len(self.lost_stracks) > 0:
                    # Retrieve the most recently lost track (last in list usually,
                    # or sort by end_frame)
                    sorted_lost = sorted(self.lost_stracks, key=lambda t: t.end_frame, reverse=True)
                    refound_track = sorted_lost[0]

                    # Force resurrection with ID preservation (or force ID 1)
                    refound_track.re_activate(track, self.frame_id, new_id=False)
                    refound_track.track_id = 1  # Enforce ID 1
                    refind_stracks.append(refound_track)

                    # Remove from lost_stracks since it's found
                    self.lost_stracks.remove(refound_track)
                    continue

                # Priority 2: If no lost track, check if we already have a tracked one?
                # If we are here, it means we didn't match the tracked one in previous steps.
                # But if single_animal_mode is True, we should only have ONE track.
                # If tracked_stracks is not empty, we have a conflict (ghost track?).
                # We should probably ignore this new detection or kill the old track?
                # For now, let's assume if we are here, the old track is lost or new start.

            track.activate(self.kalman_filter, self.frame_id)

            # SINGLE ANIMAL MODE: IMMEDIATE ACTIVATION
            # Bypass "Unconfirmed" state. If we see it, it's the fish.
            if self.single_animal_mode:
                track.is_activated = True
                # Force stable ID=1 and keep counter consistent
                track.track_id = 1
                BaseTrack._count = max(BaseTrack._count, 1)

            activated_starcks.append(track)

        """ Step 6: Update state"""
        for track in self.lost_stracks:
            # In single animal mode, keep tracks alive much longer to allow recovery
            limit = self.max_time_lost * 2 if self.single_animal_mode else self.max_time_lost
            if self.frame_id - track.end_frame > limit:
                track.mark_removed()
                removed_stracks.append(track)

        self.tracked_stracks = [t for t in self.tracked_stracks if t.state == TrackState.Tracked]
        self.tracked_stracks = joint_stracks(self.tracked_stracks, activated_starcks)
        self.tracked_stracks = joint_stracks(self.tracked_stracks, refind_stracks)

        (
            self.tracked_stracks,
            self.lost_stracks,
        ) = remove_duplicate_stracks(self.tracked_stracks, self.lost_stracks)

        # get scores of lost tracks
        output_stracks = [track for track in self.tracked_stracks if track.is_activated]

        return output_stracks


def joint_stracks(tlista, tlistb):
    exists = {}
    res = []
    for t in tlista:
        exists[t.track_id] = 1
        res.append(t)
    for t in tlistb:
        tid = t.track_id
        if not exists.get(tid, 0):
            exists[tid] = 1
            res.append(t)
    return res


def sub_stracks(tlista, tlistb):
    stracks = {}
    for t in tlista:
        stracks[t.track_id] = t
    for t in tlistb:
        tid = t.track_id
        if stracks.get(tid, 0):
            del stracks[tid]
    return list(stracks.values())


def remove_duplicate_stracks(stracksa, stracksb):
    pdist = matching.iou_distance(stracksa, stracksb)
    pairs = np.where(pdist < 0.15)
    dupa, dupb = list(), list()
    for p, q in zip(*pairs, strict=False):
        timep = stracksa[p].frame_id - stracksa[p].start_frame
        timeq = stracksb[q].frame_id - stracksb[q].start_frame
        if timep > timeq:
            dupb.append(q)
        else:
            dupa.append(p)

    resa = [t for i, t in enumerate(stracksa) if i not in dupa]
    resb = [t for i, t in enumerate(stracksb) if i not in dupb]

    return resa, resb
