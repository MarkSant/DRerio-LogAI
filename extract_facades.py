#!/usr/bin/env python3
"""Script para extrair todos os métodos facade do MainViewModel."""

import re
from pathlib import Path

# Caminho para o arquivo MainViewModel
main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

# Ler o arquivo
with open(main_vm_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Regex para identificar facades
facade_pattern = re.compile(r'Facade - delegates to (\w+)')

# Encontrar todos os facades
facades = []
current_method = None
current_line = None

for i, line in enumerate(lines, 1):
    # Procurar por definição de método
    method_match = re.match(r'\s+def\s+(\w+)\s*\(', line)
    if method_match:
        current_method = method_match.group(1)
        current_line = i

    # Procurar por facade
    facade_match = facade_pattern.search(line)
    if facade_match and current_method:
        orchestrator = facade_match.group(1)

        # Encontrar a linha de delegação (próximas 5 linhas)
        delegation = None
        for j in range(i, min(i+5, len(lines))):
            if 'return' in lines[j] and orchestrator.lower() in lines[j].lower():
                delegation = lines[j].strip()
                break

        facades.append({
            'method': current_method,
            'line': current_line,
            'orchestrator': orchestrator,
            'delegation': delegation,
            'facade_line': i
        })

# Agrupar por orchestrator
by_orchestrator = {}
for facade in facades:
    orch = facade['orchestrator']
    if orch not in by_orchestrator:
        by_orchestrator[orch] = []
    by_orchestrator[orch].append(facade)

# Imprimir resultados
print("=" * 80)
print("FACADES IDENTIFICADOS NO MAINVIEWMODEL")
print("=" * 80)

for orch, facade_list in sorted(by_orchestrator.items(), key=lambda x: -len(x[1])):
    print(f"\n{orch}: {len(facade_list)} facades")
    print("-" * 80)
    for i, facade in enumerate(facade_list, 1):
        print(f"{i:2}. Linha {facade['line']:4}: {facade['method']}")
        if facade['delegation']:
            print(f"    → {facade['delegation']}")

print(f"\nTOTAL: {len(facades)} facades")
