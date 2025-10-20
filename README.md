# ZebTrack-AI

[![CI](https://github.com/YOUR_USERNAME/ZebTrack-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/ZebTrack-AI/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

ZebTrack-AI é uma aplicação desktop construída com Tkinter que automatiza todo o fluxo de rastreamento multi-animal, análise comportamental e geração de relatórios científicos a partir de vídeos gravados ou ao vivo. O projeto combina modelos de visão computacional (YOLO/OpenVINO), análises especializadas de comportamento e uma interface amigável para laboratórios que estudam zebrafish e outros organismos aquáticos.

> _Screenshot/preview do app virá em breve._

## Sumário rápido

- [Proposito do projeto](#proposito-do-projeto)
- [Guia rápido](#guia-rápido)
- [Principais capacidades](#principais-capacidades)
- [Arquitetura geral](#arquitetura-geral)
- [Estrutura de pastas explicada](#estrutura-de-pastas-explicada)
- [Convenções de código](#convenções-de-código)
- [Pontos de atenção importantes](#pontos-de-atenção-importantes)
- [Testes](#testes)
- [Checklist de QA pré-release](#checklist-de-qa-pré-release)
- [Dados e relatórios](#dados-e-relatórios)
- [Documentação estendida](#documentação-estendida)
- [Contribuindo](#contribuindo)
- [Licença](#licença)

## Proposito do projeto

Entregar uma solução de ponta a ponta para pesquisadores que precisam rastrear múltiplos animais em vídeo, extrair métricas comportamentais e produzir relatórios publicáveis sem sair da aplicação. O ZebTrack-AI integra detecção, rastreamento, análise de ROIs, relatórios (Excel/Word/CSV/Parquet) e ferramentas de QA com foco em reprodutibilidade e alta produtividade.

## Guia rápido

### Pré-requisitos

- Python 3.12 ou superior
- [Poetry](https://python-poetry.org/) configurado no PATH
- GPU opcional (YOLO via CUDA) ou suporte OpenVINO para aceleração via CPU

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

1. **Criar um novo projeto** com o wizard inteligente de 5 etapas (ativado por padrão desde a versão 1.6).
   - Escolha o tipo de projeto (experimental, exploratório ou live) e informe se deseja reutilizar Parquets existentes.
   - Faça o scan recursivo de pastas para localizar vídeos e arquivos `*_arena.parquet`, `*_rois.parquet`, `*_trajectory.parquet`.
   - Revise a detecção automática do design experimental, ajuste regex personalizados quando necessário e defina o plano de importação (SKIP, IMPORT_ZONES, PARTIAL, FULL) vídeo a vídeo.
   - Confirme o resumo consolidado antes da criação — nada é escrito em disco até essa etapa.
2. Selecione o plugin de detector (YOLO padrão ou pesos convertidos em OpenVINO) e configure os limiares de confiança/NMS pelo painel de configuração avançada.
3. Defina arenas/ROIs (ou importe templates/parquets existentes), execute a calibração pixel/cm quando necessário e aproveite os templates reutilizáveis na aba de zonas.
4. Acompanhe o progresso em tempo real pelo overlay de análise, com indicador de modo de rastreamento (multi vs. indivíduo único), estatísticas detalhadas e seleção de trilhas bloqueada automaticamente quando o modo single subject é forçado.
5. Gere relatórios individuais ou agregados ao final. Os arquivos são gravados em `<video>_results/` com prefixos `1_`, `2_`, `3_`, mantendo o esquema Parquet imutável.

### Wizard de Criação de Projetos (padrão)

Desde a v1.6 o wizard é o fluxo oficial de criação de projetos. Não é necessário editar `config.local.yaml`; desabilite o wizard apenas em cenários de suporte legado.

#### Recursos em destaque

-
- ✅ Detecção automática de design experimental (grupos/dias/sujeitos) com regex personalizável e pré-visualização ao vivo
- ✅ Importação seletiva de arenas, ROIs e trajetórias previamente processadas
- ✅ Layout responsivo em 3 colunas (janela 1150×550px) com botões sempre visíveis
- ✅ Integração direta com o sistema de templates de ROI e com as configurações avançadas do detector
- ✅ Resumo final com plano de processamento por ação (SKIP/IMPORT_ZONES/PARTIAL/FULL), métricas de confiança e estimativa de tempo

Consulte a nossa **[Wiki](docs/wiki)** para guias de usuário detalhados, incluindo o passo a passo completo do Wizard e tutoriais.

## Principais capacidades

- **Arquitetura MVVM com Componentes de UI**: Sistema modular, testável e reativo com `StateManager` para uma fonte única de verdade e um `EventBus` para comunicação desacoplada.
- **Wizard inteligente de criação de projetos**: Assistente de 5 etapas com auto-detecção de design experimental, importação granular de Parquets e validação contextual.
- **Rastreamento multi-animal**: Utiliza modelos YOLOv8 com suporte a OpenVINO para aceleração de inferência e gerenciamento de cache.
- **Gestão avançada de ROIs**: Desenho assistido (snapping/clamping), edição segura de vértices, templates reutilizáveis e regras de inclusão configuráveis.
- **Relatórios científicos ricos**: Exportação em Excel, CSV, Parquet e Word com mapas de ROI, gráficos e apêndice de eventos.
- **Overlay em tempo real**: Exibição de modo de rastreamento, progresso detalhado e estatísticas de processamento.
- **Sistema de Projetos Persistente**: Gerencia lotes de vídeos, configurações de análise, metadados e templates de ROI.
- **Configuração avançada in-app**: Editor de `config.local.yaml` com validação Pydantic v2 em tempo real.

## Arquitetura geral

A aplicação segue uma arquitetura **MVVM-like** (Model-View-ViewModel) com uma camada de **UI baseada em componentes**, promovendo alta coesão e baixo acoplamento.

- **View Layer (`zebtrack.ui`)**: Componentes Tkinter modulares e reutilizáveis que emitem eventos.
- **ViewModel Layer (`zebtrack.core.controller`)**: O `MainViewModel` orquestra operações, ouve eventos da UI e atualiza o estado centralizado.
- **Model Layer (`zebtrack.core`, `zebtrack.analysis`)**: O `StateManager` (fonte única de verdade), serviços de domínio (`ProjectService`, `AnalysisService`) e a lógica de negócio principal.

Consulte o documento [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para um diagrama detalhado, fluxos de dados e as decisões arquiteturais do projeto.

## Estrutura de pastas explicada

```text
.
├─ src/
│  └─ zebtrack/
│     ├─ __main__.py          # Entry point do CLI/GUI (python -m zebtrack / poetry run zebtrack)
│     ├─ core/                # Controlador, gerenciamento de projetos, detectores, calibração
│     ├─ ui/                  # Interface Tkinter, diálogos e overlays da análise (wizard, templates, config)
│     ├─ analysis/            # Métricas comportamentais, ROI, reporter, serviços auxiliares
│     ├─ io/                  # Escrita de Parquet, MP4 e integrações de entrada/saída
│     ├─ plugins/             # Implementações de DetectorPlugin (YOLO, OpenVINO, mock)
│     └─ settings.py          # Modelos Pydantic, feature flags, carregamento de config.yaml
├─ tests/                     # Suite pytest (unitário, integração e fluxos de UI)
│  ├─ test_wizard*.py         # 🧙 Testes do wizard (adapter, integração, steps)
│  └─ ...
├─ docs/                      # Documentação complementar (arquitetura, guias, changelog, wiki)
│  ├─ wiki/                   # Conteúdo replicado na wiki do GitHub
│  └─ notes/                  # Estudos técnicos e propostas em andamento
├─ config.yaml                # Configuração padrão carregada em runtime
├─ config.local.yaml          # Overrides locais (ex.: apontar para GPUs específicas)
├─ poetry.lock / pyproject.toml
└─ .github/copilot-instructions.md
```

### Destaques

- **`core/controller.py`**: hub do fluxo de trabalho. Chama detecção, grava dados, atualiza GUI e agenda callbacks via `root.after` para manter a thread principal livre.
- **`ui/wizard/`** 🧙: Wizard de 5 etapas (layout 3 colunas) com adaptador para o controlador e testes dedicados.
- **`core/project_manager.py`**: Varredura granular de Parquets (`scan_input_paths()`), persistência de templates de ROI e estados por vídeo.
- **`io/recorder.py`**: garante esquema Parquet fixo (`timestamp, frame, track_id, x1, y1, x2, y2, confidence, ...`). Colunas em cm são anexadas somente quando há calibração.
- **`analysis/behavior.py` & `analysis/analysis_service.py` + `analysis/reporter.py`**: métricas comportamentais, ROI e geração de relatórios multi-formato.
- **`tests/test_wizard*.py`, `tests/test_overlay_integration.py`, `tests/test_interval_frames_config.py`**: cobertura dos fluxos críticos da UI.

## Convenções de código

- **Linguagem & runtime**: Python ≥ 3.12, dependências gerenciadas por Poetry.
- **Estilo**: [Ruff](https://docs.astral.sh/ruff/) com `line-length = 100` (execute `poetry run ruff check .`).
- **Tipagem**: uso consistente de type hints e Pydantic para contratos de configuração.
- **Logging**: `structlog` com padrão `dominio.acao.resultado` (`controller.load_project.success`, `recorder.save_parquet.error`, etc.).
- **Configurações**: nunca hardcode valores; importe `from zebtrack import settings`.
- **Testes**: pytest com fixtures em `tests/conftest.py`. Cada mudança pública deve ter cobertura.
- **Documentação**: atualize README, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/REFERENCE_GUIDE.md` e `.github/copilot-instructions.md` ao alterar fluxos principais.

## Pontos de atenção importantes

- **Esquema Parquet**: mantenha a ordem das colunas conforme definida em `io/recorder.py`. Novas colunas só podem ser adicionadas ao final e precisam de testes.
- **Escalonamento de zonas**: chame `Detector.set_zones(...)` após conhecer as dimensões reais do vídeo para evitar deslocamentos de ROI.
- **Callbacks de progresso**: agende atualizações com `root.after(0, ...)` para não bloquear a thread principal do Tkinter.
- **Modo de processamento**: fluxos de calibração e diagnóstico forçam o modo single subject; o overlay bloqueia o seletor de trilhas automaticamente.
- **Hardware opcional**: mantenha verificações para ausência de Arduino/câmeras; o app deve continuar funcional em modo offline.
- **Persistência de intervalos**: valores de `analysis_interval_frames`/`display_interval_frames` vivem em `ProjectManager.project_data` e devem ser salvos via `save_project()`.
- **Templates e ROIs**: utilizar `ProjectManager.save_zone_data()` garante que a UI, o detector e os relatórios fiquem sincronizados.

## Testes

```powershell
# Rodar todos os testes com cobertura (paralelizado)
poetry run pytest

# Rodar testes sequencialmente
poetry run pytest -n 0

# Gerar relatório de cobertura HTML
poetry run pytest --cov-report=html
```

Rodar testes específicos:

```powershell
poetry run pytest tests/test_overlay_integration.py::TestOverlayIntegration
poetry run pytest tests/test_interval_frames_config.py
poetry run pytest tests/test_wizard_integration.py
```

### Pre-commit Hooks

```powershell
# Instalar hooks (primeira vez apenas)
poetry run pre-commit install

# Rodar manualmente em todos os arquivos
poetry run pre-commit run --all-files
```

Os hooks executam automaticamente:
- Ruff (lint e format)
- Verificação de trailing whitespace
- Verificação de YAML
- Poetry lock file check

Toda cobertura de testes é automatizada. Reproduza casos extremos via fixtures de pytest e cenários documentados em `test_scenarios/`.

## Checklist de QA pré-release

1. **Atualizar artefatos compartilhados**
   - `poetry run python scripts/build_templates.py`
   - `poetry run python scripts/compile_translations.py`
2. **Executar baterias automáticas**
   - `poetry run pytest -q`
   - `poetry run ruff check .`
3. **Confirmar documentação** – conferir entradas recentes em `docs/changelog.md` e nos guias de fluxo.

## Dados e relatórios

Para cada vídeo processado é criado um diretório `*_results` contendo:

- `3_CoordMovimento_{video}.parquet`: trajetória com colunas obrigatórias `timestamp, frame, track_id, x1, y1, x2, y2, confidence` (+ métricas em cm quando calibrado).
- `{video}_summary.xlsx`: métricas globais e por ROI em formato analítico.
- `{video}_report.docx`: relatório Word com gráficos, mapas de ROI e estatísticas chave.

Relatórios consolidados (`.xlsx`, `.csv`, `.parquet`) podem ser gerados pela aba **Relatórios** após o processamento de múltiplos vídeos.

✅ Consulte [`docs/REFERENCE_GUIDE.md`](docs/REFERENCE_GUIDE.md) para as tabelas completas de variáveis, fórmulas matemáticas e tutoriais de inspeção experimental.

## Documentação estendida

- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**: A documentação técnica central. Contém a visão de componentes, fluxos de dados, decisões arquiteturais e o padrão MVVM.
- **[`docs/wiki/`](docs/wiki)**: A Wiki do projeto, com guias de usuário detalhados, tutoriais e FAQs.
- [`docs/REFERENCE_GUIDE.md`](docs/REFERENCE_GUIDE.md): Guia de referência para métricas, fórmulas e integrações.
- [`docs/COORDINATE_SYSTEMS.md`](docs/COORDINATE_SYSTEMS.md): Detalhes sobre transformações de coordenadas e calibração.

## Contribuindo

Contribuições são super bem-vindas! Leia o [CONTRIBUTING.md](CONTRIBUTING.md) para conhecer o fluxo de desenvolvimento, padrões de commit e checklist de PR.

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para detalhes.
