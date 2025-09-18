import json
import os
import shutil
import time
from pathlib import Path
from tkinter import messagebox

import structlog

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.settings import settings
from zebtrack.utils import calculate_sha256

WEIGHTS_CONFIG_FILE = "weights_config.json"
OPENVINO_CACHE_DIR = "openvino_model_cache"

log = structlog.get_logger()


class WeightManager:
    def __init__(self, config_dir="."):
        self.config_dir = config_dir
        self.config_path = os.path.join(self.config_dir, WEIGHTS_CONFIG_FILE)
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
                    "openvino_hash": "",
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
                "Erro", "Não foi possível salvar o arquivo de configuração de pesos."
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
        Adds a new weight from a given path after performing security checks.

        Args:
            new_path: The file path to the new .pt weight file.
            set_as_default: If True, this new weight will become the default.
        """
        # --- Security Check: Path Traversal ---
        try:
            # Resolve both paths to their absolute form to prevent symbolic link
            # tricks and ensure the file exists.
            project_dir = Path(self.config_dir).resolve()
            # strict=True checks existence
            model_path = Path(new_path).resolve(strict=True)

            # Check if the model path is inside the project directory.
            # This is the primary defense against path traversal.
            if not model_path.is_relative_to(project_dir):
                log.error(
                    "weights.add.path_traversal_attempt",
                    model_path=str(model_path),
                    project_dir=str(project_dir),
                )
                messagebox.showerror(
                    "Caminho do Modelo Inválido",
                    "O arquivo de modelo selecionado deve estar localizado dentro da "
                    "pasta do projeto.",
                )
                return
        except FileNotFoundError:
            log.error("weights.add.not_found", path=new_path)
            messagebox.showerror(
                "Arquivo não Encontrado",
                f"O arquivo de modelo não foi encontrado:\n{new_path}",
            )
            return
        except Exception as e:
            # This can catch issues like invalid path formats or permissions
            log.error("weights.add.invalid_path", path=new_path, error=str(e))
            messagebox.showerror(
                "Caminho Inválido",
                f"O caminho do modelo é inválido ou inacessível:\n{e}",
            )
            return
        # --- End Security Check ---

        new_name = os.path.basename(new_path)
        if new_name in self.weights:
            messagebox.showinfo(
                "Já Existe", f"Um peso com o nome '{new_name}' já existe."
            )
            return

        if set_as_default:
            # Unset the current default
            _, current_default = self.get_default_weight()
            if current_default:
                current_default["is_default"] = False

        # Store the original, user-provided path for display, but know it's safe.
        self.weights[new_name] = {
            "path": new_path,
            "is_default": set_as_default,
            "openvino_path": "",
            "openvino_hash": "",
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
                "Não é Possível Excluir",
                "Você não pode excluir o último peso disponível.",
            )
            return

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
            self.save_weights()
            return details["openvino_path"]

        log.info("openvino.export.start", model=name)
        temp_export_path = None
        
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "Ultralytics is not available for OpenVINO export. "
                "Please install ultralytics package."
            )
        
        try:
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

            # Cria arquivo de metadata
            metadata = {
                'model_type': 'instance_segmentation',
                'num_classes': 2,
                'class_names': {
                    '0': 'aquarium',
                    '1': 'zebrafish'
                },
                'task': 'segment',
                'original_model': os.path.basename(pt_path),
                'conversion_date': time.strftime('%Y-%m-%d %H:%M:%S')
            }

            metadata_path = os.path.join(cached_model_dir, 'metadata.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            log.info("openvino.metadata.created", path=metadata_path)

            # Now that the model is in place, calculate its hash and save.
            openvino_model_path = os.path.abspath(cached_model_dir)
            xml_files = list(Path(cached_model_dir).glob("*.xml"))
            if not xml_files:
                log.error("openvino.export.xml_not_found", path=cached_model_dir)
                messagebox.showerror(
                    "Erro na Exportação",
                    "Arquivo .xml do modelo OpenVINO não encontrado após a conversão.",
                )
                # Clean up the corrupted cache dir
                shutil.rmtree(cached_model_dir, ignore_errors=True)
                return None

            xml_path = xml_files[0]
            model_hash = calculate_sha256(str(xml_path))

            details["openvino_path"] = openvino_model_path
            details["openvino_hash"] = model_hash
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
            messagebox.showerror(
                "Erro na Exportação OpenVINO",
                f"Falha ao converter '{name}' para o formato OpenVINO.\n\nErro: {e}",
            )
            return None
        finally:
            # Clean up the temporary export directory if the move failed
            if temp_export_path and os.path.exists(temp_export_path):
                shutil.rmtree(temp_export_path, ignore_errors=True)
                log.info("openvino.export.cleanup", path=temp_export_path)
