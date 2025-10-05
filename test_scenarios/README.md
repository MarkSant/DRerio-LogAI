# Cenarios de Teste do Wizard v1.5

## Estrutura

### Cenario 1: Experimental (Design Detectavel)
**Caminho**: `scenario_1_experimental/`
**Estrutura**:
```
Control/Day01/S01.mp4, S02.mp4, S03.mp4
Control/Day02/S01.mp4, S02.mp4, S03.mp4
Treatment/Day01/S01.mp4, S02.mp4, S03.mp4
Treatment/Day02/S01.mp4, S02.mp4, S03.mp4
```

**Como testar**:
1. No wizard, selecione "Experimental"
2. Clique "Add Folder" e escolha `scenario_1_experimental/`
3. Na etapa Detection, verifique:
   - Pattern: "groups_as_folders"
   - Groups: ["Control", "Treatment"]
   - Days: ["Day01", "Day02"]
   - Subjects: 3 por grupo
   - Confidence: > 80%

---

### Cenario 2: Com Parquets Existentes
**Caminho**: `scenario_2_with_parquets/`
**Parquets**:
- video1: arena + rois + trajectory (completo)
- video2: arena + rois
- video3: nenhum parquet

**Como testar**:
1. Selecione "Experimental" ou "Exploratory"
2. Clique "Add Files" e escolha os 3 videos
3. Na etapa Detection, verifique:
   - "Found 2 arena parquets"
   - "Found 2 rois parquets"
   - "Found 1 trajectory parquets"
4. Na etapa Import Configuration:
   - video1: Opcoes SKIP / IMPORT_ZONES / FULL
   - video2: Opcoes IMPORT_ZONES / FULL
   - video3: Apenas FULL

---

### Cenario 3: Exploratorio
**Caminho**: `scenario_3_exploratory/Videos/`
**Videos**: 3 arquivos com datas nos nomes

**Como testar**:
1. Selecione "Exploratory"
2. Clique "Add Folder" e escolha `scenario_3_exploratory/Videos/`
3. Na etapa Detection:
   - Nenhum design detectado (ou confidence baixa)

---

## Ativacao do Wizard

Certifique-se que `config.local.yaml` existe na raiz do projeto com:

```yaml
ui_features:
  use_wizard_for_project_creation: true
```

## Executar ZebTrack

```powershell
poetry run zebtrack
```

Clique em "New Project" e veja o wizard de 5 etapas!

---

**Gerado por**: create_wizard_test_scenarios.py
**Versao**: Wizard v1.5
