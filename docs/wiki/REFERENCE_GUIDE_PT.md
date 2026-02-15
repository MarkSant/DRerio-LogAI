# Guia de Referência Operacional do ZebTrack-AI

**Última Atualização:** Dezembro 2025 (v3.2)
**Atualizações Recentes:** Max Speed metric, Geotaxis naming fix, Sequential Multi-Aquarium, Unified Reports improvements

Este guia consolida o conhecimento funcional do ZebTrack-AI para equipes de laboratório, mantenedores de software e auditores científicos. Aqui você encontra o fluxo completo de trabalho, tabelas de variáveis utilizadas nos relatórios, definições matemáticas, integrações com hardware (Arduino) e tutoriais passo a passo.

> **Escopo**: documento complementar ao `README.md`, `docs/explanation/architecture.md`, `docs/guides/developer/wizard.md` e `docs/reference/COORDINATE_SYSTEMS.md`. Sempre que novos comportamentos forem adicionados, atualize este guia junto com os testes automatizados.

---

## 1. Preparação do ambiente

| Etapa                   | Comando (PowerShell)         | Observações                                                      |
| ----------------------- | ---------------------------- | ---------------------------------------------------------------- |
| Instalar dependências   | `poetry install`             | Requer Python 3.12+ e Poetry no `PATH`.                          |
| Entrar no shell virtual | `poetry shell` _(opcional)_  | Alternativamente prefira `poetry run ...` nos exemplos a seguir. |
| Validar instalação      | `poetry run zebtrack --help` | Confirma entry point e dependências GUI.                         |
| Executar o app          | `poetry run zebtrack`        | Inicia a interface Tkinter.                                      |
| Rodar suíte de testes   | `poetry run pytest -q`       | Inclui testes de integração do wizard e da GUI.                  |
| Checagens estáticas     | `poetry run ruff check .`    | Mantém estilo e detecta problemas triviais.                      |

### Pré-requisitos opcionais

- **GPU CUDA**: habilita aceleração dos modelos YOLO nativos com PyTorch.
- **OpenVINO Runtime**: aceleração CPU/GPU para modelos convertidos (`WeightManager` cuida do cache `openvino_model_cache/`).
- **Intel GPU (incluindo plataformas EVO)**: suportadas via OpenVINO com aceleração de hardware.
- **Arduino + relés**: use portas seriais listadas pelo sistema (`COM3`, `COM4`, …). Configure `arduino_port` no wizard ou dialog legado.

#### Detecção Automática de Hardware (v1.8+)

O ZebTrack-AI detecta automaticamente o hardware disponível no startup e seleciona o backend ideal:

1. **Prioridade 1 - NVIDIA CUDA**: Se PyTorch detecta GPU NVIDIA com CUDA, usa backend PyTorch (melhor para GPUs NVIDIA).
2. **Prioridade 2 - OpenVINO com GPU Intel**: Se OpenVINO está instalado e detecta GPU Intel (incluindo EVO), usa OpenVINO com aceleração GPU.
3. **Prioridade 3 - OpenVINO CPU**: Se OpenVINO está disponível mas sem GPU, usa OpenVINO otimizado para CPU.
4. **Fallback - PyTorch CPU**: Se nenhuma das opções acima está disponível, usa PyTorch com CPU.

**Proteção contra modelo não convertido**: Se OpenVINO é recomendado mas o modelo ainda não foi convertido para formato `.xml`, o sistema automaticamente:

- Faz fallback para PyTorch temporariamente
- Exibe aviso na UI: "Recomendado mas modelo não convertido. Use 'Diagnóstico' para converter."
- Registra log de warning: `controller.init.openvino_recommended_but_not_converted`
- Oferece conversão automática ao executar o diagnóstico de pesos

**Log de startup**: A decisão é registrada no log com informações sobre hardware detectado:

```text
controller.init.auto_selected_openvino: reason="Hardware detection recommends OpenVINO and model is converted", cuda_available=False, openvino_available=True, intel_gpu=True
```

ou (quando modelo não convertido):

```text
controller.init.openvino_recommended_but_not_converted: reason="OpenVINO recommended by hardware but model not yet converted, using PyTorch", cuda_available=False, openvino_available=True, intel_gpu=True, active_weight="best_oi.pt"
```

ou (CUDA disponível):

```text
controller.init.auto_selected_pytorch: reason="Hardware detection recommends PyTorch", cuda_available=True
```

**Interface visual**: Na janela principal, seção "Estado do Modelo de Detecção", o hardware detectado é exibido:

- Com GPU: "Hardware: NVIDIA GeForce RTX 3080 (recomendado: PyTorch)"
- Com Intel GPU: "Hardware: Intel GPU (recomendado: OpenVINO)"
- CPU apenas: "Hardware: CPU apenas"

Esta detecção automática também funciona no wizard (Model Selection Step), garantindo que usuários sem NVIDIA GPUs obtenham melhor performance automaticamente.

**Progresso de diagnóstico**: Ao executar diagnóstico/teste de pesos, uma janela modal exibe:

- Barra de progresso frame-by-frame
- Status atual da execução
- Botão de cancelamento
- Log detalhado do processamento

---

## 2. Fluxo operacional completo

1. **Criação ou abertura de projeto**
   - Wizard (`ui/wizard/`) é o fluxo padrão (v1.6+); mantenha `settings.ui_features.use_wizard_for_project_creation = true`.
   - Flag `ui_features.suppress_roi_mismatch_warning` (v2.1+) permite suprimir avisos quando relatórios unificados mesclam vídeos com diferentes configurações de ROI.
   - Dialog legado (`ApplicationGUI.create_project_dialog()`) só deve ser acionado ao desabilitar manualmente a flag para cenários de suporte.
   - O `ProjectManager` persiste metadados em `project_config.json` e snapshot das configurações ativas em `config_snapshot.yaml`.

2. **Seleção de vídeos ou fonte ao vivo**
   - `ProjectManager.scan_input_paths()` identifica vídeos, parquets associados e status de dados prévios.
   - Para fluxos ao vivo, `camera_index` e metadados experimentais são salvos para reutilização.

3. **Configuração de detector e zonas**
   - `AppController.setup_detector()` carrega plugins YOLO/OpenVINO via registro `plugins.DETECTOR_PLUGINS`.
   - `Detector.set_zones()` recebe `ZoneData` (polígono da arena + ROIs) e ajusta para a resolução do vídeo/câmera.
   - Calibração opcional (`core/calibration.py`) calcula homografia e fator pixel/cm.
   - Sistema de templates de ROI permite salvar/importar/aplicar layouts reutilizáveis (`templates/`), com refresh automático do canvas e atualização do detector.
   - Modo de edição de ROIs oferece clamping de vértices e indicadores visuais (handles laranja/círculos) para pontos presos à arena, garantindo desenho válido.

4. **Execução do rastreamento**
   - `AppController._process_videos()` roda em thread dedicada, respeitando `analysis_interval_frames` e `display_interval_frames`.
   - O controlador publica `ProcessingReport` a cada atualização para informar a UI se o modo ativo é multi-animal ou indivíduo único; o overlay bloqueia o seletor de trilhas quando o modo é forçado para single subject.
   - `Recorder` grava MP4 (opcional) e Parquet com colunas ordenadas.
   - Callbacks de progresso trafegam via `root.after(0, ...)` para manter a UI responsiva.

5. **Análises e relatórios**
   - `AnalysisService.run_full_analysis()` coordena `ConcreteBehavioralAnalyzer` e `ROIAnalyzer`.
   - `Reporter` gera DataFrame "tidy" e exporta Excel/CSV/Parquet, além de relatórios Word com gráficos.
   - Resultados são salvos por vídeo dentro de `<video>_results/` com prefixos `1_`, `2_`, `3_`.

6. **Integração opcional com Arduino**
   - `ArduinoManager` abre a serial, escuta eventos e dispara comandos de relé para caixas/arenas.
   - Eventos externos (ex.: sensores) podem iniciar/parar gravações (`event_code == 1` inicia, `0` encerra).

7. **Configuração avançada & overlays aprimorados**
   - Aba "Configuração Avançada" permite editar `config.local.yaml` com validação Pydantic em tempo real, atalhos de reset e tooltips inline.
   - Overlay de análise mostra estatísticas por frame, modo de rastreamento ativo (multi vs. single subject) e status dos perfis/ROI templates aplicados.

---

## 3. Estruturas persistidas e artefatos

### 3.1 `project_config.json`

| Campo                                  | Tipo            | Descrição                                                   | Onde é usado                                 |
| -------------------------------------- | --------------- | ----------------------------------------------------------- | -------------------------------------------- | ------------ |
| `project_name`                         | `str`           | Nome amigável do experimento.                               | UI, relatórios.                              |
| `project_type`                         | `"pre-recorded" | "live"`                                                     | Define se vídeos são carregados ou gravados. | Controlador. |
| `timestamp`                            | `str (ISO)`     | Data de criação do projeto.                                 | Auditoria.                                   |
| `calibration`                          | `dict`          | Número de aquários, dimensões físicas, animais por aquário. | Calibração e ROI.                            |
| `active_weight`                        | `str`           | Peso do modelo YOLO ativo.                                  | Detector.                                    |
| `use_openvino`                         | `bool`          | Força execução com modelo convertido.                       | Detector.                                    |
| `analysis_interval_frames`             | `int`           | Salto de frames para análise.                               | Loop de processamento.                       |
| `display_interval_frames`              | `int`           | Salto de frames para overlay/UI.                            | UI.                                          |
| `use_timed_recording`                  | `bool`          | Se verdadeiro, encerra sessões após `recording_duration_s`. | `Recorder`.                                  |
| `recording_duration_s`                 | `int`           | Duração da gravação cronometrada.                           | Controlador.                                 |
| `use_countdown`/`countdown_duration_s` | `bool`/`int`    | Habilitam contagem regressiva antes de iniciar captura.     | Controlador.                                 |
| `batches`                              | `list[dict]`    | Lotes de vídeos com `sha256` e status.                      | Reprocessamento e auditoria.                 |
| `detection_zones`                      | `dict`          | Arena, ROIs, nomes e cores.                                 | Detector, recorder, análises.                |
| `detector_config`                      | `dict`          | Último estado salvo do plugin (limiar de confiança/NMS).    | UI e persistência.                           |
| `use_arduino` / `arduino_port`         | `bool` / `str`  | Integração com hardware.                                    | `ArduinoManager`.                            |

### 3.2 Artefatos por vídeo (`*_results/`)

| Arquivo                             | Descrição                                   | Observações                                 |
| ----------------------------------- | ------------------------------------------- | ------------------------------------------- |
| `1_ProcessingArea_<video>.parquet`  | Polígono da arena (warped).                 | Ordem dos pontos preservada.                |
| `2_AreasOfInterest_<video>.parquet` | ROIs, pontos ordenados por `point_index`.   | Cores não são salvas (geradas em runtime).  |
| `3_CoordMovimento_<video>.parquet`  | Trajetória com esquema fixo (vide seção 4). | Calibração adiciona colunas `_cm`.          |
| `<video>.mp4`                       | (Opcional) captura com overlays.            | Criado apenas quando `is_video_file=False`. |
| `<video>_summary.xlsx`              | Relatório tabular consolidado.              | Exportado por `Reporter`.                   |
| `<video>_report.docx`               | Relatório Word com gráficos e mapas.        | Usa `matplotlib` + `docx`.                  |
| `<video>_summary.parquet/csv`       | Formatos alternativos se escolhidos.        | Padrão: Excel.                              |

---

## 4. Esquema da trajetória (`3_CoordMovimento_*.parquet`)

Ordem das colunas obrigatórias:

1. `timestamp`
2. `frame`
3. `track_id`
4. `x1`
5. `y1`
6. `x2`
7. `y2`
8. `confidence`

Colunas opcionais (calibração conhecida):

- `x_center_px`, `y_center_px`
- `x_cm`, `y_cm`

Todas as coordenadas gravadas já estão no **espaço warped** (vide `docs/reference/COORDINATE_SYSTEMS.md`), garantindo consistência entre vídeos diferentes.

---

## 5. Variáveis de relatório e definições matemáticas

### 5.1 Métricas globais (comportamento geral)

<!-- markdownlint-disable MD060 --> <!-- justification: long math table is more readable without rigid pipe alignment -->
| Variável                                   | Expressão                                                              | Descrição                                                                                     | Fonte                                                   |
| ------------------------------------------ | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `distancia_total_cm`                       | $d_\text{total} = \sum_{i=1}^{n-1} \sqrt{\Delta x_i^2 + \Delta y_i^2}$ | Distância percorrida ao longo da trajetória suavizada.                                        | `ConcreteBehavioralAnalyzer.calculate_total_distance()`     |
| `velocidade_media_cm_s`                    | $\bar v = \frac{1}{n} \sum_{i=1}^{n} v_i$                              | Média da magnitude de velocidade $v_i = \sqrt{v_{x,i}^2 + v_{y,i}^2}$.                        | `ConcreteBehavioralAnalyzer.get_velocity_stats()`           |
| `velocidade_maxima_cm_s`                   | $v_\text{max} = \max\{v_i\}$                                           | Velocidade máxima instantânea (v3.2+). Útil para identificar comportamento de burst swimming. | Idem                                                        |
| `velocidade_mediana_cm_s`                  | Mediana de $\{v_i\}$                                                   | Medida robusta contra outliers de velocidade.                                                 | Idem                                                        |
| `desvio_padrao_velocidade_cm_s`            | $\sigma = \sqrt{\frac{1}{n-1}\sum (v_i - \bar v)^2}$                   | Variabilidade da velocidade.                                                                  | Idem                                                        |
| `contagem_curvas_acentuadas`               | $\omega_i > \theta$                                                   | Número de frames onde a velocidade angular $\omega_i$ excede o limiar ($\theta = 90^\circ/s$). | `ConcreteBehavioralAnalyzer.calculate_sharp_turns()` |
| `curvas_acentuadas_por_minuto`             | $\frac{\text{count}}{\text{duração (min)}}$                            | Frequência de curvas acentuadas por minuto.                                                   | Idem                                                        |
| `rajadas_velocidade_contagem`              | Contagem de episódios $v_i \geq v_\text{lim}$                          | Número de períodos contínuos com velocidade acima do limiar dinâmico/absoluto.                | `ConcreteBehavioralAnalyzer.calculate_speed_bursts()`       |
| `rajadas_velocidade_duracao_total_s`       | $\sum \Delta t_\text{rajada}$                                          | Duração acumulada (s) das rajadas de velocidade.                                              | Idem                                                        |
| `periodos_inatividade_contagem`            | Contagem de episódios $v_i \leq v_\text{lim}$                          | Número de períodos consecutivos abaixo do limiar de inatividade.                              | `ConcreteBehavioralAnalyzer.calculate_inactivity_periods()` |
| `periodos_inatividade_duracao_total_s`     | $\sum \Delta t_\text{inativo}$                                         | Duração acumulada (s) em inatividade.                                                         | Idem                                                        |
| `periodos_inatividade_percentual_registro` | $\frac{\sum \Delta t_\text{inativo}}{t_\text{total}} \times 100$       | Percentual do experimento passado abaixo do limiar de atividade.                              | Idem                                                        |
| `episodios_congelamento`                   | Ver seção 5.3                                                          | Lista de episódios com `start_time`, `end_time`, `duration`.                                  | `ConcreteBehavioralAnalyzer.detect_freezing_episodes()`     |
| `tortuosidade`                             | $T = \frac{d_\text{total}}{\|p_n - p_1\|}$                             | Relação caminho real / linha reta.                                                            | `ConcreteBehavioralAnalyzer.get_tortuosity()`               |
<!-- markdownlint-enable MD060 -->

#### Observações matemáticas

- As trajetórias são suavizadas via filtro Savitzky-Golay com janela adaptativa (`window_length` ímpar até 7, `polyorder` padrão 3).
- O tempo (`timestamp`) é convertido para `TimedeltaIndex`, permitindo integração temporal precisa.
- Gap de tempo maior que `max_time_gap` (quando fornecido) exclui segmentos na distância total.
- A lista completa de episódios de freezing permanece em `report["comportamento_geral"]["episodios_congelamento"]` (fora do DataFrame tidied) para inspeções cronológicas detalhadas.

### 5.2 Métricas por ROI (`ROIAnalyzer`)

| Variável                                | Expressão                                                           | Descrição                                                                 | Fonte                                      |
| --------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------ |
| `tempo_no_<roi>_s`                      | $t_\text{ROI} = \sum_{k \in \mathcal{I}_{roi}} \Delta t_k$          | Soma dos intervalos de tempo em que o animal permaneceu na ROI.           | `ROIAnalyzer.get_time_spent_in_rois()`     |
| `percentual_tempo_no_<roi>`             | $\frac{t_\text{ROI}}{t_\text{total}} \times 100$                    | Percentual do experimento passado na ROI.                                 | Idem                                       |
| `entradas_no_<roi>`                     | $\sum \mathbf{1}[s_{k-1}=0 \land s_k=1]$                            | Número de transições estáveis de fora→dentro.                             | `ROIAnalyzer.get_entry_counts()`           |
| `saidas_do_<roi>`                       | $\sum \mathbf{1}[s_{k-1}=1 \land s_k=0]$                            | Número de transições estáveis de dentro→fora.                             | `ROIAnalyzer.get_exit_counts()`            |
| `latencia_para_<roi>_s`                 | $\min\{t_k - t_0 : s_k = 1\}$                                       | Latência até a primeira entrada confirmada.                               | `ROIAnalyzer.get_latency_to_first_entry()` |
| `distancia_no_<roi>_cm`                 | $\sum_{k \in \mathcal{I}_{roi}} \sqrt{\Delta x_k^2 + \Delta y_k^2}$ | Distância percorrida enquanto o ponto final de cada segmento está na ROI. | `ROIAnalyzer.get_distance_in_rois()`       |
| `velocidade_media_no_<roi>_cm_s`        | Média de $v_i$ condicionada a $s_i = 1$.                            | Velocidade média dentro da ROI.                                           | `ROIAnalyzer.get_velocity_stats_in_rois()` |
| `episodios_congelamento_no_<roi>`       | Contagem de episódios globais cuja posição inicial ocorre na ROI.   | Episódios filtrados por ROI.                                              | `ROIAnalyzer.get_freezing_in_rois()`       |
| `duracao_total_congelamento_no_<roi>_s` | Soma das durações dos episódios associados à ROI.                   | Idem                                                                      | Idem                                       |
| `total_entradas_roi`                    | $\sum_{\text{ROI}} \text{entradas_no_<roi>}$                        | Soma total de entradas em todas as ROIs.                                  | `Reporter` (agregação).                    |

#### Notas sobre estabilidade

- `flutter_n_frames` (padrão 1) filtra oscilações rápidas: entradas/saídas só são confirmadas após N frames consecutivos.
- ROI inclusion rules suportadas (`settings.roi_inclusion_rule`): `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects`, `seg_overlap` (este último exige dados de segmentação e lança erro se indisponível).

### 5.3 Métricas complementares

| Variável                      | Expressão / Regra                                                             | Descrição                                                                          | Fonte                                                   |
| ----------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `episodios_congelamento`      | $v_i \leq v_\text{lim}$ por $\Delta t \geq d_\text{min}$                      | Threshold padrão: velocidade $1.5\ \text{cm/s}$ e duração mínima de $1\ \text{s}$. | `ConcreteBehavioralAnalyzer.detect_freezing_episodes()` |
| `transicoes_entre_rois`       | Tabela de contingência `From` → `To`.                                         | Matriz de transição entre estados estáveis (ROIs + Outside).                       | `ROIAnalyzer.get_roi_transitions()`                     |
| `log_eventos`                 | Sequência ordenada de `enter`/`exit`.                                         | Histórico completo de mudanças de ROI com timestamp.                               | `ROIAnalyzer.get_event_log()`                           |
| `inter_visit_latencies`       | Diferenças $t_{\text{entrada}} - t_{\text{última saída}}$                     | Latências entre visitas consecutivas às ROIs.                                      | `ROIAnalyzer.get_inter_visit_latencies()`               |
| `analyze_center_vs_periphery` | ROI sintética via `buffer` ou `scale`.                                        | Gera métricas separadas para centro/periferia da arena.                            | `ROIAnalyzer.analyze_center_vs_periphery()`             |
| `social_time_seconds` / `%`   | Tempo em que animais compartilham um cluster dinâmico (grafo de proximidade). | Requer `networkx`; usa raio em cm convertido para px.                              | `ROIAnalyzer.analyze_social_proximity()`                |

### 5.4 Métricas de Geotaxis (v3.2+)

Para aquários em vista lateral, o sistema calcula a preferência vertical do animal:

| Variável                    | Descrição                                                        | Fonte                                             |
| --------------------------- | ---------------------------------------------------------------- | ------------------------------------------------- |
| `geotaxis_zona_1_fundo_pct` | Percentual de tempo na zona inferior (0 até altura_zona_1)       | `ConcreteBehavioralAnalyzer.calculate_geotaxis()` |
| `geotaxis_zona_2_pct`       | Percentual de tempo na zona média                                | Idem                                              |
| `geotaxis_zona_N_pct`       | Percentual de tempo na zona superior (N = número total de zonas) | Idem                                              |

#### Configuração

- `geotaxis_num_zones`: Número de divisões horizontais (padrão: 3)
- `aquarium_perspective`: Define a orientação (`top_down` ou `lateral`)

#### Nomenclatura em relatórios

- Internamente: `geotaxis_zone_0_pct`, `geotaxis_zone_1_pct`...
- Exibição: "Geotaxis Zona 1 - Fundo (%)", "Geotaxis Zona 2 (%)"...

### 5.5 Multi-Aquarium Processing (v3.1+)

O sistema suporta processamento de múltiplos aquários por vídeo:

| Modo                  | Descrição                                  | Passagens de Vídeo |
| --------------------- | ------------------------------------------ | ------------------ |
| **Paralelo** (padrão) | Ambos aquários processados simultaneamente | 1                  |
| **Sequencial**        | Cada aquário processado separadamente      | 2                  |

#### Track ID Convention

- `Global ID = aquarium_id * 1000 + local_track_id`
- Aquário 0: IDs 0-999
- Aquário 1: IDs 1000-1999
- Aquário 2: IDs 2000-2999

#### Estrutura de saída

```text
video_results/
├── aquarium_0/
│   ├── 3_CoordMovimento_{video}.parquet
│   ├── 4_Relatorio_{video}_aq0.docx
│   └── {video}_aq0_summary.parquet
└── aquarium_1/
    └── (mesma estrutura)
```

---

## 6. Parâmetros experimentais configuráveis

| Parâmetro                    | Origem                                     | Descrição                                                                                                                 | Impacto                                                                                   |
| ---------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `analysis_interval_frames`   | Projeto / UI                               | Processa 1 frame a cada `N` (default 10).                                                                                 | Reduz custo computacional preservando tendência.                                          |
| `display_interval_frames`    | Projeto / UI                               | Frequência de atualização dos overlays.                                                                                   | Mantém UI fluida em setups modestos.                                                      |
| `use_single_subject_tracker` | Projeto / UI / Config                      | Habilita o rastreador leve para cenários de indivíduo único; pode ser temporariamente ativado por calibração/diagnóstico. | Dispara alternância automática do modo de processamento e bloqueio do seletor de trilhas. |
| `recording_duration_s`       | Projeto / UI                               | Tempo máximo por sessão ao vivo (se `use_timed_recording`).                                                               | Automatiza término alinhado a protocolos éticos.                                          |
| `countdown_duration_s`       | Projeto / UI                               | Delay antes de iniciar gravação.                                                                                          | Permite estabilização de animais/equipamentos.                                            |
| `pixel_per_cm_ratio`         | `Calibration`                              | $(\text{px/cm}_x, \text{px/cm}_y)$ calculado a partir das dimensões físicas.                                              | Usado em todas as conversões de coordenadas.                                              |
| `freezing_vel_threshold`     | `settings.analysis.freezing_vel_threshold` | Limiar absoluto para detectar freezing.                                                                                   | Ajuste sensível a espécie e setup.                                                        |
| `freezing_min_duration`      | Config global                              | Duração mínima em segundos.                                                                                               | Evita falsos positivos por ruído.                                                         |
| `roi_inclusion_rule`         | `settings.roi_inclusion_rule`              | Estratégia de inclusão (centro, buffer, bbox, segmentação).                                                               | Ajuste fundamental para ROIs complexas.                                                   |
| `roi_buffer_radius_value`    | Config global                              | Raio adicional para `centroid_in_on_buffered_roi`.                                                                        | Permite tolerância a jitter de rastreamento.                                              |

---

## 7. Calibração e sistemas de coordenadas (resumo)

1. **Arena & ROIs** são desenhadas no frame original (`gui.py`).
2. `Calibration` calcula homografia para um espaço _warped_ fixo (600 px de largura, altura proporcional).
3. `Recorder.write_detection_data()` aplica `transform_bbox()` → armazena coordenadas já corrigidas.
4. Conversão para centímetros: $x_\text{cm} = \frac{x_\text{warped}}{\text{px/cm}_x}$ e $y_\text{cm} = \frac{(H_\text{warped} - y_\text{warped})}{\text{px/cm}_y}$.

> Consulte `docs/reference/COORDINATE_SYSTEMS.md` para diagramas e exemplos numéricos completos.

---

## 7. Configurações avançadas e validações

| Item                      | Detalhes                                                                                                                                                                                                                                                                                        |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Aba **Config. Avançadas** | Disponível na tela principal do projeto. Centraliza ajustes persistidos em `config.local.yaml` (fps, intervalos de processamento, flush automático, suavização de trajetória e parâmetros padrão de ROI).                                                                                       |
| Validações automáticas    | Antes de salvar, a interface executa o mesmo conjunto de validações Pydantic do backend (ex.: `processing_offset < processing_interval`, `window_length` ímpar, `polyorder < window_length`, `roi_buffer_radius > 0` na regra com buffer). Mensagens de erro exibem detalhes do campo inválido. |
| Persistência              | As alterações são mescladas com `config.local.yaml`, preservando demais campos já existentes. O arquivo é criado automaticamente se ainda não existir.                                                                                                                                          |
| Recarregar valores        | O botão **Recarregar valores atuais** sincroniza o formulário com o estado em disco, útil após editar o YAML manualmente ou trocar de máquina.                                                                                                                                                  |
| Dicas contextuais         | Cada campo inclui micro-help explicando impactos práticos (ex.: flush frequente vs. intervalos altos). As regras de ROI exibem tooltips resumindo as diferenças entre `centroid_in`, buffer e sobreposição de bbox/segmentação.                                                                 |

> **Workflow sugerido**: ajuste apenas os parâmetros globais aceitos pelo tab, salve, valide a mensagem de sucesso e reinicie o app quando alterar FPS ou intervalos críticos. Projetos existentes herdarão as novas configurações na próxima abertura.

---

## 8. Integração com Arduino

| Item              | Detalhes                                                                                                           |
| ----------------- | ------------------------------------------------------------------------------------------------------------------ |
| Porta serial      | Configurada em `arduino_port` dentro do wizard ou dialog legado (`COMx` no Windows).                               |
| Baud rate         | `settings.arduino.baud_rate` (padrão 9600).                                                                        |
| Handshake         | `Arduino.connect()` espera string `"Arduino is ready."` após abrir a porta.                                        |
| Envio de comandos | `ArduinoManager.send_command(<numero_canal>)` envia inteiro + `\n`; aguarda resposta `OK`.                         |
| Mapeamento padrão | `_get_box_number(day, group, cobaia)` converte identificador da cobaia para inteiro. Personalize se necessário.    |
| Eventos recebidos | `1` inicia gravação (quando aguarda trigger externo), `0` solicita parada, demais valores são logados.             |
| Threads           | Um thread daemon lê a serial continuamente (`_reader_loop`). Falhas fecham a conexão com mensagens na aba Arduino. |
| Logs UI           | Chamadas a `controller.log_arduino_event()` alimentam console dedicado na interface.                               |

### Boas práticas

- Teste a comunicação com `python -m zebtrack.io.arduino` (script de diagnóstico incluído).
- Habilite `use_arduino` somente quando a porta correta estiver disponível para evitar falhas de conexão.
- Utilize relés numerados para manter coerência com `box_number` derivado da cobaia.

---

## 9. Tutoriais passo a passo

### Tutorial A — Projeto com vídeos pré-gravados

1. Execute `poetry run zebtrack`.
2. O wizard abrirá automaticamente (mantendo `ui_features.use_wizard_for_project_creation = true`). Use o diálogo legado apenas se tiver desabilitado a flag manualmente.
3. Informe nome, pasta de saída e dimensões físicas do aquário.
4. Selecione os vídeos (`.mp4/.avi/.mov`) e confirme.
5. Desenhe arena e ROIs (ou importe parquets detectados automaticamente).
6. Escolha o detector (YOLO padrão ou OpenVINO, conforme pesos instalados).
7. Ajuste `analysis_interval_frames` e `display_interval_frames` se necessário.
8. Inicie a análise. Acompanhe o overlay e o painel de progresso.
9. Abra `<video>_results/` para acessar parquets e relatórios.

### Tutorial B — Reprocessando resultados existentes

1. Abra o projeto desejado.
2. Clique em **Adicionar & Processar vídeos**.
3. Selecione a pasta com vídeos já analisados. O `ProjectManager` exibirá se existem parquets prévios.
4. Escolha _Reprocessar_ ou _Ignorar_ para cada vídeo (overlay exibe resumo).
5. Finalize para gerar novos relatórios mantendo histórico de batches.

### Tutorial C — Sessões ao vivo com Arduino

1. Configure `use_arduino=true` e a porta (`COMx`) no diálogo de projeto.
2. Conecte o Arduino e verifique que o indicador na UI mostra "Conectado".
3. Defina `use_timed_recording` ou `use_countdown` conforme o protocolo.
4. Posicione os animais, aguarde o _countdown_ (se habilitado) e pressione **Iniciar** ou use um trigger externo (`event_code=1`).
5. Ao final automático ou manual (`event_code=0`), a sessão gera um lote com todos os artefatos.

### Tutorial D — Importando arenas/ROIs de parquets

1. No wizard, habilite a opção **Reaproveitar zonas de parquets existentes**.
2. Escolha a estratégia (`replace` ou `merge`).
3. Confirme o mapeamento de vídeos e ajuste nomes de ROIs, se necessário.
4. Após a criação do projeto, revise as zonas importadas na aba **Configuração de Zonas**.

---

## 10. FAQ rápida

| Pergunta                                                                      | Resposta                                                                                                                                                       |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Posso alterar FPS e intervalos sem editar YAML?**                           | Sim. Use a aba **Config. Avançadas** na tela principal; ela valida os valores e salva em `config.local.yaml`.                                                  |
| **Como ajustar o limiar de freezing?**                                        | Edite `config.local.yaml` → `analysis.freezing_vel_threshold` e `analysis.freezing_min_duration`. Reinicie o app para aplicar.                                 |
| **Posso usar o app sem Arduino?**                                             | Sim. Deixe `use_arduino` desmarcado; o fluxo funciona integralmente offline.                                                                                   |
| **Por que meu relatório não tem colunas `x_cm`/`y_cm`?**                      | A calibração não estava disponível ao gravar o Parquet. Gere uma nova sessão com homografia configurada.                                                       |
| **Como voltar ao diálogo legado?**                                            | Defina `ui_features.use_wizard_for_project_creation: false` em `config.local.yaml` (não recomendado para fluxos padrão).                                       |
| **Como suprimir avisos de ROIs diferentes em relatórios unificados?**         | Defina `ui_features.suppress_roi_mismatch_warning: true` em `config.local.yaml` se você entende as implicações de mesclar dados de vídeos com ROIs diferentes. |
| **O que significa `has_data` na seleção de vídeos?**                          | Indica que já existe `3_CoordMovimento_<video>.parquet` e permite decidir entre reaproveitar ou reprocessar.                                                   |
| **Como adicionar novos detectores?**                                          | Implemente `DetectorPlugin` em `plugins/`, registre em `plugins/__init__.py` e forneça `process_frame()` + `draw_overlay()`.                                   |
| **O que é Max Speed e por que foi adicionado?** (v3.2)                        | `velocidade_maxima_cm_s` representa a velocidade instantânea máxima, útil para identificar comportamento de burst swimming.                                    |
| **Por que os dados de geotaxis estão vazios no relatório unificado?**         | Atualize para v3.2+. Versões anteriores tinham um bug onde `behavioral_config` não era armazenado corretamente no Reporter.                                    |
| **Qual a diferença entre processamento Paralelo e Sequencial multi-aquário?** | Paralelo (padrão) processa ambos aquários em 1 passagem de vídeo. Sequencial processa cada aquário separadamente em 2 passagens, usando menos memória.         |
| **Por que a zona aparece como "Zona 1" em vez de "Zone 0"?**                  | A partir da v3.2, zonas são exibidas com nomenclatura 1-indexada para usuários ("Zona 1 - Fundo") enquanto internamente permanecem 0-indexadas.                |

---

## 11. Checklist de inspeção experimental

1. **Integridade de arquivos**: verifique hashes `sha256` em `project_config.json` para cada vídeo.
2. **Consistência de intervalos**: confirme que `analysis_interval_frames` e `display_interval_frames` refletem as condições do protocolo.
3. **ROI coverage**: garanta que nenhuma ROI extrapole a arena após a homografia (revise na aba de zonas).
4. **Verificação dos relatórios**: abra o Excel e valide se todas as abas (`Resumo`, `ROI`, `Eventos`) foram preenchidas.
5. **Logs de hardware**: revise o console de Arduino para confirmar comandos enviados/recebidos.
6. **Testes automatizados**: execute `poetry run pytest tests/test_analysis_view_toggle.py tests/test_interval_frames_config.py` após modificar fluxos principais.

---

## 12. Arquivos com utilidade reduzida (avaliar remoção)

| Caminho                                     | Observação                                                                                      | Ação sugerida                                                                       |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `src/zebtrack/analysis/analysis_service.py` | Serviço que instancia `ConcreteBehavioralAnalyzer` e `ROIAnalyzer`, retornando relatório coeso. | Extensões devem conectar novas métricas aqui para aparecerem em relatórios.         |
| `MagicMock/ProjectManager().project_path/`  | Pasta gerada por inspeções anteriores contendo dados fictícios (`*_results` sintéticos).        | Avaliar se ainda é necessária; mover para `tests/manual/` ou arquivar externamente. |
| `debug/` scripts                            | Úteis apenas para diagnóstico pontual.                                                          | Documentar uso em `docs/notes/` ou remover se permanecerem obsoletos.               |

> Atualize esta lista quando novos componentes forem descontinuados ou substituídos.

---

### Referências cruzadas

- `README.md` - Visão geral e guia rápido.
- `docs/explanation/architecture.md` - Diagrama de componentes e decisões.
- `docs/guides/developer/wizard.md` - Passo a passo detalhado da criação de projetos e processamento em lote.
- `docs/reference/COORDINATE_SYSTEMS.md` - Detalhes matemáticos das transformações espaciais.

Mantenha este guia sincronizado com os módulos de código e a suíte de testes para garantir rastreabilidade científica completa.
