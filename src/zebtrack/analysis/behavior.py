"""This module defines the abstract base class for behavioral analysis of trajectory data."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, NotRequired, TypedDict

import numpy as np
import pandas as pd
import shapely
from scipy.signal import savgol_filter
from shapely.geometry import Polygon


class Episode(TypedDict):
    """Um episódio contíguo de um estado (congelamento, inatividade, rajada).

    ``start_time``/``end_time`` são rótulos do índice da trajetória, não
    floats: o índice é um ``TimedeltaIndex`` (ou ``DatetimeIndex``), e a
    anotação antiga ``dict[str, float]`` mentia sobre os três campos.

    ``track_id`` só aparece quando a trajetória tem mais de um animal — é o
    que permite a quem consome (``ROIAnalyzer._episode_row``) identificar a
    LINHA de origem, já que com vários sujeitos o timestamp sozinho não
    identifica linha nenhuma.
    """

    start_time: Any
    end_time: Any
    duration: float
    track_id: NotRequired[Any]


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
        arena_polygon_px: Sequence[Sequence[float]],
        fps: float = 30.0,
        window_length: int = 7,
        polyorder: int = 3,
        min_displacement_threshold_cm: float = 0.5,
        angle_calculation_window: int = 1,
        angular_velocity_smoothing_window: int = 3,
    ):
        """
        Initialize the BehavioralAnalyzer and performs preprocessing.

        Args:
            trajectory_df (pd.DataFrame): DataFrame containing raw trajectory
                data. Must include 'timestamp', 'x_center_px', 'y_center_px',
                and bounding box columns ('x1', 'y1', 'x2', 'y2').
            pixelcm_x (float): The conversion factor for pixels to cm (x-axis).
            pixelcm_y (float): The conversion factor for pixels to cm (y-axis).
            video_height_px (int): The total height of the video in pixels,
                used for inverting the Y-axis.
            arena_polygon_px (Sequence[Sequence[float]]): A list of (x, y)
                tuples defining the arena's vertices in pixels.
            fps (float, optional): Frames per second of the source video.
                Defaults to 30.0.
            window_length (int, optional): The window length for the
                Savitzky-Golay filter. Must be an odd integer. Defaults to 7.
            polyorder (int, optional): The polynomial order for the
                Savitzky-Golay filter. Must be less than window_length.
                Defaults to 3.
            min_displacement_threshold_cm (float, optional): Minimum displacement
                in cm to consider valid for angle calculation. Below this threshold,
                angular velocity is set to NaN to avoid noise amplification.
                Defaults to 0.5.
            angle_calculation_window (int, optional): Frame step for angle calculation.
                1 means consecutive frames, higher values create longer vectors.
                Defaults to 1.
            angular_velocity_smoothing_window (int, optional): Window size for
                moving average smoothing of angular velocities. Must be odd or 1
                (1 disables smoothing). Defaults to 3.
        """
        if polyorder is not None and window_length is not None and polyorder >= window_length:
            raise ValueError("polyorder must be less than window_length.")

        self._pixelcm_x = pixelcm_x
        self._pixelcm_y = pixelcm_y
        self._video_height_px = video_height_px
        self.fps = fps

        # Store angular velocity calculation parameters
        self._min_displacement_threshold_cm = min_displacement_threshold_cm
        self._angle_calculation_window = angle_calculation_window
        self._angular_velocity_smoothing_window = angular_velocity_smoothing_window

        # Store arena geometry in cm
        arena_coords_cm = [
            (x / self._pixelcm_x, (video_height_px - y) / self._pixelcm_y)
            for x, y in arena_polygon_px
        ]
        self._arena_polygon_cm = Polygon(arena_coords_cm)

        # Rótulo posicional de track (um inteiro por linha). Preenchido por
        # ``_preprocess_data``; ``_is_multi_track`` é falso quando há um único
        # sujeito — e nesse caso TODO o código abaixo cai no caminho histórico.
        self._track_labels: np.ndarray = np.zeros(0, dtype=np.int64)
        self._track_keys: list[Any] = []
        self._is_multi_track: bool = False

        # Create and preprocess the trajectory DataFrame
        self._trajectory_data = self._preprocess_data(
            trajectory_df, video_height_px, window_length, polyorder
        )

    @property
    def trajectory_data(self) -> pd.DataFrame:
        """Returns a copy of the preprocessed trajectory data."""
        return self._trajectory_data.copy()

    @property
    def is_multi_track(self) -> bool:
        """``True`` quando a trajetória contém mais de um ``track_id``."""
        return self._is_multi_track

    @property
    def track_labels(self) -> np.ndarray:
        """Rótulo inteiro de track por LINHA (posicional, não por rótulo).

        Posicional de propósito: com vários animais o índice (timestamp) tem
        duplicatas, e qualquer agrupamento por rótulo misturaria os sujeitos.
        """
        return self._track_labels

    @property
    def track_keys(self) -> list[Any]:
        """``track_id`` original de cada rótulo inteiro, na ordem dos rótulos."""
        return list(self._track_keys)

    @property
    def track_positions(self) -> list[np.ndarray]:
        """Índices POSICIONAIS das linhas de cada track, em ordem cronológica."""
        if not self._is_multi_track:
            return [np.arange(len(self._trajectory_data))]
        return [
            np.flatnonzero(self._track_labels == label) for label in range(len(self._track_keys))
        ]

    def diff_by_track(self, series: pd.Series) -> pd.Series:
        """``series.diff()`` que NÃO atravessa a fronteira entre animais.

        Com linhas de sujeitos diferentes intercaladas por frame, um ``.diff()``
        global alterna entre animais e o resultado é ruído: a "velocidade"
        medida seria a distância entre dois peixes dividida pelo intervalo.

        Com um único track devolve exatamente ``series.diff()`` — o caminho
        histórico segue bit a bit intacto.
        """
        if not self._is_multi_track:
            return series.diff()
        return series.groupby(self._track_labels).diff()

    @property
    def arena_polygon_cm(self) -> Polygon:
        """Returns the arena geometry as a Shapely Polygon in cm."""
        return self._arena_polygon_cm

    def _preprocess_data(
        self,
        df: pd.DataFrame,
        video_height_px: int,
        window_length: int,
        polyorder: int,
    ) -> pd.DataFrame:
        """Perform data conversion, cleaning, and smoothing."""
        if df.empty:
            raise ValueError(
                "Input DataFrame is empty. Cannot perform behavioral analysis on "
                "empty trajectory data."
            )
        if "timestamp" not in df.columns:
            raise ValueError(
                "Input DataFrame must include a 'timestamp' column for proper temporal analysis."
            )
        # Ensure the timestamp column is a TimedeltaIndex for calculations
        if pd.api.types.is_numeric_dtype(df["timestamp"]):
            # If timestamps are numbers (e.g., seconds), convert to timedelta
            df["timestamp"] = pd.to_timedelta(df["timestamp"], unit="s")
        elif pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            # If timestamps are datetimes, convert to time elapsed from start
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["timestamp"] = df["timestamp"] - df["timestamp"].iloc[0]

        if "track_id" in df.columns:
            numeric_ids = pd.to_numeric(df["track_id"], errors="coerce")
            df["track_id"] = numeric_ids.astype("Int64")

        df.set_index("timestamp", inplace=True)

        # Calculate center coordinates if not present (fallback for older data)
        if "x_center_px" not in df.columns and all(col in df.columns for col in ["x1", "x2"]):
            df["x_center_px"] = (df["x1"] + df["x2"]) / 2
        if "y_center_px" not in df.columns and all(col in df.columns for col in ["y1", "y2"]):
            df["y_center_px"] = (df["y1"] + df["y2"]) / 2

        # Consolida duplicatas do MESMO sujeito — nunca sujeitos diferentes.
        #
        # A agregação existe para as duplicatas de timestamp que o rastreador
        # gera para um mesmo animal. Agrupar SÓ pelo timestamp, porém, também
        # captura animais DIFERENTES vistos no mesmo instante e devolve a média
        # das posições: uma trajetória FANTASMA no ponto médio entre os peixes,
        # rotulada com o ``track_id`` de um deles. Nenhum animal esteve ali.
        # Por isso a chave inclui o ``track_id`` quando ele existe.
        if df.index.has_duplicates:
            agg_functions = {
                "x_center_px": "mean",
                "y_center_px": "mean",
                "x1": "mean",
                "y1": "mean",
                "x2": "mean",
                "y2": "mean",
            }
            # Add other columns if they exist
            if "confidence" in df.columns:
                agg_functions["confidence"] = "max"

            has_track = "track_id" in df.columns
            if not has_track:
                # Sem ``track_id`` não há como distinguir os sujeitos: o
                # comportamento histórico (média por timestamp) é o único
                # disponível.
                agg_functions["track_id"] = "first"

            # Filter the dictionary to only include columns present in the DataFrame
            valid_agg = {k: v for k, v in agg_functions.items() if k in df.columns}

            if has_track:
                index_name = df.index.name or "timestamp"
                keys = [df.index, df["track_id"]]
                df = df.groupby(keys, dropna=False, sort=False).agg(valid_agg)
                # ``groupby`` devolve MultiIndex (timestamp, track_id): o
                # ``track_id`` volta a ser coluna e o índice volta a ser só o
                # tempo, que é o contrato do resto do módulo.
                df = df.reset_index(level=1)
                df.index.name = index_name
                df.sort_index(kind="stable", inplace=True)
            else:
                df = df.groupby(df.index).agg(valid_agg)

        # Convert units from pixels to cm and invert Y-axis for the centroid
        df["x_cm"] = df["x_center_px"] / self._pixelcm_x
        df["y_cm"] = (video_height_px - df["y_center_px"]) / self._pixelcm_y

        # Drop any rows with missing data before smoothing
        df.dropna(subset=["x_cm", "y_cm"], inplace=True)

        # Os rótulos de track precisam existir ANTES da suavização: com vários
        # animais o Savitzky-Golay tem de rodar por sujeito.
        self._assign_track_labels(df)

        self._smooth_trajectory(df, window_length, polyorder)

        return df

    def _assign_track_labels(self, df: pd.DataFrame) -> None:
        """Fatora ``track_id`` em rótulos inteiros posicionais."""
        if "track_id" not in df.columns or df.empty:
            self._track_labels = np.zeros(len(df), dtype=np.int64)
            self._track_keys = []
            self._is_multi_track = False
            return

        # ``use_na_sentinel=False``: linhas sem ``track_id`` formam o seu
        # próprio grupo em vez de virarem o rótulo -1, que se misturaria com
        # um índice válido em qualquer indexação posicional.
        codes, uniques = pd.factorize(df["track_id"], use_na_sentinel=False)
        self._track_labels = np.asarray(codes, dtype=np.int64)
        self._track_keys = list(uniques)
        self._is_multi_track = len(uniques) > 1

    def _smooth_trajectory(self, df: pd.DataFrame, window_length: int, polyorder: int) -> None:
        """Aplica o Savitzky-Golay adaptativo, por sujeito quando há mais de um."""
        if not self._is_multi_track:
            self._smooth_slice(df, np.arange(len(df)), window_length, polyorder)
            return

        df["x_cm_smoothed"] = np.nan
        df["y_cm_smoothed"] = np.nan
        for label in range(len(self._track_keys)):
            positions = np.flatnonzero(self._track_labels == label)
            if positions.size:
                self._smooth_slice(df, positions, window_length, polyorder)

    def _smooth_slice(
        self,
        df: pd.DataFrame,
        positions: np.ndarray,
        window_length: int,
        polyorder: int,
    ) -> None:
        """Suaviza um bloco contíguo-por-sujeito de linhas (índices posicionais)."""
        n_points = positions.size
        whole_frame = n_points == len(df)

        # Adaptive Savitzky-Golay filter
        # Determine the largest possible odd window length
        adaptive_window = min(window_length, n_points)
        if adaptive_window % 2 == 0:
            adaptive_window -= 1

        # Ensure polyorder is less than the (potentially smaller) window
        adaptive_polyorder = min(polyorder, adaptive_window - 1)

        x_raw = df["x_cm"].to_numpy()[positions]
        y_raw = df["y_cm"].to_numpy()[positions]

        # Only apply filter if the window is large enough for the polynomial
        if adaptive_window > adaptive_polyorder and adaptive_window >= 3:
            x_smoothed = savgol_filter(x_raw, adaptive_window, adaptive_polyorder)
            y_smoothed = savgol_filter(y_raw, adaptive_window, adaptive_polyorder)
        else:
            # Fallback for very short data series
            x_smoothed = x_raw
            y_smoothed = y_raw

        if whole_frame:
            # Caminho histórico (sujeito único): atribuição direta da coluna,
            # sem passar por ``iloc``, para não alterar dtype nem ordem.
            df["x_cm_smoothed"] = x_smoothed
            df["y_cm_smoothed"] = y_smoothed
            return

        df.iloc[positions, df.columns.get_loc("x_cm_smoothed")] = x_smoothed
        df.iloc[positions, df.columns.get_loc("y_cm_smoothed")] = y_smoothed

    @abstractmethod
    def calculate_total_distance(self, max_time_gap: float | None = None) -> float:
        """
        Calculate the total distance traveled along the smoothed trajectory.

        Args:
            max_time_gap (float | None): If the time between consecutive
                points exceeds this value (in seconds), the distance segment
                is ignored. This handles tracking gaps.

        Returns:
            float: The total distance traveled in cm.
        """
        pass

    @abstractmethod
    def calculate_velocity_timeseries(self) -> pd.DataFrame:
        """
        Calculate the velocity time series from the smoothed trajectory.

        The velocity is computed as the first derivative of the position.

        Returns:
            pd.DataFrame: A DataFrame with columns for velocity components
            (vx, vy) and the total velocity magnitude (v_mag).
        """
        pass

    def get_velocity_stats(self) -> dict[str, float]:
        """
        Calculate summary statistics for the velocity magnitude.

        This is a concrete method that relies on the output of
        `calculate_velocity_timeseries`.

        Returns:
            Dict[str, float]: A dictionary containing the mean, median,
            standard deviation, and maximum of the velocity magnitude.
        """
        velocity_df = self.calculate_velocity_timeseries()
        if "v_mag" not in velocity_df.columns:
            raise KeyError(
                "The DataFrame from calculate_velocity_timeseries must contain a 'v_mag' column."
            )

        v_mag = velocity_df["v_mag"].dropna()
        stats = {
            "mean": v_mag.mean(),
            "median": v_mag.median(),
            "std_dev": v_mag.std(),
            "max": v_mag.max(),
        }
        return stats

    @abstractmethod
    def detect_freezing_episodes(
        self,
        min_duration: float,
        vel_threshold: float | None = None,
        threshold_method: str = "absolute",
        quantile: float = 0.1,
    ) -> list[Episode]:
        """
        Detect freezing episodes based on a velocity threshold.

        A freezing episode starts when velocity drops below a threshold
        and lasts for at least `min_duration`.

        Args:
            min_duration (float): The minimum duration (in seconds) to be
                considered a freezing episode.
            vel_threshold (float | None): The velocity threshold (in cm/s) for
                the 'absolute' method.
            threshold_method (str): 'absolute' or 'relative'. 'absolute' uses
                `vel_threshold`. 'relative' calculates the threshold based on
                the velocity distribution's quantile.
            quantile (float): The quantile to use for the 'relative' method.

        Returns:
            list[Episode]: One entry per freezing episode, with 'start_time',
            'end_time' and 'duration' — plus 'track_id' when the trajectory
            holds more than one animal.
        """
        pass

    @abstractmethod
    def get_angular_velocity(self, unit: str = "degrees") -> pd.Series:
        """
        Calculate the angular velocity of the trajectory.

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
        self, window_size: float | None = None, step: float | None = None
    ) -> float | pd.Series:
        """
        Calculate the tortuosity of the trajectory.

        Tortuosity is the ratio of the actual path distance to the straight-line
        distance between the start and end points.

        Args:
            window_size (float | None): The size of the sliding window in
                seconds. If None, calculates tortuosity for the entire trajectory.
            step (float | None): The step size for the sliding window in
                seconds. Used only if `window_size` is specified.

        Returns:
            Union[float, pd.Series]: A single float for the total tortuosity,
            or a time series of tortuosity values if a sliding window is used.
        """
        pass

    @abstractmethod
    def get_thigmotaxis_timeseries(self) -> pd.Series:
        """
        Calculate the time series of distances to the nearest arena wall.

        For each point in the trajectory, this method computes the minimum
        Euclidean distance to the arena boundary.

        Returns:
            pd.Series: A time series of distances to the nearest wall in cm.
        """
        pass

    def calculate_thigmotaxis_index(
        self, method: str, distance_threshold: float | None = None
    ) -> float:
        """
        Calculate a numerical index for thigmotaxis behavior.

        This concrete method supports two calculation logics:
        1. 'average_distance': The mean distance from the wall over the whole trial.
        2. 'time_near_wall': The percentage of time spent within a specified
           distance from the wall.

        Args:
            method (str): The calculation method, either 'average_distance' or
                'time_near_wall'.
            distance_threshold (float | None): The distance threshold in cm,
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
            df["dt"] = self.diff_by_track(df.index.to_series())

            # Total time is the sum of all valid time deltas
            total_time = df["dt"].sum()
            if total_time == 0:
                return 0.0

            # Time near wall is the sum of deltas for intervals where the animal was
            # near the wall
            time_near = df.loc[df["is_near_wall"], "dt"].sum()

            return (time_near / total_time) * 100

        raise ValueError(f"Unsupported method for thigmotaxis index: {method}")

    def get_geotaxis_timeseries(self) -> pd.Series:
        """Calculate distance to bottom of arena time series for geotaxis analysis.

        This metric is only meaningful for lateral perspective views where the
        Y-axis represents vertical position in the aquarium.

        Returns:
            Series with distance to bottom boundary in centimeters.
            Lower values indicate the animal is closer to the bottom.
        """
        df = self._trajectory_data
        if df.empty:
            return pd.Series([], dtype=np.float64, index=df.index, name="distance_to_bottom_cm")

        # Prefer smoothed coordinates but gracefully fall back to raw cm values
        y_series = df.get("y_cm_smoothed", pd.Series(dtype=np.float64))
        if y_series.empty or y_series.isna().all():
            y_series = df.get("y_cm", pd.Series(dtype=np.float64))

        if y_series.empty:
            return pd.Series(np.full(len(df), np.nan), index=df.index, name="distance_to_bottom_cm")

        # Get the bottom boundary (minimum Y) from the arena polygon
        if self._arena_polygon_cm.is_empty:
            return pd.Series(np.full(len(df), np.nan), index=df.index, name="distance_to_bottom_cm")

        # Extract the minimum Y coordinate as the bottom of the arena
        arena_min_y = self._arena_polygon_cm.bounds[1]  # bounds = (minx, miny, maxx, maxy)

        # Calculate distance from each point to the bottom
        distances = y_series.to_numpy() - arena_min_y

        # Ensure non-negative values (clamp if animal detected below arena)
        distances = np.maximum(distances, 0.0)

        return pd.Series(distances, index=df.index, name="distance_to_bottom_cm")

    def calculate_geotaxis_index(
        self,
        method: str = "average_distance",
        distance_threshold: float | None = None,
        num_zones: int | None = None,
        bottom_zones: int = 1,
    ) -> float | dict[str, float]:
        """Calculate geotaxis index (preference for bottom of aquarium).

        This metric is only meaningful for lateral perspective views.

        Args:
            method: Calculation method. One of:
                - "average_distance": Mean distance from bottom (cm)
                - "time_near_bottom": Percentage of time within distance_threshold of bottom
                - "zone_time": Percentage of time spent in each vertical zone

            distance_threshold: Distance threshold for "time_near_bottom" method (cm).
                Required when method is "time_near_bottom".

            num_zones: Number of vertical zones for "zone_time" method.
                Required when method is "zone_time".

            bottom_zones: Number of bottom zones to aggregate for "zone_time" (1 or 2).
                Default is 1 (only the bottom-most zone).

        Returns:
            For "average_distance" and "time_near_bottom": A single float value.
            For "zone_time": A dict mapping zone names to percentage of time.
        """
        geotaxis_series = self.get_geotaxis_timeseries().dropna()

        if geotaxis_series.empty:
            if method == "zone_time" and num_zones is not None:
                return {f"zone_{i}_pct": np.nan for i in range(num_zones)}
            return np.nan

        if method == "average_distance":
            return float(geotaxis_series.mean())

        if method == "time_near_bottom":
            if distance_threshold is None:
                raise ValueError("distance_threshold is required for 'time_near_bottom' method")
            is_near_bottom = geotaxis_series < distance_threshold
            return float(is_near_bottom.sum() / len(geotaxis_series) * 100)

        if method == "zone_time":
            if num_zones is None:
                raise ValueError("num_zones is required for 'zone_time' method")

            zone_series = self.get_vertical_zone_timeseries(num_zones)
            zone_series = zone_series.dropna()

            if zone_series.empty:
                return {f"zone_{i}_pct": np.nan for i in range(num_zones)}

            total_frames = len(zone_series)
            zone_percentages = {}

            for zone_idx in range(num_zones):
                frames_in_zone = (zone_series == zone_idx).sum()
                zone_percentages[f"zone_{zone_idx}_pct"] = float(
                    frames_in_zone / total_frames * 100
                )

            # Also calculate aggregated bottom zones
            if bottom_zones >= 1:
                bottom_frames = sum(
                    (zone_series == z).sum() for z in range(min(bottom_zones, num_zones))
                )
                zone_percentages["bottom_zones_pct"] = float(bottom_frames / total_frames * 100)

            return zone_percentages

        raise ValueError(
            f"Unknown method: {method}. Use 'average_distance', 'time_near_bottom', or 'zone_time'"
        )

    def get_vertical_zone_timeseries(self, num_zones: int) -> pd.Series:
        """Classify each frame into a vertical zone.

        Divides the arena height into equal vertical zones numbered from bottom to top.
        Zone 0 is the bottom-most zone, zone (num_zones - 1) is the top-most zone.

        Args:
            num_zones: Number of vertical zones to divide the arena into.

        Returns:
            Series with zone index (0 to num_zones-1) for each frame.
        """
        df = self._trajectory_data
        if df.empty or self._arena_polygon_cm.is_empty:
            return pd.Series([], dtype=np.int64, index=df.index, name="vertical_zone")

        # Prefer smoothed coordinates but gracefully fall back to raw cm values
        y_series = df.get("y_cm_smoothed", pd.Series(dtype=np.float64))
        if y_series.empty or y_series.isna().all():
            y_series = df.get("y_cm", pd.Series(dtype=np.float64))

        if y_series.empty:
            return pd.Series(np.full(len(df), -1), index=df.index, name="vertical_zone")

        # Get vertical bounds
        min_y, max_y = self._arena_polygon_cm.bounds[1], self._arena_polygon_cm.bounds[3]
        height = max_y - min_y

        if height <= 0:
            return pd.Series(np.full(len(df), -1), index=df.index, name="vertical_zone")

        zone_height = height / num_zones

        # Calculate zone index: floor((y - min_y) / zone_height)
        zone_indices = np.floor((y_series.to_numpy() - min_y) / zone_height).astype(int)

        # Clip indices to [0, num_zones - 1] to handle float errors or minor out-of-bounds
        zone_indices = np.clip(zone_indices, 0, num_zones - 1)

        return pd.Series(zone_indices, index=df.index, name="vertical_zone")


class ConcreteBehavioralAnalyzer(BehavioralAnalyzer):
    """A concrete implementation of BehavioralAnalyzer providing basic analysis methods."""

    def calculate_total_distance(self, max_time_gap: float | None = None) -> float:
        """Calculate total distance traveled in centimeters.

        Args:
            max_time_gap: Maximum time gap between points to consider continuous (seconds).
                Segments spanning a longer gap contribute zero.

        Returns:
            Total distance in centimeters.
        """
        df = self._trajectory_data

        # Os deslocamentos saem do quadro COMPLETO e só depois são zerados.
        # Descartar as linhas de lacuna antes do ``diff`` (como se fazia) não
        # remove o salto: apaga o ponto de reaparecimento e faz o ponto
        # SEGUINTE virar vizinho do último ponto antes da lacuna, de modo que a
        # distância atravessada continua sendo somada — só que atribuída a outro
        # par de frames. Era o oposto do que ``max_time_gap`` promete.
        dx = self.diff_by_track(df["x_cm_smoothed"])
        dy = self.diff_by_track(df["y_cm_smoothed"])
        distances = np.sqrt(dx**2 + dy**2)

        if max_time_gap is not None:
            time_diffs = self.diff_by_track(df.index.to_series())
            # Compare Timedelta with a Timedelta
            valid_segments = time_diffs <= pd.to_timedelta(max_time_gap, unit="s")
            distances = distances.where(valid_segments, 0.0)

        return distances.sum()

    def calculate_velocity_timeseries(self) -> pd.DataFrame:
        """Calculate velocity time series with vx, vy, and v_mag components.

        Returns:
            DataFrame with added velocity columns (vx, vy, v_mag in cm/s).
        """
        df = self._trajectory_data
        if "v_mag" in df.columns:
            return df

        if df.empty:
            df["vx"] = pd.Series(dtype=np.float64)
            df["vy"] = pd.Series(dtype=np.float64)
            df["v_mag"] = pd.Series(dtype=np.float64)
            return df

        dt_td = self.diff_by_track(df.index.to_series())
        dt_s = dt_td.dt.total_seconds()

        # Prevent division by zero or NaN/Inf results
        dt_s = dt_s.replace(0, np.nan)

        dx = self.diff_by_track(df["x_cm_smoothed"])
        dy = self.diff_by_track(df["y_cm_smoothed"])

        df["vx"] = dx / dt_s
        df["vy"] = dy / dt_s
        df["v_mag"] = np.sqrt(df["vx"] ** 2 + df["vy"] ** 2)
        return df

    def detect_freezing_episodes(
        self,
        min_duration: float,
        vel_threshold: float | None = None,
        threshold_method: str = "absolute",
        quantile: float = 0.1,
    ) -> list[Episode]:
        """Detect freezing episodes based on velocity threshold.

        Args:
            min_duration: Minimum duration for a freezing episode (seconds).
            vel_threshold: Velocity threshold (cm/s), or None to auto-detect.
            threshold_method: Method for threshold determination ("absolute" or "quantile").
            quantile: Quantile to use if threshold_method is "quantile" (0-1).

        Returns:
            List of Episode dicts ('start_time', 'end_time', 'duration', and
            'track_id' when there is more than one animal).
        """
        self.calculate_velocity_timeseries()
        v_mag = self._trajectory_data["v_mag"].fillna(0.0)

        if threshold_method == "relative":
            threshold = v_mag.quantile(quantile)
        elif threshold_method == "absolute":
            if vel_threshold is None:
                raise ValueError("vel_threshold must be set for 'absolute' method.")
            threshold = vel_threshold
        else:
            raise ValueError(f"Unknown threshold_method: {threshold_method}")

        is_freezing = (v_mag <= threshold).to_numpy(dtype=bool)
        # Blocos POSICIONAIS: com vários animais o índice tem timestamps
        # repetidos, e um ``groupby`` por rótulo alinharia linhas de sujeitos
        # diferentes dentro do mesmo episódio.
        block_ids = self._block_ids(is_freezing)
        freezing_rows = self._trajectory_data[is_freezing]
        freezing_blocks = freezing_rows.groupby(block_ids[is_freezing], sort=True)
        labels_in_mask = self._track_labels[is_freezing] if self._is_multi_track else None

        episodes = []
        offset = 0
        for _, block in freezing_blocks:
            size = len(block)
            if size:
                start_time = block.index[0]
                end_time = block.index[-1]
                duration = end_time - start_time
                if duration.total_seconds() >= min_duration:
                    episode: Episode = {
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": duration.total_seconds(),
                    }
                    if labels_in_mask is not None:
                        # O bloco nunca cruza sujeitos, então o rótulo da
                        # primeira linha identifica o episódio inteiro.
                        episode["track_id"] = self._track_keys[int(labels_in_mask[offset])]
                    episodes.append(episode)
            offset += size
        return episodes

    def _block_ids(self, mask: np.ndarray) -> np.ndarray:
        """IDs de bloco contíguo de mesmo valor que NÃO atravessam sujeitos.

        Sem o corte por sujeito, um episódio de congelamento "contíguo" poderia
        conter frames de dois peixes diferentes e ter a duração medida entre
        eles.
        """
        if mask.size == 0:
            return np.zeros(0, dtype=np.int64)

        changed = np.empty(mask.size, dtype=bool)
        changed[0] = True
        changed[1:] = mask[1:] != mask[:-1]
        if self._is_multi_track:
            changed[1:] |= self._track_labels[1:] != self._track_labels[:-1]
        return np.cumsum(changed) - 1

    def get_angular_velocity(self, unit: str = "degrees") -> pd.Series:
        """Calculate the angular velocity of the trajectory using a robust method.

        This method handles detection jitter and stationary states.

        This implementation addresses the numerical instability that occurs when
        calculating angles from very small displacement vectors. When the subject
        is nearly stationary, detector noise (jitter of 1-2 pixels) creates random
        micro-movements that generate spurious high angular velocities. This method
        filters out such noise by:

        1. Applying a minimum displacement threshold
        2. Supporting wider frame windows for angle calculation
        3. Optionally smoothing the resulting angular velocity series

        Args:
            unit (str): Unit for angular velocity. Only "degrees" is supported.

        Returns:
            pd.Series: Angular velocity in degrees/second, with NaN values where
                displacement is below threshold or data is insufficient.
        """
        if unit != "degrees":
            raise NotImplementedError(
                "Only 'degrees' unit is supported for this detailed implementation."
            )

        df = self._trajectory_data
        min_points = 2 * self._angle_calculation_window + 1
        if len(df) < min_points:
            return pd.Series(dtype=np.float64, name="angular_velocity_deg_s")

        angular_velocity_array = np.full(len(df), np.nan)
        if self._is_multi_track:
            # Por sujeito: as fatias deslocadas abaixo (prev/curr/next) só têm
            # sentido dentro de uma mesma trajetória. Atravessando animais elas
            # mediriam o ângulo entre peixes distintos.
            for positions in self.track_positions:
                if positions.size >= min_points:
                    angular_velocity_array[positions] = self._angular_velocity_slice(
                        df["x_cm_smoothed"].to_numpy()[positions],
                        df["y_cm_smoothed"].to_numpy()[positions],
                        df.index.to_series().iloc[positions],
                    )
        else:
            angular_velocity_array = self._angular_velocity_slice(
                df["x_cm_smoothed"].values,
                df["y_cm_smoothed"].values,
                df.index.to_series(),
            )

        # Convert to Series
        angular_velocity_series = pd.Series(
            angular_velocity_array,
            index=df.index,
            name="angular_velocity_deg_s",
        )

        # Apply optional smoothing to reduce remaining high-frequency noise
        if self._angular_velocity_smoothing_window > 1:
            # Use rolling window with center=True to avoid phase shift
            # min_periods=1 allows edges to have partial windows
            if self._is_multi_track:
                return (
                    angular_velocity_series.groupby(self._track_labels)
                    .rolling(
                        window=self._angular_velocity_smoothing_window,
                        center=True,
                        min_periods=1,
                    )
                    .mean()
                    .reset_index(level=0, drop=True)
                )
            smoothed = angular_velocity_series.rolling(
                window=self._angular_velocity_smoothing_window,
                center=True,
                min_periods=1,
            ).mean()
            return smoothed

        return angular_velocity_series

    def _angular_velocity_slice(
        self, x: np.ndarray, y: np.ndarray, timestamps: pd.Series
    ) -> np.ndarray:
        """Velocidade angular de UMA trajetória contígua (um só sujeito)."""
        # Initialize output array
        n_points = len(x)
        angular_velocity_array = np.full(n_points, np.nan)

        # Calculate angles using the specified window
        window = self._angle_calculation_window

        # Phase 7: Fully vectorized angular velocity computation
        # Slices: prev = [0 : n-2w], curr = [w : n-w], next = [2w : n]
        x_prev = x[: n_points - 2 * window]
        y_prev = y[: n_points - 2 * window]
        x_curr = x[window : n_points - window]
        y_curr = y[window : n_points - window]
        x_next = x[2 * window :]
        y_next = y[2 * window :]

        # Displacement vectors (incoming and outgoing)
        dx_in = x_curr - x_prev
        dy_in = y_curr - y_prev
        dx_out = x_next - x_curr
        dy_out = y_next - y_curr

        # Displacement magnitudes
        displacement_in = np.hypot(dx_in, dy_in)
        displacement_out = np.hypot(dx_out, dy_out)

        # Minimum displacement mask — skip near-stationary points
        valid_mask = (displacement_in >= self._min_displacement_threshold_cm) & (
            displacement_out >= self._min_displacement_threshold_cm
        )

        # Angles of the two vectors
        angle_in = np.arctan2(dy_in, dx_in)
        angle_out = np.arctan2(dy_out, dx_out)

        # Angular change with wraparound correction
        d_theta = angle_out - angle_in
        d_theta_normalized = (d_theta + np.pi) % (2 * np.pi) - np.pi
        d_theta_deg = np.degrees(d_theta_normalized)

        # Time intervals — vectorized via pandas Series
        t_prev = timestamps.iloc[: n_points - 2 * window].values
        t_next = timestamps.iloc[2 * window :].values
        dt = (t_next - t_prev).astype("timedelta64[ns]").astype(np.float64) / 1e9  # seconds

        # Combine masks: valid displacement AND positive time interval
        full_mask = valid_mask & (dt > 0)

        # Assign valid angular velocities to the output array
        result_slice = np.full(len(dx_in), np.nan)
        result_slice[full_mask] = d_theta_deg[full_mask] / dt[full_mask]
        angular_velocity_array[window : n_points - window] = result_slice

        return angular_velocity_array

    def get_angular_velocity_stats(self) -> dict[str, float]:
        """Calculate summary statistics for angular velocity.

        Returns:
            Dict with mean, median, max, and std_dev of angular velocity (deg/s).
            NaN values from stationary periods are excluded.
        """
        av_series = self.get_angular_velocity().dropna()
        if av_series.empty:
            nan = float("nan")
            return {"mean": nan, "median": nan, "max": nan, "std_dev": nan}

        # Use absolute values for summary stats (direction-agnostic magnitude)
        av_abs = av_series.abs()
        return {
            "mean": float(av_abs.mean()),
            "median": float(av_abs.median()),
            "max": float(av_abs.max()),
            "std_dev": float(av_abs.std()),
        }

    def get_tortuosity(
        self, window_size: float | None = None, step: float | None = None
    ) -> float | pd.Series:
        """Calculate path tortuosity (actual distance / straight-line distance).

        Args:
            window_size: Size of sliding window (seconds), or None for entire trajectory.
            step: Step size for sliding window (seconds).

        Returns:
            Tortuosity ratio (>=1.0, where 1.0 is perfectly straight), or Series if windowed.
        """
        # Implementation for the entire trajectory
        if window_size is not None:
            # Sliding window not implemented for this concrete class
            raise NotImplementedError("Sliding window tortuosity is not implemented.")

        if self._is_multi_track:
            # Tortuosidade é uma razão POR TRAJETÓRIA: o "início" e o "fim" de
            # uma série que mistura peixes não são pontos de percurso nenhum.
            # Com vários sujeitos devolve-se a MÉDIA das tortuosidades
            # individuais.
            return self._mean_tortuosity_by_track()

        path_distance = self.calculate_total_distance()

        start_point = self._trajectory_data.iloc[0]
        end_point = self._trajectory_data.iloc[-1]
        straight_dist = np.sqrt(
            (end_point["x_cm_smoothed"] - start_point["x_cm_smoothed"]) ** 2
            + (end_point["y_cm_smoothed"] - start_point["y_cm_smoothed"]) ** 2
        )

        if straight_dist > 0:
            return path_distance / straight_dist
        return np.nan if path_distance > 0 else 1.0

    def _mean_tortuosity_by_track(self) -> float:
        """Média das tortuosidades individuais dos sujeitos presentes."""
        x_all = self._trajectory_data["x_cm_smoothed"].to_numpy()
        y_all = self._trajectory_data["y_cm_smoothed"].to_numpy()

        values: list[float] = []
        for positions in self.track_positions:
            if positions.size < 2:
                continue
            x = x_all[positions]
            y = y_all[positions]
            path_distance = float(np.nansum(np.hypot(np.diff(x), np.diff(y))))
            straight_dist = float(np.hypot(x[-1] - x[0], y[-1] - y[0]))
            if straight_dist > 0:
                values.append(path_distance / straight_dist)
            elif path_distance == 0:
                values.append(1.0)

        if not values:
            return float(np.nan)
        return float(np.mean(values))

    def get_thigmotaxis_timeseries(self) -> pd.Series:
        """Calculate distance to wall time series for thigmotaxis analysis.

        Returns:
            Series with distance to nearest arena boundary in centimeters.
        """
        df = self._trajectory_data
        if df.empty:
            return pd.Series([], dtype=np.float64, index=df.index, name="distance_to_wall_cm")

        # Prefer smoothed coordinates but gracefully fall back to raw cm values
        x_series = df.get("x_cm_smoothed", pd.Series(dtype=np.float64))
        y_series = df.get("y_cm_smoothed", pd.Series(dtype=np.float64))

        if x_series.empty or x_series.isna().all():
            x_series = df.get("x_cm", pd.Series(dtype=np.float64))
        if y_series.empty or y_series.isna().all():
            y_series = df.get("y_cm", pd.Series(dtype=np.float64))

        coords = np.column_stack((x_series.to_numpy(), y_series.to_numpy()))
        valid_mask = ~np.isnan(coords).any(axis=1)
        distances = np.full(len(df), np.nan, dtype=np.float64)

        if valid_mask.any() and not self._arena_polygon_cm.is_empty:
            boundary = self._arena_polygon_cm.boundary
            valid_points = shapely.points(coords[valid_mask, 0], coords[valid_mask, 1])
            distances_valid = shapely.distance(valid_points, boundary)
            distances[valid_mask] = np.asarray(distances_valid, dtype=np.float64)

        return pd.Series(distances, index=df.index, name="distance_to_wall_cm")

    def calculate_speed_bursts(
        self,
        threshold_cm_s: float | None = None,
        min_duration: float = 0.5,
        quantile: float = 0.9,
    ) -> dict[str, int | float | list[Episode]]:
        """
        Detect episodes where the animal exceeds a velocity threshold.

        Args:
            threshold_cm_s: Absolute velocity threshold in cm/s. When ``None``,
                the threshold is inferred from the provided quantile of the
                velocity magnitude distribution.
            min_duration: Minimum duration (seconds) for an episode to be
                considered a burst.
            quantile: Quantile to use when inferring the threshold. Must be in
                the interval (0, 1).

        Returns:
            A dictionary containing the threshold applied, episode count, total
            duration in seconds, and a detailed list of episodes.
        """
        self.calculate_velocity_timeseries()
        if self._trajectory_data.empty:
            inferred_threshold = np.nan if threshold_cm_s is None else threshold_cm_s
            return {
                "threshold_cm_s": float(inferred_threshold)
                if inferred_threshold is not None and not np.isnan(inferred_threshold)
                else inferred_threshold,
                "count": 0,
                "total_duration_s": 0.0,
                "episodes": [],
            }

        v_mag = self._trajectory_data["v_mag"].fillna(0.0)
        if threshold_cm_s is None:
            if not 0 < quantile < 1:
                raise ValueError("quantile must be between 0 and 1 when used.")
            threshold_cm_s = float(v_mag.quantile(quantile))

        mask = v_mag >= float(threshold_cm_s)
        episodes = self._extract_velocity_episodes(mask, min_duration)
        total_duration = float(sum(ep["duration"] for ep in episodes))

        return {
            "threshold_cm_s": float(threshold_cm_s),
            "count": len(episodes),
            "total_duration_s": total_duration,
            "episodes": episodes,
        }

    def calculate_inactivity_periods(
        self,
        velocity_threshold_cm_s: float = 1.0,
        min_duration: float = 1.0,
    ) -> dict[str, int | float | list[Episode]]:
        """
        Detect inactivity episodes where the velocity stays below a threshold.

        Args:
            velocity_threshold_cm_s: Maximum velocity magnitude (cm/s) to be
                considered inactive.
            min_duration: Minimum duration (seconds) required to register an
                inactivity episode.

        Returns:
            A dictionary containing the threshold applied, episode count,
            cumulative inactivity duration, percentage of the recording spent
            inactive, and the detailed list of episodes.
        """
        self.calculate_velocity_timeseries()
        if self._trajectory_data.empty:
            return {
                "threshold_cm_s": float(velocity_threshold_cm_s),
                "count": 0,
                "total_duration_s": 0.0,
                "percentage_of_recording": np.nan,
                "episodes": [],
            }

        v_mag = self._trajectory_data["v_mag"].fillna(0.0)
        mask = v_mag <= float(velocity_threshold_cm_s)
        episodes = self._extract_velocity_episodes(mask, min_duration)
        total_duration = float(sum(ep["duration"] for ep in episodes))

        overall_duration_td = self._trajectory_data.index[-1] - self._trajectory_data.index[0]
        overall_duration_s = overall_duration_td.total_seconds()
        percentage = (
            (total_duration / overall_duration_s) * 100 if overall_duration_s > 0 else np.nan
        )

        return {
            "threshold_cm_s": float(velocity_threshold_cm_s),
            "count": len(episodes),
            "total_duration_s": total_duration,
            "percentage_of_recording": percentage,
            "episodes": episodes,
        }

    def calculate_sharp_turns(
        self, threshold_deg_s: float, cooldown_s: float = 0.5
    ) -> dict[str, float | pd.Index]:
        """
        Calculate the number of sharp turns based on angular velocity.

        Args:
            threshold_deg_s (float): The threshold in degrees per second to
                define a sharp turn.
            cooldown_s (float): The minimum time in seconds before another
                sharp turn can be detected.

        Returns:
            A dictionary with the count of sharp turns, the rate per minute,
            and the timestamps of the turns.
        """
        angular_velocity_deg_s = self.get_angular_velocity()

        if angular_velocity_deg_s.empty or angular_velocity_deg_s.isna().all():
            return {
                "sharp_turns_count": 0,
                "sharp_turns_per_minute": 0.0,
                "sharp_turns_timestamps": pd.Index([]),
            }

        # Identify sharp turns
        potential_turns = angular_velocity_deg_s[angular_velocity_deg_s.abs() > threshold_deg_s]

        if potential_turns.empty:
            return {
                "sharp_turns_count": 0,
                "sharp_turns_per_minute": 0.0,
                "sharp_turns_timestamps": pd.Index([]),
            }

        # Handle the first turn, then iterate and apply cooldown
        turn_times = potential_turns.index
        last_turn_time = turn_times[0]
        sharp_turn_timestamps = [last_turn_time]
        cooldown_td = pd.to_timedelta(cooldown_s, unit="s")

        for timestamp in turn_times[1:]:
            if timestamp - last_turn_time > cooldown_td:
                sharp_turn_timestamps.append(timestamp)
                last_turn_time = timestamp

        sharp_turns_count = len(sharp_turn_timestamps)

        # Calculate total duration for per-minute metric
        df = self._trajectory_data
        total_duration_s = (df.index[-1] - df.index[0]).total_seconds()
        total_duration_minutes = total_duration_s / 60.0 if total_duration_s > 0 else 0

        if total_duration_minutes > 0:
            sharp_turns_per_minute = sharp_turns_count / total_duration_minutes
        else:
            sharp_turns_per_minute = 0.0

        return {
            "sharp_turns_count": sharp_turns_count,
            "sharp_turns_per_minute": sharp_turns_per_minute,
            "sharp_turns_timestamps": pd.Index(sharp_turn_timestamps),
        }

    def _extract_velocity_episodes(self, mask: pd.Series, min_duration: float) -> list[Episode]:
        if min_duration < 0:
            raise ValueError("min_duration must be non-negative.")

        if len(mask) == len(self._trajectory_data):
            # Já alinhado posicionalmente. O ``reindex`` abaixo é o caminho de
            # compatibilidade e NÃO sobrevive a timestamps repetidos (índice
            # duplicado), que é justamente o caso multi-animal.
            aligned_values = mask.to_numpy(dtype=bool)
        else:
            aligned_values = (
                mask.reindex(self._trajectory_data.index, fill_value=False)
                .fillna(False)
                .to_numpy(dtype=bool)
            )
        change_groups = self._block_ids(aligned_values)
        min_duration_td = pd.to_timedelta(min_duration, unit="s")

        episodes: list[Episode] = []
        selected = self._trajectory_data[aligned_values]
        for _, block in selected.groupby(change_groups[aligned_values], sort=True):
            if block.empty:
                continue

            start_time = block.index[0]
            end_time = block.index[-1]
            duration_td = end_time - start_time

            if duration_td < min_duration_td:
                continue

            episodes.append(
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration_td.total_seconds(),
                }
            )

        return episodes
