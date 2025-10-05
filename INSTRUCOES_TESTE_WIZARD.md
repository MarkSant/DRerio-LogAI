# Instruções Completas de Teste do Wizard v1.5

## 📋 Sumário

1. [Ativação do Wizard](#1-ativação-do-wizard)
2. [Cenários de Teste Gerados](#2-cenários-de-teste-gerados)
3. [Guia de Teste Passo a Passo](#3-guia-de-teste-passo-a-passo)
4. [O que Verificar em Cada Etapa](#4-o-que-verificar-em-cada-etapa)
5. [Troubleshooting](#5-troubleshooting)

---

## 1. Ativação do Wizard

### ✅ Verificar Ativação

Certifique-se que o arquivo `config.local.yaml` existe na raiz do projeto com:

```yaml
ui_features:
  use_wizard_for_project_creation: true
```

**Status**: ✅ Já criado automaticamente!

### Executar ZebTrack

```powershell
poetry run zebtrack
```

### Como Saber se o Wizard está Ativo?

1. Abra o ZebTrack
2. Clique em **"New Project"**
3. **SE WIZARD ATIVO**: Verá janela com título "Project Creation Wizard - Step 1/5"
4. **SE DESATIVADO**: Verá dialog tradicional com todos os campos de uma vez

---

## 2. Cenários de Teste Gerados

Os cenários estão em: `test_scenarios/`

### Cenário 1: Experimental (Design Detectável)
**Localização**: `test_scenarios/scenario_1_experimental/`

**Estrutura de Pastas**:
```
Control/
  Day01/ → S01.mp4, S02.mp4, S03.mp4
  Day02/ → S01.mp4, S02.mp4, S03.mp4
Treatment/
  Day01/ → S01.mp4, S02.mp4, S03.mp4
  Day02/ → S01.mp4, S02.mp4, S03.mp4
```

**Total**: 12 vídeos

**Design Esperado**:
- Pattern: "groups_as_folders"
- Grupos: ["Control", "Treatment"]
- Dias: ["Day01", "Day02"]
- Sujeitos por grupo: 3
- Confiança: > 80%

---

### Cenário 2: Com Parquets Existentes
**Localização**: `test_scenarios/scenario_2_with_parquets/`

**Vídeos e Parquets**:
1. **video1.mp4** + `video1_results/`
   - ✅ video1_arena.parquet
   - ✅ video1_rois.parquet
   - ✅ 3_CoordMovimento_video1.parquet

2. **video2.mp4** + `video2_results/`
   - ✅ video2_arena.parquet
   - ✅ video2_rois.parquet

3. **video3.mp4** (sem parquets)

**Total**: 3 vídeos

**Detecção Esperada**:
- "Found 2 arena parquets"
- "Found 2 rois parquets"
- "Found 1 trajectory parquet"

---

### Cenário 3: Exploratório
**Localização**: `test_scenarios/scenario_3_exploratory/Videos/`

**Vídeos**:
- experiment_2025_01_15.mp4
- experiment_2025_01_16.mp4
- experiment_2025_01_17.mp4

**Total**: 3 vídeos

**Design Esperado**: Nenhum (ou confidence < 50%)

---

## 3. Guia de Teste Passo a Passo

### 🧪 TESTE 1: Cenário Experimental

#### Passo 1: Executar ZebTrack
```powershell
poetry run zebtrack
```

#### Passo 2: Iniciar Wizard
1. Clique em **"New Project"**
2. Deve aparecer: "Project Creation Wizard - Step 1/5"

#### Passo 3: Discovery (Etapa 1)
1. Selecione **"Experimental"**
2. Clique **"Next"**

#### Passo 4: File Selection (Etapa 2)
1. Clique **"Add Folder"**
2. Navegue até: `test_scenarios/scenario_1_experimental/`
3. Selecione a pasta `scenario_1_experimental`
4. Aguarde o scan (deve encontrar 12 vídeos)
5. Verifique a lista:
   - ✅ Control/Day01/S01.mp4
   - ✅ Control/Day01/S02.mp4
   - ✅ ... (todos os 12 vídeos)
6. Clique **"Next"**

#### Passo 5: Detection (Etapa 3)
1. Aguarde a detecção (progress bar)
2. **Verificar Design Detectado**:
   - Pattern: `groups_as_folders`
   - Groups: `Control, Treatment`
   - Days: `Day01, Day02`
   - Subjects per group: `3`
   - Confidence: **> 80%** (esperado: ~85%)
3. **Verificar Parquet Summary**:
   - Total arena: 0
   - Total rois: 0
   - Total trajectory: 0
   - (Nenhum parquet neste cenário)
4. Clique **"Next"**

#### Passo 6: Import Configuration (Etapa 4)
1. **NÃO deve aparecer** esta etapa (sem parquets)
2. Deve pular direto para Etapa 5 (Confirmation)

#### Passo 7: Confirmation (Etapa 5)
1. Verificar resumo:
   - Project Type: Experimental
   - Total Videos: 12
   - Design Summary: "Detected 2 groups, 2 days, 3 subjects per group"
2. Preencher:
   - Project Name: `Teste_Wizard_Experimental`
   - Project Path: Escolha uma pasta de teste
3. Clique **"Create Project"**

#### Passo 8: Verificar Projeto Criado
1. Verifique se a pasta do projeto foi criada
2. Abra `project_config.json` e verifique:
   - `"num_groups": 2`
   - `"group_names": ["Control", "Treatment"]`
   - `"experiment_days": 2`
   - `"subjects_per_group": 3`
   - `"_wizard_metadata"` presente

---

### 🧪 TESTE 2: Cenário com Parquets

#### Passo 1-3: Igual ao Teste 1
1. Execute `poetry run zebtrack`
2. Clique "New Project"
3. Selecione "Experimental" (ou "Exploratory")
4. Clique "Next"

#### Passo 4: File Selection
1. Clique **"Add Files"** (não "Add Folder")
2. Navegue até: `test_scenarios/scenario_2_with_parquets/`
3. **Selecione os 3 vídeos**:
   - video1.mp4
   - video2.mp4
   - video3.mp4
4. Clique "Abrir"
5. Verifique lista (3 vídeos)
6. Clique "Next"

#### Passo 5: Detection
1. Aguarde detecção
2. **Verificar Parquet Summary**:
   - ✅ "Found 2 arena parquets"
   - ✅ "Found 2 rois parquets"
   - ✅ "Found 1 trajectory parquet"
3. **Verificar Tabela de Vídeos**:
   - video1: Arena ✅ | ROIs ✅ | Trajectory ✅
   - video2: Arena ✅ | ROIs ✅ | Trajectory ❌
   - video3: Arena ❌ | ROIs ❌ | Trajectory ❌
4. Clique "Next"

#### Passo 6: Import Configuration (NOVA ETAPA!)
1. **Deve aparecer** a etapa de configuração de importação
2. **Verificar Tabela Interativa**:

   | Video  | Arena | ROIs | Trajectory | Action |
   |--------|-------|------|------------|--------|
   | video1 | ✅    | ✅   | ✅         | SKIP (sugerido) |
   | video2 | ✅    | ✅   | ❌         | IMPORT_ZONES |
   | video3 | ❌    | ❌   | ❌         | FULL |

3. **Testar Interatividade**:
   - Duplo-clique na célula "Arena" de video1 (deve alternar ✅ ⟷ ❌)
   - Observe a coluna "Action" atualizar automaticamente
   - Duplo-clique novamente (deve voltar)

4. **Verificar ROI Merge Strategy**:
   - Combobox: "Replace" (padrão) ou "Merge"
   - Tooltip explica a diferença

5. **Verificar Resumo no Rodapé**:
   - "Actions: 1 SKIP, 1 IMPORT_ZONES, 1 FULL"

6. Clique "Next"

#### Passo 7: Confirmation
1. Verificar resumo inclui import config
2. Preencher nome do projeto
3. Criar projeto

#### Passo 8: Verificar _wizard_metadata
1. Abra `project_config.json`
2. Verifique presença de `"_wizard_metadata"`
3. Dentro dela, verifique `"import_config"`:
   ```json
   "_wizard_metadata": {
       "import_config": [
           {
               "video": ".../video1.mp4",
               "import_arena": true,
               "import_rois": true,
               "import_trajectory": true,
               "action": "skip"
           },
           ...
       ],
       "roi_merge_strategy": "replace"
   }
   ```

---

### 🧪 TESTE 3: Cenário Exploratório

#### Passos Simplificados:
1. Execute wizard
2. Selecione **"Exploratory"**
3. Add Folder: `test_scenarios/scenario_3_exploratory/Videos/`
4. Detection: **Nenhum design detectado** (ou confidence baixa)
5. Sem etapa de Import Configuration (sem parquets)
6. Confirmation e criar projeto

---

## 4. O que Verificar em Cada Etapa

### ✅ Checklist de Funcionalidades

#### Etapa 1: Discovery
- [ ] Botões "Experimental" e "Exploratory" aparecem
- [ ] Tooltip explicativo ao passar mouse
- [ ] Botão "Next" habilitado após selecionar tipo
- [ ] Botão "Cancel" fecha o wizard

#### Etapa 2: File Selection
- [ ] "Add Files" abre file dialog
- [ ] "Add Folder" abre folder dialog e faz scan recursivo
- [ ] Lista de vídeos mostra caminhos completos
- [ ] "Remove" remove vídeo selecionado
- [ ] "Clear All" limpa a lista
- [ ] "Next" desabilitado se lista vazia
- [ ] "Next" habilitado se lista tem vídeos
- [ ] "Back" retorna à Etapa 1

#### Etapa 3: Detection
- [ ] Progress bar aparece durante detecção
- [ ] Design detectado mostra:
   - [ ] Pattern usado
   - [ ] Grupos detectados
   - [ ] Dias detectados
   - [ ] Sujeitos por grupo
   - [ ] Confidence (0-100%)
- [ ] Parquet summary mostra contagens corretas
- [ ] Tabela de vídeos lista status de parquets
- [ ] "Back" retorna à File Selection
- [ ] "Next" prossegue (pula Etapa 4 se sem parquets)

#### Etapa 4: Import Configuration (só se há parquets)
- [ ] Tabela interativa com colunas: Video, Arena, ROIs, Trajectory, Action
- [ ] Duplo-clique alterna ✅ ⟷ ❌
- [ ] Coluna "Action" atualiza automaticamente
- [ ] ROI Merge Strategy combobox presente
- [ ] Resumo de ações no rodapé
- [ ] "Back" retorna à Detection
- [ ] "Next" prossegue para Confirmation

#### Etapa 5: Confirmation
- [ ] Resumo mostra tipo de projeto
- [ ] Resumo mostra total de vídeos
- [ ] Resumo mostra design detectado (se experimental)
- [ ] Campo "Project Name" obrigatório
- [ ] Campo "Project Path" obrigatório
- [ ] Validação: nome vazio → erro
- [ ] Validação: pasta existente → erro
- [ ] "Create Project" cria projeto com sucesso
- [ ] `project_config.json` contém `_wizard_metadata`

---

## 5. Troubleshooting

### ❌ Wizard não aparece (dialog tradicional abre)

**Causa**: Feature flag desativado

**Solução**:
1. Verifique `config.local.yaml` existe na raiz
2. Conteúdo deve ter:
   ```yaml
   ui_features:
     use_wizard_for_project_creation: true
   ```
3. Reinicie o ZebTrack

---

### ❌ "Detected 0 groups" mesmo com estrutura correta

**Causa**: Padrão de pastas não reconhecido

**Solução**:
- Verifique se a estrutura é exatamente:
  - `Control/Day01/arquivo.mp4` (groups_as_folders)
  - OU `Day01/Control/arquivo.mp4` (days_as_folders)
- Nomes devem conter "Control", "Treatment", "Day01", etc.

---

### ❌ Etapa 4 não aparece mesmo com parquets

**Causa**: Parquets não foram detectados

**Verificar**:
1. Parquets devem estar em `<video>_results/`
2. Nomes devem seguir padrão:
   - `<video>_arena.parquet`
   - `<video>_rois.parquet`
   - `3_CoordMovimento_<video>.parquet`
3. Execute novamente `create_wizard_test_scenarios.py`

---

### ❌ Erro ao criar projeto

**Causa Comum**: Pasta do projeto já existe

**Solução**: Escolha novo nome ou apague a pasta existente

---

## 6. Status de Implementação

### ✅ Implementado e Funcional
- [x] Wizard de 5 etapas
- [x] Auto-detecção de design experimental
- [x] Detecção granular de parquets (arena, rois, trajectory)
- [x] Etapa de configuração de importação (UI completa)
- [x] Adapter para compatibilidade com controller
- [x] 91 testes (100% passando)
- [x] Feature flag system

### ⏳ Planejado para v1.6+
- [ ] **Execução da importação de parquets pelo controller**
  - Atualmente: Wizard coleta configuração, armazena em `_wizard_metadata`
  - Futuro: Controller lerá `_wizard_metadata.import_config` e importará automaticamente

### 🔮 Planejado para v2.0
- [ ] Etapa de calibração física (dimensões do aquário, número de animais)
- [ ] Suporte a projetos Live (gravação ao vivo)
- [ ] Edição manual de design detectado
- [ ] Templates de projeto (salvar configurações)

---

## 7. Próximos Passos

1. **Testar os 3 cenários** seguindo este guia
2. **Anotar problemas encontrados**:
   - UI confusa?
   - Bugs?
   - Sugestões de melhoria?
3. **Reportar feedback** ao time de desenvolvimento
4. **Decidir sobre rollout**:
   - Beta para usuários selecionados?
   - Ativação permanente?
   - Manter como opt-in?

---

**Gerado em**: 2025-10-04
**Versão**: Wizard v1.5
**Autor**: ZebTrack-AI Development Team
