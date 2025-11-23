# ZebTrack-AI

**Software de Rastreamento e Análise Comportamental para Danio rerio (Zebrafish)**

![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Event--Driven-green.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-yellow.svg)
![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)

O **ZebTrack-AI** é uma plataforma avançada de visão computacional projetada para automatizar a análise de comportamento de peixes *Danio rerio* em experimentos científicos. Ele combina detecção baseada em Deep Learning (YOLO/OpenVINO) com uma interface gráfica robusta e modular.

## 🚀 Novidades na Versão 4.0

*   **Arquitetura Event-Driven:** Totalmente refatorado para eliminar acoplamento, garantindo maior estabilidade e facilidade de manutenção.
*   **Interface Otimizada:** Nova aba unificada de "Processamento e Relatórios" para fluxo de trabalho simplificado.
*   **Performance:** Redução significativa no uso de memória e CPU durante a renderização da interface.
*   **Confiabilidade:** Eliminação de condições de corrida (race conditions) e melhor tratamento de erros.

## 🛠️ Instalação

1.  **Pré-requisitos:** Python 3.11 ou superior e Poetry instalado.
2.  Clone o repositório:
    ```bash
    git clone https://github.com/seu-usuario/ZebTrack-AI.git
    cd ZebTrack-AI
    ```
3.  Instale as dependências:
    ```bash
    poetry install
    ```

## ▶️ Execução

Para iniciar a aplicação:

```bash
poetry run zebtrack
```

## 📖 Documentação

A documentação completa está disponível na pasta `docs/`:

*   [Arquitetura do Sistema](docs/ARCHITECTURE.md): Detalhes técnicos sobre o design Event-Driven e Mediator.
*   [Guia do Desenvolvedor](docs/DEVELOPER_GUIDE.md): Como contribuir e estender o sistema.
*   [Guia de Eventos](docs/EVENT_BUS_GUIDE.md): Como utilizar o barramento de eventos.
*   [API Reference](docs/API_STABILITY.md): Contrato da API pública.

## 🧪 Recursos Científicos

*   **Rastreamento Preciso:** Algoritmos de filtragem para suavizar trajetórias (Savgol filter).
*   **Métricas Comportamentais:** Cálculo automático de velocidade, distância, tempo na zona (center/periphery) e imobilidade.
*   **Reprodutibilidade:** Configurações de análise salvas com os dados (arquivos Parquet e YAML).
*   **Exportação:** Relatórios em Excel e Word prontos para publicação.

## 🏗️ Estrutura do Projeto

```
src/zebtrack/
├── core/           # Lógica de negócios (Detecção, Análise)
├── io/             # Entrada/Saída (Câmera, Arquivos)
├── ui/             # Interface Gráfica (Tkinter)
│   ├── components/ # Gerenciadores (Canvas, Dialogs, Project)
│   ├── ui_coordinator.py # Mediator
│   └── gui.py      # Entry point
└── utils/          # Utilitários matemáticos e geométricos
```

## 🤝 Contribuição

Contribuições são bem-vindas! Consulte o `docs/DEVELOPER_GUIDE.md` para diretrizes de estilo e testes.

---
**Desenvolvido para:** Pesquisa de Canabidiol - UNESP