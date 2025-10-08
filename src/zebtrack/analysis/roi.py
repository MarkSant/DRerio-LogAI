# -*- coding: utf-8 -*-
"""
This module defines the ROIAnalyzer class for detailed behavioral analysis
within specific regions of interest (ROIs).
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import shapely
from shapely import prepare
from shapely.geometry import Point, Polygon, box

from zebtrack.analysis.behavior import BehavioralAnalyzer


class ROI:
    """A simple class to hold ROI data (name and geometry)."""

    def __init__(self, name: str, geometry: Polygon):
        self.name = name
        self.geometry = geometry


class ROIAnalyzer:
    """
    Performs spatial and behavioral analysis based on defined ROIs.
    """

    def __init__(
        self,
        behavior_analyzer: BehavioralAnalyzer,
        rois: List[ROI],
        flutter_n_frames: int = 3,
        inclusion_rule: str = "bbox_intersects",
        buffer_radius_value: Optional[float] = None,
        min_bbox_overlap_ratio: Optional[float] = None,
    ):
        """
        Initializes the ROIAnalyzer.

        Args:
            behavior_analyzer (BehavioralAnalyzer): An instance of
                BehavioralAnalyzer containing the full trajectory data.
            rois (List[ROI]): A list of ROI objects to be analyzed.
            flutter_n_frames (int): The number of consecutive frames an animal
                must be inside/outside an ROI to confirm an entry/exit event.
            inclusion_rule (str): Rule for determining ROI inclusion.
                Options: "centroid_in", "centroid_in_on_buffered_roi",
                "bbox_intersects", "seg_overlap"
            buffer_radius_value (Optional[float]): Radius for buffered ROI rule.
            min_bbox_overlap_ratio (Optional[float]): Minimum overlap ratio
                for bbox rule.
        """
        self._b_analyzer = behavior_analyzer
        self._rois = {roi.name: roi for roi in rois}
        self._trajectory = self._b_analyzer.trajectory_data.copy()
        self._flutter_n = flutter_n_frames
        self._inclusion_rule = inclusion_rule
        self._buffer_radius_value = buffer_radius_value or 0.5
        self._min_bbox_overlap_ratio = min_bbox_overlap_ratio or 0.10
        self._buffered_rois_cache = {}  # Cache for buffered ROI geometries
        self._validate_rois()
        self._calculate_presence_in_rois()

    @property
    def rois(self) -> Dict[str, ROI]:
        """Returns the dictionary of ROI objects."""
        return self._rois

    def _validate_rois(self):
        """Checks for empty or invalid ROIs."""
        if not self._rois:
            raise ValueError("ROI list cannot be empty.")
        for name, roi in self._rois.items():
            if not isinstance(roi.geometry, Polygon) or roi.geometry.is_empty:
                raise ValueError(f"ROI '{name}' has invalid geometry.")

    def _apply_flutter_filter(self, raw_presence: pd.Series) -> pd.Series:
        """
        Applies a flutter filter to a boolean series of presence data.

        An entry is confirmed after N consecutive `True` frames.
        An exit is confirmed after N consecutive `False` frames.
        The state during the transition period is maintained until confirmation.

        Args:
            raw_presence (pd.Series): The raw boolean series of presence.

        Returns:
            pd.Series: The stabilized boolean series.
        """
        if self._flutter_n <= 1:
            return raw_presence

        # True if the last N frames were all True (confirms entry)
        stable_true = raw_presence.rolling(self._flutter_n, min_periods=1).min() == 1
        # True if the last N frames were all False (confirms exit)
        stable_false = raw_presence.rolling(self._flutter_n, min_periods=1).max() == 0

        stable_presence = pd.Series(
            pd.NA, index=raw_presence.index, dtype="boolean"
        )
        stable_presence.loc[stable_true] = True
        stable_presence.loc[stable_false] = False

        stable_presence = stable_presence.ffill()
        stable_presence = stable_presence.fillna(False)
        stable_presence = stable_presence.astype(bool)

        return stable_presence

    def _calculate_presence_in_rois(self):
        """
        Calculates raw and stable presence for each ROI based on the
        configured inclusion rule. Also creates a single column with
        the current stable ROI name.
        """
        # Calculate time delta between frames for later use
        self._trajectory["dt"] = self._trajectory.index.to_series().diff()

        # Determine coordinate space and extract coordinates
        use_cm_coords = (
            "x_cm_smoothed" in self._trajectory.columns
            and "y_cm_smoothed" in self._trajectory.columns
            and not self._trajectory["x_cm_smoothed"].isna().all()
        )

        if use_cm_coords:
            x_coords = self._trajectory["x_cm_smoothed"].to_numpy()
            y_coords = self._trajectory["y_cm_smoothed"].to_numpy()
            coord_space = "cm"
        else:
            # Try x_center_px/y_center_px first, then derive from bbox
            if (
                "x_center_px" in self._trajectory.columns
                and "y_center_px" in self._trajectory.columns
                and not self._trajectory["x_center_px"].isna().all()
            ):
                x_coords = self._trajectory["x_center_px"].to_numpy()
                y_coords = self._trajectory["y_center_px"].to_numpy()
            elif all(
                col in self._trajectory.columns for col in ["x1", "y1", "x2", "y2"]
            ):
                x_coords = (
                    (self._trajectory["x1"] + self._trajectory["x2"]) / 2
                ).to_numpy()
                y_coords = (
                    (self._trajectory["y1"] + self._trajectory["y2"]) / 2
                ).to_numpy()
            else:
                raise ValueError(
                    "Cannot find suitable coordinate columns in trajectory data"
                )
            coord_space = "px"

        # Convert ROI geometries to appropriate coordinate space if needed
        rois_in_coord_space = self._get_rois_in_coordinate_space(coord_space)

        for name, roi_geometry in rois_in_coord_space.items():
            raw_presence = self._calculate_roi_presence_by_rule(
                roi_geometry, name, x_coords, y_coords, coord_space
            )

            self._trajectory[f"in_{name}_stable"] = self._apply_flutter_filter(
                raw_presence
            )

        # Create a single column with the name of the ROI the animal is in
        self._trajectory["stable_roi"] = "Outside"
        for name in self._rois:
            stable_col = f"in_{name}_stable"
            self._trajectory.loc[self._trajectory[stable_col], "stable_roi"] = name

    def _get_rois_in_coordinate_space(self, coord_space: str) -> Dict[str, Polygon]:
        """
        Ensures ROI geometries are in the correct coordinate space for analysis.
        Assumes that ROIs are originally defined in 'cm' space.
        """
        # If the analysis is happening in 'cm' space, ROIs are already correct.
        if coord_space == "cm":
            return {name: roi.geometry for name, roi in self._rois.items()}

        # If analysis is in 'px' space, convert ROIs from 'cm' to 'px'.
        elif coord_space == "px":
            if hasattr(self._b_analyzer, "pixelcm_x") and hasattr(
                self._b_analyzer, "pixelcm_y"
            ):
                rois_in_px = {}
                for name, roi in self._rois.items():
                    coords = list(roi.geometry.exterior.coords)
                    px_coords = [
                        (x * self._b_analyzer.pixelcm_x, y * self._b_analyzer.pixelcm_y)
                        for x, y in coords
                    ]
                    rois_in_px[name] = Polygon(px_coords)
                return rois_in_px
            else:
                # If no calibration, cannot convert. Assume ROIs are already in px.
                return {name: roi.geometry for name, roi in self._rois.items()}
        else:
            # Fallback: return original geometries if coord_space is unknown
            return {name: roi.geometry for name, roi in self._rois.items()}

    def _calculate_roi_presence_by_rule(
        self,
        roi_geometry: Polygon,
        roi_name: str,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        coord_space: str,
    ) -> pd.Series:
        """
        Calculate presence in ROI based on the configured inclusion rule.
        """
        if self._inclusion_rule == "centroid_in":
            return self._calculate_centroid_in(roi_geometry, x_coords, y_coords)
        elif self._inclusion_rule == "centroid_in_on_buffered_roi":
            return self._calculate_centroid_in_buffered(
                roi_geometry, roi_name, x_coords, y_coords, coord_space
            )
        elif self._inclusion_rule == "bbox_intersects":
            return self._calculate_bbox_intersects(roi_geometry, x_coords, y_coords)
        elif self._inclusion_rule == "seg_overlap":
            return self._calculate_seg_overlap(roi_geometry)
        else:
            raise ValueError(f"Unknown inclusion rule: {self._inclusion_rule}")

    def _calculate_centroid_in(
        self, roi_geometry: Polygon, x_coords: np.ndarray, y_coords: np.ndarray
    ) -> pd.Series:
        """Calculate presence using centroid inclusion (current behavior)."""
        prepare(roi_geometry)
        points = shapely.points(x_coords, y_coords)
        raw_presence_np = shapely.contains(roi_geometry, points)
        return pd.Series(raw_presence_np, index=self._trajectory.index)

    def _calculate_centroid_in_buffered(
        self,
        roi_geometry: Polygon,
        roi_name: str,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        coord_space: str,
    ) -> pd.Series:
        """Calculate presence using buffered ROI and centroid inclusion."""
        # Use cached buffered geometry if available
        cache_key = f"{roi_name}_{coord_space}_{self._buffer_radius_value}"
        if cache_key not in self._buffered_rois_cache:
            buffer_radius = self._buffer_radius_value
            # Note: buffer_radius is interpreted in cm when coord_space is cm,
            # px when coord_space is px
            self._buffered_rois_cache[cache_key] = roi_geometry.buffer(buffer_radius)

        buffered_roi = self._buffered_rois_cache[cache_key]
        prepare(buffered_roi)
        points = shapely.points(x_coords, y_coords)
        raw_presence_np = shapely.contains(buffered_roi, points)
        return pd.Series(raw_presence_np, index=self._trajectory.index)

    def _calculate_bbox_intersects(
        self, roi_geometry: Polygon, x_coords: np.ndarray, y_coords: np.ndarray
    ) -> pd.Series:
        """Calculate presence based on bbox intersection with ROI."""
        # Require bbox columns
        required_cols = ["x1", "y1", "x2", "y2"]
        missing_cols = [
            col for col in required_cols if col not in self._trajectory.columns
        ]
        if missing_cols:
            raise ValueError(
                f"Regra bbox_intersects requer colunas de bbox: {missing_cols}. "
                f"Essas colunas não estão disponíveis no dataset. "
                f"Considere usar 'centroid_in' ou 'centroid_in_on_buffered_roi'."
            )

        prepare(roi_geometry)
        raw_presence_list = []

        # Get video height for Y-axis inversion
        video_height_px = self._b_analyzer._video_height_px

        # Process frame by frame for bbox intersection calculation
        # TODO: This could be optimized for very large trajectories by chunking
        for idx, row in self._trajectory.iterrows():
            # Convert bbox from warped pixel space to cm, inverting Y-axis
            x1_cm = row["x1"] / self._b_analyzer._pixelcm_x
            y1_cm = (video_height_px - row["y1"]) / self._b_analyzer._pixelcm_y
            x2_cm = row["x2"] / self._b_analyzer._pixelcm_x
            y2_cm = (video_height_px - row["y2"]) / self._b_analyzer._pixelcm_y

            # Ensure min/max order (after Y inversion, y1 and y2 may swap)
            min_x = min(x1_cm, x2_cm)
            max_x = max(x1_cm, x2_cm)
            min_y = min(y1_cm, y2_cm)
            max_y = max(y1_cm, y2_cm)

            bbox = box(min_x, min_y, max_x, max_y)
            intersection = roi_geometry.intersection(bbox)
            if intersection.is_empty or bbox.area == 0:
                raw_presence_list.append(False)
            else:
                overlap_ratio = intersection.area / bbox.area
                raw_presence_list.append(overlap_ratio >= self._min_bbox_overlap_ratio)

        return pd.Series(raw_presence_list, index=self._trajectory.index)

    def _calculate_seg_overlap(self, roi_geometry: Polygon) -> pd.Series:
        """Calculate presence based on segmentation mask overlap."""
        # Check for segmentation data columns
        # Note: We don't persist segmentation masks in this PR,
        # so this will always error
        raise ValueError(
            "Regra seg_overlap requer dados de segmentação que não estão "
            "disponíveis neste dataset. "
            "Por favor, selecione outra regra de inclusão (centroid_in, "
            "centroid_in_on_buffered_roi, ou bbox_intersects)."
        )

    def get_time_spent_in_rois(self) -> Dict[str, Dict[str, float]]:
        """
        Calculates the total time (seconds and percentage) spent in each ROI.
        """
        results = {}
        total_time = self._trajectory["dt"].sum()
        if total_time == 0:
            return {name: {"seconds": 0.0, "percentage": 0.0} for name in self._rois}

        # Convert total_time Timedelta to seconds
        total_time_seconds = (
            total_time.total_seconds()
            if hasattr(total_time, 'total_seconds')
            else float(total_time)
        )

        for name in self._rois:
            time_in_roi = self._trajectory.loc[
                self._trajectory[f"in_{name}_stable"], "dt"
            ].sum()
            # Convert time_in_roi Timedelta to seconds
            time_in_roi_seconds = (
                time_in_roi.total_seconds()
                if hasattr(time_in_roi, 'total_seconds')
                else float(time_in_roi)
            )
            results[name] = {
                "seconds": time_in_roi_seconds,
                "percentage": (time_in_roi_seconds / total_time_seconds) * 100
                if total_time_seconds > 0
                else 0.0,
            }
        return results

    def get_latency_to_first_entry(self) -> Dict[str, Optional[float]]:
        """
        Calculates the latency to the first entry into each ROI.
        Returns None for a given ROI if the animal never enters it.
        """
        results = {}
        start_time = self._trajectory.index[0]

        for name in self._rois:
            entries = self._trajectory[f"in_{name}_stable"].diff() == 1
            first_entry_time = entries.idxmax() if entries.any() else None

            if (
                first_entry_time
                and self._trajectory.loc[first_entry_time, f"in_{name}_stable"]
            ):
                latency = first_entry_time - start_time
                # Convert Timedelta to seconds
                results[name] = (
                    latency.total_seconds()
                    if hasattr(latency, 'total_seconds')
                    else float(latency)
                )
            else:
                results[name] = None
        return results

    def get_entry_counts(self) -> Dict[str, int]:
        """Counts the number of entries into each ROI."""
        results = {}
        for name in self._rois:
            # An entry is a transition from False to True
            is_entry = self._trajectory[f"in_{name}_stable"].astype(int).diff() == 1
            results[name] = is_entry.sum()
        return results

    def get_exit_counts(self) -> Dict[str, int]:
        """Counts the number of exits from each ROI."""
        results = {}
        for name in self._rois:
            # An exit is a transition from True to False, which is a diff of -1.
            is_exit = self._trajectory[f"in_{name}_stable"].astype(int).diff() == -1
            results[name] = is_exit.sum()
        return results

    def get_inter_visit_latencies(self) -> Dict[str, List[float]]:
        """
        Calculates latencies for re-entries into each ROI.
        A re-entry latency is the time from the last exit from ANY ROI to the
        next entry into the specified ROI.
        """
        results = {}

        # Get all timestamps where the animal exits ANY ROI to 'Outside'
        exited_any_roi = (self._trajectory["stable_roi"] != "Outside") & (
            self._trajectory["stable_roi"].shift(-1) == "Outside"
        )
        all_exit_times = self._trajectory[exited_any_roi].index

        for name in self._rois:
            latencies = []
            # Get all entry timestamps for the current ROI
            entries = self._trajectory[f"in_{name}_stable"].diff() == 1
            entry_times = self._trajectory[entries].index

            # For each entry, find the most recent prior exit from any ROI
            for entry_time in entry_times:
                # Find the index of the exit that would be just before this entry
                # 'right' means if timestamps are equal, exit is considered after
                idx = all_exit_times.searchsorted(entry_time, side="right")
                if idx > 0:
                    # The most recent exit is at the previous index
                    last_exit_time = all_exit_times[idx - 1]
                    latencies.append(entry_time - last_exit_time)

            results[name] = latencies
        return results

    def get_roi_transitions(self) -> pd.DataFrame:
        """
        Calculates a transition matrix showing the count of direct movements
        between ROIs (and 'Outside').
        """
        states = self._trajectory["stable_roi"]
        # Compare current state with the state in the previous frame
        transitions = pd.crosstab(states, states.shift(-1), dropna=False)
        # Rename for clarity
        transitions.index.name = "From"
        transitions.columns.name = "To"
        return transitions

    def get_event_log(self) -> pd.DataFrame:
        """
        Generates a sequential log of all entry and exit events for all ROIs.

        Returns:
            A pandas DataFrame with columns for timestamp, event type, and ROI name,
            sorted chronologically.
        """
        states = self._trajectory["stable_roi"]
        # Find points where the state changes by comparing with the previous state
        state_changes = states[states != states.shift(1)]

        events = []
        # The initial state is an "entry" into wherever the animal starts
        initial_state = states.iloc[0]
        if initial_state != "Outside":
            events.append(
                {
                    "timestamp": states.index[0],
                    "event": "enter",
                    "roi_name": initial_state,
                }
            )

        # Iterate through the changes to log entries and exits
        for timestamp, current_roi in state_changes.items():
            # Skip the very first timestamp, as it's handled by the initial state
            if timestamp == states.index[0]:
                continue

            previous_roi = states.shift(1)[timestamp]

            # Log the exit from the previous ROI
            if previous_roi != "Outside":
                events.append(
                    {
                        "timestamp": timestamp,
                        "event": "exit",
                        "roi_name": previous_roi,
                    }
                )
            # Log the entry into the current ROI
            if current_roi != "Outside":
                events.append(
                    {
                        "timestamp": timestamp,
                        "event": "enter",
                        "roi_name": current_roi,
                    }
                )

        if not events:
            return pd.DataFrame(columns=["timestamp", "event", "roi_name"])

        event_df = pd.DataFrame(events).drop_duplicates()
        event_df.sort_values(by="timestamp", inplace=True)
        return event_df

    def _get_filtered_trajectory(self, roi_name: str) -> pd.DataFrame:
        """Helper to get trajectory segments only within a specific ROI."""
        if f"in_{roi_name}_stable" not in self._trajectory.columns:
            raise ValueError(f"Invalid ROI name: {roi_name}")
        return self._trajectory[self._trajectory[f"in_{roi_name}_stable"]]

    def get_distance_in_rois(self) -> Dict[str, float]:
        """Calculates the total distance traveled within each ROI."""
        results = {}
        # Calculate distance for all segments first
        if "segment_dist" not in self._trajectory.columns:
            self._trajectory["segment_dist"] = np.sqrt(
                self._trajectory["x_cm_smoothed"].diff() ** 2
                + self._trajectory["y_cm_smoothed"].diff() ** 2
            )

        for name in self._rois:
            # Sum the segment distances only for points within the ROI
            # We consider the distance for a segment to be "in" the ROI if the
            # endpoint of the segment is in the ROI.
            is_in_roi = self._trajectory[f"in_{name}_stable"]
            total_dist_in_roi = self._trajectory.loc[is_in_roi, "segment_dist"].sum()
            results[name] = total_dist_in_roi
        return results

    def get_velocity_stats_in_rois(self) -> Dict[str, Optional[Dict[str, float]]]:
        """Calculates velocity statistics within each ROI."""
        results = {}
        # Ensure velocity is calculated on the base analyzer
        if "v_mag" not in self._b_analyzer.trajectory_data.columns:
            self._b_analyzer.calculate_velocity_timeseries()

        for name in self._rois:
            roi_traj = self._get_filtered_trajectory(name)
            if roi_traj.empty:
                results[name] = None
                continue

            v_mag = roi_traj["v_mag"].dropna()
            results[name] = {
                "mean": v_mag.mean(),
                "median": v_mag.median(),
                "std_dev": v_mag.std(),
            }
        return results

    def get_freezing_in_rois(
        self, vel_threshold: float, min_duration: float
    ) -> Dict[str, Dict[str, Any]]:
        """Calculates freezing episodes that occur within each ROI."""
        results = {}
        # Ensure freezing episodes are detected on the base analyzer
        freezing_episodes = self._b_analyzer.detect_freezing_episodes(
            vel_threshold, min_duration
        )

        for name in self._rois:
            roi_episodes = []
            for episode in freezing_episodes:
                # Check if the episode occurred inside the ROI
                # We can check the start, mid, or end point. Let's use the start.
                start_t = episode["start_time"]
                if start_t in self._trajectory.index:
                    traj_at_start = self._trajectory.loc[start_t]
                    if traj_at_start[f"in_{name}_stable"]:
                        roi_episodes.append(episode)

            results[name] = {
                "count": len(roi_episodes),
                "total_duration": sum(e["duration"] for e in roi_episodes),
                "episodes": roi_episodes,
            }
        return results

    def get_tortuosity_in_rois(self) -> Dict[str, Optional[float]]:
        """Calculates trajectory tortuosity within each ROI."""
        results = {}
        for name in self._rois:
            roi_traj = self._get_filtered_trajectory(name)
            if len(roi_traj) < 2:
                results[name] = None
                continue

            # Path distance is the sum of segment lengths
            path_distance = np.sqrt(
                roi_traj["x_cm_smoothed"].diff() ** 2
                + roi_traj["y_cm_smoothed"].diff() ** 2
            ).sum()

            # Straight-line distance from start to end point
            start_point = roi_traj.iloc[0]
            end_point = roi_traj.iloc[-1]
            straight_dist = np.sqrt(
                (end_point["x_cm_smoothed"] - start_point["x_cm_smoothed"]) ** 2
                + (end_point["y_cm_smoothed"] - start_point["y_cm_smoothed"]) ** 2
            )

            if straight_dist > 0:
                results[name] = path_distance / straight_dist
            else:
                results[name] = np.inf if path_distance > 0 else 1.0
        return results

    def analyze_center_vs_periphery(self, method: str, value: float) -> Dict[str, Any]:
        """
        Generates center and periphery ROIs and runs a full analysis on them.

        Args:
            method (str): The method to define the center zone,
                          either 'distance' (cm) or 'area_ratio' (0.0-1.0).
            value (float): The corresponding value for the method.

        Returns:
            A dictionary with analysis results for 'Center' and 'Periphery'.
        """
        from shapely.affinity import scale

        arena = self._b_analyzer.arena_polygon_cm
        if method == "distance":
            center_poly = arena.buffer(-value)
        elif method == "area_ratio":
            if not 0 < value < 1:
                raise ValueError("Area ratio must be between 0 and 1.")
            # Scale the polygon's geometry around its centroid
            center_poly = scale(arena, xfact=np.sqrt(value), yfact=np.sqrt(value))
        else:
            raise ValueError("Method must be 'distance' or 'area_ratio'.")

        if not center_poly.is_valid or center_poly.is_empty:
            raise ValueError(
                "Could not generate a valid center zone with the given parameters."
            )

        periphery_poly = arena.difference(center_poly)

        # Create temporary ROIs
        center_roi = ROI(name="Center", geometry=center_poly)
        periphery_roi = ROI(name="Periphery", geometry=periphery_poly)

        # Create a temporary analyzer instance to run the analysis
        temp_analyzer = ROIAnalyzer(
            self._b_analyzer, [center_roi, periphery_roi], self._flutter_n
        )

        # Gather all results
        results = {
            "time_spent": temp_analyzer.get_time_spent_in_rois(),
            "latency_first_entry": temp_analyzer.get_latency_to_first_entry(),
            "entry_counts": temp_analyzer.get_entry_counts(),
            "inter_visit_latencies": temp_analyzer.get_inter_visit_latencies(),
            "distance": temp_analyzer.get_distance_in_rois(),
            "velocity_stats": temp_analyzer.get_velocity_stats_in_rois(),
            "tortuosity": temp_analyzer.get_tortuosity_in_rois(),
            "transitions": temp_analyzer.get_roi_transitions().to_dict("index"),
        }
        return results

    @staticmethod
    def analyze_social_proximity(
        full_trajectory_df: pd.DataFrame,
        radius_cm: float,
        pixelcm_x: float,
        pixelcm_y: float,
    ) -> Dict[str, Any]:
        """
        Performs social proximity analysis on a multi-animal trajectory DataFrame.

        Args:
            full_trajectory_df (pd.DataFrame): DataFrame with all animal tracks.
            radius_cm (float): The radius of the circular dynamic ROI.
            pixelcm_x (float): Pixel-to-cm conversion factor for x-axis.
            pixelcm_y (float): Pixel-to-cm conversion factor for y-axis.

        Returns:
            A dictionary with social metrics per animal.
        """
        try:
            import networkx as nx
        except ImportError:
            raise ImportError(
                "Please install 'networkx' to use social proximity analysis."
            )

        if "track_id" not in full_trajectory_df.columns:
            raise ValueError("Input DataFrame must contain a 'track_id' column.")

        # Use geometric mean for radius in pixels for more accuracy
        radius_px = radius_cm * np.sqrt(pixelcm_x * pixelcm_y)

        df = full_trajectory_df.copy()
        df["is_in_group"] = False
        df["group_id"] = -1

        # Group by frame number to process each time step
        grouped_by_frame = df.groupby("frame")

        for frame_id, frame_df in grouped_by_frame:
            if len(frame_df) < 2:
                continue

            animals = frame_df.index
            positions = {
                idx: (r["x_center_px"], r["y_center_px"])
                for idx, r in frame_df.iterrows()
            }

            # Create dynamic circular ROIs
            rois = {idx: Point(pos).buffer(radius_px) for idx, pos in positions.items()}

            # Build graph of interactions
            G = nx.Graph()
            G.add_nodes_from(animals)

            from itertools import combinations

            for animal1, animal2 in combinations(animals, 2):
                if rois[animal1].intersects(rois[animal2]):
                    G.add_edge(animal1, animal2)

            # Find social groups (connected components)
            social_groups = list(nx.connected_components(G))

            for group_idx, group in enumerate(social_groups):
                if len(group) > 1:
                    # Mark all animals in this group
                    member_indices = list(group)
                    df.loc[member_indices, "is_in_group"] = True
                    df.loc[member_indices, "group_id"] = f"{frame_id}-{group_idx}"

        # Calculate total time in social group for each animal
        df["dt"] = df.index.to_series().diff()  # first element remains NaN

        social_time = df[df["is_in_group"]].groupby("track_id")["dt"].sum()
        total_time = df.groupby("track_id")["dt"].sum()

        social_time_percent = (social_time / total_time * 100).fillna(0)

        results = {
            "social_time_seconds": social_time.to_dict(),
            "social_time_percentage": social_time_percent.to_dict(),
        }
        return results
