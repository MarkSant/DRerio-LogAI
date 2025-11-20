#!/usr/bin/env python3
"""Script simples para remover facades do UIStateController linha por linha."""

from pathlib import Path

# Caminho para o arquivo
main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

# Ler o arquivo
with open(main_vm_path, encoding='utf-8') as f:
    lines = f.readlines()

# PASSO 1: Atualizar chamadas internas
print("Passo 1: Atualizando chamadas internas...")

replacements = {
    'self.video_orchestrator.set_refresh_callback(self.refresh_project_views)':
        'self.video_orchestrator.set_refresh_callback(self.ui_state_controller.refresh_project_views)',
    'self.analysis_coordinator.set_refresh_callback(self.refresh_project_views)':
        'self.analysis_coordinator.set_refresh_callback(self.ui_state_controller.refresh_project_views)',
    'self.update_openvino_status()':
        'self.ui_state_controller.update_openvino_status()',
    'self._show_cancel_feedback()':
        'self.ui_state_controller._show_cancel_feedback()',
    'self.update_detector_parameters(normalized_params, scope="project")':
        'self.ui_state_controller.update_detector_parameters(normalized_params, scope="project")',
}

for i, line in enumerate(lines):
    for old, new in replacements.items():
        if old in line:
            lines[i] = line.replace(old, new)
            print(f"  Linha {i+1}: Substituido")

# PASSO 2: Remover facades do UIStateController
print("\nPasso 2: Removendo facades do UIStateController...")

# Marcar linhas para remover
to_remove = []
in_facade = False
facade_start = None
facade_name = None

for i, line in enumerate(lines):
    # Detectar início de um método
    if line.strip().startswith('def '):
        if in_facade and facade_start is not None:
            # Terminou o facade anterior
            to_remove.append((facade_start, i, facade_name))
            print(f"  Marcado para remocao: {facade_name} (linhas {facade_start+1}-{i})")
        in_facade = False
        facade_start = None
        facade_name = None

    # Detectar facade do UIStateController
    if 'Facade - delegates to UIStateController' in line:
        in_facade = True
        # Encontrar a linha def anterior
        for j in range(i-1, max(0, i-10), -1):
            if lines[j].strip().startswith('def '):
                facade_start = j
                # Extrair nome do método
                def_line = lines[j].strip()
                if '(' in def_line:
                    facade_name = def_line.split('def ')[1].split('(')[0]
                break

# Remover linhas marcadas (em ordem reversa para não afetar índices)
removed_count = 0
for start, end, name in reversed(to_remove):
    del lines[start:end]
    removed_count += 1

# Salvar arquivo
with open(main_vm_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\n===== RESUMO =====")
print(f"Facades removidos: {removed_count}")
print(f"Linhas antes: {len(open(main_vm_path.with_suffix('.py.backup')).readlines())}")
print(f"Linhas depois: {len(lines)}")
print(f"Linhas removidas: ~{len(open(main_vm_path.with_suffix('.py.backup')).readlines()) - len(lines)}")
