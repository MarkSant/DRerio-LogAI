#!/usr/bin/env python3
"""Verifica se facades são usados internamente no MainViewModel."""

import re
from pathlib import Path

# Facades do UIStateController
UI_STATE_FACADES = [
    '_schedule_on_ui', 'refresh_project_views', '_show_post_creation_guide',
    'setup_detector_zones', 'add_new_weight', 'delete_weight', 'set_active_weight',
    'manage_weights', 'load_new_weight', 'set_openvino_usage',
    'convert_active_weight_to_openvino', 'update_openvino_status',
    'update_detector_parameters', 'apply_roi_template', 'update_main_arena',
    '_show_cancel_feedback', '_validate_zones_with_ui', '_handle_validation_error',
    '_activate_analysis_view_mode', '_prepare_processing_ui', '_finalize_processing',
    '_update_diagnostic_progress', '_finish_progress_dialog',
]

# Caminho para o arquivo
main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

# Ler o arquivo
with open(main_vm_path, 'r', encoding='utf-8') as f:
    content = f.read()

print("Verificando uso interno dos facades no MainViewModel...\n")

used_internally = []
not_used = []

for method in UI_STATE_FACADES:
    # Procurar por self.{method}( mas não na definição do método
    pattern = rf'self\.{re.escape(method)}\('

    # Encontrar todas as ocorrências
    matches = list(re.finditer(pattern, content))

    # Filtrar para excluir a definição do método
    definition_pattern = rf'def {re.escape(method)}\('
    definition_match = re.search(definition_pattern, content)

    if definition_match:
        # Contar apenas as chamadas, não a definição
        calls = [m for m in matches if m.start() != definition_match.start()]

        if calls:
            print(f"[X] {method}: {len(calls)} chamadas internas")
            used_internally.append((method, len(calls)))
        else:
            print(f"[OK] {method}: nao usado internamente")
            not_used.append(method)
    else:
        print(f"[?] {method}: metodo nao encontrado")

print(f"\nResumo:")
print(f"  Facades seguros para remover: {len(not_used)}")
print(f"  Facades com uso interno: {len(used_internally)}")

if used_internally:
    print(f"\nAVISO: Os seguintes facades TÊM uso interno:")
    for method, count in used_internally:
        print(f"  - {method}: {count} chamadas")
