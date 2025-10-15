# Fase 2.1: Auditoria do MainViewModel - Relatório de Análise

**Data**: 14 de Outubro de 2025  
**Objetivo**: Identificar lógica de negócio no MainViewModel que deve ser movida para serviços

---

## Metodologia de Auditoria

### Critérios para Identificação de Lógica de Negócio

❌ **DEVE SER MOVIDO** (Lógica de Negócio):
- Manipulação direta de arquivos (open, write, read, mkdir, copy)
- Processamento pesado de dados (loops complexos, transformações)
- Lógica de análise e cálculos
- Conversão de formatos de dados
- Validação de dados complexa
- Gerenciamento de recursos externos (arquivos, diretórios)

✅ **PODE PERMANECER** (Lógica de Apresentação):
- Propriedades que a UI lê diretamente
- Delegação simples para serviços
- Coordenação entre serviços
- Event handlers que delegam
- Estado UI temporário
- Callbacks de UI

---

## Métodos Identificados para Auditoria

### 1. Categoria: Gerenciamento de Projeto (ProjectService)

| Método | Linha | Lógica de Negócio? | Ação Recomendada |
|--------|-------|-------------------|------------------|
| `create_project_workflow` | 718 | 🔴 Sim | Mover para ProjectService |
| `save_current_calibration_to_project` | 2046 | 🔴 Sim | Mover para ProjectService |
| `save_project_model_overrides` | 2159 | 🔴 Sim | Mover para ProjectService |
| `save_manual_arena` | 2337 | 🔴 Sim | Mover para ProjectService |

### 2. Categoria: Processamento de IA/Modelos (ModelService - novo)

| Método | Linha | Lógica de Negócio? | Ação Recomendada |
|--------|-------|-------------------|------------------|
| `convert_active_weight_to_openvino` | 1542 | 🔴 Sim | Mover para ModelService (novo) |
| `setup_detector` | ? | 🔴 Sim | Mover para ModelService |
| `update_detector_parameters` | ? | 🔴 Sim | Mover para ModelService |

### 3. Categoria: Análise e Processamento (AnalysisService)

| Método | Linha | Lógica de Negócio? | Ação Recomendada |
|--------|-------|-------------------|------------------|
| `process_pending_project_videos` | 3251 | 🔴 Sim | Mover para AnalysisService |
| `analyze_parquet` | ? | 🔴 Sim | Já em AnalysisService? Verificar |
| `generate_reports` | ? | 🔴 Sim | Já em AnalysisService? Verificar |

---

## Próximos Passos

### Fase 1: Auditoria Detalhada (Em Progresso)
- [x] Identificar métodos candidatos
- [ ] Examinar cada método em detalhe
- [ ] Categorizar por serviço destino
- [ ] Identificar dependências entre métodos

### Fase 2: Criação de Serviços
- [ ] Criar ModelService para lógica de IA
- [ ] Expandir ProjectService com métodos de I/O
- [ ] Expandir AnalysisService com processamento

### Fase 3: Refatoração
- [ ] Mover métodos para serviços apropriados
- [ ] Atualizar MainViewModel para delegar
- [ ] Atualizar testes
- [ ] Validar integração

---

## Status

**Fase Atual**: Auditoria Inicial
**Próxima Ação**: Examinar métodos identificados em detalhes
