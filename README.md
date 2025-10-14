# ZebTrack-AI

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

Consulte [`docs/WIZARD_USER_GUIDE.md`](docs/WIZARD_USER_GUIDE.md) para o passo a passo completo e veja a wiki (`docs/wiki/2_Full_Tutorial.md`) para um tutorial guiado.

## Principais capacidades

- **Wizard inteligente de criação de projetos** (v1.7): assistente de 5 etapas com auto-detecção de design, importação granular de Parquets e validação contextual.
- **Rastreamento multi-animal** com modelos YOLOv8 e suporte a pesos convertidos para OpenVINO, inclusive gerenciamento automático de cache (`openvino_model_cache/`).
- **Gestão avançada de ROIs**: desenho assistido com snapping/clamping dentro da arena, edição segura de vértices, templates reutilizáveis e regras de inclusão configuráveis (`centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects`, `seg_overlap`).
- **Relatórios científicos ricos**: exportação em Excel, CSV, Parquet e Word com mapas de ROI, gráficos e apêndice de eventos (entradas/saídas por ROI).
- **Overlay em tempo real**: modo multi vs. single subject, progresso detalhado, indicadores de templates aplicados e estatísticas de frames processados/detectados.
- **Cadastro de projetos persistente**: batches de vídeos, hashes SHA256, intervalos de análise/exibição, metadados experimentais e integrações de hardware (Arduino).
- **Sistema de templates**: salvar/importar/aplicar templates de ROI, com biblioteca persistida em `templates/` e suporte a round-trip automático.
- **Configuração avançada in-app**: editor de `config.local.yaml` com validação Pydantic em tempo real, tooltips e mecanismos de reset.

## Arquitetura geral

A aplicação segue uma arquitetura modular organizada em três camadas principais:

- **Interface gráfica (`zebtrack.ui.gui`)**: diálogos Tkinter, wizard (`ui/wizard/`), editor de configurações, overlays e gerenciadores de templates.
- **Camada de orquestração (`zebtrack.core`)**: `AppController` coordena captura, detecção, gravação e análise; `ProjectManager` gerencia estado persistente e varredura de Parquets.
- **Motor de análise e IO (`zebtrack.analysis`, `zebtrack.io`)**: métricas comportamentais, análise de ROI, gravação Parquet/MP4, geração de relatórios e integrações com hardware opcional.

Consulte [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para diagramas de componentes, fluxo de dados e decisões arquiteturais detalhadas.

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
- **Estilo**: [Ruff](https://docs.astral.sh/ruff/) com `line-length = 88` (execute `poetry run ruff check .`).
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
poetry run pytest -q
```

Rodar testes específicos:

```powershell
poetry run pytest tests/test_overlay_integration.py::TestOverlayIntegration
poetry run pytest tests/test_interval_frames_config.py
poetry run pytest tests/test_wizard_integration.py
```

Testes manuais (quando necessário) vivem em `tests/manual/`. Utilize os scripts atuais e fixtures de pytest para reproduzir contextos específicos.

- `tests/manual/wizard_release_check.py` – valida os templates curados e sugere checklist manual do wizard.
- `tests/manual/analysis_profiles_matrix.py` – gera perfis de análise para revisar fallback/resolução.
- `tests/manual/roi_template_roundtrip.py` – garante round-trip completo dos templates de ROI (salvar/exportar/importar).

## Checklist de QA pré-release

1. **Atualizar artefatos compartilhados**
   - `poetry run python scripts/build_templates.py`
   - `poetry run python scripts/compile_translations.py`
2. **Executar baterias automáticas**
   - `poetry run pytest -q`
   - `poetry run ruff check .`
3. **Revisar fluxos manuais críticos**
   - `python tests/manual/wizard_release_check.py`
   - `python tests/manual/analysis_profiles_matrix.py`
   - `python tests/manual/roi_template_roundtrip.py`
4. **Confirmar documentação** – conferir entradas recentes em `docs/changelog.md` e nos guias de fluxo.

## Dados e relatórios

Para cada vídeo processado é criado um diretório `*_results` contendo:

- `3_CoordMovimento_{video}.parquet`: trajetória com colunas obrigatórias `timestamp, frame, track_id, x1, y1, x2, y2, confidence` (+ métricas em cm quando calibrado).
- `{video}_summary.xlsx`: métricas globais e por ROI em formato analítico.
- `{video}_report.docx`: relatório Word com gráficos, mapas de ROI e estatísticas chave.

Relatórios consolidados (`.xlsx`, `.csv`, `.parquet`) podem ser gerados pela aba **Relatórios** após o processamento de múltiplos vídeos.

✅ Consulte [`docs/REFERENCE_GUIDE.md`](docs/REFERENCE_GUIDE.md) para as tabelas completas de variáveis, fórmulas matemáticas e tutoriais de inspeção experimental.

## Documentação estendida

- [`docs/REFERENCE_GUIDE.md`](docs/REFERENCE_GUIDE.md): guia operacional completo (fluxos, métricas, Arduino, tutoriais, ROI templates, clamping e overlays).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): visão de componentes e decisões arquiteturais.
- [`docs/PROJECT_WORKFLOW.md`](docs/PROJECT_WORKFLOW.md): fluxo detalhado de criação de projetos, processamento em lote e integração com relatórios.
- [`docs/WIZARD_USER_GUIDE.md`](docs/WIZARD_USER_GUIDE.md): passo a passo do wizard e mapeamento das ações de importação.
- [`docs/COORDINATE_SYSTEMS.md`](docs/COORDINATE_SYSTEMS.md): transformações de coordenadas, homografia e calibração.
- [`docs/wiki/*.md`](docs/wiki): versão offline da wiki com instalação, tutorial completo e FAQ atualizados.

## Contribuindo

Contribuições são super bem-vindas! Leia o [CONTRIBUTING.md](CONTRIBUTING.md) para conhecer o fluxo de desenvolvimento, padrões de commit e checklist de PR.

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para detalhes.
