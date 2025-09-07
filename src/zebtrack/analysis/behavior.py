# -*- coding: utf-8 -*-
"""
This module defines the abstract base class for behavioral analysis of trajectory data.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from shapely.geometry import Polygon


class BehavioralAnalyzer(ABC):
    """
    An abstract base class for analyzing animal trajectory data.

    This class provides a robust and extensible foundation for behavioral analysis.
    It handles initial data preprocessing, including unit conversion and trajectory
    smoothing, and defines a standard interface for various behavioral metrics.

    Attributes:
        _trajectory_data (pd.DataFrame): A DataFrame containing the preprocessed
            trajectory data, including timestamps, original and converted
            coordinates, and smoothed trajectory.
        _pixelcm_x (float): The conversion factor from pixels to cm for the x-axis.
        _pixelcm_y (float): The conversion factor from pixels to cm for the y-axis.
        _arena_polygon_cm (Polygon): The arena geometry converted to cm.
    """

    def __init__(
        self,
        trajectory_df: pd.DataFrame,
        pixelcm_x: float,
        pixelcm_y: float,
        video_height_px: int,
        arena_polygon_px: List[Tuple[float, float]],
        fps: float = 30.0,
        window_length: int = 7,
        polyorder: int = 3,
    ):
        """
        Initializes the BehavioralAnalyzer and performs preprocessing.

        Args:
            trajectory_df (pd.DataFrame): DataFrame containing raw trajectory
                data. Must include 'timestamp', 'x_center_px', 'y_center_px',
                and bounding box columns ('x1', 'y1', 'x2', 'y2').
            pixelcm_x (float): The conversion factor for pixels to cm (x-axis).
            pixelcm_y (float): The conversion factor for pixels to cm (y-axis).
            video_height_px (int): The total height of the video in pixels,
                used for inverting the Y-axis.
            arena_polygon_px (List[Tuple[float, float]]): A list of (x, y)
                tuples defining the arena's vertices in pixels.
            fps (float, optional): Frames per second of the source video.
                Defaults to 30.0.
            window_length (int, optional): The window length for the
                Savitzky-Golay filter. Must be an odd integer. Defaults to 7.
            polyorder (int, optional): The polynomial order for the
                Savitzky-Golay filter. Must be less than window_length.
                Defaults to 3.
        """
        if polyorder >= window_length:
            raise ValueError("polyorder must be less than window_length.")

        self._pixelcm_x = pixelcm_x
        self._pixelcm_y = pixelcm_y
        self._video_height_px = video_height_px
        self.fps = fps

        # Store arena geometry in cm
        arena_coords_cm = [
            (x / self._pixelcm_x, (video_height_px - y) / self._pixelcm_y)
            for x, y in arena_polygon_px
        ]
        self._arena_polygon_cm = Polygon(arena_coords_cm)

        # Create and preprocess the trajectory DataFrame
        self._trajectory_data = self._preprocess_data(
            trajectory_df, video_height_px, window_length, polyorder
        )

    def _preprocess_data(
        self,
        df: pd.DataFrame,
        video_height_px: int,
        window_length: int,
        polyorder: int,
    ) -> pd.DataFrame:
        """Performs data conversion, cleaning, and smoothing."""
        if "timestamp" not in df.columns:
            raise ValueError(
                "Input DataFrame must include a 'timestamp' column for proper "
                "temporal analysis."
            )
        df.set_index("timestamp", inplace=True)

        # Convert units from pixels to cm and invert Y-axis for the centroid
        df["x_cm"] = df["x_center_px"] / self._pixelcm_x
        df["y_cm"] = (video_height_px - df["y_center_px"]) / self._pixelcm_y

        # Drop any rows with missing data before smoothing
        df.dropna(subset=["x_cm", "y_cm"], inplace=True)

        if len(df) < window_length:
            # Not enough data to apply the filter, use unsmoothed data
            df["x_cm_smoothed"] = df["x_cm"]
            df["y_cm_smoothed"] = df["y_cm"]
        else:
            # Apply Savitzky-Golay filter for smoothing
            df["x_cm_smoothed"] = savgol_filter(df["x_cm"], window_length, polyorder)
            df["y_cm_smoothed"] = savgol_filter(df["y_cm"], window_length, polyorder)

        return df

    @abstractmethod
    def calculate_total_distance(self, max_time_gap: Optional[float] = None) -> float:
        """
        Calculates the total distance traveled along the smoothed trajectory.

        Args:
            max_time_gap (Optional[float]): If the time between consecutive
                points exceeds this value (in seconds), the distance segment
                is ignored. This handles tracking gaps.

        Returns:
            float: The total distance traveled in cm.
        """
        pass

    @abstractmethod
    def calculate_velocity_timeseries(self) -> pd.DataFrame:
        """
        Calculates the velocity time series from the smoothed trajectory.

        The velocity is computed as the first derivative of the position.

        Returns:
            pd.DataFrame: A DataFrame with columns for velocity components
            (vx, vy) and the total velocity magnitude (v_mag).
        """
        pass

    def get_velocity_stats(self) -> Dict[str, float]:
        """
        Calculates summary statistics for the velocity magnitude.

        This is a concrete method that relies on the output of
        `calculate_velocity_timeseries`.

        Returns:
            Dict[str, float]: A dictionary containing the mean, median,
            and standard deviation of the velocity magnitude.
        """
        velocity_df = self.calculate_velocity_timeseries()
        if "v_mag" not in velocity_df.columns:
            raise KeyError(
                "The DataFrame from calculate_velocity_timeseries must "
                "contain a 'v_mag' column."
            )

        v_mag = velocity_df["v_mag"].dropna()
        stats = {
            "mean": v_mag.mean(),
            "median": v_mag.median(),
            "std_dev": v_mag.std(),
        }
        return stats

    @abstractmethod
    def detect_freezing_episodes(
        self, vel_threshold: float, min_duration: float
    ) -> List[Dict[str, float]]:
        """
        Detects freezing episodes based on a velocity threshold.

        A freezing episode starts when velocity drops below `vel_threshold`
        and lasts for at least `min_duration`.

        Args:
            vel_threshold (float): The velocity threshold (in cm/s).
            min_duration (float): The minimum duration (in seconds) to be
                considered a freezing episode.

        Returns:
            List[Dict[str, float]]: A list of dictionaries, where each
            dictionary represents a freezing episode and contains 'start_time',
            'end_time', and 'duration'.
        """
        pass

    @abstractmethod
    def get_angular_velocity(self, unit: str = "degrees") -> pd.Series:
        """
        Calculates the angular velocity of the trajectory.

        This is derived from the temporal derivative of the trajectory's angle.

        Args:
            unit (str): The desired output unit, either 'degrees' or 'radians'.
                Defaults to 'degrees'.

        Returns:
            pd.Series: A time series of the angular velocity.
        """
        pass

    @abstractmethod
    def get_tortuosity(
        self, window_size: Optional[float] = None, step: Optional[float] = None
    ) -> Union[float, pd.Series]:
        """
        Calculates the tortuosity of the trajectory.

        Tortuosity is the ratio of the actual path distance to the straight-line
        distance between the start and end points.

        Args:
            window_size (Optional[float]): The size of the sliding window in
                seconds. If None, calculates tortuosity for the entire trajectory.
            step (Optional[float]): The step size for the sliding window in
                seconds. Used only if `window_size` is specified.

        Returns:
            Union[float, pd.Series]: A single float for the total tortuosity,
            or a time series of tortuosity values if a sliding window is used.
        """
        pass

    @abstractmethod
    def get_thigmotaxis_timeseries(self) -> pd.Series:
        """
        Calculates the time series of distances to the nearest arena wall.

        For each point in the trajectory, this method computes the minimum
        Euclidean distance to the arena boundary.

        Returns:
            pd.Series: A time series of distances to the nearest wall in cm.
        """
        pass

    def calculate_thigmotaxis_index(
        self, method: str, distance_threshold: Optional[float] = None
    ) -> float:
        """
        Calculates a numerical index for thigmotaxis behavior.

        This concrete method supports two calculation logics:
        1. 'average_distance': The mean distance from the wall over the whole trial.
        2. 'time_near_wall': The percentage of time spent within a specified
           distance from the wall.

        Args:
            method (str): The calculation method, either 'average_distance' or
                'time_near_wall'.
            distance_threshold (Optional[float]): The distance threshold in cm,
                required only for the 'time_near_wall' method.

        Returns:
            float: The calculated thigmotaxis index.

        Raises:
            ValueError: If an unsupported method is specified or if
                `distance_threshold` is missing for the 'time_near_wall' method.
        """
        thigmotaxis_series = self.get_thigmotaxis_timeseries().dropna()
        if thigmotaxis_series.empty:
            return np.nan

        if method == "average_distance":
            return thigmotaxis_series.mean()

        if method == "time_near_wall":
            if distance_threshold is None:
                raise ValueError(
                    "'distance_threshold' is required for the 'time_near_wall' method."
                )

            # Get the boolean series of when the animal is near the wall
            is_near_wall = self.get_thigmotaxis_timeseries() < distance_threshold

            # Use the main trajectory dataframe to calculate time deltas
            df = self._trajectory_data.copy()

            # Align the 'is_near_wall' series with the main dataframe and fill NaNs
            df["is_near_wall"] = is_near_wall
            df["is_near_wall"] = df["is_near_wall"].fillna(False)

            # Calculate time difference between each point
            df["dt"] = df.index.to_series().diff()

            # Total time is the sum of all valid time deltas
            total_time = df["dt"].sum()
            if total_time == 0:
                return 0.0

            # Time near wall is the sum of deltas for intervals where the animal was
            # near the wall
            time_near = df.loc[df["is_near_wall"], "dt"].sum()

            return (time_near / total_time) * 100

        raise ValueError(f"Unsupported method for thigmotaxis index: {method}")


class ConcreteBehavioralAnalyzer(BehavioralAnalyzer):
    """
    A concrete implementation of BehavioralAnalyzer providing basic analysis methods.
    """

    def calculate_total_distance(self, max_time_gap: Optional[float] = None) -> float:
        df = self._trajectory_data
        if max_time_gap:
            time_diffs = df.index.to_series().diff()
            valid_segments = time_diffs <= max_time_gap
            df = df[valid_segments]

        distances = np.sqrt(
            df["x_cm_smoothed"].diff() ** 2 + df["y_cm_smoothed"].diff() ** 2
        )
        return distances.sum()

    def calculate_velocity_timeseries(self) -> pd.DataFrame:
        df = self._trajectory_data
        if "v_mag" in df.columns:
            return df

        dt = df.index.to_series().diff()
        dx = df["x_cm_smoothed"].diff()
        dy = df["y_cm_smoothed"].diff()

        df["vx"] = dx / dt
        df["vy"] = dy / dt
        df["v_mag"] = np.sqrt(df["vx"] ** 2 + df["vy"] ** 2)
        return df

    def detect_freezing_episodes(
        self, vel_threshold: float, min_duration: float
    ) -> List[Dict[str, float]]:
        self.calculate_velocity_timeseries()
        is_freezing = self._trajectory_data["v_mag"] < vel_threshold

        blocks = (is_freezing.diff() != 0).cumsum()
        freezing_blocks = self._trajectory_data[is_freezing].groupby(blocks)

        episodes = []
        for _, block in freezing_blocks:
            if not block.empty:
                start_time = block.index[0]
                end_time = block.index[-1]
                duration = end_time - start_time
                if duration >= min_duration:
                    episodes.append(
                        {
                            "start_time": start_time,
                            "end_time": end_time,
                            "duration": duration,
                        }
                    )
        return episodes

    def get_angular_velocity(self, unit: str = "degrees") -> pd.Series:
        # Simplified implementation
        dx = self._trajectory_data["x_cm_smoothed"].diff()
        dy = self._trajectory_data["y_cm_smoothed"].diff()
        angles = np.arctan2(dy, dx)
        dt = self._trajectory_data.index.to_series().diff()
        angular_vel = np.diff(angles) / dt[1:]
        if unit == "degrees":
            angular_vel = np.degrees(angular_vel)
        return pd.Series(angular_vel, index=self._trajectory_data.index[1:])

    def get_tortuosity(
        self, window_size: Optional[float] = None, step: Optional[float] = None
    ) -> Union[float, pd.Series]:
        # Implementation for the entire trajectory
        if window_size is not None:
            # Sliding window not implemented for this concrete class
            raise NotImplementedError("Sliding window tortuosity is not implemented.")

        path_distance = self.calculate_total_distance()

        start_point = self._trajectory_data.iloc[0]
        end_point = self._trajectory_data.iloc[-1]
        straight_dist = np.sqrt(
            (end_point["x_cm_smoothed"] - start_point["x_cm_smoothed"]) ** 2
            + (end_point["y_cm_smoothed"] - start_point["y_cm_smoothed"]) ** 2
        )

        if straight_dist > 0:
            return path_distance / straight_dist
        return np.inf if path_distance > 0 else 1.0

    def get_thigmotaxis_timeseries(self) -> pd.Series:
        # Not implemented for this concrete class
        raise NotImplementedError("Thigmotaxis is not implemented in this class.")

    def calculate_sharp_turns(
        self, threshold_deg_s: float, cooldown_s: float = 0.5
    ) -> Dict[str, float]:
        """
        Calculates the number of sharp turns based on angular velocity.

        Args:
            threshold_deg_s (float): The threshold in degrees per second to
                define a sharp turn.
            cooldown_s (float): The minimum time in seconds before another
                sharp turn can be detected.

        Returns:
            A dictionary with the count of sharp turns and the rate per minute.
        """
        df = self._trajectory_data
        if len(df) < 2:
            return {"sharp_turns_count": 0, "sharp_turns_per_minute": 0.0}

        # 1. Use smoothed trajectory
        x = df["x_cm_smoothed"]
        y = df["y_cm_smoothed"]

        # 2. Calculate displacements
        dx = x.diff()
        dy = y.diff()

        # 3. Calculate angle
        angle_rad = np.arctan2(dy, dx)

        # 4. Calculate change in angle
        d_theta = angle_rad.diff()

        # 5. Correct for wraparound from -pi to +pi
        d_theta = (d_theta + np.pi) % (2 * np.pi) - np.pi

        # 6. Convert to degrees
        d_theta_deg = np.degrees(d_theta)

        # 7. Calculate time interval in seconds
        dt = 1.0 / self.fps

        # 8. Calculate angular velocity
        angular_velocity_deg_s = d_theta_deg / dt

        # 9. Identify sharp turns
        potential_turns = angular_velocity_deg_s[
            angular_velocity_deg_s.abs() > threshold_deg_s
        ]

        if potential_turns.empty:
            return {"sharp_turns_count": 0, "sharp_turns_per_minute": 0.0}

        # Handle the first turn, then iterate and apply cooldown
        turn_times = potential_turns.index
        last_turn_time = turn_times[0]
        sharp_turns_count = 1
        cooldown_td = pd.to_timedelta(cooldown_s, unit="s")

        for timestamp in turn_times[1:]:
            if timestamp - last_turn_time > cooldown_td:
                sharp_turns_count += 1
                last_turn_time = timestamp

        # Calculate total duration for per-minute metric
        total_duration_s = (df.index[-1] - df.index[0]).total_seconds()
        total_duration_minutes = total_duration_s / 60.0

        if total_duration_minutes > 0:
            sharp_turns_per_minute = sharp_turns_count / total_duration_minutes
        else:
            sharp_turns_per_minute = 0.0

        return {
            "sharp_turns_count": sharp_turns_count,
            "sharp_turns_per_minute": sharp_turns_per_minute,
        }
