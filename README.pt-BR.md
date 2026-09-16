<div align="center">
  <img src="src/zebtrack/ui/assets/logo_readme.png" alt="DRerio LogAI Logo" width="400"/>

# DRerio LogAI

**Plataforma Inteligente de Rastreamento e Análise Comportamental para _Danio rerio_ (Zebrafish)**

![Version](https://img.shields.io/badge/version-7.1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12%2B-yellow.svg)
![License](https://img.shields.io/badge/license-MIT%20%2B%20AGPL--3.0--or--later%20effective-lightgrey.svg)
![INPI](https://img.shields.io/badge/INPI-BR%2051%202026%20005215--7-blueviolet.svg)
<!-- O badge do DOI é uma imagem estática do shields.io de propósito. O endereço do Zenodo é
     limitado a 120 requisições por minuto e vem com no-cache, então o proxy de imagens do
     GitHub leva HTTP 429 e mostra o ícone quebrado. O texto de um DOI nunca muda. -->
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22650404-1682D4.svg)](https://doi.org/10.5281/zenodo.22650404)
[![CI](https://github.com/MarkSant/DRerio-LogAI/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MarkSant/DRerio-LogAI/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/MarkSant/DRerio-LogAI/branch/main/graph/badge.svg?token=XH937YKEOU)](https://codecov.io/gh/MarkSant/DRerio-LogAI)

**🇺🇸 [Read in English](README.md)**

[Instalação](#-instalação) · [Primeira execução](#-primeira-execução-o-que-você-verá) ·
[Primeiro projeto](#-seu-primeiro-projeto) · [Documentação](docs/INDEX.md) ·
[Novidades](docs/releases/INDEX.md)

</div>

---

## Conteúdo

- [O que é](#-o-que-é)
- [O que ele faz](#-o-que-ele-faz)
- [Como é na prática](#-como-é-na-prática)
- [Quem usa](#-quem-usa)
- [Instalação](#-instalação)
- [Primeira execução: o que você verá](#-primeira-execução-o-que-você-verá)
- [Modelos de detecção e OpenVINO](#-modelos-de-detecção-e-openvino)
- [Seu primeiro projeto](#-seu-primeiro-projeto)
- [A janela do projeto, aba por aba](#-a-janela-do-projeto-aba-por-aba)
- [Configurações e parâmetros](#-configurações-e-parâmetros)
- [O que sai do programa](#-o-que-sai-do-programa)
- [Métricas comportamentais](#-métricas-comportamentais)
- [Quando algo dá errado](#-quando-algo-dá-errado)
- [Novidades](#-novidades)
- [Citação](#-citação)
- [Titularidade, registro e licença](#-titularidade-registro-e-licença)
- [Para desenvolvedores](#-para-desenvolvedores)

## 📋 O que é

O **DRerio LogAI** é um aplicativo completo e de código aberto para análise comportamental
automatizada de zebrafish (_Danio rerio_). Ele detecta e rastreia os animais num vídeo — ou ao
vivo, direto da câmera — e transforma o movimento nas medidas que um experimento comportamental de
fato reporta: distância percorrida, velocidade, tempo em cada região do aquário, imobilidade,
tigmotaxia, geotaxia.

É um **programa de computador com interface gráfica**. Nada aqui é programado, escrito em script ou
digitado num terminal: projetos, zonas, modelos e parâmetros são escolhidos em janelas e caixas de
diálogo.

O zebrafish é usado em neurociência, farmacologia e toxicologia, e analisar o comportamento à mão é
lento (horas de trabalho por minutos de vídeo), subjetivo (observadores discordam) e limitado (uma
pessoa não acompanha vários animais ao mesmo tempo). Esta plataforma substitui isso por uma medida
automática, objetiva e repetível, guardando cada parâmetro junto dos dados para que um resultado
possa ser reproduzido depois.

**Roda num computador comum.** Não é preciso ter placa de vídeo NVIDIA: em máquinas Intel os modelos
rodam por OpenVINO, na CPU, no vídeo integrado ou na NPU.

## ✨ O que ele faz

- **🤖 Detecção e rastreamento** — modelos Ultralytics YOLO (caixas ou máscaras de segmentação), com
  rastreamento multiobjeto por ByteTrack e manutenção da identidade em oclusões breves.
- **🐟 Um animal ou vários**, num aquário ou em vários filmados lado a lado no mesmo vídeo
  (multi-aquário), analisados em paralelo ou um de cada vez.
- **📹 Vídeo pré-gravado e câmera ao vivo.** Um projeto ao vivo grava e analisa a sessão ao mesmo
  tempo, por animal, por dia, por grupo.
- **🎯 Arena e regiões de interesse** desenhadas sobre um quadro real da sua própria gravação, com
  quatro regras de inclusão, modelos reutilizáveis e detecção automática da arena.
- **📏 Unidades reais.** As dimensões do aquário em centímetros convertem pixels em cm, então
  distâncias e velocidades saem em cm e cm/s.
- **📊 Métricas científicas** — locomoção, velocidade angular, episódios comportamentais,
  tigmotaxia, geotaxia (novel tank test), ocupação de ROI e tabelas por animal.
- **🔌 Hardware em malha fechada.** Um Arduino pode ser acionado na entrada e na saída de uma ROI,
  ou ser ele a disparar o início da gravação, com a latência quadro→acionamento registrada.
- **📦 Formatos padrão** — Parquet (trajetórias), Excel (métricas) e Word (relatório ilustrado),
  além de um relatório unificado de todo o projeto.
- **🔬 Reprodutibilidade.** Toda configuração é gravada junto dos dados, o esquema da trajetória é
  imutável e o release é arquivado com DOI.

## 📸 Como é na prática

A tela inicial informa quais pesos de detecção estão carregados e se o OpenVINO está ativo, antes
de qualquer análise:

![Tela inicial do DRerio LogAI, com o painel de status dos modelos](docs/wiki/screenshots/main_window.png)

Zonas e regiões de interesse são desenhadas direto sobre um quadro da gravação real, de modo que a
geometria da análise é definida contra a arena de verdade:

![Configuração de zonas e ROIs sobre um quadro adquirido](docs/wiki/screenshots/roi_config.png)

Cada sessão rende a trajetória reconstruída e um mapa de calor de ocupação em centímetros, sem
pós-processamento manual:

![Trajetória de natação com as quatro ROIs definidas pelo operador](docs/wiki/screenshots/trajectory_output.png)

Mais telas, passo a passo, no [guia do usuário](docs/wiki/user-guide/PRIMEIROS_PASSOS.md).

## 🎓 Quem usa

- **Farmacologia** — triagem de fármacos (canabidiol, ansiolíticos, antidepressivos), desenhos de
  dose-resposta ao longo de grupos e dias.
- **Toxicologia** — toxicidade ambiental, desfechos comportamentais após exposição.
- **Neurociência** — comportamento tipo-ansiedade (novel tank test, claro/escuro), memória e
  aprendizagem.
- **Genética** — fenotipagem de mutantes e transgênicos.
- **Metodologia** — estimulação em malha fechada, caracterização de latência, rastreamento de
  vários animais.

## 📥 Instalação

### O que o computador precisa

| Componente | Mínimo                     | Recomendado                              |
| ---------- | -------------------------- | ---------------------------------------- |
| Python     | 3.12                       | 3.12 (3.13 funciona; **3.14 não**)       |
| Disco      | 3 GB livres                | 5 GB+                                    |
| RAM        | 8 GB                       | 16 GB+                                   |
| CPU        | Dois núcleos               | Quatro núcleos+ (Intel Core Ultra p/ NPU)|
| GPU        | Não é necessária           | NPU Intel Core Ultra via OpenVINO        |
| SO         | Windows 10, Linux, macOS   | Windows 11 (onde é validado)             |

**Nenhum compilador é necessário** — toda dependência instala a partir de pacote pronto.

**O espaço em disco é o requisito que pega as pessoas de surpresa.** PyTorch, OpenVINO, OpenCV e
SciPy respondem pela maior parte de um ambiente virtual de ~1,7 GB, e os modelos somam mais ~240 MB.

### Instale em cinco passos (Windows)

Este é o procedimento completo para usar o programa. Não exige Git, terminal nem programação. Cada
passo está explicado clique a clique, com o que fazer quando falha, no
**[guia de instalação completo](docs/wiki/1_Instalacao.md)** — leia aquele se algo aqui for
desconhecido.

1. **Instale o Python 3.12** em
   [python.org](https://www.python.org/downloads/release/python-3129/) — o botão
   "Windows installer (64-bit)". Na **primeira** tela desse instalador, marque
   **"Add python.exe to PATH"** antes de clicar em Install.

   _O Python é o motor sobre o qual o programa roda. Se você pular este passo, o instalador do
   passo 4 se oferece para fazê-lo por você._

2. **Baixe o DRerio LogAI**: abra a
   [página de releases](https://github.com/MarkSant/DRerio-LogAI/releases) e, em **Assets** do
   release mais recente, clique em **Source code (zip)**.

3. **Extraia o ZIP** num lugar permanente: botão direito no arquivo baixado → **Extrair tudo**.
   Escolha uma pasta simples, como `C:\DRerio-LogAI`. **Não** a pasta Downloads — essa pasta vira a
   casa do programa, guardando os modelos, as configurações e (por padrão) seus projetos.

4. **Dê dois cliques em `install.bat`** dentro da pasta extraída. O Windows pode avisar que
   protegeu o computador; escolha **Mais informações → Executar assim mesmo** (o arquivo é um
   script de uma linha, e o aviso só significa que ele veio da internet).

   Ele confere o Python, confere o Poetry, **se oferece para instalar o que estiver faltando**,
   instala as bibliotecas, baixa os ~240 MB de modelos e cria o ícone **DRerio LogAI** na área de
   trabalho e no menu Iniciar. Conte com alguns minutos. Responda `Y` ao que ele perguntar.

5. **Abra o programa** pelo ícone **DRerio LogAI**.

É só isso. O programa pergunta o idioma, mede o hardware, cria suas pastas e abre. Câmera, porta do
Arduino e todo o resto são escolhidos dentro da interface — não há arquivo de configuração para
escrever à mão.

### Linux e macOS

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
./setup.sh          # Debian/Ubuntu: dependências, modelos e atalho .desktop
```

No macOS, e nas distribuições onde o `setup.sh` não se aplica, instale
[Python 3.12](https://www.python.org/downloads/) e
[Poetry](https://python-poetry.org/docs/#installation) e então:

```bash
poetry install
poetry run fetch-weights     # ~240 MB de modelos treinados, obrigatório
poetry run zebtrack
```

O Linux também precisa das ligações do Tk: `sudo apt install python3.12-tk` em sistemas baseados em
Ubuntu.

### Atualizando para uma versão nova

Baixe e extraia o ZIP novo, copie para ele o `config.local.yaml`, a pasta `weights/` e os projetos
guardados dentro da pasta antiga, e rode o `install.bat` de novo. Com Git, `git pull` seguido de
`install.bat` faz o mesmo. Rode o instalador novamente também depois de **mover** a pasta: o atalho
guarda um caminho absoluto.

## 🚀 Primeira execução: o que você verá

Na ordem, na primeiríssima abertura:

1. **A pergunta de idioma.** Sua resposta é gravada em `config.local.yaml`. O idioma do sistema
   operacional **não** é consultado de propósito — antes da v5.0.0 uma máquina brasileira gerava
   relatórios em português sem ninguém pedir. Mude depois em **Configurações → Idioma...**.

2. **Uma tela de abertura rodando um teste de hardware.** Ela converte um modelo para OpenVINO e
   mede a inferência nos dispositivos que encontra, para escolher o backend. Esta é a abertura mais
   lenta que você terá: o resultado fica em cache e as próximas pulam a etapa. Uma medição que não
   mediu nada é marcada como inconclusiva e refeita na próxima vez, em vez de virar um chute
   permanente.

3. **A janela principal**, com **Criar Novo Projeto**, **Abrir Projeto Existente**, **Analisar
   Vídeo Único** e **Analisar Câmera ao Vivo**, além do painel que informa os pesos ativos e o
   estado do OpenVINO.

4. **A janela de Primeiros passos**, explicando os modelos de detecção, os quatro papéis que eles
   preenchem e se vale ligar o OpenVINO **na sua máquina** — ela lê o hardware encontrado e nomeia
   os dispositivos, em vez de dar conselho genérico. O botão dela abre o painel de modelos direto.

   Dispensá-la em definitivo é seguro: ela volta por **Ajuda → Primeiros passos...**, e o painel
   para onde ela aponta fica em **Configurações → Definições de modelo...**.

Os modelos de detecção **não** são baixados aqui. Eles vêm uma única vez, antes, pelo
`fetch-weights`, que o instalador executa por você. Sem eles o programa abre e depois se recusa a
rastrear, nomeando os arquivos que faltam.

## 🧠 Modelos de detecção e OpenVINO

Esta é a única coisa que vale configurar antes da primeira análise.

### Os seis modelos

O `fetch-weights` instala seis modelos YOLO treinados em `weights/` e confere cada um contra um
SHA-256 registrado em `weights_manifest.json`.

| Modelo | Tipo | Ângulo da câmera | Use quando |
| --- | --- | --- | --- |
| `best_det_lateral.pt` | detecção (caixa) | lateral | Novel tank test, geotaxia, aquários filmados de lado |
| `best_seg_lateral.pt` | segmentação (máscara) | lateral | O mesmo, quando a precisão nas bordas importa |
| `best_det_topdown.pt` | detecção (caixa) | de cima | Campo aberto, claro/escuro, arenas filmadas de cima |
| `best_seg_topdown.pt` | segmentação (máscara) | de cima | O mesmo, quando a precisão nas bordas importa |
| `best_oi.pt` | detecção (caixa) | qualquer | Montagens que os especialistas não atendem; traz a classe `zup-aqua` |
| `best_seg.pt` | segmentação (máscara) | qualquer | O mesmo, com máscaras |

**Um modelo treinado para um ângulo não devolve nada no outro.** Um modelo lateral numa gravação de
cima não detecta o peixe que está claramente visível — então a primeira coisa a acertar é combinar
o modelo com a forma como sua câmera está montada.

Os quatro especialistas já vêm atribuídos como padrão. Os dois generalistas ficam registrados mas
não ocupam nenhum papel: são uma escolha explícita sua.

### Os quatro papéis

Em **Configurações → Definições de modelo...**, em **Pesos padrão por papel**, um modelo é
atribuído a cada papel:

| Papel | O que ele encontra |
| --- | --- |
| 🐠 **Aquário (Detecção)** | A arena, como um retângulo |
| 🐠 **Aquário (Segmentação)** | A arena, na forma real |
| 🐟 **Animal (Detecção)** | Cada peixe, como uma caixa |
| 🐟 **Animal (Segmentação)** | Cada peixe, como uma máscara |

Qual par é usado numa análise depende do método escolhido para aquele projeto, no passo **Modelos e
Pesos** do assistente.

**Detecção ou segmentação?**

- **Detecção (`det`)** é mais leve e basta quando a posição aproximada é o que você precisa.
- **Segmentação (`seg`)** é a melhor escolha quando a análise depende de precisão espacial — ROIs
  pequenas, bordas, vários animais próximos — e é **obrigatória** para a regra de ROI
  `seg_overlap`, que precisa de máscaras gravadas.

### OpenVINO

O OpenVINO é o acelerador de inferência da Intel. Se vale ligá-lo depende da sua máquina, e a
janela de Primeiros passos responde isso para a máquina à sua frente:

| Seu hardware | O que fazer |
| --- | --- |
| Placa de vídeo NVIDIA | Deixe o OpenVINO **desligado**; PyTorch com CUDA costuma ser mais rápido |
| CPU Intel, vídeo integrado ou NPU, sem NVIDIA | **Ligue** — é o caminho rápido aqui (3–5× em CPUs Intel) |
| Nenhum dos dois | Roda mesmo assim, na CPU, só mais devagar |

Em **Configurações → Definições de modelo...**: marque **Otimizar com OpenVINO (para hardware
Intel)**, escolha o **dispositivo OpenVINO** (CPU, GPU ou NPU) e use **Converter para OpenVINO** nos
pesos que pretende usar. **A conversão acontece uma vez** e fica em cache em
`openvino_model_cache/`; o painel mostra cada peso como ✓ Pronto, ⏳ Convertendo ou ✗ Falhou.

O mesmo painel tem **Adicionar peso...** (registrar um modelo treinado por você), **Validar
caminhos**, **Reescanear a pasta de pesos**, manutenção de cache e **Refazer o benchmark de
hardware**.

### Conferir ou reparar os modelos

```bash
poetry run fetch-weights --check    # confere o que está instalado, sem baixar nada
poetry run fetch-weights            # baixa o que faltar ou estiver corrompido
```

## 🚀 Seu primeiro projeto

### A versão curta, de ponta a ponta

1. **Criar Novo Projeto**, na janela principal, abre o assistente.
2. Responda ao assistente (7 passos no pré-gravado, 6 no ao vivo — detalhados abaixo).
3. Em **Configuração de Zonas**, desenhe a arena e as regiões de interesse sobre um quadro real e
   clique em **✅ Finalizar e Salvar Projeto**.
4. Em **Controle Principal** (pré-gravado), use **Analisar Vídeo(s) Selecionado(s)** ou **Processar
   Vídeos Pendentes...**; num projeto ao vivo, **▶️ Iniciar Gravação**.
5. Em **Processamento e Relatórios**, gere os relatórios parcial e unificado.
6. Abra o `.xlsx` e o `.docx` gravados ao lado de cada vídeo.

### O assistente, passo a passo

Os dois fluxos partem de **Criar Novo Projeto**. O assistente tem 1150×550 px e mostra seu próprio
contador de passos.

#### Projeto pré-gravado — 7 passos

| # | Passo | O que você faz |
| --- | --- | --- |
| 1 | **Descoberta** | Tipo de projeto (experimental / ao vivo), se as pastas têm significado experimental e o que fazer com arquivos `.parquet` encontrados ao lado dos vídeos |
| 2 | **Seleção de vídeos** | **📁 Adicionar arquivos...** ou **📂 Adicionar pasta...**; uma prévia mostra a estrutura entendida |
| 3 | **Calibração física** | **Largura (cm)** e **Altura (cm)** do aquário, número de aquários por vídeo, animais por aquário, intervalo de análise, opções comportamentais |
| 4 | **Detecção automática do desenho** | A estrutura de pastas vira Grupos / Dias / Sujeitos. Revise e corrija com **✏️ Editar desenho** ou **🔧 Regex personalizada** |
| 5 | **Modelos e Pesos** | Método e peso por papel, OpenVINO, confiança/NMS do YOLO e os parâmetros do ByteTrack |
| 6 | **Configuração de importação** | Por vídeo: importar arena, ROIs, trajetória — e a estratégia de mesclagem quando já existem ROIs |
| 7 | **Confirmação** | Nome e local do projeto, resumo de tudo, opcionalmente **💾 Salvar como modelo** |

#### Projeto ao vivo — 6 passos

| # | Passo | O que você faz |
| --- | --- | --- |
| 1 | **Descoberta** | Tipo de projeto: ao vivo |
| 2 | **Desenho experimental** | Dias, grupos, nomes dos grupos, animais por grupo — o assistente mostra quantas gravações isso dá |
| 3 | **Configuração da gravação ao vivo** | **🔍 Detectar câmeras** e escolher uma; porta do Arduino opcional com **🔌 Testar**; modo de gatilho externo; gravação temporizada e contagem regressiva |
| 4 | **Calibração física** | Como acima |
| 5 | **Modelos e Pesos** | Como acima |
| 6 | **Confirmação** | Como acima |

**Organizando as pastas de vídeo.** Quando as pastas têm significado experimental, um arranjo como
`Grupo_CBD/Dia_1/Sujeito_4/CECT_4.mp4` é detectado automaticamente em grupos, dias e sujeitos. O
mesmo nome de arquivo pode se repetir entre dias — um desenho longitudinal grava o mesmo sujeito
todo dia — porque um vídeo é identificado pelo **caminho**, nunca só pelo nome.

> **O modo de gatilho externo** (o Arduino inicia a gravação) é opcional e vem desligado. Ele exige
> um sketch que envie `1`/`0` pela serial; o sketch de referência deste repositório **não** faz
> isso. Veja [`docs/guides/user/external-trigger.md`](docs/guides/user/external-trigger.md).

### Desenhando a arena e as ROIs

Na aba **Configuração de Zonas**, sobre um quadro do seu próprio vídeo:

- **Detectar Aquário (Auto)** propõe a arena; **Suavização (quadros)** reduz o ruído dessa detecção.
  Ou desenhe você mesmo com **Polígono Principal**.
- **Região de Interesse (ROI)** desenha cada região — polígonos, retângulos e círculos. Dê nome a
  elas; as métricas saem por ROI com esses nomes.
- **Modelos de ROI** salvam um conjunto de regiões para reutilizar em outros vídeos e projetos.
- Desfazer e refazer estão sempre à mão (`Ctrl+Z` / `Ctrl+Y`).
- Com vários aquários no mesmo vídeo, o **Modo de processamento** escolhe entre **Simultâneo** (uma
  passada) e **Sequencial** (um aquário por vez).

As zonas pertencem ao vídeo em que foram desenhadas. Um vídeo sem zonas próprias usa o padrão do
projeto.

## 🧩 A janela do projeto, aba por aba

- **Controle Principal** — ações conforme o tipo de projeto (ao vivo: iniciar/parar gravação;
  pré-gravado: adicionar e processar vídeos), a árvore grupo/dia/sujeito/vídeo e o painel **Status
  do Modelo de Detecção**.
- **Configuração de Zonas** — arena e ROIs, regra de inclusão, estabilização, modelos.
- **Análise de Vídeo** — acompanhar a análise em curso e selecionar quais `track_id` considerar.
- **Processamento e Relatórios** — geração de trajetória, exportação do sumário, relatórios parciais
  e unificados, com árvore de status por vídeo; duplo clique abre o arquivo.
- **Config. Modelo IA** / **Diagnóstico de Modelo IA** — o painel de modelos deste projeto e um
  teste contra um quadro de exemplo.
- **Configurações Avançadas** — editor das configurações dentro do programa, persistido em
  `config.local.yaml`.
- **Progresso do Experimento** (projetos ao vivo) — a grade dia × grupo com as sessões concluídas.

Projetos ao vivo também expõem o **Painel do Arduino**, com status da conexão, comandos e nova
varredura de portas.

## 🔩 Configurações e parâmetros

**Não há nada para escrever à mão.** O `config.local.yaml` é criado por você — responder à pergunta
de idioma é o que o escreve — e tudo que um operador precisa está na interface.

### O que ajustar, e quando

| Parâmetro | Onde | Padrão | Aumente quando | Diminua quando |
| --- | --- | --- | --- | --- |
| **Confiança mínima** | Assistente → Modelos e Pesos; Configurações Avançadas | 0,05 | Aparecem detecções falsas (reflexos, sombras, o termostato) | O animal é perdido, ou some em quadros escuros |
| **NMS (sobreposição)** | Idem | 0,5 | O mesmo peixe é detectado duas vezes | Dois peixes próximos viram um só |
| **Track Threshold** | Idem (ByteTrack) | 0,25 | Surgem IDs em cima de ruído | As trilhas se partem |
| **Match Threshold** | Idem | 0,95 (permissivo) | As trilhas se partem entre quadros analisados | IDs pulam de um animal para outro |
| **Track Buffer (quadros)** | Idem | 150 | O animal é ocluído com frequência e volta | A identidade não deve sobreviver a uma ausência longa |
| **Distância máxima (px)** | Idem | 400 | O animal nada rápido para o intervalo de análise | IDs são trocados entre vizinhos |
| **Intervalo de análise (quadros)** | Assistente → Calibração; Config. Avançadas | 10 | O processamento está lento demais | Você precisa de mais resolução temporal |
| **Regra de inclusão de ROI** | Configuração de Zonas | `bbox_intersects` | — | Veja abaixo |
| **Número de animais** | Assistente → Calibração | 1 | — | Precisa bater com a realidade; "1 animal" é respeitado |
| **Duração da gravação** | Assistente → ao vivo, por bloco ou por cobaia | 300 s | — | — |

O padrão de confiança é deliberadamente baixo porque ele é o piso para achar o **aquário**, uma vez.
O limiar do animal é separado (`animal_confidence_threshold`) e herda esse valor até você defini-lo:
aceitar um tanque uma vez e aceitar um peixe em todo quadro são perguntas diferentes.

> **Ajuste um parâmetro de cada vez, em passos de ±0,05, e teste.** A interface diz o mesmo, pela
> mesma razão: mexer em dois ao mesmo tempo torna o resultado impossível de atribuir.

**As regras de inclusão de ROI** decidem o que conta como "o animal está dentro da região":

| Regra | Conta como dentro quando |
| --- | --- |
| `bbox_intersects` (padrão) | A caixa do animal sobrepõe a região em pelo menos `roi_min_bbox_overlap_ratio` (0,10) |
| `centroid_in` | O centro do animal está dentro da região |
| `centroid_in_on_buffered_roi` | O mesmo, numa região expandida ou contraída por uma margem |
| `seg_overlap` | A **máscara** de segmentação sobrepõe a região acima de uma fração (0,3 por padrão) |

A `seg_overlap` precisa de máscaras, que só existem se tiverem sido gravadas — método de
segmentação, persistência de máscaras ligada e essa regra em vigor. Quando faltam, a análise
**degrada para `bbox_intersects` com um aviso no relatório**, em vez de falhar.

**Câmera e porta do Arduino ficam salvas no projeto, e o valor do projeto vence o global.** Defini-los
globalmente à mão, portanto, não faz nada por um projeto que tem os seus — que é todo projeto criado
pelo assistente.

Se ainda assim editar o `config.local.yaml`, escreva nele _apenas_ as chaves que está sobrescrevendo:

```yaml
camera:
  index: 0
```

> **Não** copie o `config.yaml` inteiro para dentro dele. Os dois são mesclados recursivamente, então
> uma cópia completa congela todos os padrões atuais na sua máquina e esconde silenciosamente toda
> correção futura.

## 📁 O que sai do programa

Cada vídeo processado gera uma pasta de resultados ao lado dele:

```text
<video>_results/
├── 1_ArenaROI_<video>.parquet       # Definições de arena/ROI
├── 2_Zones_<video>.parquet          # Metadados das zonas
├── 3_CoordMovimento_<video>.parquet # Trajetória (esquema imutável)
├── 3b_Mascaras_<video>.parquet      # Máscaras de segmentação (só quando gravadas)
├── <video>_summary.xlsx             # Métricas por ROI + tabela por animal
└── <video>_report.docx              # Relatório Word com gráficos
```

Multi-aquário acrescenta as subpastas `aquarium_0/`, `aquarium_1/` espelhando esse arranjo. Sessões
ao vivo somam um registro de quadros (`6_FrameLedger_*`), que mapeia cada quadro analisado ao
instante real de captura, e, com o Arduino, um log de latência em malha fechada (`5_ClosedLoop_*`).

O relatório do projeto inteiro reúne todos os vídeos:

```text
<projeto>/unified_reports/
├── project_summary_<run_id>.parquet   # Dados brutos
├── project_summary_<run_id>.xlsx      # Abas "Dados" + "Estatísticas descritivas"
├── project_summary_<run_id>.csv       # Igual à aba de dados
├── project_summary_<run_id>.docx      # Boxplots comparativos + tabela descritiva
└── project_summary_<run_id>.json      # Manifesto com metadados da execução
```

O esquema da trajetória é fixo e não muda entre versões:

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence
[x_center_px, y_center_px, x_cm, y_cm]*   — quando há calibração
```

## 📊 Métricas comportamentais

Por vídeo, por animal e por ROI:

| Família | O que é reportado |
| --- | --- |
| **Locomoção** | Distância total (cm), média / máxima / desvio da velocidade (cm/s), tortuosidade |
| **Angular** | Média / máxima / desvio da velocidade angular (°/s), viradas bruscas, viradas por minuto |
| **Episódios** | Surtos de velocidade (contagem e duração), inatividade (contagem, duração, % da gravação) |
| **Espacial** | Tigmotaxia (% do tempo perto da parede, distância média), ocupação geotáxica por zona vertical |
| **Por ROI** | Tempo, entradas, saídas, latência até a primeira entrada, distância e velocidade dentro da região |
| **Sessão** | Experimento, grupo, dia, duração do vídeo, quadros analisados |

A distância até a parede é a distância euclidiana exata até a aresta mais próxima do polígono do
aquário, válida para qualquer número de lados, convexo ou côncavo — o gráfico de tigmotaxia faz
sentido para um aquário de 8 lados, não só para um retângulo.

**Referência completa, com cada nome de coluna e fórmula:**
[`docs/reference/metrics.md`](docs/reference/metrics.md).

> **Comparar métricas absolutas entre gravações de durações diferentes é inválido** (distância
> total, número de entradas, tempo em ROI). O programa avisa antes de gerar o relatório parcial ou
> em lote e carimba a ressalva dentro do `.docx`; a coluna `video_duration_s` está no `.xlsx`
> justamente para permitir a normalização.

## 🔧 Quando algo dá errado

| Sintoma | O que fazer |
| --- | --- |
| O instalador para com uma mensagem amarela | Ela nomeia a causa e a solução; a mais comum é um Python fora da faixa (3.14) |
| `ModuleNotFoundError: No module named 'zebtrack'` | O ambiente foi criado no Python errado. [Guia de instalação](docs/wiki/1_Instalacao.md#se-o-fetch-weights-disser-que-não-existe-módulo-chamado-zebtrack) |
| O ícone da área de trabalho não faz nada | Rode o instalador de novo; uma pasta movida deixa o atalho apontando para o vazio. Veja `logs/analysis.log` |
| O programa abre mas se recusa a rastrear | Faltam os modelos: `poetry run fetch-weights` |
| O peixe não é detectado | Modelo errado para o ângulo da câmera (lateral × de cima), ou confiança alta demais |
| O rastreamento está lento | Ligue o OpenVINO em hardware Intel e converta o peso; aumente o intervalo de análise |
| Nenhuma câmera é listada | Feche o que mais estiver usando a câmera e clique em **🔍 Detectar câmeras** de novo |
| A aba de relatórios está vazia | Processe os vídeos primeiro; a árvore atualiza sob demanda |

Listas mais longas: [Solução de problemas](docs/wiki/user-guide/TROUBLESHOOTING.md),
[FAQ](docs/wiki/3_FAQ.md), [Problemas conhecidos](docs/reference/KNOWN_ISSUES.md).

## 🆕 Novidades

**Versão 7.1.0** — o release da primeira execução: instalador guiado e atalho na área de trabalho
(sem terminal), janela de primeiros passos explicando os modelos, tela de abertura que aparece na
hora, benchmark inicial que de fato mede alguma coisa, e os seis modelos instalados e selecionáveis.

**Histórico completo:** [novidades, versão por versão](docs/releases/INDEX.md) ·
[CHANGELOG](CHANGELOG.md).

## 📖 Citação

Se usar o DRerio LogAI em pesquisa, cite-o pelos metadados de [CITATION.cff](CITATION.cff)
(reconhecido pelo GitHub como "Cite this repository").

O software está arquivado no Zenodo:

| DOI | Resolve para |
| --- | --- |
| [`10.5281/zenodo.22650404`](https://doi.org/10.5281/zenodo.22650404) | **Todas as versões.** Cite este, a menos que precise fixar um release específico. |
| [`10.5281/zenodo.22650405`](https://doi.org/10.5281/zenodo.22650405) | O release **7.0.0** especificamente. |

> **Reproduzindo os resultados publicados.** Os números de validação e benchmark reportados nos
> manuscritos associados foram produzidos com o release **4.0.0** (tag
> [`v4.0.0`](https://github.com/MarkSant/DRerio-LogAI/tree/v4.0.0)), não com este. Use aquela tag
> para reprodução exata; cite o DOI acima para a plataforma arquivada.

## 📜 Titularidade, registro e licença

O **DRerio LogAI** tem **Registro de Programa de Computador concedido pelo INPI**, sob a Lei
9.609/98 (direito autoral de software — **não** é patente): processo **BR 51 2026 005215-7**,
petição 870260066857, depósito em 07/07/2026, data de criação declarada 22/10/2025.

A **titular** dos direitos patrimoniais é a **Universidade Estadual Paulista "Júlio de Mesquita
Filho" (UNESP)**, CNPJ 48.031.918/0001-24. Os **autores** (direitos morais) são:

- **Marco Antônio Sant'Ana Camargos** — Universidade Estadual Paulista (UNESP), Botucatu, Brasil
- **Percília Cardoso Giaquinto** — Universidade Estadual Paulista (UNESP), Botucatu, Brasil

O código-fonte original é licenciado sob a **Licença MIT** ([LICENSE](LICENSE)).

⚠️ **Licença efetiva de distribuição.** Este projeto depende do
[Ultralytics YOLO](https://github.com/ultralytics/ultralytics), licenciado sob
**AGPL-3.0-or-later**. Por causa desse copyleft, a obra combinada distribuída (este código mais o
`ultralytics`) fica sujeita à AGPL-3.0-or-later, a menos que se obtenha uma licença comercial da
Ultralytics. A MIT cobre o código original da UNESP; ela não cobre, por si só, o pacote distribuído
como um todo. O [NOTICE](NOTICE) traz o levantamento completo das dependências.

> **Não confunda com o PyZebArdYolo.** É um repositório irmão, mais simples em escopo, focado numa
> unidade de aquisição em tempo real (webcam + YOLO11 + Arduino) usada num artigo de hardware
> separado. Ele **não** é coberto pelo registro INPI acima e não carrega a exigência de titularidade
> da UNESP. Os dois projetos são independentes.

## 👨‍💻 Para desenvolvedores

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
poetry install --with dev
poetry run pre-commit install
poetry run fetch-weights
poetry run pytest -q
```

`install.ps1 -Dev` faz o mesmo no Windows, mais o atalho.

O programa é Python 3.12+, Tkinter, MVVM-S com injeção de dependência e um barramento de eventos
(`EventBusV2`); ~3700 testes rodam em 6–7 minutos.

| Tema | Documento |
| --- | --- |
| **Contribuição** | [CONTRIBUTING.md](CONTRIBUTING.md) |
| **Arquitetura** | [docs/explanation/architecture.md](docs/explanation/architecture.md) |
| **Onboarding de desenvolvedor** | [docs/guides/developer/getting_started.md](docs/guides/developer/getting_started.md) |
| **Mapa código → testes** | [docs/testing/TEST_MAP.md](docs/testing/TEST_MAP.md) |
| **Sistemas de coordenadas** | [docs/reference/COORDINATE_SYSTEMS.md](docs/reference/COORDINATE_SYSTEMS.md) |
| **Eventos** | [docs/reference/events.md](docs/reference/events.md) |
| **Desempenho / NPU** | [docs/guides/developer/performance-tuning.md](docs/guides/developer/performance-tuning.md) · [docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md](docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md) |
| **Configuração do VS Code** | [docs/guides/developer/VSCODE.md](docs/guides/developer/VSCODE.md) |
| **Publicar um release** | [docs/guides/developer/RELEASE.md](docs/guides/developer/RELEASE.md) |
| **Todo o resto** | [docs/INDEX.md](docs/INDEX.md) |

Contribuições são bem-vindas — correções de [KNOWN_ISSUES.md](docs/reference/KNOWN_ISSUES.md),
documentação e traduções, cobertura de testes, melhorias de interface, novos plugins de detecção.

## 🙏 Agradecimentos

**UNESP** — Universidade Estadual Paulista, e o **Laboratório de Fisiologia e Comportamento de
Peixes** (Depto. de Fisiologia — IBB/UNESP).

Construído sobre [Ultralytics YOLO](https://github.com/ultralytics/ultralytics),
[OpenVINO](https://github.com/openvinotoolkit/openvino),
[BYTETracker](https://github.com/ifzhang/ByteTrack),
[Tkinter](https://docs.python.org/3/library/tkinter.html),
[Poetry](https://python-poetry.org/), [Pydantic](https://pydantic.dev/) e
[structlog](https://www.structlog.org/) — e sobre a comunidade de código aberto em torno deles.

---

<div align="center">

<h4>Feito com ❤️ para a pesquisa científica</h4>

<h4>UNESP - Laboratório de Fisiologia e Comportamento de Peixes (Depto. de Fisiologia - IBB/UNESP)</h4>

[⬆ Voltar ao topo](#drerio-logai)

</div>
