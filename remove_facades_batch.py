#!/usr/bin/env python3
"""Script genérico para remover facades de qualquer orchestrator."""

import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Uso: python remove_facades_batch.py <orchestrator_name>")
    print("Exemplos:")
    print("  python remove_facades_batch.py ProjectOrchestrator")
    print("  python remove_facades_batch.py CalibrationOrchestrator")
    sys.exit(1)

orchestrator_name = sys.argv[1]

main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

with open(main_vm_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Removendo facades de {orchestrator_name}...")

# Marcar linhas para remover
to_remove = []
in_facade = False
facade_start = None
facade_name = None

for i, line in enumerate(lines):
    if line.strip().startswith('def ') or line.strip().startswith('@'):
        if in_facade and facade_start is not None:
            to_remove.append((facade_start, i, facade_name))
            print(f"  Marcado: {facade_name} (linhas {facade_start+1}-{i})")
        in_facade = False
        facade_start = None
        facade_name = None

    if f'Facade - delegates to {orchestrator_name}' in line:
        in_facade = True
        for j in range(i-1, max(0, i-10), -1):
            if lines[j].strip().startswith('def ') or lines[j].strip().startswith('@'):
                facade_start = j
                def_line = lines[j].strip()
                if 'def ' in def_line and '(' in def_line:
                    facade_name = def_line.split('def ')[1].split('(')[0]
                break

# Remover linhas (ordem reversa)
removed_count = 0
for start, end, name in reversed(to_remove):
    del lines[start:end]
    removed_count += 1

with open(main_vm_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"\n===== RESUMO =====")
print(f"Orchestrator: {orchestrator_name}")
print(f"Facades removidos: {removed_count}")
print(f"Linhas no arquivo: {len(lines)}")
