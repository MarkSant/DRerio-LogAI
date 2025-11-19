#!/usr/bin/env python3
"""Remove facades do RecordingSessionOrchestrator (Batch 2)."""

from pathlib import Path

main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

with open(main_vm_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("BATCH 2: Removendo facades RecordingSessionOrchestrator...")

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

    if 'Facade - delegates to RecordingSessionOrchestrator' in line:
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

print(f"\n===== RESUMO BATCH 2 =====")
print(f"Facades removidos: {removed_count}")
print(f"Linhas no arquivo: {len(lines)}")
