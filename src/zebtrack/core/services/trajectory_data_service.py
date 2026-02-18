"""Trajectory data loading service.

Phase 5.6b: Encapsulates ``pd.read_parquet`` calls that were previously
scattered across coordinators, so that coordinators no longer import
pandas directly.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import pandas as pd

log = structlog.get_logger()


class TrajectoryDataService:
    """Service for loading trajectory Parquet files.

    Provides a safe wrapper around ``pd.read_parquet`` with existence
    checks, error handling, and structured logging.

    Coordinators receive this via constructor injection instead of
    importing pandas directly.
    """

    @staticmethod
    def load_trajectory(path: str) -> pd.DataFrame:
        """Load a trajectory Parquet file.

        Args:
            path: Absolute path to a ``3_CoordMovimento_*.parquet`` file.

        Returns:
            A pandas DataFrame with trajectory data.

        Raises:
            FileNotFoundError: If *path* does not exist.
            Exception: Re-raises any pyarrow/pandas read error.
        """
        import pandas as _pd

        if not os.path.exists(path):
            raise FileNotFoundError(f"Trajectory file not found: {path}")
        df = _pd.read_parquet(path)
        log.debug(
            "trajectory_data_service.load.ok",
            path=path,
            rows=len(df),
            columns=list(df.columns),
        )
        return df

    @staticmethod
    def load_trajectory_safe(path: str) -> pd.DataFrame | None:
        """Load a trajectory file, returning ``None`` on any error.

        This is the preferred method for coordinator code that already
        handles missing files gracefully.

        Args:
            path: Absolute path to a trajectory Parquet file.

        Returns:
            DataFrame or ``None`` if the file is missing / unreadable.
        """
        try:
            return TrajectoryDataService.load_trajectory(path)
        except FileNotFoundError:
            log.warning(
                "trajectory_data_service.load.not_found",
                path=path,
            )
            return None
        except Exception:
            log.error(
                "trajectory_data_service.load.error",
                path=path,
                exc_info=True,
            )
            return None
