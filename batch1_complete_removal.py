#!/usr/bin/env python3
"""Script completo para Batch 1: Atualizar chamadas internas e remover facades."""

import re
from pathlib import Path

# Caminho para o arquivo
main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

# Ler o arquivo
with open(main_vm_path, encoding='utf-8') as f:
    content = f.read()

print("=" * 80)
print("BATCH 1: REMOÇÃO DE FACADES UISTATECONTROLLER")
print("=" * 80)

# PASSO 1: Atualizar chamadas internas
print("\nPasso 1: Atualizando chamadas internas...")

replacements = [
    # refresh_project_views (2 chamadas)
    (r'self\.video_orchestrator\.set_refresh_callback\(self\.refresh_project_views\)',
     r'self.video_orchestrator.set_refresh_callback(self.ui_state_controller.refresh_project_views)'),
    (r'self\.analysis_coordinator\.set_refresh_callback\(self\.refresh_project_views\)',
     r'self.analysis_coordinator.set_refresh_callback(self.ui_state_controller.refresh_project_views)'),

    # update_openvino_status (1 chamada)
    (r'(\s+)self\.update_openvino_status\(\)',
     r'\1self.ui_state_controller.update_openvino_status()'),

    # _show_cancel_feedback (2 chamadas)
    (r'(\s+)self\._show_cancel_feedback\(\)',
     r'\1self.ui_state_controller._show_cancel_feedback()'),

    # update_detector_parameters (1 chamada)
    (r'self\.update_detector_parameters\(normalized_params, scope="project"\)',
     r'self.ui_state_controller.update_detector_parameters(normalized_params, scope="project")'),
]

for pattern, replacement in replacements:
    old_content = content
    content = re.sub(pattern, replacement, content)
    if content != old_content:
        print(f"  [OK] Substituicao aplicada: {pattern[:50]}...")

# PASSO 2: Remover todos os facades do UIStateController
print("\nPasso 2: Removendo facades do UIStateController...")

# Padrão mais robusto para encontrar facades
# Procura por métodos que contenham "Facade - delegates to UIStateController"
pattern = r'(\n    def \w+\([^)]*\):[^\n]*\n(?:.*?\n)*?.*?Facade - delegates to UIStateController.*?\n(?:.*?\n)*?.*?(?=\n    def |\n\nclass |\Z))'

# Encontrar todos os facades
matches = list(re.finditer(pattern, content, re.DOTALL | re.MULTILINE))

print(f"Encontrados {len(matches)} facades do UIStateController")

# Extrair nomes dos métodos antes de remover (para log)
facade_names = []
for match in matches:
    method_match = re.search(r'def (\w+)\(', match.group(1))
    if method_match:
        facade_names.append(method_match.group(1))

# Remover cada facade (em ordem reversa para não afetar índices)
removed_count = 0
for i, match in enumerate(reversed(matches)):
    idx = len(matches) - 1 - i
    method_name = facade_names[idx] if idx < len(facade_names) else "unknown"
    print(f"  {removed_count + 1:2}. Removendo: {method_name}")
    content = content[:match.start()] + content[match.end():]
    removed_count += 1

# Salvar arquivo modificado
with open(main_vm_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n" + "=" * 80)
print("RESUMO")
print("=" * 80)
print(f"Facades removidos: {removed_count}")
print(f"Arquivo atualizado: {main_vm_path}")
print("\nPróximo passo: Executar testes para validar remoções")
