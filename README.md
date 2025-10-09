# ZebTrack-AI

ZebTrack-AI é uma aplicação desktop construída com Tkinter que automatiza todo o fluxo de rastreamento multi-animal, análise comportamental e geração de relatórios científicos a partir de vídeos gravados ou ao vivo. O projeto combina modelos de visão computacional (YOLO/OpenVINO), análises especializadas de comportamento e uma interface amigável para laboratórios que estudam zebrafish e outros organismos aquáticos.

> _Screenshot/preview do app virá em breve._

## Sumário rápido

- [📋 Propósito do projeto](#-propósito-do-projeto)
- [🚀 Guia rápido](#-guia-rápido)
- [🔑 Principais capacidades](#-principais-capacidades)
- [🏗️ Arquitetura geral](#-arquitetura-geral)
- [📁 Estrutura de pastas explicada](#-estrutura-de-pastas-explicada)
- [🔧 Convenções de código](#-convenções-de-código)
- [⚠️ Pontos de atenção importantes](#-pontos-de-atenção-importantes)
- [🧪 Testes](#-testes)
- [🗂️ Dados e relatórios](#-dados-e-relatórios)
- [📚 Documentação estendida](#-documentação-estendida)
- [🤝 Contribuindo](#-contribuindo)
- [📄 Licença](#-licença)

## 📋 Propósito do projeto

Fornecer uma solução de ponta a ponta para pesquisadores que precisam rastrear múltiplos animais em vídeo, extrair métricas comportamentais e produzir relatórios publicáveis sem deixar o ambiente da aplicação. O ZebTrack-AI integra detecção, rastreamento, análise de ROIs e geração de relatórios (Excel/Word/CSV/Parquet) com foco em reprodutibilidade e alta produtividade.

## 🚀 Guia rápido

### Pré-requisitos

- Python 3.12 ou superior
- [Poetry](https://python-poetry.org/) configurado no PATH
- GPU opcional (YOLO via CUDA) ou suporte OpenVINO se desejar aceleração via CPU

### Instalação

```powershell
poetry install
poetry run python -m zebtrack --help
```

### Executar a interface gráfica

```powershell
poetry run zebtrack
```

Fluxo inicial recomendado:

1. **Criar novo projeto** usando o wizard inteligente de 5 etapas (ativável via feature flag):
   - Seleciona tipo de projeto (experimental/exploratório)
   - Escolhe vídeos e pastas com scan recursivo
   - Detecção automática de design experimental a partir de pastas
   - Configuração granular de importação de parquets (arena, ROIs, trajetória)
   - Revisão e confirmação antes da criação
2. Selecionar o plugin de detector (YOLO padrão ou modelos convertidos em OpenVINO).
3. Definir arenas/ROIs (ou importar de parquets existentes) e calibrar pixel/cm.
4. Acompanhar o progresso em tempo real pelo overlay de análise.
5. Gerar relatórios individuais ou agregados ao final.

### 🧙 Wizard de Criação de Projetos (Novo!)

O wizard v1.5 está disponível via feature flag. Para ativar, crie `config.local.yaml`:

```yaml
ui_features:
  use_wizard_for_project_creation: true
```

**Recursos do Wizard:**
- ✅ Auto-detecção de design experimental (grupos, dias, sujeitos)
- ✅ Importação seletiva de zonas de parquets existentes
- ✅ Configuração granular por vídeo (skip/import_zones/partial/full)
- ✅ Validação inteligente e resumo antes da criação

Consulte [`docs/WIZARD_USER_GUIDE.md`](docs/WIZARD_USER_GUIDE.md) para guia completo e [`docs/WIZARD_INTEGRATION.md`](docs/WIZARD_INTEGRATION.md) para documentação técnica.

## 🔑 Principais capacidades

- **Wizard inteligente de criação de projetos** (v1.5): Assistente de 5 etapas com auto-detecção de design experimental, importação de zonas de parquets e configuração granular por vídeo.
- **Rastreamento multi-animal** com modelos YOLOv8 e suporte a pesos OpenVINO.
- **Detecção granular de Parquet**: Identifica automaticamente arquivos `*_arena.parquet`, `*_rois.parquet` e `*_trajectory.parquet` para reaproveitamento seletivo.
- **Importação de zonas**: Reutiliza arenas e ROIs de análises anteriores sem necessidade de redesenhar.
- **Análise comportamental automática**: distância, velocidade, freezing, thigmotaxis, giros bruscos e métricas por ROI.
- **Gestão avançada de ROIs** com regras de inclusão configuráveis (`centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects`, `seg_overlap`).
- **Relatórios científicos** em Excel e Word com mapas de ROI, gráficos e tabelas consolidadas.
- **Fluxo guiado por projetos** com persistência de configurações, batches de vídeos e metadados experimentais.
- **Monitoramento em tempo real** do processamento, incluindo ETA, frames processados/detectados e visualização dos overlays da detecção.
- **Integração com Arduino** para sincronizar estímulos externos e gravação via relés/sensores, com monitoramento dedicado na UI.

## 🏗️ Arquitetura geral

A aplicação segue uma arquitetura modular organizada em três camadas principais:

- **Interface gráfica (`zebtrack.ui.gui`)**: fornece os diálogos Tkinter, controla widgets e sincroniza estados com o controlador.
- **Camada de orquestração (`zebtrack.core`)**: `AppController` coordena captura, detecção, gravação de dados e análise; `ProjectManager` gerencia estado persistente do projeto.
- **Motor de análise e IO (`zebtrack.analysis` e `zebtrack.io`)**: executa métricas comportamentais, grava Parquet/MP4, produz relatórios e integra com hardware opcional (Arduino).

Consulte [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para diagramas de componentes, fluxo de dados e decisões arquiteturais detalhadas.

## 📁 Estrutura de pastas explicada

```text
.
├─ src/
│  └─ zebtrack/
│     ├─ __main__.py          # Entry point do CLI/GUI (python -m zebtrack / poetry run zebtrack)
│     ├─ core/                # Controlador, gerenciamento de projetos, detectores, calibração
│     ├─ ui/                  # Interface Tkinter, diálogos e overlays da análise
│     │  └─ wizard/           # 🧙 Wizard de criação de projetos (5 steps, v1.5)
│     ├─ analysis/            # Métricas comportamentais, ROI, relatórios
│     ├─ io/                  # Escrita de Parquet, MP4 e integrações de entrada/saída
│     ├─ plugins/             # Implementações de DetectorPlugin (YOLO, OpenVINO, etc.)
│     └─ settings.py          # Modelos Pydantic, feature flags e carregamento de config.yaml
├─ tests/                     # Suite pytest (unitário, integração e cenários guiados)
│  ├─ test_wizard*.py         # 🧙 Testes do wizard (91 testes)
│  └─ ...
├─ docs/                      # Documentação complementar (notas, wiki, arquitetura)
│  ├─ WIZARD_*.md             # 🧙 Documentação do wizard (3 arquivos)
│  └─ ...
├─ config.yaml                # Configuração padrão carregada em runtime
├─ config.local.yaml          # 🧙 Overrides locais (feature flags, etc.)
├─ poetry.lock / pyproject.toml
└─ .github/copilot-instructions.md
```

### Destaques

- **`core/controller.py`**: hub do fluxo de trabalho. Chama detecção, grava dados, atualiza GUI e agenda callbacks pelo `root.after`.
- **`ui/wizard/`** 🧙: Wizard de 5 etapas para criação inteligente de projetos com auto-detecção de design e importação de parquets.
- **`core/project_manager.py`**: Detecção granular de parquets (`scan_input_paths()`) e importação seletiva de zonas.
- **`io/recorder.py`**: garante esquema Parquet fixo (`timestamp, frame, track_id, x1, y1, x2, y2, confidence, ...`).
- **`analysis/behavior.py` & `analysis/analysis_service.py` com `analysis/reporter.py`**: calculam métricas comportamentais e fabricam relatórios multi-formato.
- **`plugins/`**: novos detectores devem implementar `DetectorPlugin` e ser registrados em `plugins/__init__.py`.
- **`tests/test_wizard*.py`**: 91 testes cobrindo wizard (83) + adapter (8) com 100% de sucesso.

## 🔧 Convenções de código

- **Linguagem & runtime**: Python ≥ 3.12, dependências gerenciadas por Poetry.
- **Estilo**: [Ruff](https://docs.astral.sh/ruff/) com `line-length = 88` (execute `poetry run ruff check .`).
- **Tipagem**: uso consistente de type hints e dataclasses/Pydantic para contratos.
- **Logging**: `structlog` com padrão `dominio.acao.resultado` (`controller.load_project.success`, `recorder.save_parquet.error`, etc.).
- **Configurações**: nunca hardcode valores; importe `from zebtrack import settings`.
- **Testes**: pytest com fixtures em `tests/conftest.py`. Cada mudança pública deve ter cobertura.
- **Documentação**: atualize README, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` e `.github/copilot-instructions.md` quando alterar fluxos principais.

## ⚠️ Pontos de atenção importantes

- **Esquema Parquet**: mantenha a ordem das colunas conforme definida em `io/recorder.py`. Novas colunas só podem ser adicionadas ao final e precisam de testes.
- **Escalonamento de zonas**: chame `Detector.set_zones(...)` após conhecer as dimensões reais do vídeo para evitar deslocamentos de ROI.
- **Callbacks de progresso**: agende atualizações com `root.after(0, ...)` para não bloquear a thread principal do Tkinter.
- **Integração OpenVINO**: pesos convertidos exigem `.xml/.bin` pareados e hash conferido por `WeightManager`.
- **Hardware opcional**: mantenha verificações para ausência de Arduino/câmeras; o app deve continuar funcional em modo offline.
- **Persistência de intervalos**: valores de `analysis_interval_frames`/`display_interval_frames` vivem em `ProjectManager.project_data` e devem ser salvos via `save_project()`.

## 🧪 Testes

```powershell
poetry run pytest -q
```

Rodar testes específicos:

```powershell
poetry run pytest tests/test_overlay_integration.py::TestOverlayIntegration
poetry run pytest tests/test_interval_frames_config.py
```

Testes manuais (quando necessário) vivem em `tests/manual/`. Os antigos geradores automáticos de cenários do "Wizard" foram descontinuados; utilize os scripts atuais e fixtures de pytest para reproduzir contextos específicos.

## 🗂️ Dados e relatórios

Para cada vídeo processado é criado um diretório `*_results` contendo:

- `3_CoordMovimento_{video}.parquet`: trajetória com colunas obrigatórias `timestamp, frame, track_id, x1, y1, x2, y2, confidence` (+ métricas cm quando calibrado).
- `{video}_summary.xlsx`: métricas globais e por ROI em formato analítico.
- `{video}_report.docx`: relatório Word com gráficos, mapas de ROI e estatísticas chave.

Relatórios consolidados (`.xlsx`, `.csv`, `.parquet`) podem ser gerados pela aba **Relatórios** após o processamento de múltiplos vídeos.

✅ Consulte [`docs/REFERENCE_GUIDE.md`](docs/REFERENCE_GUIDE.md) para as tabelas completas de variáveis, fórmulas matemáticas e tutoriais de inspeção experimental.

## 📚 Documentação estendida

- [`docs/REFERENCE_GUIDE.md`](docs/REFERENCE_GUIDE.md): guia operacional completo (fluxos, métricas, Arduino, tutoriais e FAQ).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): visão de componentes e decisões arquiteturais.
- [`docs/PROJECT_WORKFLOW.md`](docs/PROJECT_WORKFLOW.md): fluxo detalhado de criação de projetos e processamento em lote.
- [`docs/WIZARD_USER_GUIDE.md`](docs/WIZARD_USER_GUIDE.md): passo a passo do wizard de cinco etapas.
- [`docs/COORDINATE_SYSTEMS.md`](docs/COORDINATE_SYSTEMS.md): transformações de coordenadas e calibração.

## 🤝 Contribuindo

Contribuições são super bem-vindas! Leia o [CONTRIBUTING.md](CONTRIBUTING.md) para conhecer o fluxo de desenvolvimento, padrões de commit e checklist de PR.

## 📄 Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para detalhes.
