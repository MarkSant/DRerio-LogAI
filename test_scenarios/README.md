# Test Scenarios para Wizard v1.5

Este diretrio contm cenrios de teste gerados automaticamente para o wizard.

##  Estrutura

### Cenrio 1: Experimental (Design Detectvel)
**Caminho**: `scenario_1_experimental/`
**Design**:
- 2 grupos: Control, Treatment
- 2 dias: Day01, Day02
- 3 sujeitos por grupo (S01, S02, S03)

**Como testar**:
1. No wizard, selecione "Experimental"
2. Em "File Selection", clique em "Add Folder" e escolha `scenario_1_experimental/`
3. Na etapa "Detection", verifique se detectou:
   - Pattern: "groups_as_folders"
   - Groups: ["Control", "Treatment"]
   - Days: ["Day01", "Day02"]
   - Subjects: 3
   - Confidence: ~0.85+

---

### Cenrio 2: Com Parquets Existentes
**Caminho**: `scenario_2_with_parquets/`
**Parquets**:
- `video1`: arena + rois + trajectory (completo)
- `video2`: arena + rois
- `video3`: nenhum parquet

**Arquivos gerados**:
- `video1_results/1_ProcessingArea_video1.parquet`
- `video1_results/2_AreasOfInterest_video1.parquet`
- `video1_results/3_CoordMovimento_video1.parquet`
- `video2_results/1_ProcessingArea_video2.parquet`
- `video2_results/2_AreasOfInterest_video2.parquet`

**Como testar**:
1. No wizard, selecione "Experimental" ou "Exploratory"
2. Em "File Selection", clique em "Add Files" e selecione os 3 vídeos
3. Na etapa "Detection", verifique se mostra:
   - "✅ Arena: 2"
   - "✅ ROIs: 2"
   - "✅ Trajetória: 1"
4. Na etapa "Import Configuration", veja as opções por vídeo:
   - video1: SKIP (tem tudo completo)
   - video2: IMPORT_ZONES (tem arena+rois, falta trajectory)
   - video3: FULL (processar do zero)

---

### Cenrio 3: Exploratrio
**Caminho**: `scenario_3_exploratory/Videos/`
**Vdeos**: 3 arquivos com datas nos nomes

**Como testar**:
1. No wizard, selecione "Exploratory"
2. Em "File Selection", clique em "Add Folder" e escolha `scenario_3_exploratory/Videos/`
3. Na etapa "Detection", verifique:
   - Nenhum design detectado (ou confiana baixa)
   - Opo de importar parquets no aparece (no h parquets)

---

##  Checklist de Testes Manuais

### Step 1: Discovery
- [ ] Selecionar "Experimental"  prossegue para File Selection
- [ ] Selecionar "Exploratory"  prossegue para File Selection
- [ ] Voltar (Back)  retorna ao Discovery

### Step 2: File Selection
- [ ] "Add Files"  dialog de seleo de arquivos
- [ ] "Add Folder"  dialog de seleo de pasta, scan recursivo funciona
- [ ] Remove vdeo da lista  vdeo removido
- [ ] Clear All  lista fica vazia
- [ ] Next sem vdeos  mensagem de erro
- [ ] Next com vdeos  prossegue para Detection

### Step 3: Detection
- [ ] Cenrio 1: Design experimental detectado corretamente
- [ ] Cenrio 2: Parquets detectados e contados corretamente
- [ ] Cenrio 3: Nenhum design detectado (ou baixa confiana)
- [ ] Progress bar aparece durante scan
- [ ] Cancel interrompe o scan

### Step 4: Import Configuration (s aparece se h parquets)
- [ ] Cenrio 2 video1: Opes "Skip", "Import Zones", "Partial", "Full"
- [ ] Cenrio 2 video2: Opes "Skip", "Import Zones"
- [ ] Cenrio 2 video3: Opes "Skip" (sem import)
- [ ] Alterar action de um vdeo  persiste ao navegar Back/Next
- [ ] ROI Merge Strategy: "Replace" vs "Merge"  tooltip explica

### Step 5: Confirmation
- [ ] Mostra resumo correto (nome, tipo, vdeos, design)
- [ ] "Create Project"  projeto criado com sucesso
- [ ] Validao: nome vazio  erro
- [ ] Validao: pasta existente  erro

---

##  Comandos

### Gerar cenrios
```powershell
poetry run python scripts/create_test_scenarios.py
```

### Executar ZebTrack com wizard ativado
1. Certifique-se que `config.local.yaml` tem:
   ```yaml
   ui_features:
     use_wizard_for_project_creation: true
   ```
2. Execute:
   ```powershell
   poetry run zebtrack
   ```

### Limpar cenrios
```powershell
Remove-Item -Recurse -Force test_scenarios
```

---

##  Arquivos Gerados

Cada vdeo mock tem:
- **Durao**: 3-5 segundos
- **Resoluo**: 640x480
- **FPS**: 30
- **Contedo**: Gradiente de cor + texto + "fish" simulado (crculo branco se movendo)

Cada parquet mock tem:
- **Arena** (`1_ProcessingArea_{video}.parquet`):
  - Schema: `x, y` (pontos do polígono)
  - Conteúdo: Polígono retangular 640x480 (4 pontos)
- **ROIs** (`2_AreasOfInterest_{video}.parquet`):
  - Schema: `roi_name, point_index, x, y`
  - Conteúdo: 2 ROIs (Center: 4 pontos, Edge: 4 pontos)
- **Trajectory** (`3_CoordMovimento_{video}.parquet`):
  - Schema: `timestamp, frame, track_id, x1, y1, x2, y2, confidence`
  - Conteúdo: 30 frames, 1 animal, track_id=1

---

**Gerado por**: `scripts/create_test_scenarios.py`
**Verso**: Wizard v1.5
