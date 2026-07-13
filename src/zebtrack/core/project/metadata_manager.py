"""Metadata manager for DRerio LogAI.

Handles metadata loading from CSV, experiment metadata lookup,
detector state persistence, session tracking, and group caching.

Phase 4.2: Extracted from ProjectManager to reduce god-class complexity.
All methods are stateless — they receive project_data, project_path, and
callbacks as parameters from the ProjectManager facade.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

    # pandas DataFrame used for metadata.csv; only at type-check time
    import pandas as pd

log = structlog.get_logger()


class MetadataManager:
    """Manages metadata, detector state, and session tracking.

    Phase 4.2: Extracted from ProjectManager. This class is stateless;
    all project state (project_path, project_data) is passed as parameters.
    """

    def __init__(self) -> None:
        """Initialize MetadataManager."""

    # ------------------------------------------------------------------
    # Metadata CSV
    # ------------------------------------------------------------------

    @staticmethod
    def load_metadata(project_path: Path | str | None) -> pd.DataFrame | None:
        """Load the metadata.csv file from the project root into a pandas DataFrame.

        Args:
            project_path: Path to the project root directory.

        Returns:
            pandas DataFrame with metadata, or None if not found / failed.
        """
        import pandas as pd_mod  # Lazy import to avoid loading pandas during startup

        if not project_path:
            return None

        metadata_path = os.path.join(project_path, "metadata.csv")
        if os.path.exists(metadata_path):
            try:
                df = pd_mod.read_csv(metadata_path)
                log.info("project.metadata.loaded", path=metadata_path)
                return df
            except OSError as e:
                log.error(
                    "project.metadata.io_error",
                    path=metadata_path,
                    error=str(e),
                )
                return None
            except (UnicodeDecodeError, ValueError) as e:
                log.error(
                    "project.metadata.parse_error",
                    path=metadata_path,
                    error=str(e),
                )
                return None
            # except Exception justified: pandas parquet I/O — heterogeneous data errors
            except Exception as e:
                log.error(
                    "project.metadata.unexpected_error",
                    path=metadata_path,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return None
        else:
            log.info("project.metadata.not_found", path=metadata_path)
            return None

    @staticmethod
    def get_metadata_for_experiment(
        experiment_id: str | None,
        video_path: Path | str | None = None,
        *,
        metadata_df: Any | None,
        project_data: dict[str, Any],
        find_video_entry_fn: Callable[..., dict | None],
    ) -> dict:
        """Retrieve a dictionary of metadata for a given experiment ID or video path.

        Priority:
        1. metadata.csv (if loaded)
        2. Internal Project Data (project_config.json 'videos' hierarchy)
        3. Regex parsing of experiment_id

        Args:
            experiment_id: The ID of the experiment (e.g., the video file stem).
            video_path: Absolute path to the video file (optional but recommended).
            metadata_df: Loaded pandas DataFrame from metadata.csv, or None.
            project_data: The project data dictionary.
            find_video_entry_fn: Callback to find a video entry.

        Returns:
            A dictionary of metadata for that experiment.
        """
        # Guard against None or empty experiment_id
        if not experiment_id:
            log.debug(
                "metadata.lookup.skipped",
                reason="experiment_id is None or empty",
            )
            return {}

        meta: dict = {}

        # 1. Try to find the data in the metadata.csv file
        if metadata_df is not None and "experiment_id" in metadata_df.columns:
            row = metadata_df[metadata_df["experiment_id"] == experiment_id]
            if not row.empty:
                meta = row.iloc[0].to_dict()
                if meta.get("group") or meta.get("group_id"):
                    return meta

        # 2. Internal Project Data Lookup
        if project_data:
            video_info = find_video_entry_fn(path=video_path, experiment_id=experiment_id)

            if video_info:
                nested_meta = video_info.get("metadata") or {}
                for key in (
                    "day",
                    "group",
                    "group_id",
                    "group_display_name",
                    "subject",
                    "subject_id",
                ):
                    val = nested_meta.get(key) or video_info.get(key)
                    if val is not None and key not in meta:
                        meta[key] = val

                if meta.get("group") or meta.get("group_id"):
                    return meta

        # 3. Fallback: Try to extract from experiment_id using regex
        log.info(
            "metadata.fallback.attempt",
            experiment_id=experiment_id,
            reason="Not found in metadata.csv or project structure",
        )
        pattern = re.compile(r"D(\d+)_G(.+)_S(\d+)")
        match = pattern.match(experiment_id)
        if match:
            try:
                day = int(match.group(1))
                group = match.group(2)
                subject = int(match.group(3))

                if "day" not in meta:
                    meta["day"] = day
                if "group" not in meta:
                    meta["group"] = group
                if "subject" not in meta:
                    meta["subject"] = subject

                return meta
            except (ValueError, IndexError):
                log.warning("metadata.fallback.parse_error", experiment_id=experiment_id)

        return meta

    # ------------------------------------------------------------------
    # Detector state
    # ------------------------------------------------------------------

    @staticmethod
    def save_detector_state(
        detector_config: dict,
        *,
        project_data: dict[str, Any],
        project_path: Path | str | None,
        save_project_fn: Callable[[], None],
    ) -> bool:
        """Save detector configuration to project data.

        Args:
            detector_config: Dictionary with detector configuration keys.
            project_data: The project data dictionary.
            project_path: Path to the project root directory.
            save_project_fn: Callback to save the project.

        Returns:
            True if saved successfully, False if no project/data available.
        """
        if not project_data:
            log.debug("project.detector_state.save.no_project_data")
            return False

        log.info("project.detector_state.save.start", config=detector_config)

        if "last_updated" not in detector_config:
            detector_config["last_updated"] = datetime.now().isoformat()

        project_data["detector_config"] = detector_config

        overrides = project_data.setdefault("model_overrides", {})
        normalized_thresholds = MetadataManager._normalize_detector_thresholds(detector_config)
        if normalized_thresholds:
            merged = dict(overrides.get("detector_parameters") or {})
            merged.update(normalized_thresholds)
            overrides["detector_parameters"] = merged
        elif not detector_config:
            overrides.pop("detector_parameters", None)

        if project_path:
            save_project_fn()
            log.info(
                "project.detector_state.save.success",
                plugin=detector_config.get("plugin_name"),
            )
        else:
            log.info(
                "project.detector_state.save.in_memory",
                plugin=detector_config.get("plugin_name"),
                reason="single_video_workflow",
            )

        return True

    @staticmethod
    def get_detector_state(project_data: dict[str, Any]) -> dict:
        """Retrieve detector configuration from project data.

        Args:
            project_data: The project data dictionary.

        Returns:
            Detector configuration or empty dict if not found.
        """
        return project_data.get("detector_config", {})

    @staticmethod
    def _normalize_detector_thresholds(detector_config: dict | None) -> dict[str, float]:
        """Normalize detector threshold keys to canonical names.

        Args:
            detector_config: Raw detector configuration dictionary.

        Returns:
            Dictionary with normalized threshold keys and float values.
        """
        mapping = {
            "conf_threshold": "confidence_threshold",
            "confidence_threshold": "confidence_threshold",
            "nms_threshold": "nms_threshold",
            "track_threshold": "track_threshold",
            "match_threshold": "match_threshold",
        }

        normalized: dict[str, float] = {}
        if not detector_config:
            return normalized

        for source_key, target_key in mapping.items():
            if source_key not in detector_config:
                continue
            try:
                normalized[target_key] = float(detector_config[source_key])
            except (TypeError, ValueError):
                log.warning(
                    "project.detector_state.normalize_failed",
                    key=source_key,
                    value=detector_config[source_key],
                )

        return normalized

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    @staticmethod
    def get_completed_sessions(project_path: Path | str | None) -> set[tuple[int, str, str]]:
        """Scan the project directory for completed session folders.

        A session is a tuple of (day, group_name, subject_id).
        subject_id is returned as string for UI compatibility.

        Args:
            project_path: Path to the project root directory.

        Returns:
            Set of (day, group_name, subject_id) tuples.
        """
        if not project_path:
            return set()

        completed: set[tuple[int, str, str]] = set()

        # Pattern 1: New format - day{day}_{group}_{subject}_{timestamp}
        pattern_new = re.compile(r"^day(\d+)_(.+)_(\d+)_\d{8}_\d{6}$")

        # Pattern 1b: Without trailing timestamp (older live recorder output)
        pattern_new_no_ts = re.compile(r"^day(\d+)_(.+)_(\d+)$")

        # Pattern 2: Legacy format - D{day}_G{group}_S{subject}
        pattern_legacy = re.compile(r"^D(\d+)_G(.+)_S(\d+)$")

        def _match_and_add(entry_name: str) -> None:
            """Try every pattern against ``entry_name`` (directory basename);
            add to ``completed`` if matched. Parameter is just a name string,
            not a path — the project-wide path-consistency hook would flag
            ``folder_name`` here even though no filesystem access happens."""
            for pattern in (pattern_new, pattern_new_no_ts):
                m = pattern.match(entry_name)
                if m:
                    try:
                        completed.add((int(m.group(1)), m.group(2), m.group(3)))
                    except (ValueError, IndexError):
                        log.debug(
                            "project.scan.new_format_parse_error",
                            name=entry_name,
                            exc_info=True,
                        )
                    return
            legacy_m = pattern_legacy.match(entry_name)
            if legacy_m:
                try:
                    completed.add(
                        (int(legacy_m.group(1)), legacy_m.group(2), str(legacy_m.group(3)))
                    )
                except (ValueError, IndexError):
                    log.warning("project.scan.invalid_folder_name", name=entry_name)

        # Scan project root for session folders.
        for item in os.scandir(project_path):
            if item.is_dir():
                _match_and_add(item.name)

        # Audit Erro 2 follow-up (2026-05-25): also scan the legacy live
        # recorder output directory. ``LiveSessionManager`` writes new live
        # sessions under ``<project>/live_analysis_sessions/<folder>/`` when
        # the caller does not specify a hierarchical ``output_base_dir``, so
        # the session folders never appear at the project root and the
        # Progresso grid stays stuck on "pending" forever.
        live_dir = Path(project_path) / "live_analysis_sessions"
        if live_dir.exists() and live_dir.is_dir():
            for item in os.scandir(live_dir):
                if item.is_dir():
                    _match_and_add(item.name)

        # Audit Erro 2 follow-up round 3 (2026-05-25): the modern live flow
        # uses a hierarchical layout — ``<project>/Grupo_X/Dia_Y/Sujeito_Z/
        # live_<ts>/`` — where the leaf folder name carries no metadata. We
        # must extract day/group/subject from the path SEGMENTS instead.
        # Without this, the Progresso grid never recognises hierarchical
        # sessions as completed even after clicking "Atualizar Grade".
        MetadataManager._scan_hierarchical_live_sessions(Path(project_path), completed)

        return completed

    @staticmethod
    def _scan_hierarchical_live_sessions(
        project_root: Path, completed: set[tuple[int, str, str]]
    ) -> None:
        """Add completed sessions from ``Grupo_X/Dia_Y/Sujeito_Z/<session>/``.

        Extracted from ``get_completed_sessions`` to keep cyclomatic
        complexity below the project ruff threshold. Mutates ``completed``
        in place.
        """
        group_re = re.compile(r"^Grupo_(.+)$")
        day_re = re.compile(r"^Dia_0*(\d+)$")
        subject_re = re.compile(r"^Sujeito_0*(\d+)$")
        try:
            group_entries = list(os.scandir(project_root))
        except OSError:
            log.debug(
                "project.scan.hierarchical_root_scan_failed",
                project_path=str(project_root),
                exc_info=True,
            )
            return
        for group_entry in group_entries:
            if not group_entry.is_dir():
                continue
            group_match = group_re.match(group_entry.name)
            if not group_match:
                continue
            MetadataManager._scan_hierarchical_group(
                Path(group_entry.path), group_match.group(1), day_re, subject_re, completed
            )

    @staticmethod
    def _scan_hierarchical_group(
        group_dir: Path,
        group_name: str,
        day_re: re.Pattern[str],
        subject_re: re.Pattern[str],
        completed: set[tuple[int, str, str]],
    ) -> None:
        try:
            day_entries = list(os.scandir(group_dir))
        except OSError:
            return
        for day_entry in day_entries:
            if not day_entry.is_dir():
                continue
            day_match = day_re.match(day_entry.name)
            if not day_match:
                continue
            try:
                day_num = int(day_match.group(1))
            except ValueError:
                continue
            MetadataManager._scan_hierarchical_day(
                Path(day_entry.path), day_num, group_name, subject_re, completed
            )

    @staticmethod
    def _scan_hierarchical_day(
        day_dir: Path,
        day_num: int,
        group_name: str,
        subject_re: re.Pattern[str],
        completed: set[tuple[int, str, str]],
    ) -> None:
        try:
            subject_entries = list(os.scandir(day_dir))
        except OSError:
            return
        for subject_entry in subject_entries:
            if not subject_entry.is_dir():
                continue
            subject_match = subject_re.match(subject_entry.name)
            if not subject_match:
                continue
            if MetadataManager._subject_dir_has_session(Path(subject_entry.path)):
                completed.add((day_num, group_name, subject_match.group(1)))

    @staticmethod
    def _subject_dir_has_session(subject_dir: Path) -> bool:
        """A subject folder counts as completed iff at least one nested
        session folder contains a trajectory or arena parquet AND is not
        marked as cancelled (``.cancelled`` marker file — audit Erro 1
        round 4, 2026-05-25)."""
        try:
            for session_entry in os.scandir(subject_dir):
                if not session_entry.is_dir():
                    continue
                session_path = Path(session_entry.path)
                if (session_path / ".cancelled").exists():
                    continue
                if any(session_path.glob("3_CoordMovimento_*.parquet")):
                    return True
                if any(session_path.glob("1_ProcessingArea_*.parquet")):
                    return True
        except OSError:
            log.debug(
                "project.scan.hierarchical_session_scan_failed",
                subject_dir=str(subject_dir),
                exc_info=True,
            )
        return False

    @staticmethod
    def save_last_session_details(
        day: int,
        group: str,
        *,
        project_data: dict[str, Any],
        project_path: Path | str | None,
        save_project_fn: Callable[[], None],
    ) -> None:
        """Save the last selected day and group to the project config.

        Args:
            day: Day number.
            group: Group name.
            project_data: The project data dictionary.
            project_path: Path to the project root directory.
            save_project_fn: Callback to save the project.
        """
        if not project_path:
            return
        project_data["last_selected_day"] = day
        project_data["last_selected_group"] = group
        save_project_fn()

    @staticmethod
    def get_last_session_details(
        project_data: dict[str, Any],
    ) -> tuple[int | None, str | None]:
        """Retrieve the last selected day and group from the project config.

        Args:
            project_data: The project data dictionary.

        Returns:
            Tuple of (day, group), both None if not set.
        """
        if not project_data:
            return None, None

        day = project_data.get("last_selected_day")
        group = project_data.get("last_selected_group")
        return day, group

    # ------------------------------------------------------------------
    # Groups cache
    # ------------------------------------------------------------------

    @staticmethod
    def get_available_groups(
        project_data: dict[str, Any],
        metadata_df: Any | None,
        get_all_videos_fn: Callable[[], list[dict]],
    ) -> list[str]:
        """Collect all unique group names used in the project.

        Args:
            project_data: The project data dictionary.
            metadata_df: Loaded pandas DataFrame from metadata.csv, or None.
            get_all_videos_fn: Callback to get all video entries.

        Returns:
            Sorted list of unique group name strings.
        """
        groups: set[str] = set()

        # 0. Include groups defined in the project (from wizard)
        for g in project_data.get("groups", []):
            if g:
                groups.add(str(g))

        # 1. Scan video entries
        videos = get_all_videos_fn() or []
        for video in videos:
            metadata = video.get("metadata", {})

            if group := metadata.get("group"):
                groups.add(str(group))

            multi_outputs = video.get("multi_aquarium_outputs", {})
            for output in multi_outputs.values():
                if group := output.get("group"):
                    groups.add(str(group))

        # 2. Check metadata.csv if available
        if metadata_df is not None and "group" in metadata_df.columns:
            for g in metadata_df["group"].dropna().unique():
                groups.add(str(g))

        return sorted(list(groups))
