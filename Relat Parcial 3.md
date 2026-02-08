# EFEITO DO CANABIDIOL SOBRE ESTRESSE E MEMÓRIA AVERSIVA APÓS ESTRESSE AGUDO E INTENSO EM ZEBRAFISH

## Terceiro relatório parcial

Projeto de Iniciação Científica em graduação em

Medicina da Universidade Estadual Paulista do

campus de Botucatu – FMB/UNESP

**Bolsista:** Marco Antônio Sant’ Ana Camargos

**Orientadora:** Profª. Drª. Percília Cardoso Giaquinto

**Processo:** 2023/14200-3

**Vigência:** 01/03/2024 à 28/02/2026

**Período do Relatório:** 01/03/2025 à 28/02/2026

Botucatu, São Paulo

2026

Processo FAPESP nº 2023/14200-3

---

## Sumário

1. Resumo do projeto proposto
2. Resumo das realizações durante o período referente a este relatório
3. Adequações e aperfeiçoamentos
   3.1 Consolidação do aparato automatizado (estressores + testes comportamentais)
   3.2 Aprimoramento da Inteligência Artificial (dataset, treinamento e validação)
   3.3 Softwares de controle, rastreamento e processamento (ZebTrack-AI e ZebTrack)
   3.4 Evolução do desenvolvimento do programa (funções e inovações)
4. Execução e coleta de dados
   4.1 Validação do modelo de TEPT (Artigo I)
   4.2 Tratamento com Cannabis Full Spectrum (Artigo II)
5. Processamento e análise de dados
   5.1 Pipeline de dados (vídeo → rastreio por IA → variáveis → estatística)
   5.2 Evolução metodológica da análise estatística em R (ciclo 2025)
   5.3 Principais resultados consolidados (TEPT e Cannabis Full Spectrum)
6. Pedido para prorrogação excepcional de vigência (12 meses) – justificativas
7. Plano de atividades e cronograma para 12 meses adicionais
8. Referências
9. Anexos

---

## 1. Resumo do projeto proposto

O estresse é um problema global com impacto negativo na saúde e bem-estar. O canabidiol (CBD)
tem demonstrado propriedades antagonistas ao estresse e à inflamação. Este projeto de pesquisa
visa investigar os efeitos do CBD sobre o estresse e a memória aversiva em zebrafish (*Danio
rerio*), um modelo animal promissor devido ao seu baixo custo, facilidade de manejo, rápida
reprodução e elevada homologia genética com humanos.

Utiliza-se um modelo de estresse agudo (um único dia), no qual os peixes são expostos a
estressores físicos intensos combinados com uma pista visual (cor vermelha), posteriormente
reapresentada durante testes comportamentais para evocar a memória aversiva. A proposta é
emular um evento traumático único e intenso, capaz de induzir um fenótipo comportamental
duradouro, incluindo evitação de gatilhos e possíveis sinais de generalização do medo.

Ao longo do projeto, verificou-se que a hipótese experimental exigia uma plataforma de
monitoramento em tempo real e de alta precisão. Por isso, além dos protocolos biológicos,
foram desenvolvidos softwares de controle e rastreamento por inteligência artificial (YOLO),
integrados a microcontroladores (Arduino) para controle de estímulos (LEDs RGB) e geração
automática de logs e relatórios, reduzindo variáveis humanas e aumentando a reprodutibilidade.

O projeto se organiza em dois eixos integrados:

1) Validar e caracterizar o modelo de trauma (TEPT) em zebrafish, com monitoramento diário
por 7 dias.

2) Avaliar o potencial terapêutico de extratos de *Cannabis* ricos em CBD (ex.: Full Spectrum),
investigando se modulam a expressão comportamental do trauma.

---

## 2. Resumo das realizações durante o período referente a este relatório

No período ao qual se refere este relatório, foram consolidadas entregas experimentais e
tecnológicas que permitiram completar a coleta e a análise comportamental de duas frentes
centrais do projeto (em formato de manuscritos em elaboração):

1) **Artigo I (Validação do modelo de TEPT):** execução do protocolo estressor e monitoramento
comportamental automatizado por 7 dias, demonstrando um fenótipo persistente (redução de
atividade locomotora, aumento de *freezing*), formação de memória aversiva (evitação
progressiva do vermelho) e evidências consistentes com generalização do medo (alterações
em área neutra – azul).

2) **Artigo II (Cannabis Full Spectrum / equivalente a 10 mg/kg/dia de CBD):** execução de
tratamento crônico por 7 dias em animais estressados, com monitoramento diário. Os resultados
indicam reversão progressiva do retardo locomotor induzido pelo trauma e modulação da
estratégia de enfrentamento, com evidências de redução do *freezing* em contexto aversivo,
sem “apagar” a memória do medo.

Paralelamente, houve evolução substancial na infraestrutura de inteligência artificial e pipeline
de dados:

- Ampliação e curadoria do dataset no Roboflow, atingindo **30.940 imagens** (v15), com divisão
**94%/4%/2%** (29.148 treino, 1.192 validação, 600 teste).
- Validação de desempenho do modelo (YOLOv11 object detection, v15) com métricas de
**mAP@50 = 96,5%**, **Precisão = 96,4%**, **Recall = 94,1%**, sustentando rastreio robusto.
- Consolidação de um dataset complementar para segmentação (projeto “ZebraFish Detection 2”)
com **8.034 imagens** e **10.242 anotações**.
- Estruturação de gastos de 2025 vinculados ao ciclo de desenvolvimento/treino, totalizando
**944,41** (com **348,00** em Colab – unidades + Pro), viabilizando iterações rápidas de treino,
validação e ajuste fino.

Além do volume de dados, destaca-se a dimensão operacional do trabalho: para chegar a um
dataset nessa escala, é necessário **anotar manualmente** as imagens, uma a uma, com caixas
delimitadoras (*bounding boxes*) consistentes, corrigindo casos difíceis (reflexos, baixa luz,
oclusão parcial, bolhas/ondulações) e realizando revisões para reduzir erros de rótulo. Esse
processo é uma etapa crítica e intensiva em tempo, pois a qualidade da anotação impacta
diretamente a estabilidade do rastreio e, consequentemente, a validade dos resultados
comportamentais.

---

## 3. Adequações e aperfeiçoamentos

### 3.1 Consolidação do aparato automatizado (estressores + testes comportamentais)

No período, consolidou-se o aparato de testes comportamentais automatizados, composto por:

- Aquário central com quatro câmaras laterais (áreas de interesse), nas quais pistas visuais (LEDs
RGB) são apresentadas de forma controlada.
- Randomização diária das cores (vermelho, azul, verde) nas câmaras laterais, para reduzir
habituação e efeitos de aprendizagem espacial.
- Registro do comportamento com webcam (visão superior) e rastreamento por IA em tempo
real.
- Integração com microcontrolador (Arduino) para acionamento coordenado dos LEDs e,
quando aplicável, módulos de estresse (flash e eletrochoque), conforme o protocolo.

Essas adequações reduziram o tempo manual de análise e aumentaram a confiabilidade na
identificação de entradas/saídas e permanência do animal nas áreas de interesse.

### 3.2 Aprimoramento da Inteligência Artificial (dataset, treinamento e validação)

O rastreio automatizado foi sustentado por um modelo baseado em YOLO (detecção de objetos),
treinado em dataset curado no Roboflow. Os principais marcos verificados no período foram:

- **Escala do dataset:** v15 com **30.940 imagens** totais e *split* **94%/4%/2%**.
- **Pré-processamento e robustez:** *resize* (480×640), equalização e ajustes que visam mitigar
reflexos, ondulações e variações de luz.
- **Desempenho:** YOLOv11 object detection v15 com **mAP@50 = 96,5%**, **Precisão = 96,4%**,
**Recall = 94,1%**, assegurando estabilidade de detecção ao longo de sessões.

Para espelhar a lógica de avaliação adotada ao longo do desenvolvimento (como descrito nos
relatórios anteriores), destaca-se que:

- **Perdas de treinamento/validação (box/cls/dfl):** indicam, respectivamente, qualidade de
localização das caixas, acerto de classificação e refinamento da distribuição de bordas/caixas.
Reduções consistentes ao longo das épocas sugerem aprendizado estável e melhor generalização.
- **Métricas de desempenho (Precisão/Recall/mAP@50):** quantificam o equilíbrio entre falsos
positivos e falsos negativos e o grau de sobreposição entre caixas previstas e reais.

**Comparação numérica (e significado prático para o experimento):**

**Detecção de objetos (ZebraFish Detection – conjunto de validação do Roboflow):**

| Versão do modelo | Tipo (upload/treino) | mAP@50 | Precisão | Recall |
| --- | --- | --- | --- | --- |
| ZebraFish Detection 7 | Roboflow 3.0 Object Detection (Fast) | 93,2% | 94,5% | 88,7% |
| ZebraFish Detection 9 | Roboflow 3.0 Object Detection (Fast) | 91,2% | 93,4% | 86,3% |
| ZebraFish Detection 10 | yolov8s Model Upload | 90,2% | 89,4% | 84,7% |
| ZebraFish Detection 12 | yolov11s Model Upload | 88,6% | 90,6% | 83,1% |
| ZebraFish Detection 13 | yolov8s Model Upload | 89,9% | 90,7% | 85,6% |
| ZebraFish Detection 14 | yolov11s Model Upload | 90,2% | 91,6% | 86,6% |
| ZebraFish Detection 15 | YOLOv11 Object Detection (Accurate), v15 | **96,5%** | **96,4%** | **94,1%** |

**Ganho consolidado (v14 → v15):** mAP@50 **+6,3 p.p.**, Precisão **+4,8 p.p.**, Recall
**+7,5 p.p.**. Em termos práticos, isso representa menos perdas do animal em condições difíceis
(reflexos/ondulação/oclusão) e menos falsos eventos, fortalecendo o uso do rastreio como parte
do método experimental (evento → estímulo → log).

**Segmentação por instância (ZebraFish Detection 2 – conjunto de validação do Roboflow):**

| Versão do modelo | Tipo (upload/treino) | mAP@50 | Precisão | Recall |
| --- | --- | --- | --- | --- |
| ZebraFish Detection 2 1 | YOLOv11 Instance Segmentation (Accurate) | 96,5% | 96,5% | 94,0% |
| ZebraFish Detection 2 2 | yolov11s Model Upload | 97,2% | 97,1% | 94,8% |
| ZebraFish Detection 2 3 | yolov11s-seg Model Upload | 95,8% | 96,1% | 93,9% |
| ZebraFish Detection 2 4 | yolov11s-seg Model Upload | 95,6% | 96,4% | 93,4% |
| ZebraFish Detection 2 5 | yolov11s-seg Model Upload | **97,3%** | **98,0%** | **96,2%** |

Na prática, esses avanços numéricos e de escala significam: (i) menos falsos negativos (animal
“desaparecendo” em reflexo/onda/oclusão), (ii) menos falsos positivos (reflexos e artefatos
contados como “animal”), e (iii) menor variabilidade artificial no registro de entradas/saídas nas
áreas de interesse — elementos essenciais para sustentar comparações longitudinais em 7 dias.

No contexto deste projeto, a IA não foi empregada apenas como um “identificador de peixe”,
mas como uma **camada de instrumentação do experimento**. Ou seja: a rede neural passa a ser
parte do método experimental, pois sustenta (i) o rastreio contínuo e (ii) a detecção de eventos
comportamentais (entrada/saída em áreas de interesse) que podem disparar estímulos e gerar
logs reprodutíveis.

**Trabalho de anotação e curadoria (ponto crítico):**

- Cada imagem utilizada para treino/validação/teste requer anotação manual do animal.
- Em um dataset com **30.940 imagens**, o volume de anotação representa dezenas de milhares
de decisões de rotulagem, com necessidade de padronização (tamanho/posição das caixas,
consistência entre dias e condições de iluminação).
- A curadoria inclui revisões para reduzir: caixas deslocadas, falsos positivos em reflexos,
imagens com o animal fora de foco, e inconsistências que levam a “flickering” (perdas e
re-aquisições do rastreio).

Como parte do amadurecimento do pipeline, também foi mantido um dataset complementar para
**segmentação** (instância), útil para cenários mais complexos e como base para evoluções
futuras (ex.: melhor separação do corpo em baixa resolução e contornos sob oclusão).

Em termos práticos, as métricas elevadas de segmentação são estratégicas porque tendem a
melhorar a robustez em condições de **baixa luminosidade/período noturno**, reflexos e
oclusões, além de servirem como base para futuras funções etológicas mais exigentes (ex.:
identificação individual mais estável e análise de interações sociais).

No eixo financeiro, as despesas de 2025 (anexo) totalizam **944,41**, com foco em:

- **Treino em nuvem (Colab):** 348,00 (unidades + Pro), garantindo ciclos de treinamento
compatíveis com o volume de dados e com a necessidade de validação rápida.
- **Ferramentas de produtividade:** assinaturas e créditos para apoio ao desenvolvimento,
documentação e depuração.

Para evitar ambiguidades, explicita-se que:

- **“Unidades computacionais” (nuvem):** referem-se ao uso de **Colab Pro** e **Colab Computation
   Units** para acesso a hardware acelerado (especialmente GPU) durante treinos/validações,
   permitindo iterar mais rápido em datasets grandes e repetir experimentos de forma controlada.
- **“Créditos adicionais” (ferramentas):** referem-se a gastos por consumo/uso extra em
   ferramentas de apoio ao desenvolvimento e redação técnica — neste projeto, isso inclui
   assinaturas e/ou créditos de uso como **ChatGPT Plus**, **Claude Pro** (e **Claude extra
   usage**) e **GitHub Copilot Usage** — utilizados para acelerar depuração, padronização de
   outputs e escrita/organização de documentação.

**Vínculo entre gastos, produtividade e excelência (ponto de mérito):** o avanço do modelo e do
software não depende apenas de “treinar uma rede”, mas de executar ciclos repetidos de:
curadoria/anotação → treinamento → validação → correções → reprocessamento de dados.
Para um dataset que chegou a dezenas de milhares de imagens e para a necessidade de rodar e
validar o sistema em um experimento longitudinal (7 dias) com hardware integrado, foi crucial
dispor de recursos pagos (assinaturas, créditos e unidades computacionais em nuvem) para
reduzir tempo de treinamento/iteração, manter versões paralelas de pesos (segmentação e
detecção) e viabilizar validações rápidas de trade-offs (ex.: ajuste fino de thresholds/ByteTrack e
alternância CPU/GPU/OpenVINO), evitando gargalos impraticáveis em máquina local.

No contexto de um bolsista no 4º ano de Medicina, com carga acadêmica intensa, esses recursos
foram determinantes para transformar tempo limitado em entregas concretas (melhores métricas,
maior robustez, automação do pipeline e inovação metodológica), preservando a qualidade
científica do projeto e viabilizando a consolidação do ZebTrack-AI como tecnologia publicável.

### 3.3 Softwares de controle, rastreamento e processamento (ZebTrack-AI e ZebTrack)

Para garantir reprodutibilidade, rastreio consistente e geração automática de variáveis, o período
foi marcado pela integração prática entre:

1) **Software customizado em Python para orquestração experimental e rastreamento por IA
(ZebTrack-AI):**

- Captura do vídeo em tempo real (webcam) e sincronização com sessão experimental.
- Inferência por IA (YOLO) para localizar o animal e registrar caixa delimitadora (*bounding box*).
- Registro periódico das coordenadas do animal e da confiança da detecção, com timestamps.
- Armazenamento organizado por sessão/animal e geração de arquivos de referência (aquário
e áreas de interesse).
- Integração com microcontrolador para acionar LEDs RGB conforme entrada/saída em áreas.
- Produção de logs e estrutura de saída padronizada para análise estatística posterior.

Além dos itens acima, o desenvolvimento do software envolveu um conjunto de funções e
inovações práticas (com impacto direto na rotina do laboratório) que viabilizam a execução
contínua de experimentos, minimizando intervenção manual e reduzindo fontes de erro:

- **Padronização e rastreabilidade do dado:** organização automática de pastas por sessão,
animal e dia; nomes consistentes; associação explícita entre vídeo, logs e parâmetros.
- **Definição e persistência das áreas de interesse (AOIs):** arquivos contendo coordenadas do
aquário e das quatro câmaras laterais; possibilidade de reaproveitar configurações entre dias.
- **Detecção de eventos a partir da IA:** identificação de entrada/saída em AOIs e registro do
timestamp correspondente, permitindo reconstruir a sequência comportamental sem inspeção
manual de frames.
- **Integração robusta com hardware:** envio de comandos seriais para o Arduino de forma
controlada (acender/apagar LEDs RGB por câmara), sincronizando estímulo e comportamento.
- **Controle de qualidade do rastreio:** uso do grau de confiança do modelo para registrar
incertezas; redução de “saltos” e perdas de detecção; mitigação de artefatos visuais.
- **Reprodutibilidade experimental:** o mesmo pipeline (câmera → IA → evento → log) é aplicado
diariamente, aumentando comparabilidade longitudinal.

#### 3.3.1 Controle fino e parametrização via interface (UI)

Um diferencial central do ZebTrack-AI (frente a soluções “caixa-preta” com poucos ajustes
expostos) é a ênfase em **controle fino e transparência metodológica**: a interface do programa
expõe parâmetros críticos do rastreio, do processamento e das variáveis comportamentais, com
**explicações em linguagem natural (help labels/tooltips)** e **validações automáticas**. Isso
permite calibrar o método às condições reais do laboratório (vídeos longos, reflexos, variabilidade
de iluminação, instabilidade inicial da água), reduzindo variância de operador e aumentando
reprodutibilidade.

Em termos práticos, foram implementados e consolidados na UI:

- **Editor de Configurações Avançadas dentro do app:** permite ajustar parâmetros do `config.yaml`
sem edição manual; as alterações são persistidas em `config.local.yaml` e recarregadas
automaticamente, garantindo padronização entre sessões e rastreabilidade das escolhas.
- **Processamento de vídeo (performance × resolução temporal):** FPS de saída do MP4, intervalo de
processamento (processar 1 frame a cada N frames), intervalo de exibição (atualização da UI a cada
N frames processados) e *offset* inicial (ignorar os primeiros frames para descartar estabilização do
aquário ou interferências do experimentador).
- **Suavização de trajetória (qualidade de métricas):** parâmetros do filtro Savitzky–Golay
(tamanho da janela e ordem do polinômio), com orientação de trade-offs entre remoção de tremor e
preservação de movimentos bruscos, visando métricas de distância/velocidade mais robustas.
- **Gravação e segurança do dado (Recorder):** parâmetros de *flush* automático (por tempo) e
limite de linhas em memória (por volume), equilibrando proteção contra perda de dados e custo de I/O.
- **Lógica de inclusão em AOIs/ROIs (critério “dentro/fora” da zona):** regra de inclusão selecionável
(centroide, centroide com buffer, intersecção da *bounding box* e sobreposição por segmentação), com
parâmetros associados (raio de buffer e fração mínima de sobreposição), além da distinção explícita
entre **padrões globais** e ajustes **por projeto** na aba de zonas.
- **Padrões de análise comportamental (thigmotaxis/geotaxis):** seleção da perspectiva do aquário
(top-down vs lateral), limiares em cm para thigmotaxis e geotaxis, habilitação condicional de geotaxis
na vista lateral e escolha do modo (por distância vs por zonas verticais), incluindo número de zonas e
quantas zonas inferiores compõem o “fundo”.
- **Wizard guiado com tooltips (redução de erro e padronização):** etapas que documentam e
operacionalizam decisões do experimento (ex.: número de dias, grupos e animais por grupo; nomes dos
grupos; organização automática de saídas) e decisões do rastreio (ex.: ativação de OpenVINO quando
disponível; uso de ByteTrack; thresholds de detecção YOLO como confiança e NMS; parâmetros de
associação/rastreamento como track threshold, match threshold, buffer, distância máxima e IoU), com
guia rápido e opção de restaurar valores padrão recomendados.

Adicionalmente, a UI aplica **validações ao salvar** (ex.: coerência entre *offset* e intervalos;
restrições do filtro; limites de parâmetros), prevenindo configurações inconsistentes que poderiam
introduzir vieses nas métricas ou dificultar comparações longitudinais.

#### 3.3.2 Assistente de criação de projetos (“Wizard”): automação e padronização ponta-a-ponta

Uma parte substancial do desenvolvimento foi dedicada ao **Wizard de criação de projeto**, que
transforma a configuração (normalmente manual e propensa a erros) em um fluxo guiado, com
resumo final e validações. O Wizard é **dinâmico por tipo de projeto** e acumula as decisões em
um dicionário único de configuração (incluindo versão de esquema), garantindo rastreabilidade.

**Fluxos suportados (seleção automática de etapas):**

- **Pré-gravado (experimental ou exploratório):** Discovery → Seleção de Vídeos → Calibração
Física → Detecção/Validação de Design → Seleção de Modelo/Pesos/Parâmetros → Configuração
de Importação → Confirmação.
- **Ao vivo:** Discovery → Design Experimental → Configuração Ao Vivo (câmera/Arduino) →
Calibração Física → Seleção de Modelo/Pesos/Parâmetros → Confirmação.

**Etapas e decisões operacionalizadas (com tooltips e validações):**

- **Discovery (contexto inicial):** define tipo de projeto (experimental/exploratório/ao vivo),
significado de estrutura de pastas (quando aplicável) e escopo de importação de parquets
existentes (somente arena vs zonas vs tudo). Permite **carregar templates** para padronizar
configurações entre experimentos.
- **Seleção de Vídeos (pré-gravado):** adiciona arquivos individuais e/ou pastas inteiras; a
varredura é recursiva e o Wizard fornece **resumo de seleção** e **pré-visualização da estrutura**
(com limites de profundidade e número de nós para manter a UI responsiva).
- **Design Experimental (ao vivo):** parametriza **número de grupos, dias e sujeitos por grupo** e
nomes de grupos, gerando estrutura coerente para organização de saídas e para a grade visual de
progresso do experimento.
- **Configuração Ao Vivo (ao vivo):** detecta câmeras, mapeia nome exibido → índice de câmera,
configura gravação (tempo total, contagem regressiva), intervalos de processamento/exibição e
opcionalmente habilita **Arduino** (detecção de portas, teste de conexão, modo de gatilho externo),
além de metadados de sessão (grupo/dia/sujeito) e recomendações baseadas em capacidade de
hardware.
- **Calibração Física (todos os modos):** define dimensões reais da arena (cm) para conversão
pixel→cm, número de aquários (vídeos) e número de animais por aquário, além de intervalos de
análise/exibição. A etapa incorpora um widget de **configuração comportamental** (parâmetros
relacionados a thigmotaxis/geotaxis e interpretação espacial) dentro do fluxo do projeto.
- **Detecção/Validação de Design (pré-gravado):** realiza varredura de caminhos de entrada,
**detecta automaticamente o design experimental** a partir da estrutura de pastas (com
pontuação de confiança), permite ajustar padrões via **regex customizada**, abrir um **editor de
design** para confirmação e sumariza a presença de arquivos parquet (arena/ROIs/trajetória).
- **Configuração de Importação (pré-gravado):** apresenta tabela por vídeo para escolher o que
importar (arena/ROIs/trajetória), aplica *defaults* inteligentes conforme as escolhas iniciais e
permite operações em lote (importar tudo/arenas/ROIs/trajetórias), incluindo estratégia de merge
de ROIs (replace/merge/manual).
- **Seleção de Modelo/Pesos/Parâmetros (todos os modos):** separa a estratégia por tarefa
(aquário vs animal), escolhendo **método** (segmentação vs detecção), **peso** (catálogo), uso de
**OpenVINO** (quando recomendado) e parâmetros de inferência/rastreamento (confiança, NMS,
ativação e parâmetros do ByteTrack, com opção de restaurar padrões recomendados).
- **Confirmação (todos os modos):** gera um **resumo completo** das escolhas, permite editar
nome e localização do projeto, aplica validações e possibilita **salvar as configurações como
template** para reuso.

Na prática, esse Wizard reduz variabilidade de operador e concentra a intervenção humana em
decisões metodológicas verificáveis (design, calibração, modelo/pesos e regras de zonas), em vez
de procedimentos repetitivos e pouco auditáveis.

#### 3.3.3 Janela do projeto: modos (pré-gravado × ao vivo) e cobertura completa das abas

Após a criação, o projeto é operado em uma janela principal com **abas (Notebook)**. O conjunto
de abas é consistente entre modos, com componentes específicos quando o projeto é “ao vivo”.
Esse desenho foi deliberado para sustentar duas necessidades: (i) execução em tempo real e (ii)
processamento reprodutível em lote para vídeos pré-gravados.

**Aba “Controle Principal”:**

- **Botões por tipo de projeto:** **Ao vivo:** iniciar/parar gravação, com estado
habilitado/desabilitado conforme a sessão. **Pré-gravado:** adicionar e processar novos
vídeos/pastas, iniciando pipeline de análise.
- **Fechar projeto (sempre presente):** finaliza o contexto e evita mistura de saídas.
- **Painel de overview do projeto:** árvore hierárquica (grupo/dia/sujeito/vídeo) e cartões de
status para acompanhar o estado (ex.: arena/ROIs/trajetória/resumo) sem abrir arquivos.
- **Estado do modelo:** exibe peso ativo e estado de OpenVINO (quando aplicável) e dá acesso a
janelas de calibração global e de preferências específicas do projeto.
- **Componentes adicionais em projetos ao vivo:** aviso de gatilho externo (quando habilitado) e
**dashboard do Arduino** (estado de conexão, comandos e rechecagem de portas), integrando
hardware à execução do experimento.

**Aba “Configuração de Zonas”:**

- Organização em dois painéis (controles + visualização), com **lista e edição de zonas** e
visualização do vídeo; suporte a seleção de vídeo e carregamento do frame de referência.
- Ferramentas de desenho (polígono para arena e ROIs), desfazer/refazer e menu de contexto.
- Parâmetros de estabilização (ignorar frames iniciais) e regras de inclusão em ROIs (centroide,
intersecção de *bbox*, sobreposição por segmentação), com parâmetros associados.
- Mecanismos para reutilização (templates) e para cenários com múltiplos aquários/partições
(detecção/edição de regiões por aquário quando aplicável).

**Aba “Análise de Vídeo”:**

- Exibe metadados e controles de acompanhamento da análise, incluindo seletor de
**track_id** (todos ou IDs específicos) e ações de cancelamento/controle do fluxo.

**Aba “Processamento e Relatórios”:**

- Consolida ações de processamento e geração de artefatos em um único local: gerar
trajetórias, exportar sumários, gerar relatórios parciais e relatório unificado.
- Tabela/árvore de status por vídeo, evidenciando a existência/ausência de arena, ROIs,
trajetória e sumários; suporta abrir artefatos por duplo clique.

**Aba “Config. Avançadas”:**

- Editor dentro do app para ajustes de parâmetros avançados; ações de salvar/resetar e
sincronização por eventos, mantendo rastreabilidade via `config.local.yaml` e reduzindo erros de
edição manual.

**Aba “Progresso do Experimento” (ao vivo):**

- Grade visual para acompanhar sessões/itens do desenho experimental e um mecanismo de
atualização da grade, auxiliando a execução longitudinal e o controle de completude.

Esse conjunto de abas foi desenvolvido para cobrir toda a cadeia operacional: criar projeto,
calibrar arena, definir zonas, executar (ou processar) vídeos, acompanhar qualidade do rastreio e
emitir relatórios sem etapas externas.

#### 3.3.4 Gestão de pesos e reprodutibilidade: catálogo, padrões por tipo e OpenVINO

Para evitar que o laboratório fique “preso” a um único peso/modelo (e para permitir evolução do
dataset sem reescrever código), foi implementado um **catálogo persistente de pesos**
(`weights_config.json`) com suporte explícito a:

- **Tipos de peso (seg vs det):** classificação por sufixo de arquivo (ex.: `*_seg.pt` para
segmentação e `*_oi.pt` para detecção), com validação de compatibilidade na UI.
- **Padrões independentes por tipo:** existência de um peso padrão para segmentação e outro
para detecção (campos equivalentes a “default_seg” e “default_det”), permitindo manter um
conjunto estável “de referência” e, ao mesmo tempo, testar versões novas sem quebrar o fluxo.
- **Seleção no Wizard por tarefa:** escolha de método e peso separadamente para “aquário” e
“animal”, viabilizando combinações metodologicamente coerentes (ex.: detecção para arena e
segmentação para animais) no mesmo projeto.
- **Conversão e cache OpenVINO:** suporte a exportação/conversão com estados explícitos
(não convertido, convertendo, pronto, falhou) e cache em diretório dedicado, reduzindo custo
computacional quando OpenVINO é preferível ao backend padrão.

Na prática, isso permite manter pesos padrão carregados no ambiente (incluindo pesos
distribuídos com o projeto) e, simultaneamente, habilitar **gestão de pesos customizados**
para experimentos específicos, com rastreabilidade por tipo e sem perder reprodutibilidade.

#### 3.3.5 Detecção (det) vs Segmentação (seg): implicações metodológicas e computacionais

O ZebTrack-AI opera com dois paradigmas de visão computacional que têm consequências diretas
na interpretação comportamental e no custo computacional:

- **Detecção (det):** representa o alvo como *bounding boxes*. É adequada quando o interesse é
localização aproximada e rastreamento com baixo custo, incluindo cenários de animal único em que
o ByteTrack mantém identidade ao longo do tempo.
- **Segmentação (seg):** representa o alvo como máscara/polígono. É adequada quando o interesse
é **precisão espacial** (ocupação de ROIs e bordas) e/ou múltiplos animais no mesmo aquário.

**Impacto direto nas métricas e na lógica de zonas:**

- Em critérios de “dentro/fora” de uma ROI, a detecção tende a depender de centroide e
intersecção de caixa, enquanto a segmentação permite definir inclusão por **fração de sobreposição
da máscara**, reduzindo ambiguidades nas bordas e em ROI pequenas.
- Para métricas espaciais (ex.: thigmotaxis), a segmentação pode oferecer maior fidelidade quando
o animal está parcialmente ocluído, próximo à parede ou quando a iluminação cria contornos
equívocos para caixas.

**Impacto no rastreamento e na estabilidade temporal:**

- O uso de ByteTrack (com parâmetros ajustáveis na UI) é crítico para reduzir trocas de identidade
e perdas de trilha em detecção, principalmente em condições reais com reflexos/bolhas.
- A segmentação tende a ter custo maior, mas pode melhorar separação em multi-animal e reduzir
falsos positivos associados a artefatos de fundo.

**Consequência prática:** a existência de controles explícitos (método/peso/thresholds e
rastreamento) permite alinhar a escolha técnica ao objetivo científico (precisão espacial vs
throughput) e documentar o compromisso metodológico adotado em cada conjunto de dados.

1) **Processamento de variáveis comportamentais a partir dos logs (ZebTrack – Pinheiro da
Silva et al., 2017, com adaptações):**

- Adaptação para receber relatórios de rastreio produzidos por IA.
- Extração automática de um conjunto de variáveis (ex.: distância total, *freezing*, velocidade,
entradas e métricas por cor).
- Implementação de processamento em lote, permitindo analisar sequencialmente múltiplos
animais e produzir relatórios individuais e consolidados sem inspeção frame a frame.

No plano de evolução do software, também se destaca a transição de um modelo “semi-manual”
para um modelo de **automação completa**, no qual o esforço humano migra de “clicar frame a
frame” para (i) calibrar o método, (ii) curar o dataset e (iii) revisar estatísticas e relatórios.
Essa mudança é a principal inovação operacional do período.

### 3.4 Evolução do desenvolvimento do programa (funções e inovações)

Para fins de transparência e para explicitar o ganho incremental ao longo do tempo, sintetiza-se
abaixo a evolução funcional do programa. Esta cronologia não descreve apenas “versões de
software”, mas mudanças de método que impactam diretamente a capacidade do laboratório de
executar, registrar e analisar experimentos com reprodutibilidade.

**Fase 1 – Identificação do gargalo e abandono do legado (início do projeto):**

- Os métodos tradicionais (ex.: subtração de fundo) mostraram-se insuficientes em condições
reais de laboratório (reflexos, bolhas, ondulações, sujeira no acrílico), exigindo correção manual
e tornando a análise inviável em escala.
- O gargalo não era apenas “detectar o animal”, mas **detectar com estabilidade ao longo do
tempo**, pois micro-erros acumulados distorcem métricas longitudinalmente.

**Fase 2 – Introdução da IA como núcleo do rastreio (YOLO) e produção de logs:**

- Implementou-se inferência por IA para localizar o animal em cada trecho do vídeo.
- Foram definidos outputs padronizados (coordenadas, timestamps e confiança), permitindo
que os dados brutos fossem analisáveis sem inspeção frame a frame.
- A confiança do modelo passou a ser registrada como variável de qualidade, útil para
identificar sessões com ruído visual e reduzir falsos eventos.

**Fase 3 – Integração IA → evento → hardware (controle experimental automatizado):**

- A IA deixou de ser apenas “análise posterior” e passou a compor o método experimental:
entrada/saída em áreas de interesse (AOIs) passou a gerar eventos que acionam LEDs RGB,
permitindo uma lógica de pista visual dependente do comportamento do animal.
- Esta integração reduz variabilidade do operador e aumenta precisão temporal do estímulo.

**Fase 4 – Automação do processamento e consolidação do pipeline (alto throughput):**

- O fluxo vídeo → logs → variáveis foi acoplado a processamento em lote, gerando relatórios
individuais e consolidados por dia/animal sem intervenção manual.
- O método passou a incorporar uma camada explícita de **parametrização reprodutível** via UI
(wizard com tooltips + editor de configurações avançadas), permitindo calibrar thresholds, intervalos e
filtros de forma documentada, sem dependência de edição manual de arquivos.
- A rotina do laboratório passou a priorizar: coleta reprodutível, curadoria do dataset e análise
estatística, em vez de tarefas repetitivas de extração manual de métricas.

**Fase 5 – Escalonamento do dataset e amadurecimento do treinamento/validação:**

- A evolução do desempenho (mAP/precisão/recall) acompanhou a expansão do dataset e o
refino de anotações, com revisões para reduzir inconsistências.
- Nesta fase, a anotação manual e a curadoria tornaram-se a principal “força de trabalho” do
sistema: a robustez do rastreio depende diretamente da qualidade da base anotada.

**Fase 6 – Formalização do projeto via Wizard e importação inteligente (redução de erro):**

- O processo de criação de projeto passou a ser guiado e auditável, com etapas explícitas para
seleção de entradas, calibração e validação do design a partir de estrutura de pastas.
- Introduziu-se a capacidade de importar seletivamente arenas/ROIs/trajetórias por vídeo (com
estratégias de merge), facilitando reprocessamentos sem perda de trabalho anterior.

**Fase 7 – Estratégia dual (det vs seg), gestão de pesos e aceleração (OpenVINO):**

- Consolidou-se a separação de método e pesos por tarefa (aquário vs animal) e por tipo
(segmentação vs detecção), com padrões independentes e gestão em catálogo persistente.
- Aceleração por OpenVINO e ajustes finos de rastreamento (ByteTrack) foram incorporados ao
fluxo de projeto, permitindo otimizar estabilidade e performance conforme o hardware.

Em síntese, a inovação do período não foi apenas a adoção de IA, mas a transformação da IA
em um componente central do desenho experimental, com geração de dados padronizados,
reprodutíveis e aptos a modelos estatísticos longitudinais.

Como resultado, a análise comportamental passou a ser executável de maneira sistemática,
reduzindo vieses de avaliação manual e tornando a estatística longitudinal viável em rotina.

---

## 4. Execução e coleta de dados

### 4.1 Validação do modelo de TEPT (Artigo I)

Animais adultos foram divididos em dois grupos experimentais (n=13 por grupo): Controle (GC)
e Estresse (GE). O grupo GE foi submetido ao protocolo de estresse multimodal (60 min)
pareado com a pista visual (vermelho), incluindo:

- Sensibilização tempo-dependente com substância de alarme conspecífica (CAS) e jejum.
- Imobilização (25 min).
- Restrição com exposição parcial ao ar (25 min).
- Alternância hipóxia + choque térmico + estresse luminoso (10 min).
- Eletrochoque (5 s; 3 ± 0,2 V AC).

Após o protocolo, ambos os grupos foram testados diariamente por 7 dias, com gravação de 5
min por animal e rastreamento por IA. Foram gerados logs e variáveis comportamentais por
sessão e por cor.

### 4.2 Tratamento com Cannabis Full Spectrum (Artigo II)

Em um desenho experimental de tratamento em animais estressados, foram utilizados dois
grupos (n=13 por grupo): Grupo Controle Estressado (GCE; sem tratamento) e Grupo Estresse
Tratado (GET; óleo de *Cannabis* Full Spectrum incorporado à dieta, dose equivalente a
10 mg/kg/dia de CBD).

O tratamento foi aplicado de forma crônica durante 7 dias, concomitantemente aos testes
comportamentais diários. O consumo alimentar variável foi registrado como limitação prática,
mas os resultados mostraram efeitos progressivos e consistentes na dimensão locomotora e em
parâmetros da estratégia de enfrentamento.

---

## 5. Processamento e análise de dados

### 5.1 Pipeline de dados (vídeo → rastreio por IA → variáveis → estatística)

O fluxo operacional consolidado no período seguiu as etapas:

1) Gravação (5 min/animal/dia) e rastreio por IA em tempo real.
2) Exportação de logs com coordenadas, timestamps e confiança da detecção.
3) Conversão/extração de variáveis comportamentais gerais e por cor.
4) Análise estatística em R com modelos mistos (LMM/GLMM), adequados a dados
longitudinais e com pontos faltantes.

### 5.2 Evolução metodológica da análise estatística em R (ciclo 2025)

No ciclo de 2025, consolidou-se uma mudança metodológica importante: a análise deixou de ser
um processamento “ad-hoc” de médias e comparações estáticas e passou a ser tratada como um
problema de **séries temporais hierárquicas** (aprendizagem/comportamento ao longo do tempo),
em que cada animal possui trajetória própria. Essa mudança foi decisiva para sustentar a
interpretação neurobiológica e a robustez estatística dos achados.

**(i) Arquitetura de dados (Wide → Long):**

- A estruturação final dos dados em formato *Long* foi motivada pela limitação de estruturas
*Wide* em capturar variância intraindivíduo e dependência temporal.
- Na prática, isso permitiu tratar **ID do animal** como fator de agrupamento e modelar a
correlação serial inerente ao desenho longitudinal (7 dias), em vez de reduzir o fenômeno a
médias agregadas.
- Implementou-se um pipeline de limpeza e *pivot* (ex.: `dplyr`/`tidyr`) para que cada linha
representasse um estado discreto no tempo (dia/sessão/área), aumentando reprodutibilidade e
auditabilidade.

**(ii) Crise de modelagem e escolha de GLMMs (prova por contradição):**

- Modelos gaussianos simples (ANOVA/regressão linear) foram rejeitados quando apresentaram
resíduos heterocedásticos e previsões implausíveis para variáveis limitadas (ex.: tempos, contagens).
- Testes com Poisson evidenciaram **superdispersão**, levando à adoção de **Binomial
Negativa** e, quando necessário, **Tweedie** para variáveis contínuas com inflação de zeros.
- A inclusão de efeitos aleatórios (ex.: **(1|ID_Animal)**) foi justificada por testes (ex.: LRT),
evitando inflar artificialmente significância ao ignorar individualidade (redução de erro tipo I).

**(iii) Diagnósticos (DHARMa como filtro final):**

- A seleção do modelo final foi orientada por diagnósticos residuais (ex.: uniformidade e
ausência de viés sistemático em resíduos simulados), e não apenas por “obter p < 0,05”.
- Esse controle adicionou segurança às inferências e permitiu descartar estruturas instáveis.

**(iv) Interpretação de efeito (emmeans/emtrends e taxas de aprendizagem):**

- Além de significância, a análise passou a entregar **estimativas de efeito** e **velocidade de
mudança** (slopes), essenciais para interpretar “aprendizagem” e modulação temporal.
- O uso de `emtrends` permitiu quantificar diferenças de taxas (ex.: “grupo aprende mais rápido”),
proporcionando interpretação mais direta e defensável.

**(v) Modularização e reprodutibilidade:**

- O código foi estruturado em módulos (ingestão → diagnóstico → modelagem → contraste),
permitindo reanálises rápidas quando a base é atualizada e elevando o padrão de
reprodutibilidade exigido por agências de fomento.

### 5.3 Principais resultados consolidados (TEPT e Cannabis Full Spectrum)

**(A) Validação do modelo de TEPT (GC vs GE):**

- **Atividade locomotora:** estresse reduziu significativamente a distância total percorrida
(t(33,73) = -2,08, p = 0,0449) e a velocidade média (t(33,69) = -2,09, p = 0,0445).
- **Freezing:** aumento significativo do tempo total de *freezing* no GE (média da resposta
= 101,1 s) em comparação ao GC (51,6 s; p = 0,0439).
- **Memória aversiva (vermelho):** diferença significativa na evolução do tempo na área vermelha
(z = 2,47, p = 0,0135), com diminuição progressiva no GE (slope = -0,2148;
95% CI [-0,376, -0,053]).
- **Generalização do medo (azul):** aumento progressivo do tempo na área azul no GE
(slope = 0,5672; 95% CI [0,340, 0,794]) e aumento progressivo de *freezing* na área azul
(slope = 0,3859; 95% CI [0,1983, 0,5736]).

**(B) Cannabis Full Spectrum em animais estressados (GCE vs GET):**

- **Recuperação locomotora ao longo do tempo:** tendência de interação tratamento × tempo
para distância e velocidade média (z = 1,81; p ≈ 0,0699), com aumento progressivo no GET
(slope = 0,0545; 95% CI [0,0188, 0,0902] para distância e [0,0188, 0,0903] para velocidade
média).
- **Interação com áreas coloridas:** proporção de animais do GET que interagiu com as cores foi
significativamente menor (Fisher: Vermelho p = 0,0159; Azul p = 0,0075; Verde p < 0,0001),
sugerindo modulação do padrão exploratório.
- **Contexto aversivo (vermelho):** não houve evidência de “apagamento” da memória aversiva,
mas houve modulação da estratégia: o GET apresentou diminuição do *freezing* ao longo dos
dias na área vermelha (slope = -0,146; 95% CI [-0,287, -0,00444]).

Em conjunto, os resultados sustentam: (i) validade comportamental do paradigma de TEPT
com formação de memória aversiva e componentes compatíveis com generalização do medo; e
(ii) efeito terapêutico do extrato Full Spectrum principalmente sobre a dimensão tônica do
estresse (retardo locomotor), com modulação da resposta comportamental em contexto aversivo.

---

## 6. Pedido para prorrogação excepcional de vigência (12 meses) – justificativas

Solicita-se prorrogação excepcional de vigência por 12 meses (01/03/2026 à 28/02/2027), com
base nos seguintes pontos, em formato compatível com os relatórios anteriores:

- O projeto gerou um volume de dados comportamentais robusto e dois manuscritos em
elaboração, mas a fase de consolidação (revisões, integração final e submissão) exige tempo
dedicado para assegurar qualidade e reprodutibilidade.
- As análises moleculares previstas (ex.: cortisol e marcadores de neuroinflamação) dependem
da aquisição/execução de kits (ELISA/RT-qPCR) e integração cuidadosa com os dados
comportamentais já coletados.
- Há necessidade de ampliar e generalizar a plataforma computacional para aumentar o impacto da
tecnologia no país, por meio de: (i) ampliação do dataset com **maior variabilidade
multi-perspectiva** (incluindo vistas já contempladas, como **perspectiva lateral**, e novas
condições de captura), com foco em generalização e robustez; (ii) **aprimoramento/validação da
autodetecção de áreas de interesse (AOIs/ROIs)** já implementada, ampliando a variabilidade de
imagens/padrões e fortalecendo critérios de qualidade/consistência; (iii) módulo para
processamento de vídeos pré-gravados (reprocessamento de acervos e comparações entre
protocolos); (iv) aprimoramentos contínuos da interface gráfica **já baseada em Tkinter** e do
empacotamento/distribuição; (v) redação da **documentação do programa voltada ao público-alvo**;
e (vi) **validação cruzada** do ZebTrack-AI executando os mesmos vídeos e comparando resultados
com outros programas/pipelines (quando aplicável), para quantificar concordância e limites.
- Atualização tecnológica do modelo de IA para uma arquitetura de próxima geração (incluindo
explicitamente a meta de migração/avaliação com YOLOv26), visando robustez, manutenção e
melhoria do desempenho em cenários adversos.

Digno de nota: no início deste ano, foi publicado o **YOLOv26**, trazendo uma oportunidade
inesperada (e muito favorável) para o objetivo de **acessibilidade** do ZebTrack-AI. A proposta
é avaliar sua adoção porque, no contexto atual, esse tipo de atualização pode permitir que o
pesquisador execute o rastreio em seu **próprio computador**, reduzindo a dependência de
placas gráficas dedicadas e caras (ex.: GPUs NVIDIA ou Intel e/ou outras soluções específicas de alto
custo, inclusive opções que não estão amplamente disponíveis no contexto de pesquisa no
Brasil). Isso aumenta a produtividade (menos tempo de processamento), melhora a viabilidade
de uso contínuo e amplia o espectro de pesquisadores capazes de utilizar o software mesmo em
cenários com recursos tecnológicos escassos.

- Finalização da documentação, padronização de outputs e preparação do pacote para uso por
outros laboratórios, maximizando o retorno do investimento da FAPESP.
- Publicação e entrega do trabalho final: consolidação dos manuscritos, organização do pacote
para uso público (release) e divulgação científica dos resultados e do software.

---

## 7. Plano de atividades e cronograma para 12 meses adicionais

O cronograma abaixo segue o modelo previamente adotado (tópicos mensais), adaptado ao
período de 12 meses adicionais.

| Etapas | 2026-03 | 2026-04 | 2026-05 | 2026-06 | 2026-07 | 2026-08 | 2026-09 | 2026-10 | 2026-11 | 2026-12 | 2027-01 | 2027-02 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Consolidação estatística final (TEPT + Cannabis) e submissão dos manuscritos | ∙ | ∙ | ∙ | ∙ | ∙ | ∙ | ∙ |  |  |  |  |  |
| Análises fisiológicas e genômicas (cortisol/RT-qPCR/ELISA) e integração com comportamento |  | ∙ | ∙ | ∙ | ∙ | ∙ |  |  |  |  |  |  |
| Ampliação do dataset (novas condições + maior variabilidade multi-perspectiva; inclui lateral já treinada e incrementos em FullHD para individualização) |  |  | ∙ | ∙ | ∙ |  |  |  |  |  |  |  |
| Treinamento/validação da IA (incluindo avaliação de migração para YOLOv26) |  |  |  | ∙ | ∙ | ∙ | ∙ |  |  |  |  |  |
| Aprimoramento/validação da autodetecção de áreas de interesse (já implementada) |  |  |  |  | ∙ | ∙ | ∙ |  |  |  |  |  |
| Módulo para vídeos pré-gravados (processamento em lote de acervos) |  |  |  |  |  | ∙ | ∙ | ∙ | ∙ |  |  |  |
| Aprimoramentos da interface Tkinter (UX/estabilidade) e empacotamento/distribuição |  |  |  |  |  |  |  | ∙ | ∙ | ∙ |  |  |
| Documentação para o público-alvo, tutorialização e divulgação acadêmica |  |  |  |  |  |  |  |  | ∙ | ∙ | ∙ | ∙ |
| Validação cruzada com outros programas/pipelines (concordância e limites) |  |  |  |  |  |  |  |  | ∙ | ∙ |  |  |

---

## 8. Referências

As referências completas utilizadas na fundamentação metodológica e na redação dos
manuscritos constam nos rascunhos anexos e serão padronizadas na versão final submetida.
Como referências centrais de método e contexto do período, destacam-se:

- Pinheiro-da-Silva, J. et al. (2017). ZebTrack: software base para análise comportamental automatizada em zebrafish.
- Lima, M. G. et al. (2016). Time-dependent sensitization of stress responses in zebrafish: modelo putativo de TEPT. *Behavioural Processes*.
- Yang, H. et al. (2020). Respostas tardias e persistentes após estresse agudo intenso (base conceitual para efeitos prolongados).
- Bozhko, D. V. et al. (2022). Artificial intelligence-driven phenotyping of zebrafish psychoactive drug responses. *Progress in Neuro-Psychopharmacology and Biological Psychiatry*, 112, 110405.
- Lukivikov, D. A. et al. (2024). Open-access AI-driven platform for CNS drug discovery using adult zebrafish. *Journal of Neuroscience Methods*, 411, 110256.
- Redmon, J. et al. (2015). You Only Look Once: Unified, Real-Time Object Detection. arXiv. Disponível em: <https://arxiv.org/abs/1506.02640>.
- Bates, D. et al. (2015). Fitting Linear Mixed-Effects Models Using lme4. *Journal of Statistical Software*.
- Brooks, M. E. et al. (2017). glmmTMB: Balances speed and flexibility among packages for zero-inflated generalized linear mixed modeling. *The R Journal*.
- Hartig, F. (DHARMa). Residual diagnostics for hierarchical (mixed) regression models (R package). Disponível em: <https://cran.r-project.org/package=DHARMa>.
- Lenth, R. (emmeans). Estimated Marginal Means, aka Least-Squares Means (R package). Disponível em: <https://cran.r-project.org/package=emmeans>.

---

## 9. Anexos

- Registros auxiliares de histórico de desenvolvimento (arquivos de log exportados do Git):
  - [docs/tasks/active/ROLLING_TASK_LOG.md](docs/tasks/active/ROLLING_TASK_LOG.md)
  - [docs/archive/legacy/fapesp/](docs/archive/legacy/fapesp/) (arquivo histórico principal)
  - [docs/archive/legacy/fapesp/git/](docs/archive/legacy/fapesp/git/) (evidências Git exportadas)
- Métricas verificadas do Roboflow (dataset e modelos) consolidadas no texto.
- Tabela de gastos de 2025: CSV exportado (anexo financeiro) em
  [docs/archive/legacy/fapesp/finance/Tabela Itens e Notas FAPESP - 2025.csv](docs/archive/legacy/fapesp/finance/Tabela%20Itens%20e%20Notas%20FAPESP%20-%202025.csv).
- Documento formal para submissão conjunta: proposta de prorrogação excepcional (submetida e
  aceita) – arquivo `Cópia de Projeto_Prorrogacao_Excepcional_Aceita_v1.md`.
- Rascunhos/manuscritos: validação do modelo de TEPT e tratamento com Cannabis Full
Spectrum (documentos de trabalho) em
  [docs/archive/legacy/fapesp/manuscripts/](docs/archive/legacy/fapesp/manuscripts/).
- Rascunhos históricos de relatórios/propostas (versões anteriores) em:
  - [docs/archive/legacy/fapesp/reports/](docs/archive/legacy/fapesp/reports/)
  - [docs/archive/legacy/fapesp/proposals/](docs/archive/legacy/fapesp/proposals/)
- Notebooks de treinamento/experimentação (detecção/segmentação) em
  [docs/archive/legacy/fapesp/notebooks/](docs/archive/legacy/fapesp/notebooks/).

**Marco Antônio Sant’ Ana Camargos**
Bolsista FAPESP

**Profª. Drª. Percília Cardoso Giaquinto**
Orientadora
