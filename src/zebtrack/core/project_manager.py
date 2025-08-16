import hashlib
import json
import logging
import os
import shutil
from tkinter import messagebox

import yaml
from ultralytics import YOLO

from zebtrack.settings import settings

CONFIG_FILE_NAME = "project_config.json"
SETTINGS_SNAPSHOT_FILE_NAME = "config_snapshot.yaml"


def _calculate_sha256(filepath: str) -> str:
    """Calculates the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Read and update hash in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError:
        logging.error(f"Could not read file to calculate hash: {filepath}")
        return ""


class ProjectManager:
    def __init__(self):
        self.project_path = None
        self.project_data = {}

    def _save_settings_snapshot(self):
        """Saves a snapshot of the current settings to the project directory."""
        if not self.project_path:
            return False

        snapshot_path = os.path.join(self.project_path, SETTINGS_SNAPSHOT_FILE_NAME)
        try:
            # Convert Pydantic settings to a dict and save as YAML
            settings_dict = settings.model_dump(mode="json")
            with open(snapshot_path, "w") as f:
                yaml.dump(settings_dict, f, indent=4, sort_keys=False)
            logging.info(f"Settings snapshot saved to {snapshot_path}")
            return True
        except (IOError, TypeError) as e:
            # Log the error but don't block project creation
            logging.error(f"Could not save settings snapshot: {e}")
            return False

    def create_new_project(
        self, project_path, project_type, use_openvino=False, video_files=None
    ):
        """
        Initializes a new project, creating its directory and config file.
        If use_openvino is True, it also converts the model to OpenVINO format.
        """
        self.project_path = project_path

        if project_type == "pre-recorded" and not video_files:
            raise ValueError("Pre-recorded projects require a list of video files.")

        try:
            os.makedirs(self.project_path, exist_ok=True)
        except OSError as e:
            messagebox.showerror(
                "Creation Error",
                f"Could not create project directory:\n{e}\n\n"
                "Please check folder permissions and ensure the path is valid.",
            )
            return False

        # Save a snapshot of the settings for reproducibility
        self._save_settings_snapshot()

        # Export the model if requested, checking for a cached version first.
        openvino_model_path = ""
        if use_openvino:
            cache_dir = "openvino_model_cache"
            base_model_name = os.path.splitext(
                os.path.basename(settings.yolo_model.path)
            )[0]
            # Ultralytics appends `_openvino_model` to the exported directory name.
            cached_model_dir_name = f"{base_model_name}_openvino_model"
            cached_model_dir = os.path.join(cache_dir, cached_model_dir_name)

            # The actual model file has .xml extension
            # Note: ultralytics export might name it `best.xml` or
            # `<base_model_name>.xml`. We will just check for existence of the
            # directory for simplicity, detector.py finds the xml.

            if os.path.exists(cached_model_dir):
                logging.info(f"Found cached OpenVINO model at {cached_model_dir}")
                openvino_model_path = os.path.abspath(cached_model_dir)
            else:
                logging.info("No cached OpenVINO model found. Exporting now...")
                try:
                    model = YOLO(settings.yolo_model.path)
                    # Export to a temporary default location
                    exported_path = model.export(format="openvino", half=True)

                    # Ensure cache directory exists
                    os.makedirs(cache_dir, exist_ok=True)

                    # Move the exported model to our cache directory.
                    # The name of the exported dir is returned by `exported_path`.
                    # To prevent race conditions, we remove the destination
                    # first if it exists.
                    shutil.rmtree(cached_model_dir, ignore_errors=True)

                    try:
                        shutil.move(exported_path, cached_model_dir)
                        openvino_model_path = os.path.abspath(cached_model_dir)
                        logging.info(
                            f"Model exported and cached at {openvino_model_path}"
                        )
                    except Exception as move_exc:
                        logging.error(
                            "Failed to move exported model to cache directory: "
                            f"{move_exc}"
                        )
                        messagebox.showerror(
                            "OpenVINO Export Error",
                            "Failed to move the exported OpenVINO model to the cache directory.\n"
                            f"Please check permissions.\n\nError: {move_exc}",
                        )
                        return False
                except Exception as e:
                    logging.error(f"Failed to export model to OpenVINO format: {e}")
                    messagebox.showerror(
                        "OpenVINO Export Error",
                        "An unexpected error occurred during OpenVINO model export.\n"
                        "Ensure all dependencies are installed correctly and the model path is valid.\n\n"
                        f"Error: {e}",
                    )
                    return False

        self.project_data = {
            "project_name": os.path.basename(project_path),
            "project_type": project_type,
            "use_openvino": use_openvino,
            "openvino_model_path": openvino_model_path,
            "videos": [],
        }

        if video_files:
            for video_path in video_files:
                video_hash = _calculate_sha256(video_path)
                self.project_data["videos"].append(
                    {
                        "path": video_path,
                        "sha256": video_hash,
                        "status": "pending",  # Other statuses: "processing", "complete"
                    }
                )

        return self.save_project()

    def load_project(self, project_path):
        """
        Loads project data from a config file in the given directory.
        """
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        if not os.path.exists(config_path):
            messagebox.showerror(
                "Load Error",
                f"Project config file '{CONFIG_FILE_NAME}' not found in the selected directory:\n{project_path}\n\n"
                "Please ensure you have selected a valid project folder.",
            )
            return False

        try:
            with open(config_path, "r") as f:
                self.project_data = json.load(f)
            self.project_path = project_path
            print(
                f"Project '{self.project_data.get('project_name')}' "
                "loaded successfully."
            )
            return True
        except (json.JSONDecodeError, IOError) as e:
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
            print(f"Project state saved to {config_path}")
            return True
        except IOError as e:
            messagebox.showerror(
                "Save Error",
                f"Failed to save project config file:\n{config_path}\n\n"
                f"Please check folder permissions.\n\nError: {e}",
            )
            return False

    def update_video_status(self, video_path, new_status):
        """
        Updates the status of a specific video and saves the project.
        """
        for video in self.project_data.get("videos", []):
            if video["path"] == video_path:
                video["status"] = new_status
                print(
                    f"Updated status of '{os.path.basename(video_path)}' to "
                    f"'{new_status}'"
                )
                return self.save_project()
        return False

    def get_next_video(self):
        """
        Returns the path of the next video with 'pending' status.
        """
        for video in self.project_data.get("videos", []):
            if video["status"] == "pending":
                return video["path"]
        return None  # No more pending videos

    def get_project_name(self):
        return self.project_data.get("project_name", "N/A")

    def get_project_type(self):
        return self.project_data.get("project_type")


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
