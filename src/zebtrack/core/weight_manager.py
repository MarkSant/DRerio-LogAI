import json
import os
import shutil
import time
from pathlib import Path

import structlog

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.utils import calculate_sha256

WEIGHTS_CONFIG_FILE = "weights_config.json"
OPENVINO_CACHE_DIR = "openvino_model_cache"

log = structlog.get_logger()

OPENVINO_STATUS_NOT_CONVERTED = "not_converted"
OPENVINO_STATUS_CONVERTING = "converting"
OPENVINO_STATUS_READY = "ready"
OPENVINO_STATUS_FAILED = "failed"


class OpenVINOExportError(Exception):
    """Exception raised when OpenVINO export fails."""
    pass


class WeightManager:
    def __init__(self, settings_obj=None, config_dir="."):
        """Initialize WeightManager with settings dependency injection.

        Args:
            settings_obj: Settings instance (injected, required for non-test usage)
            config_dir: Directory for weights configuration file
        """
        self.settings = settings_obj
        self.config_dir = config_dir
        self.config_path = os.path.join(self.config_dir, WEIGHTS_CONFIG_FILE)
        self.weights = {}
        self._load_weights()

    def _load_weights(self):
        """Loads the weights configuration from the JSON file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    self.weights = json.load(f)

                # Migrate old format weights to new format with type support
                migrated = False
                for name, details in self.weights.items():
                    if "type" not in details:
                        # Classify weight type based on filename
                        weight_type = self._classify_weight_type(name) or "seg"
                        details["type"] = weight_type
                        details["is_default_seg"] = (
                            details.get("is_default", False) and weight_type == "seg"
                        )
                        details["is_default_det"] = (
                            details.get("is_default", False) and weight_type == "det"
                        )
                        migrated = True
                        log.info("weights.migration.type_added", name=name, type=weight_type)

                    if "openvino_status" not in details:
                        if details.get("openvino_path"):
                            details["openvino_status"] = OPENVINO_STATUS_READY
                        else:
                            details["openvino_status"] = OPENVINO_STATUS_NOT_CONVERTED
                        migrated = True

                    if "last_conversion_error" not in details:
                        details["last_conversion_error"] = None
                        migrated = True

                if migrated:
                    self.save_weights()
                    log.info("weights.migration.completed")

                log.info("weights.config.loaded", path=self.config_path)
            except (OSError, json.JSONDecodeError) as e:
                log.error("weights.config.load_error", error=str(e))
                self.weights = {}
                self._initialize_default_weight()
        else:
            self._initialize_default_weight()

    def get_weight_path_by_method(self, method: str, task: str) -> str | None:
        """
        Gets the weight path for a specific method and task.

        Args:
            method: "seg" or "det"
            task: "aquarium" or "animal" (for logging purposes)

        Returns:
            Path to the appropriate weight file, or None if not found
        """
        if method == "seg":
            name, details = self.get_default_seg_weight()
        elif method == "det":
            name, details = self.get_default_det_weight()
        else:
            log.error("weights.get_path.invalid_method", method=method, task=task)
            return None

        if details:
            path = details.get("path")
            log.info(
                "weights.get_path.selected",
                method=method,
                task=task,
                name=name,
                path=path,
            )
            return path
        else:
            log.warning("weights.get_path.not_found", method=method, task=task)
            return None

    def _classify_weight_type(self, filename: str) -> str | None:
        """
        Classifies weight type based on filename suffix.

        Args:
            filename: The weight filename

        Returns:
            "seg" for segmentation models (*_seg.pt), "det" for detection models
            (*_oi.pt), None if classification can't be determined from suffix.
        """
        filename_lower = filename.lower()
        if filename_lower.endswith("_seg.pt"):
            return "seg"
        elif filename_lower.endswith("_oi.pt"):
            return "det"
        else:
            return None

    def _initialize_default_weight(self):
        """Initializes the config with the default weight from settings."""
        if self.settings is None:
            log.warning(
                "weight_manager.init.no_settings",
                message="Settings not injected, skipping initialization",
            )
            return

        log.info("weights.config.initializing_default")
        self.weights = {}

        # Check for both seg and det weights from settings
        potential_weights = []

        # Add weights from the new settings - register them even if files don't
        # exist yet. This allows the weight management system to be configured
        # before files are available.
        if self.settings.weights.seg_filename:
            potential_weights.append(("seg", self.settings.weights.seg_filename))
        if self.settings.weights.det_filename:
            potential_weights.append(("det", self.settings.weights.det_filename))

        # Check the legacy yolo_model.path for backward compatibility
        legacy_path = self.settings.yolo_model.path
        if legacy_path:
            legacy_name = os.path.basename(legacy_path)
            legacy_type = self._classify_weight_type(legacy_name)
            # Add legacy path if it's not already in potential_weights
            legacy_already_added = any(filename == legacy_path for _, filename in potential_weights)
            if not legacy_already_added:
                potential_weights.append((legacy_type or "seg", legacy_path))

        weights_found = False
        for weight_type, filename in potential_weights:
            # Only register weights if the file actually exists
            if not os.path.exists(filename):
                log.debug(
                    "weights.config.file_not_found",
                    filename=filename,
                    type=weight_type,
                )
                continue

            weight_name = os.path.basename(filename)
            classified_type = self._classify_weight_type(weight_name)
            # Use classified type if available, otherwise use the expected type
            final_type = classified_type or weight_type

            self.weights[weight_name] = {
                "path": filename,
                "is_default": True,  # Keep for backward compatibility
                "type": final_type,
                "is_default_seg": final_type == "seg",
                "is_default_det": final_type == "det",
                "openvino_path": "",
                "openvino_hash": "",
                "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
                "last_conversion_error": None,
            }
            weights_found = True
            log.info(
                "weights.config.weight_initialized",
                name=weight_name,
                type=final_type,
                path=filename,
            )

        if weights_found:
            self.save_weights()
        else:
            log.warning(
                "weights.config.no_weights_found",
                seg_filename=self.settings.weights.seg_filename,
                det_filename=self.settings.weights.det_filename,
                legacy_path=legacy_path,
            )

    def save_weights(self):
        """Saves the current weights configuration to the JSON file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.weights, f, indent=4)
            log.info("weights.config.saved", path=self.config_path)
        except OSError as e:
            log.error("weights.config.save_error", error=str(e))
            raise OSError(f"Não foi possível salvar o arquivo de configuração de pesos: {e}") from e

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

    def get_default_weight_by_type(self, weight_type: str) -> tuple[str, dict] | tuple[None, None]:
        """
        Returns the name and details of the default weight for a specific type.

        Args:
            weight_type: "seg" or "det"

        Returns:
            Tuple of (name, details) or (None, None) if not found
        """
        default_key = f"is_default_{weight_type}"
        for name, details in self.weights.items():
            if details.get(default_key):
                return name, details
        return None, None

    def get_default_seg_weight(self) -> tuple[str, dict] | tuple[None, None]:
        """Returns the name and details of the default segmentation weight."""
        return self.get_default_weight_by_type("seg")

    def get_default_det_weight(self) -> tuple[str, dict] | tuple[None, None]:
        """Returns the name and details of the default detection weight."""
        return self.get_default_weight_by_type("det")

    def set_default_weight_by_type(self, name_to_set: str, weight_type: str):
        """
        Sets a new default weight for a specific type.

        Args:
            name_to_set: Weight name to set as default
            weight_type: "seg" or "det"
        """
        if name_to_set not in self.weights:
            log.error(
                "weights.default_by_type.not_found",
                name=name_to_set,
                type=weight_type,
            )
            return

        weight_details = self.weights[name_to_set]
        if weight_details.get("type") != weight_type:
            log.warning(
                "weights.default_by_type.type_mismatch",
                name=name_to_set,
                expected_type=weight_type,
                actual_type=weight_details.get("type"),
            )
            return

        default_key = f"is_default_{weight_type}"

        # Unset current default for this type
        for name, details in self.weights.items():
            details[default_key] = False

        # Set new default
        self.weights[name_to_set][default_key] = True
        self.save_weights()
        log.info("weights.default_by_type.set", name=name_to_set, type=weight_type)

    def set_default_weight(self, name: str):
        """Sets a new default weight with proper type handling."""
        target_weight = self.get_weight_details(name)
        if not target_weight:
            log.warning("set_default.not_found", name=name)
            return False

        weight_type = target_weight.get("type", "unknown")
        if weight_type not in ("seg", "det"):
            log.error("set_default.unknown_type", name=name, type=weight_type)
            return False

        # Resetar todos os defaults
        for weight in self.weights.values():
            weight["is_default"] = False
            if weight.get("type") == "seg":
                weight["is_default_seg"] = False
            if weight.get("type") == "det":
                weight["is_default_det"] = False

        # Definir o novo default
        target_weight["is_default"] = True
        if weight_type == "seg":
            target_weight["is_default_seg"] = True
        elif weight_type == "det":
            target_weight["is_default_det"] = True

        log.info("set_default.success", name=name, type=weight_type)
        self.save_weights()
        return True

    def add_weight(
        self, new_path: Path | str, set_as_default: bool, weight_type: str | None = None
    ):
        """
        Adds a new weight from a given path after performing security checks.

        Args:
            new_path: The file path to the new .pt weight file.
            set_as_default: If True, this new weight will become the default.
            weight_type: Optional weight type ("seg" or "det"). If None, will be
                         classified from filename.
        """
        new_path = Path(new_path) if isinstance(new_path, str) else new_path
        # --- Security Check: Path Traversal ---
        try:
            # Resolve both paths to their absolute form to prevent symbolic link
            # tricks and ensure the file exists.
            project_dir = Path(self.config_dir).resolve()
            # strict=True checks existence
            model_path = new_path.resolve(strict=True)

            # Check if the model path is inside the project directory.
            # If not, copy it to the project directory.
            if not model_path.is_relative_to(project_dir):
                log.info("weights.add.external_file.copying", source=str(model_path))
                try:
                    target_path = project_dir / model_path.name
                    if target_path.exists():
                        raise ValueError(
                            f"Arquivo de peso '{model_path.name}' já existe no "
                            f"diretório de configuração."
                        )
                    shutil.copy2(model_path, target_path)
                    model_path = target_path  # Use the new copied path
                    log.info("weights.add.external_file.copied", target=str(target_path))
                except Exception as e:
                    log.error("weights.add.external_file.copy_failed", error=str(e))
                    raise ValueError(f"Falha ao copiar o arquivo de peso externo: {e}") from e
        except FileNotFoundError:
            log.error("weights.add.not_found", path=new_path)
            raise FileNotFoundError(f"O arquivo de modelo não foi encontrado: {new_path}") from None
        except Exception as e:
            # This can catch issues like invalid path formats or permissions
            log.error("weights.add.invalid_path", path=new_path, error=str(e))
            raise ValueError(f"O caminho do modelo é inválido ou inacessível: {e}") from e
        # --- End Security Check ---

        new_name = os.path.basename(model_path)
        if new_name in self.weights:
            raise ValueError(f"Um peso com o nome '{new_name}' já existe.")

        # Determine weight type
        if weight_type is None:
            weight_type = self._classify_weight_type(new_name)

        # If still can't classify, this will need to be handled by the caller
        # (GUI should prompt user for type)
        if weight_type is None:
            log.warning("weights.add.type_unclassified", name=new_name)
            # For backward compatibility, default to "seg"
            weight_type = "seg"

        if set_as_default:
            # Unset the current default
            _, current_default = self.get_default_weight()
            if current_default:
                current_default["is_default"] = False

        # Store the safe, resolved path
        self.weights[new_name] = {
            "path": str(model_path),
            "is_default": set_as_default,
            "type": weight_type,
            "is_default_seg": weight_type == "seg" and set_as_default,
            "is_default_det": weight_type == "det" and set_as_default,
            "openvino_path": "",
            "openvino_hash": "",
            "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
            "last_conversion_error": None,
        }
        self.save_weights()
        log.info("weights.add.success", name=new_name, path=str(model_path), type=weight_type)

    def delete_weight(self, name_to_delete: str):
        """Deletes a weight from the configuration."""
        if name_to_delete not in self.weights:
            log.warning("weights.delete.not_found", name=name_to_delete)
            raise ValueError(f"Peso '{name_to_delete}' não encontrado.")

        if len(self.weights) <= 1:
            log.error("weights.delete.last_weight", name=name_to_delete)
            raise ValueError("Você não pode excluir o último peso disponível.")

        details = self.weights[name_to_delete]
        was_default = details.get("is_default")

        # Delete the OpenVINO cache if it exists
        if details.get("openvino_path") and os.path.exists(details["openvino_path"]):
            shutil.rmtree(details["openvino_path"], ignore_errors=True)
            log.info(
                "weights.delete.openvino_cache_removed",
                path=details["openvino_path"],
            )

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

        # The cache should be relative to the manager's config directory
        openvino_base_cache_dir = os.path.join(self.config_dir, OPENVINO_CACHE_DIR)
        cached_model_dir = os.path.join(openvino_base_cache_dir, cached_model_dir_name)

        if os.path.exists(cached_model_dir):
            log.info("openvino.cache.found", path=cached_model_dir)
            # Ensure the path is absolute for consistency
            details["openvino_path"] = os.path.abspath(cached_model_dir)
            details["openvino_status"] = OPENVINO_STATUS_READY
            details["last_conversion_error"] = None
            self.save_weights()
            return details["openvino_path"]

        log.info("openvino.export.start", model=name)
        temp_export_path = None

        if not ULTRALYTICS_AVAILABLE:
            details["openvino_status"] = OPENVINO_STATUS_FAILED
            details["last_conversion_error"] = "Ultralytics package is required for OpenVINO export"
            details["openvino_path"] = ""
            details["openvino_hash"] = ""
            self.save_weights()
            raise ImportError(
                "Ultralytics is not available for OpenVINO export. "
                "Please install ultralytics package."
            )

        details["openvino_status"] = OPENVINO_STATUS_CONVERTING
        details["last_conversion_error"] = None
        self.save_weights()

        try:
            assert YOLO is not None  # Satisfy type checkers after availability guard
            model = YOLO(pt_path)
            # The 'half=True' argument enables FP16 quantization.
            # The export will create a directory named e.g., 'yolov8n_openvino_model'.
            temp_export_path = model.export(format="openvino", half=True)

            os.makedirs(openvino_base_cache_dir, exist_ok=True)

            # In case of a previous failed attempt, remove the destination first.
            if os.path.exists(cached_model_dir):
                shutil.rmtree(cached_model_dir, ignore_errors=True)

            # Atomically move the exported model to its final destination.
            shutil.move(temp_export_path, cached_model_dir)
            temp_export_path = None  # The move was successful

            # Determina o tipo de modelo e cria metadata apropriado
            weight_type = details.get("type", "seg")

            if weight_type == "seg":
                metadata = {
                    "model_type": "instance_segmentation",
                    "num_classes": 2,
                    "class_names": {"0": "aquarium", "1": "zebrafish"},
                    "task": "segment",
                    "weight_type": "seg",
                    "description": (
                        "Modelo de segmentação para detecção de peixes individuais (zebrafish)"
                    ),
                    "original_model": os.path.basename(pt_path),
                    "conversion_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            else:  # det
                metadata = {
                    "model_type": "object_detection",
                    "num_classes": 1,
                    "class_names": {"0": "aquarium"},
                    "task": "detect",
                    "weight_type": "det",
                    "description": "Modelo de detecção para localização de aquários/arenas",
                    "original_model": os.path.basename(pt_path),
                    "conversion_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

            metadata_path = os.path.join(cached_model_dir, "metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            log.info(
                "openvino.metadata.created",
                path=metadata_path,
                model_type=metadata["model_type"],
                weight_type=weight_type,
            )

            # Now that the model is in place, calculate its hash and save.
            openvino_model_path = os.path.abspath(cached_model_dir)
            xml_files = list(Path(cached_model_dir).glob("*.xml"))
            if not xml_files:
                log.error("openvino.export.xml_not_found", path=cached_model_dir)
                # Clean up the corrupted cache dir
                shutil.rmtree(cached_model_dir, ignore_errors=True)
                details["openvino_status"] = OPENVINO_STATUS_FAILED
                details["last_conversion_error"] = (
                    "Arquivo .xml do modelo OpenVINO não encontrado após a conversão."
                )
                self.save_weights()
                raise OpenVINOExportError(
                    "Arquivo .xml do modelo OpenVINO não encontrado após a conversão."
                )

            xml_path = xml_files[0]
            model_hash = calculate_sha256(str(xml_path))

            details["openvino_path"] = openvino_model_path
            details["openvino_hash"] = model_hash
            details["openvino_status"] = OPENVINO_STATUS_READY
            details["last_conversion_error"] = None
            self.save_weights()

            log.info(
                "openvino.export.success",
                path=openvino_model_path,
                hash=model_hash,
            )
            return openvino_model_path

        except Exception as e:
            log.error("openvino.export.failed", exc_info=e)
            # Clean up any partial export directory if it exists
            if os.path.exists(cached_model_dir):
                shutil.rmtree(cached_model_dir, ignore_errors=True)
            details["openvino_path"] = ""
            details["openvino_hash"] = ""
            details["openvino_status"] = OPENVINO_STATUS_FAILED
            details["last_conversion_error"] = str(e)
            self.save_weights()
            raise OpenVINOExportError(
                f"Falha ao converter '{name}' para o formato OpenVINO: {e}"
            ) from e
        finally:
            # Clean up the temporary export directory if the move failed
            if temp_export_path and os.path.exists(temp_export_path):
                shutil.rmtree(temp_export_path, ignore_errors=True)
                log.info("openvino.export.cleanup", path=temp_export_path)
