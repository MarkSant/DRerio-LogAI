import glob
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import pandas as pd
import structlog
import yaml

from zebtrack.core.detector import ZoneData
from zebtrack.settings import settings

CONFIG_FILE_NAME = "project_config.json"
SETTINGS_SNAPSHOT_FILE_NAME = "config_snapshot.yaml"

log = structlog.get_logger()


def _calculate_sha256(filepath: str) -> str:
    """Calculates the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError:
        log.error("file.hash.read_error", filepath=filepath)
        return ""


class ProjectManager:
    def __init__(self):
        self.project_path = None
        self.project_data = {}
        self.metadata = None  # Will hold the DataFrame for metadata.csv

    @staticmethod
    def scan_input_paths(paths: list[str]) -> list[dict]:
        """
        Scans a list of input paths (files or directories) and identifies video files.
        For each video, it checks if corresponding parquet files exist.

        Args:
            paths: A list of file or directory paths.

        Returns:
            A list of dictionaries, where each dictionary represents a video and
            contains its path and a flag indicating if it has existing data.
            Example: [{'path': 'path/to/video.mp4', 'has_data': True}, ...]
        """
        video_files = []
        video_extensions = {".mp4", ".avi", ".mov"}

        for p_str in paths:
            p = Path(p_str)
            if p.is_dir():
                # Recursively find all video files in the directory
                for video_path in p.rglob("*"):
                    if video_path.suffix.lower() in video_extensions:
                        video_files.append(video_path)
            elif p.is_file() and p.suffix.lower() in video_extensions:
                video_files.append(p)

        results = []
        for video_path in sorted(list(set(video_files))):  # Sorted unique list
            # A video has data if a parquet file with the same stem exists
            # in the same directory.
            # Example: for "video1.mp4", it checks for "video1.parquet".
            # This is a simplification based on the expected output format.
            # A more robust check might look for specific parquet files.
            parent_dir = video_path.parent
            base_name = video_path.stem
            has_data = any(parent_dir.glob(f"{base_name}*.parquet"))
            results.append({"path": str(video_path), "has_data": has_data})

        return results

    def _save_settings_snapshot(self):
        """Saves a snapshot of the current settings to the project directory."""
        if not self.project_path:
            return False

        snapshot_path = os.path.join(self.project_path, SETTINGS_SNAPSHOT_FILE_NAME)
        try:
            settings_dict = settings.model_dump(mode="json")
            with open(snapshot_path, "w") as f:
                yaml.dump(settings_dict, f, indent=4, sort_keys=False)
            log.info("settings.snapshot.saved", path=snapshot_path)
            return True
        except (IOError, TypeError) as e:
            log.error("settings.snapshot.save_error", error=str(e))
            return False

    def create_new_project(
        self,
        project_path,
        project_type,
        use_openvino=False,
        active_weight=None,
        video_files=None,
        num_aquariums: int = 1,
        aquarium_width_cm: float = 0.0,
        aquarium_height_cm: float = 0.0,
        # New live project params
        experiment_days: int | None = None,
        subjects_per_group: int | None = None,
        group_names: list[str] | None = None,
    ):
        """
        Initializes a new project, creating its directory and config file.
        It no longer handles OpenVINO conversion, just records the settings.
        """
        self.project_path = project_path
        log_context = log.bind(
            project_path=project_path,
            project_type=project_type,
            use_openvino=use_openvino,
            active_weight=active_weight,
            num_aquariums=num_aquariums,
        )
        log_context.info("project.create.start")

        if project_type == "pre-recorded" and not video_files:
            raise ValueError("Pre-recorded projects require a list of video files.")

        try:
            os.makedirs(self.project_path, exist_ok=True)
        except OSError as e:
            log.error("project.create.dir_error", error=str(e))
            messagebox.showerror(
                "Creation Error",
                (
                    f"Could not create project directory:\n{e}\n\n"
                    "Please check folder permissions and ensure the path is valid."
                ),
            )
            return False

        self._save_settings_snapshot()

        self.project_data = {
            "project_name": os.path.basename(project_path),
            "project_type": project_type,
            "calibration": {
                "num_aquariums": num_aquariums,
                "aquarium_width_cm": aquarium_width_cm,
                "aquarium_height_cm": aquarium_height_cm,
            },
            "use_openvino": use_openvino,
            "active_weight": active_weight,
            "batches": [],  # Changed from "videos" to "batches"
            "groups": group_names if project_type == "live" else [],
            "experiment_days": experiment_days if project_type == "live" else None,
            "subjects_per_group": subjects_per_group
            if project_type == "live"
            else None,
            "last_selected_day": 1,
            "last_selected_group": group_names[0] if group_names else None,
        }

        if video_files:
            # The initial set of videos becomes the first batch
            self.add_video_batch(video_files, save_project=False)

        return self.save_project()

    def add_video_batch(self, video_files: list[dict], save_project: bool = True):
        """
        Adds a new batch of videos to the project.

        Args:
            video_files: A list of video dicts from scan_input_paths.
            save_project: Whether to save the project file after adding.
        """
        if not video_files:
            return

        new_batch = {
            "timestamp": datetime.now().isoformat(),
            "videos": [],
        }

        for video_info in video_files:
            video_path = video_info["path"]
            video_hash = _calculate_sha256(video_path)
            new_batch["videos"].append(
                {
                    "path": video_path,
                    "sha256": video_hash,
                    "status": "processed" if video_info["has_data"] else "pending",
                }
            )

        self.project_data.setdefault("batches", []).append(new_batch)
        log.info("project.batch.added", count=len(video_files))

        if save_project:
            self.save_project()

    def load_project(self, project_path):
        """
        Loads project data from a config file in the given directory.
        """
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        log_context = log.bind(path=config_path)
        log_context.info("project.load.start")

        if not os.path.exists(config_path):
            log_context.error("project.load.not_found")
            messagebox.showerror(
                "Load Error",
                (
                    f"Project config file '{CONFIG_FILE_NAME}' not found in the "
                    f"selected directory:\n{project_path}\n\nPlease ensure you have "
                    "selected a valid project folder."
                ),
            )
            return False

        try:
            with open(config_path, "r") as f:
                self.project_data = json.load(f)
            self.project_path = project_path
            self.load_metadata()  # Load metadata right after loading the project
            log_context.info(
                "project.load.success",
                project_name=self.project_data.get("project_name"),
            )
            return True
        except (json.JSONDecodeError, IOError) as e:
            log_context.error("project.load.error", exc_info=e)
            messagebox.showerror(
                "Load Error",
                f"Failed to load or parse the project config file:\n{config_path}\n\n"
                f"The file may be corrupted or unreadable.\n\nError: {e}",
            )
            return False

    def save_project(self):
        """
        Saves the current project data to the config file.
        """
        if not self.project_path:
            return False

        config_path = os.path.join(self.project_path, CONFIG_FILE_NAME)
        try:
            with open(config_path, "w") as f:
                json.dump(self.project_data, f, indent=4)
            log.info("project.save.success", path=config_path)
            return True
        except IOError as e:
            log.error("project.save.error", path=config_path, exc_info=e)
            messagebox.showerror(
                "Save Error",
                f"Failed to save project config file:\n{config_path}\n\n"
                f"Please check folder permissions.\n\nError: {e}",
            )
            return False

    def update_video_status(self, video_path, new_status):
        """
        Updates the status of a specific video across all batches and saves the project.
        """
        for batch in self.project_data.get("batches", []):
            for video in batch.get("videos", []):
                if video["path"] == video_path:
                    video["status"] = new_status
                    log.info(
                        "video.status.update",
                        video_path=video_path,
                        status=new_status,
                    )
                    return self.save_project()
        return False

    def reset_all_video_statuses(self, to_status: str = "pending"):
        """Reset every video status to a given value (default 'pending')."""
        changed = False
        for batch in self.project_data.get("batches", []):
            for video in batch.get("videos", []):
                if video.get("status") != to_status:
                    video["status"] = to_status
                    changed = True
        if changed:
            log.info("video.status.reset_all", to_status=to_status)
            self.save_project()
        return changed

    def get_all_videos(self) -> list[dict]:
        """Returns a flat list of all videos from all batches."""
        all_vids = []
        for batch in self.project_data.get("batches", []):
            all_vids.extend(batch.get("videos", []))
        return all_vids

    def get_next_video(self):
        """
        Returns the path of the next video with 'pending' status from all batches.
        """
        for video in self.get_all_videos():
            if video["status"] == "pending":
                return video["path"]
        return None

    def get_project_name(self):
        return self.project_data.get("project_name", "N/A")

    def get_project_type(self):
        return self.project_data.get("project_type")

    def get_zone_data(self) -> ZoneData:
        """
        Retrieves zone data from the project configuration, returning a ZoneData object.
        """
        zone_dict = self.project_data.get("detection_zones", {})
        if zone_dict:
            # Pydantic dataclasses can be instantiated from dictionaries
            return ZoneData(**zone_dict)
        return ZoneData()

    def load_metadata(self):
        """Loads the metadata.csv file from the project root into a pandas DataFrame."""
        if not self.project_path:
            return

        metadata_path = os.path.join(self.project_path, "metadata.csv")
        if os.path.exists(metadata_path):
            try:
                self.metadata = pd.read_csv(metadata_path)
                log.info("project.metadata.loaded", path=metadata_path)
            except Exception as e:
                self.metadata = None
                log.error(
                    "project.metadata.load_error", path=metadata_path, error=str(e)
                )
                messagebox.showwarning(
                    "Metadata Warning",
                    f"Could not load or parse 'metadata.csv'.\n\nError: {e}"
                )
        else:
            self.metadata = None
            log.info("project.metadata.not_found", path=metadata_path)

    def get_metadata_for_experiment(self, experiment_id: str) -> dict:
        """
        Retrieves a dictionary of metadata for a given experiment ID.

        Args:
            experiment_id: The ID of the experiment, typically the subfolder name.

        Returns:
            A dictionary of metadata for that experiment, or an empty dict if not found.
        """
        if self.metadata is None:
            return {}

        # Ensure 'experiment_id' column exists
        if 'experiment_id' not in self.metadata.columns:
            log.warning("project.metadata.no_id_column")
            return {}

        row = self.metadata[self.metadata['experiment_id'] == experiment_id]
        if not row.empty:
            return row.iloc[0].to_dict()

        return {}

    def get_completed_sessions(self) -> set[tuple[int, str, int]]:
        """
        Scans the project directory for completed session folders and returns them.
        A session is a tuple of (day, group_name, subject_id).
        """
        if not self.project_path:
            return set()

        completed = set()
        # Regex to capture day, group name, and subject ID from folder names
        # like "D1_GControl_S3" or "D12_GGroup Name with spaces_S15"
        pattern = re.compile(r"^D(\d+)_G(.+)_S(\d+)$")

        for item in os.scandir(self.project_path):
            if not item.is_dir():
                continue

            match = pattern.match(item.name)
            if match:
                try:
                    day = int(match.group(1))
                    group_name = match.group(2)
                    subject_id = int(match.group(3))
                    completed.add((day, group_name, subject_id))
                except (ValueError, IndexError):
                    log.warning("project.scan.invalid_folder_name", name=item.name)
                    continue

        return completed

    def save_last_session_details(self, day: int, group: str):
        """Saves the last selected day and group to the project config."""
        if not self.project_path:
            return
        self.project_data["last_selected_day"] = day
        self.project_data["last_selected_group"] = group
        self.save_project()

    def get_last_session_details(self) -> tuple[int | None, str | None]:
        """Retrieves the last selected day and group from the project config."""
        if not self.project_data:
            return None, None

        day = self.project_data.get("last_selected_day")
        group = self.project_data.get("last_selected_group")
        return day, group


if __name__ == "__main__":
    # Example usage for testing the ProjectManager
    print("Testing ProjectManager...")

    # Setup test directory
    test_dir = "pm_test_project"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    pm = ProjectManager()

    # 1. Test creating a new pre-recorded project
    print("\n--- Test 1: Creating a new project ---")
    video_list = ["C:/videos/vid1.mp4", "C:/videos/vid2.mp4"]
    success = pm.create_new_project(test_dir, "pre-recorded", video_files=video_list)
    if success:
        print(f"Project created at: {pm.project_path}")
        print("Project data:", pm.project_data)
    else:
        print("Project creation failed.")

    # 2. Test loading an existing project
    print("\n--- Test 2: Loading a project ---")
    pm_loader = ProjectManager()
    success = pm_loader.load_project(test_dir)
    if success:
        print(f"Loaded project name: {pm_loader.get_project_name()}")
        print("Loaded data:", pm_loader.project_data)

        # 3. Test updating and getting next video
        print("\n--- Test 3: Updating and getting next video ---")
        next_vid = pm_loader.get_next_video()
        print(f"Next video to process: {next_vid}")

        if next_vid:
            pm_loader.update_video_status(next_vid, "complete")
            print("Updated project data:", pm_loader.project_data)

        next_vid = pm_loader.get_next_video()
        print(f"Next video to process after update: {next_vid}")

    # Clean up the test directory
    import shutil

    shutil.rmtree(test_dir)
    print(f"\nCleaned up test directory: {test_dir}")

    print("\nProjectManager test finished.")
