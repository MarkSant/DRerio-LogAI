#!/usr/bin/env python3
"""Verifica uso interno dos facades RecordingSessionOrchestrator."""

import re
from pathlib import Path

# Facades do RecordingSessionOrchestrator
RECORDING_FACADES = [
    'is_recording',  # property getter
    # 'is_recording',  # property setter (mesmo nome, ignorar)
    '_on_recording_state_changed',
    '_setup_recording_service_callbacks',
    '_init_recording_service',
    '_clear_external_trigger_wait',
    'on_arduino_event',
    'trigger_recording',
    '_schedule_recording',
    'run_live_calibration',
    '_handle_external_trigger',
    'start_recording',
    'stop_recording',
    'start_live_project_session',
    '_ensure_zones_before_recording',
]

# Caminho
main_vm_path = Path(__file__).parent / "src" / "zebtrack" / "core" / "main_view_model.py"

# Ler o arquivo
with open(main_vm_path, 'r', encoding='utf-8') as f:
    content = f.read()

print("Verificando uso interno dos facades RecordingSessionOrchestrator...\n")

used_internally = []
not_used = []

for method in RECORDING_FACADES:
    # Procurar por self.{method}(
    pattern = rf'self\.{re.escape(method)}\('

    # Encontrar todas as ocorrências
    matches = list(re.finditer(pattern, content))

    # Filtrar para excluir a definição do método e properties
    definition_pattern = rf'def {re.escape(method)}\('
    property_pattern = rf'@property|@{re.escape(method)}\.setter'

    definition_matches = re.finditer(definition_pattern, content)
    definition_positions = [m.start() for m in definition_matches]

    # Contar apenas as chamadas, não definições
    calls = [m for m in matches if m.start() not in definition_positions]

    if calls:
        print(f"[X] {method}: {len(calls)} chamadas internas")
        used_internally.append((method, len(calls)))
    else:
        print(f"[OK] {method}: nao usado internamente")
        not_used.append(method)

print(f"\nResumo:")
print(f"  Facades seguros para remover: {len(not_used)}")
print(f"  Facades com uso interno: {len(used_internally)}")

if used_internally:
    print(f"\nAVISO: Os seguintes facades TEM uso interno:")
    for method, count in used_internally:
        print(f"  - {method}: {count} chamadas")
