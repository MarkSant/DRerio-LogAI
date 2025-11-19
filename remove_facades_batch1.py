#!/usr/bin/env python3
"""Script para remover facades do UIStateController do MainViewModel."""

import re
from pathlib import Path

# Facades do UIStateController a remover
UI_STATE_FACADES = [
    ('_schedule_on_ui', 951),
    ('refresh_project_views', 1242),
    ('_show_post_creation_guide', 1368),
    ('setup_detector_zones', 1428),
    ('add_new_weight', 1469),
    ('delete_weight', 1480),
    ('set_active_weight', 1487),
    ('manage_weights', 1494),
    ('load_new_weight', 1501),
    ('set_openvino_usage', 1515),
    ('convert_active_weight_to_openvino', 1522),
    ('update_openvino_status', 1529),
    ('update_detector_parameters', 1611),
    ('apply_roi_template', 1759),
    ('update_main_arena', 1780),
    ('_show_cancel_feedback', 1983),
    ('_validate_zones_with_ui', 2095),
    ('_handle_validation_error', 2102),
    ('_activate_analysis_view_mode', 2279),
    ('_prepare_processing_ui', 2286),
    ('_finalize_processing', 2293),
    ('_update_diagnostic_progress', 2725),
    ('_finish_progress_dialog', 2743),
]

# Caminho para o arquivo
main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

# Ler o arquivo
with open(main_vm_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Encontrar e remover cada facade
removed_count = 0
lines_removed = 0

for method_name, approx_line in UI_STATE_FACADES:
    # Procurar a definição do método (pode ter deslocado devido a remoções anteriores)
    found = False
    for i in range(max(0, approx_line - 50), min(len(lines), approx_line + 50)):
        if f'def {method_name}(' in lines[i]:
            # Encontrou o método, agora encontrar onde termina
            start_line = i

            # Encontrar o fim do método (próximo def ou fim do arquivo)
            end_line = start_line + 1
            indent = len(lines[start_line]) - len(lines[start_line].lstrip())

            while end_line < len(lines):
                line = lines[end_line]
                # Se linha não está vazia e tem indentação menor ou igual, terminou o método
                if line.strip() and not line.strip().startswith('#'):
                    line_indent = len(line) - len(line.lstrip())
                    if line_indent <= indent:
                        break
                end_line += 1

            # Verificar se é realmente um facade UIStateController
            method_block = ''.join(lines[start_line:end_line])
            if 'Facade - delegates to UIStateController' in method_block:
                print(f"Removendo {method_name} (linhas {start_line+1}-{end_line})")
                # Remover o método
                del lines[start_line:end_line]
                removed_count += 1
                lines_removed += (end_line - start_line)
                found = True
                break

    if not found:
        print(f"AVISO: Não encontrou {method_name} próximo à linha {approx_line}")

# Salvar arquivo modificado
with open(main_vm_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"\nResumo:")
print(f"  Facades removidos: {removed_count}/{len(UI_STATE_FACADES)}")
print(f"  Linhas removidas: {lines_removed}")
print(f"  Arquivo atualizado: {main_vm_path}")
