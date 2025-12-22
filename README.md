<div align="center">
  <img src="src/zebtrack/ui/assets/logo_readme.png" alt="ZebTrack-AI Logo" width="400"/>

  # ZebTrack-AI

  **Plataforma Inteligente de Rastreamento e Análise Comportamental para *Danio rerio* (Zebrafish)**

  ![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)
  ![Architecture](https://img.shields.io/badge/architecture-Event--Driven-green.svg)
  ![Python](https://img.shields.io/badge/python-3.11%2B-yellow.svg)
  ![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)
  ![Tests](https://img.shields.io/badge/tests-2568%20passing-brightgreen.svg)
  ![Coverage](https://img.shields.io/badge/coverage-61%25-orange.svg)

  [Documentação](docs/) | [Guia de Contribuição](docs/guides/developer/DEVELOPER_GUIDE.md) | [Arquitetura](docs/architecture/ARCHITECTURE.md) | [Changelog](docs/changelog.md)
</div>

---

## 📋 Sobre o Projeto

O **ZebTrack-AI** é uma solução completa e de código aberto para análise automatizada de comportamento de peixes zebrafish (*Danio rerio*) em experimentos científicos. Desenvolvido com foco em **reprodutibilidade**, **precisão** e **facilidade de uso**, o sistema combina técnicas avançadas de visão computacional com Deep Learning para rastreamento multi-objeto em tempo real.

### 🎯 Motivação

Pesquisadores em neurociência, farmacologia e toxicologia frequentemente utilizam zebrafish como modelo animal devido à sua transparência óptica, rápido desenvolvimento e alta homologia genética com humanos (~70%). No entanto, a análise manual de vídeos comportamentais é:
- **Demorada**: Horas de trabalho para analisar minutos de vídeo
- **Subjetiva**: Variabilidade entre observadores
- **Limitada**: Impossibilidade de rastrear múltiplos indivíduos simultaneamente

O **ZebTrack-AI** resolve esses problemas oferecendo análise automatizada, objetiva e escalável.

### ✨ Diferenciais

- **🤖 Deep Learning Otimizado**: Modelos YOLO v8/v11 com aceleração OpenVINO para detecção em tempo real
- **📊 Métricas Científicas**: Cálculo automático de velocidade, distância percorrida, tempo em zonas, imobilidade, proximidade social
- **🎨 Interface Intuitiva**: Wizard de 5 etapas para configuração de projetos sem necessidade de programação
- **🔬 Reprodutibilidade**: Todas as configurações e parâmetros de análise são salvos junto com os dados
- **📹 Análise ao Vivo**: Captura e análise em tempo real com câmeras USB/webcams
- **🏗️ Arquitetura Event-Driven**: Sistema modular e extensível baseado em eventos
- **📦 Formatos Padrão**: Exportação para Parquet (dados), Excel (métricas) e Word (relatórios)

## 🚀 Novidades na Versão 4.0

### Refatoração Arquitetural Completa

A v4.0 representa uma reescrita fundamental do sistema com foco em estabilidade, manutenibilidade e performance:

*   **🏗️ Arquitetura Event-Driven**: Refatoração completa para eliminar acoplamento direto entre componentes
    - Sistema de eventos com `EventBus` para comunicação assíncrona
    - Padrão Mediator (`UICoordinator`) para orquestração da UI
    - Eliminação de 90+ linhas de código legado de threads
*   **🎨 Interface Otimizada**: Nova aba unificada de "Processamento e Relatórios"
    - Redução de 50% no uso de memória durante renderização
    - Eliminação de race conditions em atualizações de UI
    - Preview em tempo real com `LivePreviewWindow`
*   **⚡ Performance**: Melhorias significativas de velocidade
    - Startup 67% mais rápido (6.0s → 2.0s) com lazy loading
    - `RecorderFactory` para carregamento sob demanda de pandas/pyarrow
    - Cache de hardware com TTL de 30s (5x mais rápido)
*   **🔒 Confiabilidade**: Sistema de testes robusto
    - 2568 testes (61% de cobertura)
    - Testes E2E para fluxos críticos
    - Timeout automático para prevenir travamentos (pytest-timeout)
*   **🐛 Correções Críticas**: Resolução de bugs de câmera ao vivo
    - Seleção correta de `camera_index` em projetos live
    - Respeito a intervalos de análise configurados
    - Unificação de `LiveCameraService` para ambos os contextos

### Multi-Aquarium v2 (Novo!)

Suporte avançado para análise simultânea de múltiplos aquários:

*   **🔄 Detecção Paralela**: `detect_partitioned_parallel()` com ThreadPoolExecutor (~30-40% speedup)
*   **📦 Inferência em Lote**: `detect_batch()` para processamento offline otimizado
*   **✂️ Recorte ROI**: `_crop_aquarium_region()` para extração individual por aquário
*   **📊 Métricas de Incerteza**: Colunas `uncertainty` e `bbox_iou` no Parquet para análise de qualidade
*   **🔬 Thigmotaxis**: Métricas de preferência de borda por aquário
*   **✅ Validação Avançada**: `validate_multi_aquarium_config()` retorna erros e avisos
*   **🔍 Detecção de Gaps**: `_detect_per_aquarium_gaps()` para lacunas de trajetória por aquário
*   **🛡️ Recuperação de Erros**: Fallback automático quando detecção em aquário individual falha
*   **📤 Exportação R/Python**: Scripts prontos para análise estatística em R ou Python
*   **🖼️ Preview Lado-a-lado**: `create_side_by_side_preview()` para comparação visual
*   **📝 Relatórios por Aquário (Word/Excel)**: artefatos separados por `aquarium_0/`, `aquarium_1/` e exibição correta na aba de Relatórios

## 🛠️ Instalação

### Requisitos do Sistema

| Componente | Versão Mínima | Recomendado |
|-----------|---------------|-------------|
| Python | 3.11 | 3.12+ |
| RAM | 4 GB | 8 GB+ |
| CPU | Dual-core | Quad-core+ |
| GPU | Não requerida | NVIDIA com CUDA (opcional) |
| SO | Windows 10, Linux, macOS | Ubuntu 22.04+ |

### Instalação Rápida

1.  **Pré-requisitos**: Certifique-se de ter Python 3.11+ e Poetry instalados
    ```bash
    # Verificar versão do Python
    python --version

    # Instalar Poetry (se necessário)
    curl -sSL https://install.python-poetry.org | python3 -
    ```

2.  **Clone o repositório**:
    ```bash
    git clone https://github.com/MarkSant/ZebTrack-AI.git
    cd ZebTrack-AI
    ```

3.  **Instale as dependências**:
    ```bash
    poetry install
    ```

4.  **(Opcional) Configure parâmetros locais**:
    ```bash
    # Copie o template de configuração local
    cp config.yaml config.local.yaml

    # Edite config.local.yaml com suas preferências
    # (índice da câmera, porta Arduino, parâmetros de detecção, etc.)
    ```

### Instalação para Desenvolvimento

Se você pretende contribuir ou modificar o código:

```bash
# Clone e instale com dependências de desenvolvimento
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install --with dev

# Instale os hooks de pré-commit
poetry run pre-commit install

# Execute os testes para verificar a instalação
poetry run pytest -q
```

## ▶️ Execução

### Modo Gráfico (GUI)

Para iniciar a interface gráfica:

```bash
poetry run zebtrack
```

### Modo Linha de Comando (CLI)

O ZebTrack-AI também pode ser executado via linha de comando:

```bash
# Processar um vídeo específico
poetry run zebtrack process --video /caminho/para/video.mp4 --project meu_projeto

# Análise ao vivo com câmera
poetry run zebtrack live --camera 0 --duration 300

# Gerar relatório de um projeto existente
poetry run zebtrack report --project meu_projeto
```

### Primeira Execução

Na primeira execução, o sistema irá:
1. **Baixar modelos YOLO**: Os modelos de detecção (~6 MB) serão baixados automaticamente
2. **Criar diretórios**: Estrutura de pastas para projetos, templates e cache
3. **Exibir Wizard**: Interface guiada para criar seu primeiro projeto

## 🎬 Guia Rápido de Uso

### Fluxo de Trabalho Típico

1. **Criar Projeto** (Wizard de 5 Etapas)
   - Configurar informações do experimento (nome, descrição, duração)
   - Definir arena e ROIs (Regions of Interest)
   - Configurar detector e parâmetros de rastreamento
   - Selecionar vídeos para análise
   - Configurar hardware (Arduino, câmera) se aplicável

2. **Processar Vídeos**
   - Detecção automática de peixes com YOLO
   - Rastreamento multi-objeto com BYTETracker
   - Filtragem de trajetórias (Savitzky-Golay)
   - Cálculo de métricas comportamentais

3. **Analisar Resultados**
   - Visualizar trajetórias e heatmaps
   - Revisar métricas por ROI e zona
   - Exportar dados para análise estatística

4. **Gerar Relatórios**
   - Relatórios automatizados em Word
   - Planilhas Excel com métricas agregadas
   - Gráficos de velocidade, distância e ocupação

### Exemplo: Análise de Vídeo Pré-gravado

```bash
# 1. Criar projeto via GUI
poetry run zebtrack

# 2. Ou via CLI (avançado)
poetry run zebtrack create-project \
  --name "Experimento CBD" \
  --arena-type circular \
  --roi-count 4 \
  --videos "video1.mp4,video2.mp4"

# 3. Processar vídeos
poetry run zebtrack process --project "Experimento CBD"

# 4. Gerar relatório
poetry run zebtrack report --project "Experimento CBD" --format docx
```

### Exemplo: Análise ao Vivo

```bash
# Iniciar sessão de análise ao vivo (5 minutos)
poetry run zebtrack live \
  --camera 0 \
  --duration 300 \
  --project "Teste Live" \
  --preview
```

## 🔬 Funcionalidades Científicas

### Detecção e Rastreamento

- **Modelos de Detecção**: YOLO v8/v11 (nano, small, medium)
- **Aceleração**: OpenVINO para CPUs Intel (3-5x mais rápido)
- **Multi-objeto**: Rastreamento simultâneo de até 96 peixes
- **Filtragem**: Savitzky-Golay para suavização de trajetórias
- **Persistência**: Manutenção de IDs através de oclusões temporárias

### Métricas Comportamentais

#### Métricas Espaciais
- **Distância Total Percorrida**: Em pixels e centímetros (com calibração)
- **Velocidade Média/Máxima**: Cálculo frame-a-frame com janelas temporais
- **Ocupação de Zonas**: Tempo em centro vs. periferia (tixotropismo)
- **Ocupação de ROIs**: Tempo em cada região de interesse definida
- **Proximidade Social**: Distância média entre indivíduos

#### Métricas Temporais
- **Tempo de Imobilidade**: Detecção de freezing (velocidade < threshold)
- **Tempo em Movimento**: Atividade locomotora contínua
- **Latência de Resposta**: Tempo até primeiro movimento após estímulo
- **Frequência de Eventos**: Entradas/saídas de zonas ou ROIs

#### Métricas Avançadas
- **Tortuosidade**: Razão entre distância percorrida e distância euclidiana
- **Meandros**: Mudanças de direção (ângulos de curva)
- **Distribuição Espacial**: Heatmaps e mapas de ocupação
- **Padrões Circadianos**: Análise de atividade ao longo do tempo

### Calibração e Coordenadas

- **Calibração Espacial**: Conversão pixels → cm usando arUco markers
- **Sistemas de Coordenadas**: Referência (original) e display (redimensionado)
- **Geometria de ROIs**: Suporte a polígonos, círculos e retângulos
- **Buffer de ROIs**: Expansão/contração de regiões para análises de proximidade

### Reprodutibilidade

- **Formato Parquet**: Dados tabulares compactados e eficientes
- **Schema Imutável**: Garantia de compatibilidade entre versões
- **Metadados YAML**: Todas as configurações salvas junto com os dados
- **Versionamento**: Rastreabilidade de modelos e parâmetros usados
- **Timestamps**: Sincronização precisa entre eventos

## 📖 Documentação Completa

A documentação técnica está disponível na pasta `docs/`:

### Guias Essenciais
*   📚 [**CHEATSHEET.md**](docs/guides/developer/CHEATSHEET.md) - Referência rápida de comandos e padrões
*   🏗️ [**ARCHITECTURE.md**](docs/architecture/ARCHITECTURE.md) - Arquitetura Event-Driven e Mediator
*   👨‍💻 [**DEVELOPER_GUIDE.md**](docs/guides/developer/DEVELOPER_GUIDE.md) - Guia completo para contribuidores
*   🧙 [**DEVELOPER_GUIDE_WIZARD.md**](docs/guides/developer/DEVELOPER_GUIDE_WIZARD.md) - Desenvolvimento do Wizard
*   🧪 [**README_TESTS.md**](README_TESTS.md) - Guia completo de testes (2568 testes)

### Guias Técnicos
*   🔌 [**DEPENDENCY_INJECTION_GUIDE.md**](docs/architecture/DEPENDENCY_INJECTION_GUIDE.md) - Padrões de DI
*   📡 [**EVENT_BUS_GUIDE.md**](docs/architecture/EVENT_BUS_GUIDE.md) - Sistema de eventos
*   🗺️ [**COORDINATE_SYSTEMS.md**](docs/reference/COORDINATE_SYSTEMS.md) - Sistemas de coordenadas
*   🎯 [**STATE_MANAGEMENT_GUIDE.md**](docs/architecture/STATE_MANAGEMENT_GUIDE.md) - Gerenciamento de estado
*   🚀 [**PERFORMANCE_TUNING.md**](docs/performance/PERFORMANCE_TUNING.md) - Otimizações

### Guias Operacionais
*   📋 [**REFERENCE_GUIDE.md**](docs/reference/REFERENCE_GUIDE.md) - Guia operacional completo
*   🔄 [**WORKFLOWS.md**](docs/guides/developer/WORKFLOWS.md) - Fluxos de trabalho detalhados
*   🐛 [**QUICK_DEBUG_GUIDE.md**](docs/guides/developer/QUICK_DEBUG_GUIDE.md) - Solução de problemas
*   ⚠️ [**KNOWN_ISSUES.md**](docs/reference/KNOWN_ISSUES.md) - Problemas conhecidos e soluções
*   📝 [**CHANGELOG.md**](docs/changelog.md) - Histórico de versões

### Documentos Históricos
*   📦 [**archive/**](docs/archive/) - Documentação de versões anteriores

## 🏗️ Estrutura do Projeto

### Organização de Diretórios

```
ZebTrack-AI/
├── src/zebtrack/               # Código-fonte principal
│   ├── __main__.py            # Entry point e Composition Root (DI)
│   ├── core/                   # Camada de negócios
│   │   ├── state_manager.py   # Gerenciamento de estado (thread-safe)
│   │   ├── main_view_model.py # Orquestrador principal (MVVM)
│   │   ├── detector.py        # Serviço de detecção AI
│   │   ├── detector_service.py # Wrapper do detector
│   │   ├── project_manager.py  # Gerenciamento de projetos
│   │   ├── project_service.py  # Lógica de projetos
│   │   ├── wizard_service.py   # Lógica do wizard
│   │   ├── live_camera_service.py # Análise ao vivo
│   │   ├── recording_service.py   # Gravação de sessões
│   │   └── video_processing_service.py # Processamento de vídeos
│   ├── io/                     # Camada de I/O
│   │   ├── recorder.py         # Persistência Parquet
│   │   ├── recorder_factory.py # Lazy loading de recorder
│   │   ├── video_source.py     # Fonte de frames (vídeos)
│   │   ├── camera.py           # Captura de câmera
│   │   ├── live_stream_source.py # Fonte limitada por tempo
│   │   └── frame_source_factory.py # Factory de fontes
│   ├── ui/                     # Interface gráfica
│   │   ├── gui.py              # Janela principal (10759 linhas)
│   │   ├── ui_coordinator.py   # Mediator (Event-Driven)
│   │   ├── components/         # Gerenciadores de UI
│   │   │   ├── canvas_manager.py
│   │   │   ├── event_dispatcher.py
│   │   │   ├── project_view_manager.py
│   │   │   └── video_manager.py
│   │   ├── dialogs/            # Diálogos extraídos (14 diálogos)
│   │   │   ├── live_analysis_dialog.py
│   │   │   ├── live_preview_window.py
│   │   │   └── ...
│   │   ├── wizard/             # Wizard de 5 etapas
│   │   │   ├── models.py       # Modelos Pydantic
│   │   │   ├── wizard_step1.py
│   │   │   └── ...
│   │   └── assets/             # Recursos visuais (logos)
│   ├── analysis/               # Análise comportamental
│   │   ├── analysis_service.py
│   │   ├── behavior.py         # Métricas comportamentais
│   │   ├── roi.py              # Análise de ROIs
│   │   └── reporter.py         # Geração de relatórios
│   ├── plugins/                # Sistema de plugins
│   │   ├── base.py             # Interface de plugins
│   │   ├── yolov8_detector.py
│   │   └── openvino_detector.py
│   └── utils/                  # Utilitários
│       ├── geometry.py         # Cálculos geométricos
│       ├── coordinates.py      # Conversão de coordenadas
│       └── filters.py          # Filtros de trajetória
├── tests/                      # Suíte de testes (2568 testes)
│   ├── conftest.py            # Fixtures e hooks pytest
│   ├── unit/                  # Testes unitários (~1586)
│   ├── integration/           # Testes de integração (~949)
│   └── e2e/                   # Testes end-to-end (~35)
├── docs/                       # Documentação técnica
│   ├── ARCHITECTURE.md
│   ├── DEVELOPER_GUIDE.md
│   ├── CHEATSHEET.md
│   └── archive/               # Documentação histórica
├── config.yaml                 # Configuração padrão
├── config.local.yaml          # Configuração local (git-ignored)
├── pyproject.toml             # Configuração Poetry
└── README.md                  # Este arquivo
```

### Arquitetura (MVVM-S + Event-Driven)

#### Camadas Principais

| Camada | Responsabilidade | Componentes Chave |
|--------|------------------|-------------------|
| **Model** | Estado e dados | `StateManager`, `ProjectManager`, `DetectorService` |
| **View** | Interface Tkinter | `GUI`, `Dialogs`, `Wizard` |
| **ViewModel** | Orquestração | `MainViewModel`, `UICoordinator` |
| **Services** | Lógica de negócios | `WizardService`, `AnalysisService`, `LiveCameraService` |

#### Fluxo de Dados (Event-Driven)

```
User → UI Event → EventBus → Handler → StateManager → UI Update
                                ↓
                          Services/Model
```

**Benefícios**:
- ✅ Desacoplamento total entre componentes
- ✅ Testabilidade (injeção de dependências)
- ✅ Thread-safety (comunicação assíncrona)
- ✅ Manutenibilidade (responsabilidades claras)

## 🧪 Testes

### Executar Testes

```bash
# Testes rápidos (excluindo GUI/slow) - ~1586 testes
poetry run pytest

# Todos os testes - ~2568 testes (6-7 min)
poetry run pytest -m "" -n0

# Testes de GUI (sequencial) - ~949 testes
poetry run pytest -m gui -n0

# Testes lentos - ~35 testes
poetry run pytest -m slow

# Com cobertura
poetry run pytest --cov=src/zebtrack --cov-report=html
```

### Estatísticas de Testes

| Categoria | Quantidade | Tempo |
|-----------|-----------|-------|
| **Testes Unitários** | 1586 | ~2 min |
| **Testes de GUI** | 949 | ~3 min |
| **Testes de Integração** | 33 | ~1 min |
| **Testes E2E** | 16 | ~30s |
| **Testes Lentos** | 35 | ~1 min |
| **TOTAL** | **2568** | **6-7 min** |

### Cobertura

- **Cobertura Global**: 61%
- **Módulos Críticos**: >80% (detector, recorder, state_manager)
- **Meta**: 70% (em progresso)

### Marcadores de Teste

```python
@pytest.mark.unit         # Teste unitário rápido
@pytest.mark.integration  # Teste de integração
@pytest.mark.gui          # Teste de interface Tkinter
@pytest.mark.slow         # Teste lento (>5s)
@pytest.mark.e2e          # Teste end-to-end
```

Para mais detalhes, consulte [README_TESTS.md](README_TESTS.md).

## 🤝 Contribuição

Contribuições são muito bem-vindas! Este projeto segue práticas modernas de desenvolvimento:

### Como Contribuir

1. **Fork** o repositório
2. **Clone** seu fork localmente
3. **Crie uma branch** para sua feature/fix:
   ```bash
   git checkout -b feature/minha-feature
   ```
4. **Instale dependências de desenvolvimento**:
   ```bash
   poetry install --with dev
   poetry run pre-commit install
   ```
5. **Faça suas alterações** seguindo os padrões do projeto
6. **Execute os testes**:
   ```bash
   poetry run pytest -q
   poetry run ruff check .
   ```
7. **Commit** suas mudanças com mensagens claras:
   ```bash
   git commit -m "feat: adiciona suporte para YOLO v12"
   ```
8. **Push** para seu fork e abra um **Pull Request**

### Diretrizes de Código

- ✅ **Python 3.11+**: Use type hints e recursos modernos
- ✅ **Ruff**: Linter e formatador (linha máxima: 100 caracteres)
- ✅ **Docstrings**: Google Style para funções públicas
- ✅ **Testes**: Adicione testes para novas funcionalidades
- ✅ **DI**: Sempre use injeção de dependências
- ✅ **Event-Driven**: Prefira comunicação via `EventBus`
- ✅ **Logging**: Use `structlog` com padrão `domain.action.result`

### Áreas que Precisam de Ajuda

- 🐛 **Correção de bugs** listados em [KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)
- 📝 **Documentação**: Tradução, tutoriais, exemplos
- 🧪 **Testes**: Aumentar cobertura para 70%+
- 🎨 **UI/UX**: Melhorias na interface gráfica
- 🚀 **Performance**: Otimizações de processamento
- 🔌 **Plugins**: Novos detectores ou exportadores

Consulte o [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) para diretrizes completas.

## 📊 Casos de Uso

### Pesquisa Acadêmica

- **Farmacologia**: Screening de drogas (canabidiol, antidepressivos)
- **Toxicologia**: Testes de toxicidade ambiental
- **Neurociência**: Estudos de ansiedade e memória
- **Genética**: Análise de mutantes e transgênicos

### Publicações Científicas

Este software foi desenvolvido para suportar pesquisas científicas com zebrafish. Se você usar o ZebTrack-AI em suas publicações, por favor cite:

```
Santos, M. (2025). ZebTrack-AI: Automated Behavioral Tracking and Analysis
Platform for Danio rerio. GitHub repository.
https://github.com/MarkSant/ZebTrack-AI
```

## 📄 Licença

Este projeto está licenciado sob a **MIT License** - veja o arquivo [LICENSE](LICENSE) para detalhes.

**Em resumo**, você pode:
- ✅ Usar comercialmente
- ✅ Modificar
- ✅ Distribuir
- ✅ Uso privado

**Condições**:
- 📋 Manter a licença e copyright
- ⚠️ Sem garantias

## 🙏 Agradecimentos

### Instituições

- **UNESP** - Universidade Estadual Paulista
- **Laboratório de Pesquisa de Canabidiol**

### Tecnologias Open Source

- [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) - Detecção de objetos
- [OpenVINO](https://github.com/openvinotoolkit/openvino) - Aceleração de inferência
- [BYTETracker](https://github.com/ifzhang/ByteTrack) - Rastreamento multi-objeto
- [Tkinter](https://docs.python.org/3/library/tkinter.html) - Interface gráfica
- [Poetry](https://python-poetry.org/) - Gerenciamento de dependências
- [Pydantic](https://pydantic.dev/) - Validação de dados
- [structlog](https://www.structlog.org/) - Logging estruturado

### Comunidade

Agradecimentos especiais a todos os contribuidores e à comunidade open source que tornou este projeto possível.

---

<div align="center">

**Desenvolvido com ❤️ para pesquisa científica**

**UNESP - Laboratório de Pesquisa de Canabidiol**

[⬆ Voltar ao topo](#zebtrack-ai)

</div>
