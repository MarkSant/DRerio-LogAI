import os
import json
from tkinter import messagebox
from ultralytics import YOLO
import logging

import config


CONFIG_FILE_NAME = "project_config.json"

class ProjectManager:
    def __init__(self):
        self.project_path = None
        self.project_data = {}

    def create_new_project(self, project_path, project_type, use_openvino=False, video_files=None):
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
            messagebox.showerror("Creation Error", f"Could not create project directory: {e}")
            return False

        # Export the model if requested, BEFORE saving the project config
        openvino_model_path = ""
        if use_openvino:
            try:
                logging.info("Starting OpenVINO model export...")
                model = YOLO(config.YOLO_MODEL_PATH)
                # The export path will be inside the new project directory
                export_dir = os.path.join(self.project_path, "model")
                exported_path = model.export(format='openvino', half=True, workspace=export_dir)
                openvino_model_path = exported_path
                logging.info(f"Model exported successfully to {openvino_model_path}")
            except Exception as e:
                logging.error(f"Failed to export model to OpenVINO format: {e}")
                messagebox.showerror("OpenVINO Export Error", f"Failed to export model to OpenVINO format: {e}")
                return False

        self.project_data = {
            "project_name": os.path.basename(project_path),
            "project_type": project_type,
            "use_openvino": use_openvino,
            "openvino_model_path": openvino_model_path,
            "videos": []
        }

        if video_files:
            for video_path in video_files:
                self.project_data["videos"].append({
                    "path": video_path,
                    "status": "pending" # Other statuses: "processing", "complete"
                })

        return self.save_project()

    def load_project(self, project_path):
        """
        Loads project data from a config file in the given directory.
        """
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        if not os.path.exists(config_path):
            messagebox.showerror("Load Error", f"Project config file not found at:\n{config_path}")
            return False

        try:
            with open(config_path, 'r') as f:
                self.project_data = json.load(f)
            self.project_path = project_path
            print(f"Project '{self.project_data.get('project_name')}' loaded successfully.")
            return True
        except (json.JSONDecodeError, IOError) as e:
            messagebox.showerror("Load Error", f"Failed to load project config: {e}")
            return False

    def save_project(self):
        """
        Saves the current project data to the config file.
        """
        if not self.project_path:
            return False

        config_path = os.path.join(self.project_path, CONFIG_FILE_NAME)
        try:
            with open(config_path, 'w') as f:
                json.dump(self.project_data, f, indent=4)
            print(f"Project state saved to {config_path}")
            return True
        except IOError as e:
            messagebox.showerror("Save Error", f"Failed to save project config: {e}")
            return False

    def update_video_status(self, video_path, new_status):
        """
        Updates the status of a specific video and saves the project.
        """
        for video in self.project_data.get("videos", []):
            if video["path"] == video_path:
                video["status"] = new_status
                print(f"Updated status of '{os.path.basename(video_path)}' to '{new_status}'")
                return self.save_project()
        return False

    def get_next_video(self):
        """
        Returns the path of the next video with 'pending' status.
        """
        for video in self.project_data.get("videos", []):
            if video["status"] == "pending":
                return video["path"]
        return None # No more pending videos

    def get_project_name(self):
        return self.project_data.get("project_name", "N/A")

    def get_project_type(self):
        return self.project_data.get("project_type")

if __name__ == '__main__':
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
    success = pm.create_new_project(test_dir, "pre-recorded", video_list)
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
