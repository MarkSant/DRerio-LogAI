# Guia Geral de Métricas e Parâmetros de Análise

Este documento fornece uma explicação detalhada de todos os itens exportados nos relatórios (Excel e Word) do ZebTrack-AI, incluindo métodos de cálculo, parâmetros associados e sua configurabilidade.

---

## 1. Métricas de Locomoção (Geral)

| Item no Excel | Descrição | Forma de Cálculo | Parâmetros Associados | Configurável? |
| :--- | :--- | :--- | :--- | :--- |
| **Total Distance (cm)** | Distância total percorrida. | Soma das distâncias euclidianas entre frames consecutivos da trajetória suavizada. Gaps longos são ignorados. | FPS, Calibração (px/cm) | Sim (Setup) |
| **Mean Speed (cm/s)** | Velocidade média. | Média aritmética da magnitude da velocidade instantânea (v = Δd / Δt). | FPS, Calibração, Suavização | Sim (Setup) |
| **Median Speed (cm/s)** | Velocidade mediana. | Valor central da distribuição de velocidades, robusto a ruídos. | - | Não |
| **Max Speed (cm/s)** | Velocidade máxima. | Maior valor de velocidade instantânea registrado. | - | Não |
| **Speed Std Dev (cm/s)** | Desvio padrão da velocidade. | Variabilidade da velocidade ao longo do teste. | - | Não |

---

## 2. Métricas de Mudança de Direção e Explosão (Bursts)

| Item no Excel | Descrição | Forma de Cálculo | Parâmetros e Valores Padrão | Configurável? |
| :--- | :--- | :--- | :--- | :--- |
| **Sharp Turns (count)** | Contagem de curvas acentuadas. | Numero de vezes que a velocidade angular (deg/s) excedeu o limiar. | **Threshold:** 45.0 a 90.0 °/s (padrão 90); **Cooldown:** 0.5s | Sim (`config.yaml`) |
| **Sharp Turns (per min)** | Taxa de curvas por minuto. | `Count / (Duração Total / 60)`. | - | Não |
| **Speed Bursts (count)** | Episódios de alta velocidade ("arrancadas"). | Episódios onde a velocidade excedeu o limiar por pelo menos o tempo mínimo. | **Threshold:** Quantil 90% (dinâmico) ou fixo; **Duração Mín:** 0.5s | Sim (Código/Config) |
| **Speed Bursts Duration (s)**| Duração total das arrancadas. | Soma das durações de todos os episódios de Speed Burst. | - | Não |
| **Speed Burst Threshold (cm/s)** | Valor de corte para arrancada. | Valor calculado (via quantil 90%) ou definido pelo usuário. | **Padrão:** Dinâmico (Quantil 0.9) | Não (Interface) |

---

## 3. Métricas de Inatividade e Freezing

| Item no Excel | Descrição | Forma de Cálculo | Parâmetros e Valores Padrão | Configurável? |
| :--- | :--- | :--- | :--- | :--- |
| **Inactivity Periods (count)** | Contagem de períodos inativos. | Episódios com velocidade abaixo do limiar de inatividade. | **Threshold:** 1.0 cm/s; **Duração Mín:** 1.0s | Sim (Código) |
| **Inactivity Duration (s)** | Tempo total inativo. | Soma das durações de inatividade. | - | Não |
| **Inactivity (% of time)** | Porcentagem de inatividade. | `(Inactivity Duration / Total Time) * 100`. | - | Não |
| **Freezing Time (s)** | Tempo total em freezing. | Similar à inatividade, mas focado em imobilidade comportamental (congelamento). | **Threshold:** 1.5 cm/s; **Duração Mín:** 1.0s | Sim (Wizard/UI) |
| **Freezing Episodes** | Contagem de freezing. | Numero de episódios validados de freezing. | - | Sim (Wizard/UI) |

---

## 4. Métricas de Qualidade e Validação (`Val:`)

| Item no Excel | Descrição | Forma de Cálculo | Explicação | Configurável? |
| :--- | :--- | :--- | :--- | :--- |
| **Val: Total Frames** | Total de frames processados. | Contagem de linhas no DataFrame de trajetória. | Indica o volume de dados coletados. | Não |
| **Val: Unique Tracks** | IDs únicos de rastreio. | Número de `track_id` distintos encontrados. | Deve ser 1 para vídeos de animal único. | Não |
| **Val: Coverage (%)** | Cobertura temporal. | `Total Frames / Range de Frames * 100`. | Se < 100%, indica que houve frames sem detecção. | Não |
| **frame_range_min / max** | Intervalo de quadros. | O primeiro e o último frame onde o animal foi detectado. | Define o "janelamento" da análise. | Não |
| **frame_range_span** | Amplitude do intervalo. | `Max - Min + 1`. | Duração teórica da detecção. | Não |
| **temporal_gaps_count** | Quantidade de falhas. | Vezes que o contador de quadros saltou (ex: frame 10 -> 20). | Indica oclusões ou falhas de detecção. | Não |
| **temporal_gaps_max_frames** | Maior falha (gaps). | O maior salto consecutivo de frames sem detecção. | Gaps grandes afetam a precisão da distância. | Não |

---

## 5. Métricas de ROI (Regiões de Interesse)

*Para cada ROI (ex: "Braço Aberto"), os itens seguem o padrão:*

| Prefixo/Sufixo | Descrição | Forma de Cálculo | Configurável? |
| :--- | :--- | :--- | :--- |
| **Time in [ROI] (s)** | Tempo na região. | Soma dos quadros dentro da ROI / FPS. | Sim (Desenho ROI) |
| **Time in [ROI] (%)** | Porcentagem de tempo. | `(Time in ROI / Total Time) * 100`. | Sim (Desenho ROI) |
| **Entries in [ROI]** | Frequência de entradas. | Contagem de transiçoes "fora -> dentro" (com filtro de flutter). | Sim (Flutter frames) |
| **Latency to [ROI] (s)** | Latência de entrada. | Tempo decorrido até a primeira entrada confirmada. | Sim (Desenho ROI) |
| **Distance in [ROI] (cm)** | Distância na região. | Distância percorrida apenas enquanto estava dentro da ROI. | Sim (Desenho ROI) |
| **Mean Speed in [ROI]** | Velocidade na região. | Velocidade média apenas durante a permanência na ROI. | Sim (Desenho ROI) |

---

## 6. Parâmetros de Processamento (Ajustáveis)

Estes parâmetros afetam como os dados brutos são interpretados antes do cálculo das métricas acima:

* **Trajectory Smoothing (Savitzky-Golay):**
  * `window_length` (Padrão: 7): Janela de suavização. Janelas maiores removem mais ruído, mas podem "arredondar" curvas reais.
  * `polyorder` (Padrão: 3): Ordem do polinômio de ajuste.
* **ROI Inclusion Rule:**
  * `centroid_in`: Animal dentro se o centro estiver na ROI.
  * `bbox_intersects`: Animal dentro se qualquer parte da caixa envolvente tocar a ROI (Padrão).
* **Flutter Filter:** Evita que pequenas oscilações na borda da ROI sejam contadas como múltiplas entradas. (Padrão: 1-3 frames).

---
> [!IMPORTANT]
> A maioria desses parâmetros pode ser ajustada via arquivo `config.yaml` ou durante a criação do projeto no Wizard (Passo 4 - Behavioral Analysis).
