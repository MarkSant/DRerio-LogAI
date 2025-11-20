#!/usr/bin/env python3
"""Script melhorado para remover TODOS os facades do UIStateController."""

import re
from pathlib import Path

# Caminho para o arquivo
main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

# Ler o arquivo
with open(main_vm_path, encoding='utf-8') as f:
    content = f.read()

# Padrão para encontrar facades do UIStateController
# Procura por métodos que contenham "Facade - delegates to UIStateController"
pattern = r'(\n    def \w+\([^)]*\):.*?Facade - delegates to UIStateController.*?(?=\n    def |\n\nclass |\Z))'

# Encontrar todos os facades
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"Encontrados {len(matches)} facades do UIStateController\n")

# Remover cada facade
removed_count = 0
for match in reversed(matches):  # Reverso para não afetar índices
    # Extrair nome do método para log
    method_match = re.search(r'def (\w+)\(', match.group(1))
    if method_match:
        method_name = method_match.group(1)
        print(f"Removendo facade: {method_name}")
        # Remover o facade do conteúdo
        content = content[:match.start()] + content[match.end():]
        removed_count += 1

# Salvar arquivo modificado
with open(main_vm_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n===== RESUMO =====")
print(f"Facades do UIStateController removidos: {removed_count}")
print(f"Arquivo atualizado: {main_vm_path}")
