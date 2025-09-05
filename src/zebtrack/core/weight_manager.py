import json
import os
import shutil
from tkinter import messagebox

import structlog
from ultralytics import YOLO

from zebtrack.settings import settings

WEIGHTS_CONFIG_FILE = "weights_config.json"
OPENVINO_CACHE_DIR = "openvino_model_cache"

log = structlog.get_logger()


class WeightManager:
    def __init__(self, config_dir="."):
        self.config_path = os.path.join(config_dir, WEIGHTS_CONFIG_FILE)
        self.weights = {}
        self._load_weights()

    def _load_weights(self):
        """Loads the weights configuration from the JSON file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.weights = json.load(f)
                log.info("weights.config.loaded", path=self.config_path)
            except (json.JSONDecodeError, IOError) as e:
                log.error("weights.config.load_error", error=str(e))
                self.weights = {}
                self._initialize_default_weight()
        else:
            self._initialize_default_weight()

    def _initialize_default_weight(self):
        """Initializes the config with the default weight from settings."""
        log.info("weights.config.initializing_default")
        default_path = settings.yolo_model.path
        if default_path and os.path.exists(default_path):
            weight_name = os.path.basename(default_path)
            self.weights = {
                weight_name: {
                    "path": default_path,
                    "is_default": True,
                    "openvino_path": "",
                }
            }
            self.save_weights()
        else:
            self.weights = {}
            log.warning("weights.config.default_not_found", path=default_path)

    def save_weights(self):
        """Saves the current weights configuration to the JSON file."""
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.weights, f, indent=4)
            log.info("weights.config.saved", path=self.config_path)
        except IOError as e:
            log.error("weights.config.save_error", error=str(e))
            messagebox.showerror(
                "Error", "Could not save the weights configuration file."
            )

    def get_all_weights(self) -> list[str]:
        """Returns a list of names of all available weights."""
        return list(self.weights.keys())

    def get_weight_details(self, name: str) -> dict | None:
        """Returns the details dictionary for a given weight name."""
        return self.weights.get(name)

    def get_default_weight(self) -> tuple[str, dict] | tuple[None, None]:
        """Returns the name and details of the default weight."""
        for name, details in self.weights.items():
            if details.get("is_default"):
                return name, details
        return None, None

    def set_default_weight(self, name_to_set: str):
        """Sets a new default weight."""
        if name_to_set not in self.weights:
            log.error("weights.default.not_found", name=name_to_set)
            return

        for name, details in self.weights.items():
            details["is_default"] = name == name_to_set
        self.save_weights()
        log.info("weights.default.set", name=name_to_set)

    def add_weight(self, new_path: str, set_as_default: bool):
        """
        Adds a new weight from a given path.

        Args:
            new_path: The file path to the new .pt weight file.
            set_as_default: If True, this new weight will become the default.
        """
        if not os.path.exists(new_path):
            log.error("weights.add.not_found", path=new_path)
            return

        new_name = os.path.basename(new_path)
        if new_name in self.weights:
            messagebox.showinfo(
                "Already Exists", f"A weight named '{new_name}' already exists."
            )
            return

        if set_as_default:
            # Unset the current default
            _, current_default = self.get_default_weight()
            if current_default:
                current_default["is_default"] = False

        self.weights[new_name] = {
            "path": new_path,
            "is_default": set_as_default,
            "openvino_path": "",
        }
        self.save_weights()
        log.info("weights.add.success", name=new_name, path=new_path)

    def delete_weight(self, name_to_delete: str):
        """Deletes a weight from the configuration."""
        if name_to_delete not in self.weights:
            log.warning("weights.delete.not_found", name=name_to_delete)
            return

        if len(self.weights) <= 1:
            messagebox.showerror(
                "Cannot Delete", "You cannot delete the last available weight."
            )
            return

        details = self.weights[name_to_delete]
        was_default = details.get("is_default")

        # Delete the OpenVINO cache if it exists
        if details.get("openvino_path") and os.path.exists(details["openvino_path"]):
            shutil.rmtree(details["openvino_path"], ignore_errors=True)
            log.info("weights.delete.openvino_cache_removed", path=details["openvino_path"])

        # We don't delete the .pt file itself, just the entry from our config

        del self.weights[name_to_delete]

        # If the deleted weight was the default, set another one as default
        if was_default:
            first_remaining_weight = next(iter(self.weights.keys()))
            self.set_default_weight(first_remaining_weight)

        self.save_weights()
        log.info("weights.delete.success", name=name_to_delete)

    def convert_to_openvino(self, name: str) -> str | None:
        """
        Converts the specified weight to OpenVINO format.
        Handles caching and updates the config file.
        Returns the path to the converted model directory or None on failure.
        """
        details = self.get_weight_details(name)
        if not details:
            log.error("openvino.convert.not_found", name=name)
            return None

        pt_path = details["path"]
        base_model_name = os.path.splitext(os.path.basename(pt_path))[0]
        cached_model_dir_name = f"{base_model_name}_openvino_model"
        cached_model_dir = os.path.join(OPENVINO_CACHE_DIR, cached_model_dir_name)

        if os.path.exists(cached_model_dir):
            log.info("openvino.cache.found", path=cached_model_dir)
            details["openvino_path"] = os.path.abspath(cached_model_dir)
            self.save_weights()
            return details["openvino_path"]

        log.info("openvino.export.start", model=name)
        try:
            model = YOLO(pt_path)
            # The 'half=True' argument enables FP16 quantization
            exported_path = model.export(format="openvino", half=True)
            os.makedirs(OPENVINO_CACHE_DIR, exist_ok=True)

            # In case of a previous failed attempt, remove the destination first
            shutil.rmtree(cached_model_dir, ignore_errors=True)

            shutil.move(exported_path, cached_model_dir)

            openvino_model_path = os.path.abspath(cached_model_dir)
            details["openvino_path"] = openvino_model_path
            self.save_weights()

            log.info("openvino.export.success", path=openvino_model_path)
            return openvino_model_path

        except Exception as e:
            log.error("openvino.export.failed", exc_info=e)
            shutil.rmtree(cached_model_dir, ignore_errors=True) # Clean up partial export
            messagebox.showerror(
                "OpenVINO Export Error",
                f"Failed to convert '{name}' to OpenVINO format.\n\nError: {e}",
            )
            return None
