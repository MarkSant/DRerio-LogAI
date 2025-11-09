# Agent Instructions - Phase 4, Group 2 (APÓS GROUP 1)

**⚠️ AGUARDAR: Group 1 (Agent-12, Agent-13) DEVE concluir primeiro**

## 📋 Visão Geral
- **Grupo de Execução**: Phase 4, Group 2
- **Número de Agentes**: 2 (paralelo após Group 1)
- **Dependências**: ✋ **Agent-12 e Agent-13 concluídos**
- **Branch**: `refactor/phase-4-performance-docs` (mesma do Group 1)
- **Duração**: 3-4 dias

## ⚠️ PRÉ-REQUISITO

```bash
# Pull das mudanças do Group 1
git checkout refactor/phase-4-performance-docs
git pull origin refactor/phase-4-performance-docs

# Verifique que profiling e docs foram adicionados
test -f scripts/profile_performance.py && echo "✅ Agent-12 concluído"
grep -q "DialogManager" docs/ARCHITECTURE.md && echo "✅ Agent-13 concluído"
```

**Se algum check falhar**: ❌ **PARE E AGUARDE Group 1**

---

## 🤖 AGENT-14: User Documentation (P4-T3)

### 📌 Contexto
Você é o **Agent-14** responsável por criar documentação para usuários finais (não desenvolvedores).

### 🎯 Objetivo
Criar guia completo de usuário com screenshots, tutoriais e troubleshooting.

### 📂 Acesso
```bash
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
git checkout refactor/phase-4-performance-docs

# IMPORTANTE: Pull para pegar mudanças do Group 1
git pull origin refactor/phase-4-performance-docs

poetry install
poetry shell
```

### 📖 Documentação Base
- `README.md` (atualizar)
- `docs/wiki/` (nova seção)

### 🛠️ Implementação Passo a Passo

#### Passo 1: Criar Estrutura de Documentação
```bash
mkdir -p docs/wiki/user-guide
mkdir -p docs/wiki/screenshots
```

#### Passo 2: Criar User Guide
Crie `docs/wiki/user-guide/GETTING_STARTED.md`:

```markdown
# Getting Started with DRerio LogAI

## Installation

### Prerequisites
- Windows 10/11
- Python 3.12+
- Webcam or video files

### Install via Poetry (Recommended)
```bash
# Clone repository
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# Install dependencies
poetry install

# Run application
poetry run zebtrack
```

### Install from Release (Coming Soon)
Download `.exe` from [Releases](https://github.com/MarkSant/ZebTrack-AI/releases)

## First Project

### Step 1: Launch Application
1. Run `poetry run zebtrack`
2. Main window opens:

![Main Window](../screenshots/main_window.png)

### Step 2: Create New Project
1. Click **File → New Project**
2. Project wizard opens (5 steps)

![Project Wizard](../screenshots/wizard_step1.png)

### Step 3: Configure ROI
1. Draw regions of interest on video
2. Name each ROI (e.g., "Zone A", "Zone B")
3. Click **Next**

![ROI Configuration](../screenshots/roi_config.png)

### Step 4: Configure Tracking
1. Select detection model (YOLO recommended)
2. Set confidence threshold (default: 0.5)
3. Enable/disable multi-subject tracking
4. Click **Next**

### Step 5: Run Analysis
1. Click **Start Analysis**
2. Monitor progress bar
3. Wait for completion

![Analysis Progress](../screenshots/analysis_running.png)

## Understanding Results

### Output Files
After analysis completes, find results in `<video_name>_results/`:

```
my_video_results/
├── 1_summary_report.csv       # Overall statistics
├── 2_roi_metrics.csv          # Time in each ROI
├── 3_tracking_data.parquet    # Frame-by-frame tracking
└── output_video.mp4           # Annotated video
```

### Reading Summary Report
Open `1_summary_report.csv` in Excel:

| Metric | Value | Unit |
|--------|-------|------|
| Total Time | 120.5 | seconds |
| Distance Traveled | 345.2 | cm |
| Average Speed | 2.86 | cm/s |
| Time in ROI A | 45.3 | seconds |
| Time in ROI B | 32.1 | seconds |

### Visualizing Heatmaps
Heatmaps show movement density:

![Heatmap Example](../screenshots/heatmap.png)

## Troubleshooting

### Camera Not Found
**Problem**: "Camera ID 0 not available"

**Solutions**:
1. Check camera is connected
2. Try different camera ID (File → Settings → Camera ID)
3. Check camera permissions (Windows Settings → Privacy → Camera)

### Low Detection Accuracy
**Problem**: Missing or false detections

**Solutions**:
1. Increase confidence threshold (Settings → Detection → Confidence)
2. Try different model (Settings → Detection → Model)
3. Improve lighting conditions
4. Use higher resolution camera

### Slow Performance
**Problem**: Analysis is very slow (<5 FPS)

**Solutions**:
1. Enable GPU acceleration (Settings → Hardware → GPU)
2. Reduce video resolution
3. Enable frame skipping (Settings → Performance → Skip Frames)
4. Close other applications

## Advanced Features

### Batch Processing
Process multiple videos automatically:
1. File → Batch Processing
2. Add videos to queue
3. Configure shared settings
4. Click **Start Batch**

### Custom ROI Templates
Save ROI configurations for reuse:
1. Configure ROIs in project
2. File → Save ROI Template
3. Load template in future projects

### Export Options
Choose export format:
- **Parquet**: Best for Python analysis (pandas)
- **CSV**: Excel-compatible
- **JSON**: Web applications

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New Project |
| `Ctrl+O` | Open Project |
| `Ctrl+S` | Save Project |
| `Space` | Play/Pause |
| `→` | Next Frame |
| `←` | Previous Frame |
| `Ctrl+R` | Run Analysis |

## Getting Help

- **Documentation**: [docs.zebtrack.ai](https://docs.zebtrack.ai)
- **Issues**: [GitHub Issues](https://github.com/MarkSant/ZebTrack-AI/issues)
- **Email**: support@zebtrack.ai
```

#### Passo 3: Criar FAQ
Crie `docs/wiki/user-guide/FAQ.md`:

```markdown
# Frequently Asked Questions

## General

**Q: What animals does ZebTrack-AI support?**
A: Primarily zebrafish, but works with any small aquatic animals (medaka, larvae, etc.)

**Q: Can I use with multiple cameras?**
A: Not simultaneously, but can analyze multiple videos in batch mode.

**Q: Is GPU required?**
A: No, but recommended for real-time performance (25+ FPS).

## Technical

**Q: What video formats are supported?**
A: MP4, AVI, MOV, MKV (any format supported by OpenCV)

**Q: Maximum video resolution?**
A: Tested up to 4K (3840x2160), but 1080p recommended for performance.

**Q: How much disk space needed?**
A: ~1GB per hour of 1080p video (for tracking data + annotated video)

## Analysis

**Q: How to improve tracking accuracy?**
A: (1) Better lighting, (2) Higher resolution, (3) Adjust confidence threshold

**Q: What is "confidence threshold"?**
A: Minimum score (0-1) for accepting a detection. Higher = fewer false positives.

**Q: Can I edit ROIs after analysis?**
A: No, must re-run analysis. Save ROI templates to speed up re-configuration.
```

#### Passo 4: Atualizar README.md
Edite `README.md` - adicione seção User Guide:

```markdown
## 📖 Documentation

### For Users
- **[Getting Started Guide](docs/wiki/user-guide/GETTING_STARTED.md)** - First project tutorial
- **[FAQ](docs/wiki/user-guide/FAQ.md)** - Common questions and answers
- **[Troubleshooting](docs/wiki/user-guide/TROUBLESHOOTING.md)** - Problem solving

### For Developers
- **[Architecture](docs/ARCHITECTURE.md)** - System design
- **[Development Guide](CONTRIBUTING.md)** - Contributing guidelines
- **[API Reference](docs/api/)** - Code documentation
```

#### Passo 5: Capturar Screenshots
```bash
# Execute aplicação e capture telas
poetry run zebtrack

# Salve screenshots em docs/wiki/screenshots/
# - main_window.png
# - wizard_step1.png
# - roi_config.png
# - analysis_running.png
# - heatmap.png
```

#### Passo 6: Commit
```bash
git add docs/wiki/ README.md
git commit -m "docs: Add comprehensive user documentation (P4-T3)

- Create Getting Started guide with screenshots
- Add FAQ with 10+ common questions
- Add troubleshooting guide
- Update README with user documentation links
- Include keyboard shortcuts reference

Phase: 4
Task: P4-T3
Agent: Agent-14
Depends: P4-T1, P4-T2"

git push origin refactor/phase-4-performance-docs
```

### ✅ Critérios de Sucesso
- [ ] Getting Started guide criado (2000+ palavras)
- [ ] FAQ com 10+ perguntas
- [ ] Troubleshooting guide
- [ ] Screenshots capturados (5+)
- [ ] README atualizado

### ⏱️ Estimativa: ~5-6 horas

---

## 🤖 AGENT-15: Documentation Curation (P4-T4)

### 📌 Contexto
Você é o **Agent-15** responsável por curar TODA a documentação do repositório, removendo obsoleto e organizando.

### 🎯 Objetivo
Auditar todos os `.md` files, remover outdated docs, reorganizar estrutura, criar índice central.

### 📂 Acesso
```bash
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
git checkout refactor/phase-4-performance-docs
git pull origin refactor/phase-4-performance-docs

poetry install
poetry shell
```

### 🛠️ Implementação Passo a Passo

#### Passo 1: Auditar Documentação Existente
```bash
# Liste todos os markdown files
find . -name "*.md" -type f | grep -v node_modules | grep -v ".venv" > docs_inventory.txt

# Analise cada arquivo:
# - Última modificação
# - Referências obsoletas
# - Duplicações
```

#### Passo 2: Criar Índice Central
Crie `docs/INDEX.md`:

```markdown
# ZebTrack-AI Documentation Index

**Last Updated**: November 2025  
**Version**: 2.1.0

## 📚 Overview
This index provides centralized navigation for all ZebTrack-AI documentation.

---

## 👤 For Users

### Getting Started
- **[Installation Guide](../README.md#installation)** - Setup instructions
- **[Quick Start Tutorial](wiki/user-guide/GETTING_STARTED.md)** - First project walkthrough
- **[FAQ](wiki/user-guide/FAQ.md)** - Frequently asked questions
- **[Troubleshooting](wiki/user-guide/TROUBLESHOOTING.md)** - Common problems

### Features
- **[Behavioral Metrics](BEHAVIORAL_METRICS.md)** - Available analysis metrics
- **[Coordinate Systems](COORDINATE_SYSTEMS.md)** - Understanding ROI coordinates
- **[Video Formats](wiki/user-guide/VIDEO_FORMATS.md)** - Supported file types

---

## 🛠️ For Developers

### Architecture & Design
- **[Architecture Overview](ARCHITECTURE.md)** - System design ⭐ START HERE
- **[Dependency Injection Guide](DEPENDENCY_INJECTION_GUIDE.md)** - DI patterns
- **[State Management](STATE_MANAGEMENT_GUIDE.md)** - StateManager usage
- **[Service Layer Patterns](SERVICE_LAYER_PATTERNS.md)** - Service design

### Development Workflows
- **[Contributing Guide](../CONTRIBUTING.md)** - How to contribute
- **[Developer Guide - Wizard](DEVELOPER_GUIDE_WIZARD.md)** - Wizard development
- **[Testing Guide](TESTING_TKINTER_WINDOWS.md)** - Testing Tk applications
- **[Error Handling](ERROR_HANDLING.md)** - Exception handling patterns

### API Reference
- **[DetectorService API](detector_service_api.md)** - Detection interface
- **[Widgets](WIDGETS.md)** - Custom UI components
- **[Workflows](WORKFLOWS.md)** - Common development flows

### Performance & Optimization
- **[Performance Tuning](PERFORMANCE_TUNING.md)** - Optimization guide
- **[Performance Baseline](PERFORMANCE_BASELINE.md)** - Current metrics
- **[Benchmark Guide](BENCHMARK_GUIDE.md)** - Benchmarking tools

### Refactoring (2025)
- **[Refactoring Plan Part 1](../PLANO_REFATORACAO_PARALELA_PARTE1.md)** - Phase 1
- **[Refactoring Plan Part 2](../PLANO_REFATORACAO_PARALELA_PARTE2.md)** - Phases 2-4
- **[Agent Orchestration Guide](../AGENT_ORCHESTRATION_GUIDE.md)** - Execution guide
- **[Quick Reference](../REFACTORING_QUICK_REFERENCE.md)** - Summary

---

## 🗂️ Archive (Historical Reference Only)

These documents are kept for historical context but may be outdated:
- **[archive/MAINVIEWMODEL_ANALYSIS.md](archive/MAINVIEWMODEL_ANALYSIS.md)** - Pre-refactoring analysis
- **[archive/GOD_OBJECTS_ANALYSIS.md](archive/GOD_OBJECTS_ANALYSIS.md)** - Initial assessment
- **[archive/PHASE3_FINAL_STATUS.md](archive/PHASE3_FINAL_STATUS.md)** - Old phase tracking

---

## 📋 Quick Navigation

### By Role
- **New User** → Start with [Getting Started](wiki/user-guide/GETTING_STARTED.md)
- **New Developer** → Start with [Architecture](ARCHITECTURE.md) + [Contributing](../CONTRIBUTING.md)
- **Debugger** → See [Quick Debug Guide](QUICK_DEBUG_GUIDE.md)
- **Performance Engineer** → See [Performance Tuning](PERFORMANCE_TUNING.md)

### By Task
- **Implementing new feature** → [Workflows](WORKFLOWS.md) + [Service Patterns](SERVICE_LAYER_PATTERNS.md)
- **Fixing bug** → [Error Handling](ERROR_HANDLING.md) + [Testing](TESTING_TKINTER_WINDOWS.md)
- **Adding detector** → [DetectorService API](detector_service_api.md)
- **UI change** → [Widgets](WIDGETS.md) + [State Management](STATE_MANAGEMENT_GUIDE.md)

---

## 🔄 Maintenance

This index is maintained by Agent-15 (P4-T4) as part of documentation curation.  
**Update frequency**: After each major release or refactoring phase.

**Missing documentation?** [Open an issue](https://github.com/MarkSant/ZebTrack-AI/issues/new)
```

#### Passo 3: Mover Arquivos Obsoletos para Archive
```bash
# Crie diretório archive
mkdir -p docs/archive

# Mova documentos obsoletos (pré-refactoring)
mv GOD_OBJECTS_ANALYSIS.md docs/archive/
mv GOD_OBJECTS_QUICK_REFERENCE.txt docs/archive/
mv MAINVIEWMODEL_ANALYSIS.md docs/archive/
mv MAINVIEWMODEL_QUICK_REFERENCE.txt docs/archive/
mv PHASE3_FINAL_STATUS.md docs/archive/
mv PHASE3_SESSION_PROGRESS.md docs/archive/
mv TASK_CONTEXTS.md docs/archive/
mv TASK_CONTEXTS_RODADAS_3_4_5.md docs/archive/
```

#### Passo 4: Reorganizar Estrutura
```bash
# Organize em categorias
mkdir -p docs/user-guide
mkdir -p docs/developer-guide
mkdir -p docs/api-reference

# Mova para estrutura lógica
# (user-guide, developer-guide, api-reference)
```

#### Passo 5: Atualizar Links Quebrados
```bash
# Encontre links quebrados
grep -r "\[.*\](.*\.md)" docs/ | grep -v "docs/archive"

# Atualize referencias para novos paths
# Ex: [Architecture](ARCHITECTURE.md) → [Architecture](docs/ARCHITECTURE.md)
```

#### Passo 6: Criar CHANGELOG para Docs
Edite `docs/CHANGELOG_DOCS.md`:

```markdown
# Documentation Changelog

## [November 2025] - Major Curation (P4-T4)

### Added
- Central documentation index (`docs/INDEX.md`)
- User guide section (Getting Started, FAQ, Troubleshooting)
- Performance baseline documentation
- Architecture diagrams (updated post-refactoring)

### Changed
- Reorganized into user-guide/ and developer-guide/
- Updated all internal links
- Moved outdated docs to archive/

### Removed
- Duplicate README files
- Obsolete refactoring tracking docs (moved to archive)
- Outdated API examples (pre-DI)

### Fixed
- 15+ broken internal links
- Inconsistent formatting across guides
- Missing copyright notices
```

#### Passo 7: Commit
```bash
git add docs/ *.md
git commit -m "docs: Complete documentation curation and reorganization (P4-T4)

- Create central documentation index (INDEX.md)
- Archive 10+ obsolete documents
- Reorganize into user-guide/ and developer-guide/
- Fix 15+ broken internal links
- Add documentation changelog
- Improve discoverability and navigation

Phase: 4
Task: P4-T4
Agent: Agent-15
Depends: P4-T1, P4-T2, P4-T3"

git push origin refactor/phase-4-performance-docs
```

### ✅ Critérios de Sucesso
- [ ] `docs/INDEX.md` criado
- [ ] Arquivos obsoletos arquivados (10+)
- [ ] Links quebrados corrigidos (todos)
- [ ] Estrutura reorganizada (user/developer)
- [ ] Changelog de documentação criado

### ⏱️ Estimativa: ~4-5 horas

---

## 📊 Resumo Group 2 (Phase 4)

### Dependência de Group 1
✋ **Agent-14 e Agent-15 SÓ iniciam após Agent-12 e Agent-13**

### Execução Paralela (Dentro do Group 2)
✅ Agent-14 e Agent-15 podem trabalhar simultaneamente

### Comunicação Final - Phase 4 Completa
```
✅ PHASE 4 CONCLUÍDA (TODAS AS 4 PHASES)

Group 1:
- ✅ Performance profiling (Agent-12)
- ✅ Architecture docs (Agent-13)

Group 2:
- ✅ User documentation (Agent-14)
- ✅ Documentation curation (Agent-15)

Branch: refactor/phase-4-performance-docs

🎉🎉🎉 REFATORAÇÃO COMPLETA - PRONTO PARA MERGE FINAL 🎉🎉🎉

Próximos passos:
1. Merge refactor/phase-4-performance-docs → main
2. Tag release v2.2.0
3. Deploy updated documentation
4. Celebrate! 🍾
```

---

**Início**: ___________
**Conclusão**: ___________
**Status**: [ ] Aguardando Group 1 | [ ] Em Progresso | [ ] Concluído
