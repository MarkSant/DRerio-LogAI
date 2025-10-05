```markdown
# WIZARD PROJECT CREATION - VERSÃO 2
Documento de Especificação Ampliado  
Arquivo: `docs/WIZARD_PROJECT_CREATION_V2.md`  
Baseado na versão original: `docs/WIZARD_PROJECT_CREATION.md` (mantida sem alterações)  
Status: Especificação Expandida / Pré-Implementação  
Schema do Wizard: `wizard_schema_version = 1`  
Última atualização: 2025-10-04  
Idioma: PT-BR (termos técnicos preservados)  

---

## 0. Sumário

1. Propósito e Motivação  
2. Principais Melhorias vs. Versão Original  
3. Glossário e Convenções  
4. Enumerações Formais (Canonical Enums)  
5. Fórmula de Confiança (Design Detection Confidence)  
6. Arquitetura Geral do Wizard  
7. Fluxo Completo por Etapa (Steps 1–5)  
8. Estados, Validações e Eventos (Back/Next/Create)  
9. Modelo de Dados Unificado (Wizard Data Contract)  
10. Estratégia de Importação (Import Config + ROI Merge)  
11. Algoritmos de Detecção (Folders, Filenames, Parquets)  
12. Estimativa de Tempo de Processamento  
13. Logging, Auditoria e Telemetria  
14. Estratégia de Acessibilidade (A11y)  
15. Internacionalização (i18n)  
16. Desempenho e Escalabilidade  
17. Tratamento de Erros e Edge Cases  
18. Testes (Unit, Integração, E2E, Stress)  
19. Roadmap de Implementação por Fases  
20. Checklist Final Antes de Criar o Projeto  
21. Exemplo de JSON Final Persistido  
22. Plano de Migração / Legado  
23. Riscos e Mitigações  
24. Apêndices (Tabela de Ações Derivadas, Exemplos de Logs, Regex)  

---

## 1. Propósito e Motivação

O wizard substitui o fluxo monolítico do `CreateProjectDialog` para:
- Reduzir esforço manual (aproveitar estrutura de pastas, nomes de arquivos e parquets existentes).
- Permitir importação seletiva (arena, ROIs, trajetória).
- Evitar reprocessamento desnecessário.
- Fornecer transparência (confiança das detecções e explicabilidade).
- Escalar para projetos grandes (centenas de vídeos).
- Base sólida para incrementalidade (futuras adições de novos lotes).

---

## 2. Principais Melhorias vs. Versão Original

| Categoria | Original | Versão 2 |
|-----------|----------|----------|
| Consistência de Ações | Nomes mistos (“Import”, “Import Zones”) | Enum unificado `ImportAction` |
| Confiança | Valor isolado | Fórmula explícita + componentes (folder, filename, merge) |
| ROI Merge | Apenas descrição superficial | Estratégia formal (Replace, Merge, Manual) + regras de renome |
| JSON Final | Exemplo parcial | Esquema completo, versionado |
| Edge Cases | Pouco detalhados | Tabela de casos e tratamento |
| Acessibilidade | Não abordada | Requisitos de foco, atalhos, avisos |
| i18n | Mistura EN/PT | Padronização PT-BR + suporte futuro |
| Testes | Cenários listados | Matriz detalhada de níveis + métricas |
| Performance | Não tratado | Caching, paralelismo, lazy, debouncing |
| Logging & Telemetria | Ausente | Formato estruturado + KPIs |
| Estimativa de Tempo | Texto ilustrativo | Fórmula baseada em metadados e ações |

---

## 3. Glossário e Convenções

- “Video Info”: Estrutura com metadados e flags de parquet (arena, rois, trajectory).  
- “Design”: (groups, days, subjects_per_group) derivado de estrutura/nome.  
- “Outlier”: Vídeo que não se encaixa no padrão detectado.  
- “Confidence”: Métrica de 0.0–1.0 para quão sólida é a inferência de design.  
- “ImportAction”: Estratégia aplicada a cada vídeo durante a criação.  
- “ZoneData”: Estrutura interna (arena + lista de ROIs).  

---

## 4. Enumerações Formais (Canonical Enums)

```python
from enum import Enum

class ProjectType(Enum):
    EXPERIMENTAL = "experimental"
    EXPLORATORY = "exploratory"

class ImportAction(Enum):
    SKIP = "skip"                # Tudo existente (arena+ROIs+trajetória) → não processa
    IMPORT_ZONES = "import_zones" # Arena+ROIs reutilizados; gerar trajetória
    PARTIAL = "partial"          # Apenas arena reutilizada; definir ROIs + trajetória
    FULL = "full"                # Nada reutilizado; definir tudo + trajetória

class ROIMergeStrategy(Enum):
    REPLACE = "replace"
    MERGE = "merge"
    MANUAL = "manual"

class WizardStepID(Enum):
    DISCOVERY = 1
    FILE_SELECTION = 2
    DETECTION_VALIDATION = 3
    IMPORT_CONFIG = 4
    CONFIRMATION = 5
```

Mapeamento de checkboxes (arena/rois/trajectory) → ImportAction (derivação canônica):

| arena | rois | trajectory | Action        |
|-------|------|------------|---------------|
| T     | T    | T          | skip          |
| T     | T    | F          | import_zones  |
| T     | F    | F          | partial       |
| F     | F    | F          | full          |
| Outros (ex: rois=True sem arena) | - | - | Normalizar ou forçar revisão (inconsistente) |

---

## 5. Fórmula de Confiança (Design Detection Confidence)

A confiança final (merged_confidence) resulta da fusão de duas análises (pasta e filename) e penalização por outliers.

Componentes:
- `pattern_consistency`: Proporção de vídeos que seguem o padrão dominante.
- `coverage_ratio`: (grupos_detectados * dias_detectados * subjects_per_group) / vídeos_esperados (se aplicável).
- `naming_uniformity`: Similaridade média de prefixos (“Grupo”, “Dia”, “Sujeito”, “G”, “D”).  
- `outliers_ratio`: outliers / total_videos.

Fórmulas:

```
folder_confidence = 0.45*pattern_consistency + 0.35*coverage_ratio + 0.20*(1 - outliers_ratio)
filename_confidence = 0.55*pattern_consistency_filename + 0.25*naming_uniformity + 0.20*(1 - outliers_ratio_filename)

merged_confidence = 
  if max(folder_confidence, filename_confidence) >= 0.80:
      0.6*max + 0.4*min
  else:
      0.5*folder_confidence + 0.5*filename_confidence

final_confidence = merged_confidence * (1 - 0.5*outliers_ratio_global)
```

Faixas:
- ≥ 0.90: Alta — aplica-se por padrão, permitir edição.
- 0.75–0.89: Média — recomenda-se revisão visual.
- 0.50–0.74: Baixa — exige confirmação ativa do usuário (checkbox “Aceito usar este design”).
- < 0.50: Falha — força modo de configuração manual antes de prosseguir.

---

## 6. Arquitetura Geral do Wizard

Diretório: `src/zebtrack/ui/wizard/`

Estrutura:
```
wizard_dialog.py
base.py
step_discovery.py
step_file_selection.py
step_detection_validation.py
step_import_config.py
step_confirmation.py
```

Serviços de análise:
```
src/zebtrack/analysis/design_detector.py
src/zebtrack/analysis/parquet_analyzer.py
src/zebtrack/analysis/time_estimator.py
```

Caching:
- Cache em memória de: 
  * `scan_results_by_path: dict[path -> VideoParquetInfo]`
  * `design_detection_cache: hash(video_paths_set) -> DetectionResult`
- Invalidação: ao remover/adicionar vídeo, hash muda.

---

## 7. Fluxo Completo por Etapa

### Step 1: Discovery (DISCOVERY)
Objetivo: Capturar contexto mínimo antes de escanear profundamente.

Campos:
- Tipo de Projeto: Experimental / Exploratory
- Organização de Pastas (se Experimental):
  - “Pastas representam estrutura experimental”
  - “Pastas apenas organizacionais”
  - “Tudo em um único diretório”
- Parquets existentes:
  - “Quero importar zonas (arena/ROIs)”
  - “Quero importar tudo (zonas + trajetória)”
  - “Não tenho parquets”
Saída:
```json
{
  "project_type": "experimental",
  "folder_structure_declared": "experimental", 
  "parquet_import_scope": "zones"  // "zones" | "all" | "none"
}
```
Validações:
- Obrigatório escolher cada grupo de radios.
Eventos:
- Ao avançar → inicializa contexto de detecção futura.

### Step 2: File Selection (FILE_SELECTION)
Função: Selecionar arquivos de vídeo e/ou pastas.

UI:
- Botões: [Adicionar Pasta], [Adicionar Vídeos], [Remover Selecionados], [Limpar]
- Lista hierárquica (opcional) ou lista plana.
- Resumo: total de arquivos, extensões suportadas (.mp4 inicialmente), avisos (pastas vazias).

Validações:
- Pelo menos 1 vídeo válido.
- Remover duplicatas (mesmo path).
- Aviso se > N (limite soft configurável, ex: 500) → alerta de performance.

Saída parcial:
```json
{
  "selected_paths": ["C:/Videos/GrupoA", "C:/Videos/extra1.mp4"],
  "discovered_videos": ["C:/Videos/GrupoA/Dia1/S1.mp4", "..."]
}
```

### Step 3: Detection & Validation (DETECTION_VALIDATION)
Ações:
1. Rodar `DesignDetector` (folders + filenames).
2. Rodar `ParquetAnalyzer` nos vídeos detectados.
3. Calcular confiança.
4. Exibir:
   - Design proposto (pattern, groups, days, subjects_per_group).
   - Estatísticas de parquets (arena, rois, trajectory, completos).
   - Outliers (lista com checkbox “Excluir do projeto?”).
   - Warnings.

Interações:
- Botão “Editar Design Manualmente...”
- Ao editar manualmente: abrir diálogo com spinboxes e tabela mapping (video → group/day/subject).
- Checkbox “Usar este design” (apenas se confiança < 0.75).
- Ação “Reprocessar Detecção” (se vídeos alterados no Step 2 via Back).

Saída:
```json
{
  "design": {
    "pattern": "{Group}/{Day}/{Subject}",
    "groups": ["GrupoControle", "GrupoTratamento"],
    "days": ["Dia1","Dia2","Dia3"],
    "subjects_per_group": 8
  },
  "design_detection_meta": {
    "folder_confidence": 0.82,
    "filename_confidence": 0.91,
    "merged_confidence": 0.88,
    "final_confidence": 0.86,
    "outliers": ["extra_video.mp4"],
    "confidence_formula": "ver seção 5"
  },
  "parquet_analysis": {
    "videos_with_arena": 10,
    "videos_with_rois": 9,
    "videos_with_trajectory": 4,
    "complete_videos": 4,
    "roi_names": ["Top","Bottom"],
    "roi_consistency": {
       "is_consistent": true,
       "common_roi_names": ["Top","Bottom"],
       "conflicts": []
    },
    "video_details": [
       {
         "video": "GC_D1_S1.mp4",
         "has_arena": true,
         "has_rois": true,
         "has_trajectory": false,
         "parquet_paths": {
            "arena": ".../arena.parquet",
            "rois": ".../rois.parquet",
            "trajectory": null
         }
       }
    ]
  },
  "excluded_videos": ["test_recording.mp4"]  // Se usuário optou excluir
}
```

### Step 4: Import Configuration (IMPORT_CONFIG)
Exibe tabela por vídeo:

| Vídeo | Arena | ROIs | Trajectory | Ação (derivada) | Grupo/Dia/Subj | Fonte |

Fonte:
- “Parquet (arena+rois)” / “Parquet (completo)” / “Novo (Full)”.

Bulk actions:
- [Marcar Todos Arena] [Marcar Arena+ROIs onde existam] [Marcar Skip para completos] [Resetar Todos]
- Filtro (dropdown): Todos / Skip / Import Zones / Partial / Full / Outliers

ROI Merge Strategy (radio):
- Replace: Substitui completamente.
- Merge: Mantém existentes; renomeia conflitos (padrão: `Nome → Nome_imported`).
- Manual: Abre diálogo para cada conflito.

Validação:
- Pelo menos 1 vídeo com ação != skip OU todos skip com confirmação (“Todos os vídeos serão apenas carregados sem processamento — confirmar?”).
- Inconsistências de checkboxes normalizadas.
- Exibir sumário dinâmico (contagens por ação).
- Recalcular estimativa de tempo a cada mudança.

Saída:
```json
{
  "import_config": [
    {
      "video": "GC_D1_S1.mp4",
      "import_arena": true,
      "import_rois": true,
      "import_trajectory": false,
      "action": "import_zones"
    },
    ...
  ],
  "roi_merge_strategy": "replace"
}
```

### Step 5: Confirmation (CONFIRMATION)
Componentes:
- Nome do Projeto (editável) + validação regex (`^[A-Za-z0-9_\\- ]+$`)
- Local do Projeto (browse)
- Resumo do Design
- Resumo do Plano de Processamento
- Configurações de Análise (intervalos, modelo)
- Estimativa de tempo (detalhes)
- Warnings finais (outliers, ROI inconsistente, pasta já existe)
- Botão “Exportar Config JSON” (opcional)
- Botões: [< Voltar] [Criar Projeto]

Validação:
- Pasta gravável.
- Pasta existente → pergunta se deseja usar (se não vazia, abortar ou criar subpasta).
- Nome não vazio e único (dentro do diretório pai).
- Se final_confidence < 0.50 → impedir se usuário não revisou manualmente.

---

## 8. Estados, Validações e Eventos

| Etapa | Evento | Ação |
|-------|--------|------|
| 1 → 2 | Next | Armazena discovery_data |
| 2 → 3 | Next | Escaneia vídeos (se cache inválido) |
| 3 | Edit Manual | Abre diálogo; substitui design e recalcula consistência |
| 3 → 4 | Next | Gera config inicial com smart defaults |
| 4 | Altera checkbox | Recalcula ação derivada e estimativa de tempo |
| 4 → 5 | Next | Valida coerência; agrega contagem ações |
| 5 | Create | Serializa JSON config → `project_config.json` |

---

## 9. Modelo de Dados Unificado (Wizard Data Contract)

```json
{
  "wizard_schema_version": 1,
  "project_type": "experimental",
  "discovery": {
    "folder_structure_declared": "experimental",
    "parquet_import_scope": "zones"
  },
  "selected_paths": [...],
  "videos": [
    {
      "path": "C:/Videos/GrupoControle/Dia1/S1.mp4",
      "design_mapping": {
        "group": "GrupoControle",
        "day": "Dia1",
        "subject": "S1"
      }
    }
  ],
  "excluded_videos": [],
  "design": {
    "pattern": "{Group}/{Day}/{Subject}",
    "groups": ["GrupoControle","GrupoTratamento"],
    "days": ["Dia1","Dia2","Dia3"],
    "subjects_per_group": 8
  },
  "design_detection_meta": {
    "folder_confidence": 0.82,
    "filename_confidence": 0.91,
    "merged_confidence": 0.88,
    "final_confidence": 0.86,
    "confidence_formula": "ver seção 5",
    "outliers": ["extra_video.mp4"]
  },
  "parquet_analysis": {
    "videos_with_arena": 10,
    "videos_with_rois": 9,
    "videos_with_trajectory": 4,
    "complete_videos": 4,
    "roi_names": ["Top","Bottom"],
    "roi_consistency": {
      "is_consistent": true,
      "common_roi_names": ["Top","Bottom"],
      "conflicts": []
    },
    "video_details": [
      {
        "video": "GC_D1_S1.mp4",
        "has_arena": true,
        "has_rois": true,
        "has_trajectory": false,
        "parquet_paths": {
          "arena": "…/arena.parquet",
          "rois": "…/rois.parquet",
          "trajectory": null
        }
      }
    ]
  },
  "import_config": [
    {
      "video": "GC_D1_S1.mp4",
      "import_arena": true,
      "import_rois": true,
      "import_trajectory": false,
      "action": "import_zones"
    }
  ],
  "roi_merge_strategy": "replace",
  "processing_parameters": {
    "model": "yolov8n",
    "analysis_interval_frames": 10,
    "display_interval_frames": 10,
    "animals_per_aquarium": 1
  },
  "project_output": {
    "project_name": "Experimento_Zebrafish_01",
    "project_path": "C:/Projects/Experimento_Zebrafish_01"
  },
  "time_estimate": {
    "total_minutes": 42,
    "per_action_breakdown": {
      "import_zones": 3.2,
      "partial": 5.5,
      "full": 30.1
    },
    "videos_to_process": 8
  }
}
```

---

## 10. Estratégia de Importação (Import Config + ROI Merge)

Regras de derivação (Smart Defaults):
- Se `parquet_import_scope == "all"` e vídeo completo (arena+rois+trajectory) → `action=skip`.
- Se `parquet_import_scope == "zones"` e vídeo tem arena+rois → `action=import_zones`.
- Se tem apenas arena → `action=partial`.
- Senão → `action=full`.

ROI Merge Strategy:
- replace: Apaga ROIs existentes (se houver) e substitui.
- merge: Adiciona ROIs importadas; em conflitos: `Nome → Nome_imported`. Se já existir, incrementa sufixo `_imported2`.
- manual: Para cada vídeo com conflito abre diálogo:
  - Lista: [Conflito: Top] → Opções: [Manter existente / Manter importada / Renomear (input)].

---

## 11. Algoritmos de Detecção

### 11.1 FolderStructureDetector
1. Construir árvore de profundidade relativa.
2. Detectar possíveis níveis (group/day/subject) por:
   - Frequência distinta de nomes.
   - Padrões de prefixo (Grupo, G, Dia, D, Sujeito, S).
   - Cardinalidades semelhantes entre grupos (ex: cada grupo tem mesmo número de days).
3. Avaliar consistência por contagem de combinações.

### 11.2 FilenamePatternDetector
Regex templates (exemplos):
- `^(?P<group>G[A-Za-z]+)_?(?P<day>D(?:ia)?\d+)_?(?P<subject>S\d+)$`
- Capturas flexíveis substituíveis via lista configurável.

### 11.3 ParquetAnalyzer
Para cada vídeo:
- Procurar arquivos `.parquet` com mesmo basename ou convenções (`basename_arena.parquet` etc.).
- Identificar colunas mínimas (ex: `x`, `y` para trajetória).
- ROI consistency:
  - Agregar conjunto de nomes por vídeo.
  - `is_consistent = (interseção tamanho >= 70% do conjunto médio)`.

---

## 12. Estimativa de Tempo de Processamento

Modelo inicial simples (ajustável via feedback):

```
t_full = base_track_time_per_minute_video * video_duration_minutes
t_partial = t_full * 0.75
t_import_zones = t_full * 0.40
t_skip = 0
```

Se duração desconhecida, estimar pelo tamanho do arquivo:
```
duration_est = file_size_mb / avg_mb_per_minute (heurística)
```

Exibir:
- “Estimativa total ~42 min (8 vídeos a processar: 2 full, 3 partial, 3 import_zones)”.

---

## 13. Logging, Auditoria e Telemetria

Formato (JSON line oriented):
```
{
  "event": "wizard_step_completed",
  "step": 3,
  "timestamp": "...",
  "videos_total": 48,
  "confidence_final": 0.86,
  "outliers": 2
}
```
Eventos:
- wizard_opened
- step_entered / step_validated
- detection_run (com tempos)
- import_config_changed
- project_created (com breakdown de ações)
- error_occurred (com stack simplificada)

KPIs:
- % vídeos reaproveitados (skip + import_zones + partial)
- Média de confiança
- Tempo médio detecção
- Erros por execução

---

## 14. Estratégia de Acessibilidade

Requisitos:
- Navegação via Tab e Shift+Tab em ordem lógica.
- Foco inicial sempre no primeiro campo significativo.
- Indicadores de estado (ex: erros) com ícone + texto.
- Mensagens de alerta acessíveis (ex: usar `aria-role` se futuramente migrar de Tkinter).
- Atalhos:
  - Alt+N → Próximo
  - Alt+B → Voltar
  - Alt+F → Criar Projeto

---

## 15. Internacionalização (i18n)

Plano:
- Extrair todas as strings fixas para `resources/strings_pt_BR.json`.
- Chaves:
  - `wizard.step1.title`, `wizard.action.next`, `wizard.label.confidence`.
- Preparar base para `en_US.json` (futuro).
- Função utilitária: `tr(key: str) -> str`.

---

## 16. Desempenho e Escalabilidade

Medidas:
- Scan paralelo (ThreadPool) limitado (ex: 4 threads) para parsing de metadados.
- Cache persistente na sessão enquanto wizard aberto.
- Debounce de 300ms em eventos de alteração de seleção antes de reprocessar.
- Adiar cálculo de estimativa de tempo até Step 4 (não fazer antes).

---

## 17. Tratamento de Erros e Edge Cases

| Caso | Tratamento |
|------|------------|
| Nenhum vídeo | Bloquear avanço Step 2 |
| Parquet corrompido | Log warning; marcar vídeo como sem dados |
| Vídeo duplicado | Remover automaticamente; notificar |
| ROI inconsistente | Mostrar warning + opção “Normalizar nomes” |
| Design falhou (<0.5) | Exigir edição manual |
| Pasta destino existe e não vazia | Prompt: Criar subpasta `nome_projeto_1` ou cancelar |
| Vídeo sem extensão suportada | Excluir do conjunto silenciosamente + aviso final |
| Conflito ROI (merge) múltiplas vezes | Incrementar sufixo `_importedN` |
| Interrupção do wizard | Confirmar se descartar rascunho |
| JSON final falha ao salvar | Prompt re-tentar / escolher outro diretório |

---

## 18. Testes

### 18.1 Unit
- `DesignDetector`: múltiplos padrões (Group/Day/Subject, inversos).
- `FilenamePatternDetector`: regex variantes.
- `ParquetAnalyzer`: cenários com/sem arena/ROIs/trajectory.
- ROI merge renomeando conflitos.

### 18.2 Integração
- Fluxo Step 1 → Step 5 com dados sintéticos.
- Alterar seleção no Step 2 e revalidar Step 3.

### 18.3 E2E
- Projeto pequeno (3 vídeos).
- Projeto médio (60 vídeos).
- Projeto com outliers e manual edit.

### 18.4 Stress
- 1000 vídeos simulados em árvore profunda.
- Paralelismo controlado (tempo < limiar definido).

### 18.5 Regressão
- Assegurar compatibilidade com `ProjectManager.create_new_project()` (interval frames, etc.).

Métricas de Teste:
- Cobertura lógica ≥ 85% nos módulos de detecção.
- Tempo de detecção para 200 vídeos ≤ X segundos (parametrizável).

---

## 19. Roadmap de Implementação por Fases

| Fase | Conteúdo | Duração Estimada |
|------|----------|------------------|
| 1 | Infra Wizard (steps skeleton + navegação + base enums) | 3 dias |
| 2 | File selection + caching + scan básico | 2 dias |
| 3 | Design & parquet detection + fórmula confiança | 4 dias |
| 4 | Import config (tabela + bulk + derivação ações) | 3 dias |
| 5 | Confirmation + persistência JSON + project create | 2 dias |
| 6 | ROI merge strategies + estimador tempo | 2 dias |
| 7 | Testes (unit+integração+E2E) + otimizações | 4 dias |
| 8 | i18n scaffolding + logging + refino final | 2 dias |
| Total | ~22 dias úteis (buffer incluído) | ~4-5 semanas corridas |

---

## 20. Checklist Final Antes de Criar o Projeto

- [ ] Nome do projeto válido (regex)  
- [ ] Diretório de saída definido e gravável  
- [ ] Design aprovado (ou manual)  
- [ ] Confiança ≥ 0.50 ou revisão manual confirmada  
- [ ] Nenhum vídeo sem ação definida  
- [ ] Ações derivadas coerentes (sem combinações inválidas)  
- [ ] Vídeos excluídos revisados  
- [ ] Nenhum conflito de ROI pendente (merge/manual resolvido)  
- [ ] Estimativa de tempo exibida ao usuário  
- [ ] JSON de configuração pronto (memória)  
- [ ] Usuário confirmou warnings críticos (outliers, inconsistência ROI)  

---

## 21. Exemplo de JSON Final Persistido

(Arquivo salvo como `project_config.json` dentro da pasta do projeto)

```json
{
  "wizard_schema_version": 1,
  "project_name": "Experimento_Canabidiol_2025",
  "created_at": "2025-10-04T12:33:21Z",
  "project_type": "experimental",
  "design": {
    "pattern": "{Group}/{Day}/{Subject}",
    "groups": ["GrupoControle","GrupoTratamento"],
    "days": ["Dia1","Dia2","Dia3"],
    "subjects_per_group": 8
  },
  "design_detection_meta": {
    "folder_confidence": 0.83,
    "filename_confidence": 0.92,
    "merged_confidence": 0.89,
    "final_confidence": 0.87,
    "outliers": ["extra_video.mp4"],
    "confidence_formula": "0.45*pattern_consistency + ..."
  },
  "videos": [
    {
      "path": "C:/Videos/GrupoControle/Dia1/Sujeito1.mp4",
      "import_action": "import_zones",
      "parquet_flags": {
        "has_arena": true,
        "has_rois": true,
        "has_trajectory": false
      }
    }
  ],
  "import_summary": {
    "skip": 4,
    "import_zones": 6,
    "partial": 1,
    "full": 1
  },
  "roi_merge_strategy": "replace",
  "processing_parameters": {
    "model": "yolov8n",
    "analysis_interval_frames": 10,
    "display_interval_frames": 10,
    "animals_per_aquarium": 1
  },
  "time_estimate": {
    "total_minutes": 45,
    "videos_to_process": 8
  },
  "audit": {
    "wizard_version": "1.0.0",
    "user_confirmed_warnings": true
  }
}
```

---

## 22. Plano de Migração / Legado

- Manter `CreateProjectDialog` como `CreateProjectDialogLegacy`.
- Flag de feature (ex: constante `ENABLE_NEW_WIZARD = True`).
- Menu: “Novo Projeto (Wizard)” / “Novo Projeto (Legado)” durante fase beta.
- Após estabilização: descontinuar legado (etapa futura).
- Compatibilidade: `ProjectManager.create_new_project()` aceita novos campos (`import_config`, `roi_merge_strategy`).

---

## 23. Riscos e Mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Complexidade inicial alta | Atrasos | Implementação faseada |
| Detecção lenta em grandes árvores | UX ruim | Caching + threads |
| Usuário confiar em design errado | Dados distorcidos | Mostrar outliers + confiança + explicação |
| Conflitos de ROI em massa | Demora | Limitar manual a quando >0 e < N conflitos |
| Memória elevada (muitos vídeos) | Falha | Processar metadados lazy |
| Divergência de enums | Bugs | Centralizar enums em módulo único |

---

## 24. Apêndices

### 24.1 Tabela de Derivação de Ações (Detalhada)
| has_arena | has_rois | has_trajectory | Escopo User (zones/all/none) | Ação Default |
|-----------|----------|----------------|------------------------------|--------------|
| T | T | T | all | skip |
| T | T | F | zones | import_zones |
| T | T | F | all | import_zones |
| T | F | F | zones | partial (arena apenas) |
| T | F | F | none | full (força redefinição) |
| F | F | F | any | full |
| T | T | T | none | skip (mas confirmar: usuário disse “none”) |

### 24.2 Exemplo de Log Estruturado
```json
{
  "ts": "2025-10-04T12:32:00Z",
  "event": "detection_run",
  "videos": 48,
  "folder_confidence": 0.83,
  "filename_confidence": 0.92,
  "merged_confidence": 0.89,
  "outliers": 2,
  "duration_ms": 734
}
```

### 24.3 Regex Exemplos (Filtragem)
- Day tokens: `(?:Dia|D)(\d+)`
- Subject tokens: `Sujeito(\d+)|S(\d+)`
- Group tokens: `(Grupo(?:Controle|Tratamento)|G[A-Za-z0-9]+)`

---

## Conclusão

Esta Versão 2 fornece uma especificação sólida, detalhada e implementável, cobrindo:
- Estrutura modular clara
- Modelo de dados versionado
- Transparência de detecção e confiança
- Fluxo UX orientado a contexto
- Estratégias robustas de importação e merge
- Base para escalabilidade e manutenção futura

Próximo passo: Implementar Fase 1 (estrutura do wizard e base de dados) antes de avançar para detecção.

---
(Fim do documento - Versão 2)
```
