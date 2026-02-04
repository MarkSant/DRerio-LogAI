<!-- markdownlint-disable MD024 -->

# Multi-Subject Wizard Troubleshooting Guide

**Data**: 2024-12-24
**Contexto**: Problema reportado onde o wizard detecta 2 sujeitos por vídeo no regex, mas a estrutura do projeto mostra apenas 1 sujeito por arquivo.

## Problema Relatado

O usuário reporta que ao usar o wizard com projetos multi-aquário (2 aquários por vídeo):

1. ✅ A nomenclatura dos arquivos está correta (ex: `G1_D1_S1--G1_D1_S2.mp4`)
2. ✅ O regex identifica corretamente 2 sujeitos por vídeo
3. ❌ **MAS** a estrutura do projeto (dias/grupos/sujeitos) mostra apenas 1 sujeito por arquivo

## Arquitetura Atual (Como DEVERIA Funcionar)

### Fluxo de Dados Correto

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. DETECÇÃO (detection_step.py)                            │
│    _pattern_custom_regex()                                 │
│    └─> subject_mappings = {                                │
│         "G1_D1_S1--G1_D1_S2.mp4": [                        │
│           {"group": "G1", "day": "D1", "subject": "S1"},   │
│           {"group": "G1", "day": "D1", "subject": "S2"}    │
│         ]                                                   │
│       }                                                     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ENRIQUECIMENTO (project_workflow_service.py)            │
│    _enrich_videos_with_design_metadata()                   │
│    └─> enriched_videos = [                                 │
│         {                                                   │
│           "path": "G1_D1_S1--G1_D1_S2.mp4",                │
│           "metadata": {                                     │
│             "is_multi_subject": True,                       │
│             "subject_entries": [                            │
│               {"group": "G1", "day": "D1", "subject": "S1"}│
│               {"group": "G1", "day": "D1", "subject": "S2"}│
│             ]                                               │
│           }                                                 │
│         }                                                   │
│       ]                                                     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. EXIBIÇÃO (validation_manager.py)                        │
│    _build_video_hierarchy()                                │
│    └─> EXPANDE vídeos multi-subject em múltiplas entradas: │
│        G1 → Day01 → S01 (G1_D1_S1--G1_D1_S2.mp4)           │
│                  └→ S02 (G1_D1_S1--G1_D1_S2.mp4)           │
└─────────────────────────────────────────────────────────────┘
```

### Código Relevante

#### 1. Detecção ([detection_step.py:424-525](../../src/zebtrack/ui/wizard/detection_step.py#L424-L525))

```python
# Mapa de arquivos → lista de sujeitos
subject_mappings: dict[str, list[dict]] = {}

for path in paths:
    path_str = str(path)
    file_subjects: list[dict] = []

    # ... extração via regex ...

    # Armazena mapeamento
    if file_subjects:
        subject_mappings[path_str] = file_subjects

# Retorna no detected_design
return {
    "groups": sorted(list(groups_found)),
    "days": sorted(list(days_found)),
    "subjects_per_group": subjects_per_group_sorted,
    "subject_mappings": subject_mappings,  # ← CRÍTICO
}
```

#### 2. Enriquecimento ([project_workflow_service.py:1176-1264](../../src/zebtrack/core/project_workflow_service.py#L1176-L1264))

```python
# Extrai subject_mappings do design detectado
raw_subject_mappings = detected_design.get("subject_mappings") or {}

# Normaliza paths (Windows \ vs /)
subject_mappings: dict[str, list[dict]] = {}
for key, value in raw_subject_mappings.items():
    normalized_key = str(Path(key).as_posix())
    subject_mappings[normalized_key] = value
    subject_mappings[key] = value  # Mantém original também

# Para cada vídeo escaneado
for original_video in scanned_videos:
    path_str = str(enriched.get("path", ""))

    # Tenta lookup (original e normalizado)
    file_subjects = subject_mappings.get(path_str, [])
    if not file_subjects:
        normalized_path = str(Path(path_str).as_posix())
        file_subjects = subject_mappings.get(normalized_path, [])

    # Se encontrou 2+ sujeitos, marca como multi-subject
    if len(file_subjects) > 1:
        enriched["is_multi_subject"] = True
        enriched["subject_entries"] = file_subjects
        metadata["is_multi_subject"] = True
        metadata["subject_entries"] = file_subjects  # ← CRÍTICO
```

#### 3. Expansão UI ([validation_manager.py:1005-1030](../../src/zebtrack/ui/components/validation_manager.py#L1005-L1030))

```python
for video in all_videos:
    metadata = video.get("metadata") or {}

    is_multi_subject = metadata.get("is_multi_subject", False)
    subject_entries = metadata.get("subject_entries", [])

    if is_multi_subject and len(subject_entries) > 1:
        # Expande em múltiplas entradas
        for idx, entry in enumerate(subject_entries):
            self._add_video_entry_to_hierarchy(
                hierarchy,
                video,
                metadata,
                normalized,
                subject_override=entry.get("subject"),  # ← Usa sujeito específico
                group_override=entry.get("group"),
                day_override=entry.get("day"),
                is_multi_subject_entry=True,
                multi_subject_index=idx,
            )
```

## Possíveis Causas do Problema

### 1. **Regex Customizada NÃO Foi Usada**

❌ **Problema**: Usuário pode ter usado detecção automática de pastas, que NÃO suporta multi-subject.

✅ **Solução**: No wizard, usar **"Configuração Personalizada"** e definir regex customizada.

**Como Verificar**:

```python
# Verificar no projeto salvo:
project_data = project_manager.project_data
detected_design = project_data.get("project_metadata", {}).get("detected_design", {})
pattern_used = detected_design.get("pattern_used")

print(f"Padrão usado: {pattern_used}")
# Esperado: "custom_regex"
# Se for "groups_as_folders" ou outro → ERRADO
```

### 2. **Path Normalization Mismatch**

❌ **Problema**: Paths podem estar em formatos diferentes entre detecção e enriquecimento.

**Exemplo**:

- Detecção: `"C:\\Videos\\G1_D1_S1--G1_D1_S2.mp4"` (Windows backslash)
- Enriquecimento: `"C:/Videos/G1_D1_S1--G1_D1_S2.mp4"` (POSIX forward slash)
- Lookup falha mesmo com normalização se houver outros problemas

✅ **Solução**: O código JÁ tenta ambos os formatos (linhas 1224-1228), mas pode haver edge cases.

### 3. **subject_mappings Não Foi Preservado**

❌ **Problema**: O `design_editor_dialog.py` pode não estar preservando `subject_mappings` quando usuário edita design.

**Como Verificar**:

```python
# Após o wizard, verificar se subject_mappings está lá:
detected_design = wizard_data.get("detected_design", {})
sm = detected_design.get("subject_mappings", {})

print(f"Subject mappings count: {len(sm)}")
# Se for 0 → PROBLEMA!
```

**Fix Atual**: [design_editor_dialog.py:520-522](../../src/zebtrack/ui/wizard/design_editor_dialog.py#L520-L522)

```python
# Preserve subject_mappings from input_design
if self.input_design.get("subject_mappings"):
    self.edited_design["subject_mappings"] = self.input_design["subject_mappings"]
```

### 4. **Projeto É Live (Câmera Ao Vivo)**

❌ **Problema**: Projetos Live NÃO usam enriquecimento de metadados.

**Como Verificar**:

```python
project_type = project_data.get("project_type")
print(f"Project type: {project_type}")
# Se for "live" → Multi-subject NÃO é suportado ainda para Live
```

**Fix**: Enriquecimento só acontece se `not is_live` (linha 432 de `project_workflow_service.py`).

## Diagnóstico Passo-a-Passo

### Passo 1: Execute o Script de Diagnóstico

```bash
poetry run python scripts/debug_multi_subject_wizard.py
```

Este script adiciona logging detalhado em 🔍 **PATCH** messages.

### Passo 2: Crie um Projeto Multi-Subject no Wizard

1. Arquivos de exemplo: `G1_D1_S1--G1_D1_S2.mp4`
2. No wizard, escolha **"Configuração Personalizada"**
3. Defina regex:
   - **Grupos**: `G(\d+)`
   - **Dias**: `D(\d+)`
   - **Sujeitos**: `S(\d+)`
4. Complete o wizard

### Passo 3: Verifique os Logs

Procure por:

#### ✅ **SUCESSO** - Detecção funcionou

```text
🔍 PATCH: detection_step._pattern_custom_regex completed
  total_files=10
  subject_mappings_count=10
  multi_subject_files=[
    {
      "file": "G1_D1_S1--G1_D1_S2.mp4",
      "subjects": 2,
      "entries": [
        {"group": "G1", "day": "D1", "subject": "S1"},
        {"group": "G1", "day": "D1", "subject": "S2"}
      ]
    }
  ]
```

#### ❌ **ERRO** - subject_mappings vazio

```text
⚠️ PATCH: detection_step._pattern_custom_regex NO subject_mappings!
  has_result=True
  result_keys=['groups', 'days', 'subjects_per_group', 'confidence', 'pattern_used']
```

#### ✅ **SUCESSO** - Enriquecimento recebeu dados

```text
🔍 PATCH: _enrich_videos_with_design_metadata called
  scanned_videos_count=10
  has_subject_mappings=True
  subject_mappings_count=10
```

#### ❌ **ERRO** - subject_mappings não chegou

```text
🔍 PATCH: _enrich_videos_with_design_metadata called
  has_subject_mappings=False
  subject_mappings_count=0
```

#### ✅ **SUCESSO** - Vídeos marcados como multi-subject

```text
🔍 PATCH: _enrich_videos_with_design_metadata completed
  multi_subject_videos_count=10
  multi_subject_videos=[
    {
      "path": "G1_D1_S1--G1_D1_S2.mp4",
      "is_multi_subject": True,
      "subject_entries_count": 2
    }
  ]
```

#### ❌ **ERRO** - Nenhum vídeo marcado

```text
🔍 PATCH: _enrich_videos_with_design_metadata completed
  multi_subject_videos_count=0
```

#### ✅ **SUCESSO** - UI recebeu vídeos multi-subject

```text
🔍 PATCH: _build_video_hierarchy called
  total_videos=10
  multi_subject_videos=[
    {
      "path": "G1_D1_S1--G1_D1_S2.mp4",
      "is_multi_subject": True,
      "subject_entries_count": 2
    }
  ]
```

#### ✅ **SUCESSO** - Hierarquia expandida corretamente

```text
🔍 PATCH: _build_video_hierarchy completed
  groups_count=1
  total_tree_entries=20  # ← 10 vídeos × 2 sujeitos = 20 entradas!
```

## Soluções Potenciais

### Solução 1: Garantir Uso de Regex Customizada

**NO WIZARD**, certifique-se de:

1. Escolher **"Configuração Personalizada"**
2. Preencher todos os campos de regex
3. Testar o padrão antes de finalizar

### Solução 2: Adicionar Logging Permanente

Se o problema persistir, adicionar logging permanente em pontos críticos:

```python
# Em project_workflow_service.py, após linha 1228:
log.warning(
    "MULTI_SUBJECT_DEBUG.path_lookup",
    video_path=path_str[-50:],
    file_subjects_found=len(file_subjects),
    subject_mappings_sample=list(subject_mappings.keys())[:3],
)
```

### Solução 3: Verificar Formato dos Nomes de Arquivo

Os nomes **DEVEM** seguir o padrão:

- Separator `--` entre sujeitos
- Padrão consistente: `G1_D1_S1--G1_D1_S2.mp4`
- Regex deve capturar todos os matches

### Solução 4: Forçar Normalização Agressiva

Se há problemas de path, adicionar normalização extra:

```python
# Em project_workflow_service.py:1183-1187
for key, value in raw_subject_mappings.items():
    # Normaliza para forward slashes
    normalized_key = str(Path(key).as_posix()).lower()
    subject_mappings[normalized_key] = value
    # Também mantém original
    subject_mappings[str(key)] = value
    subject_mappings[str(key).lower()] = value
```

## Checklist de Verificação

Antes de reportar como bug, verificar:

- [ ] Usou **regex customizada** no wizard (não detecção automática)
- [ ] Nomes dos arquivos seguem padrão correto
- [ ] Regex captura todos os grupos/dias/sujeitos corretamente
- [ ] Executou script de diagnóstico e verificou logs
- [ ] Projeto NÃO é do tipo "live"
- [ ] `subject_mappings` aparece nos logs de detecção
- [ ] Vídeos foram marcados como `is_multi_subject=True`
- [ ] `subject_entries` tem 2+ entradas

## Arquivos Relacionados

### Código Principal

- [detection_step.py](../../src/zebtrack/ui/wizard/detection_step.py) - Linhas 387-575
- [project_workflow_service.py](../../src/zebtrack/core/project_workflow_service.py) - Linhas 1139-1279
- [validation_manager.py](../../src/zebtrack/ui/components/validation_manager.py) - Linhas 1000-1030
- [design_editor_dialog.py](../../src/zebtrack/ui/wizard/design_editor_dialog.py) - Linhas 520-522

### Testes

- [test_multi_aquarium_regex.py](../../tests/test_multi_aquarium_regex.py) - Testes de extração multi-subject

### Scripts

- [debug_multi_subject_wizard.py](../../scripts/debug_multi_subject_wizard.py) - Script de diagnóstico

## Próximos Passos

1. Execute o script de diagnóstico
2. Compartilhe os logs `🔍 PATCH` messages
3. Se não aparecerem, o problema está na detecção
4. Se aparecerem mas não propagarem, o problema está no enriquecimento
5. Se propagarem mas não expandirem na UI, o problema está na ValidationManager

---

**Status**: Documentação criada em 2024-12-24
**Investigador**: Claude (via MarkSant)
**Arquitetura Validada**: v2.1+ (Multi-Subject Support)
