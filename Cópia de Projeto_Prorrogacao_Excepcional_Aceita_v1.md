# EFEITO DO CANABIDIOL SOBRE ESTRESSE E MEMÓRIA AVERSIVA APÓS ESTRESSE AGUDO E INTENSO EM ZEBRAFISH

## Proposta de prorrogação excepcional (submetida e aceita)

Projeto de Iniciação Científica em graduação em

Medicina da Universidade Estadual Paulista do

campus de Botucatu – FMB/UNESP

**Bolsista:** Marco Antônio Sant’ Ana Camargos

**Orientadora:** Profª. Drª. Percília Cardoso Giaquinto

**Processo:** 2023/14200-3

**Vigência original da bolsa:** 01/03/2024 à 28/02/2026 (24 meses)

**Período de prorrogação excepcional (aceito):** 01/03/2026 à 28/02/2027 (12 meses)

Botucatu, São Paulo

2026

Processo FAPESP nº 2023/14200-3

## Sumário

1. Resumo do pedido de prorrogação excepcional (aceita)
2. Justificativas técnico-científicas e de mérito
   2.1 Por que a prorrogação excepcional é essencial para atingir excelência
   2.2 Por que a não concessão inviabilizaria resultados no nível de excelência esperado
3. Metodologia e plano de execução do período prorrogado
   3.1 Consolidação e publicação científica do software (ZebTrack-AI)
   3.2 Identificação individual dos animais (rastreamento longitudinal e persistência de identidade)
   3.3 Estudos de interação social e comportamento gregário (métricas e validação)
   3.4 Módulo de análise em período noturno (baixa luminosidade) e novos etogramas
   3.5 Validação colaborativa com pesquisadores do grupo e replicabilidade
4. Cronograma de execução (12 meses)
5. Bibliografia

---

## 1. Resumo do pedido de prorrogação excepcional (aceita)

Este documento formaliza a **prorrogação excepcional**, submetida e **já aceita**, para a
continuidade do projeto FAPESP (Processo 2023/14200-3) além do limite usual de **24 meses** de
bolsa, no período de **01/03/2026 a 28/02/2027**.

A necessidade de prorrogação excepcional decorre do amadurecimento e expansão do eixo mais
inovador do projeto ao longo de sua execução: o desenvolvimento do **ZebTrack-AI** como uma
plataforma prática, reprodutível e escalável para rastreio automatizado e análise etológica de
*Danio rerio*.

Durante o desenvolvimento, surgiram demandas científicas e técnicas que **não eram plenamente
previsíveis no início**, mas que se mostraram essenciais para alcançar um nível de excelência
compatível com a complexidade do comportamento do zebrafish e com o padrão de publicação
internacional esperado. Entre essas demandas, destacam-se:

**Esclarecimento (alinhamento com o estado atual do software):** ao longo do período regular,
foram implementadas e consolidadas melhorias que inicialmente eram tratadas como “mudanças”
de escopo (ex.: automação de partes do fluxo, melhorias de interface e módulos de processamento).
Assim, a **prorrogação excepcional** não se justifica por “iniciar uma GUI” ou “criar do zero”
automações já existentes, mas por concluir o ciclo de excelência: **empacotamento/ distribuição
para terceiros**, documentação voltada ao público-alvo, validações rigorosas (incluindo cruzadas)
e módulos etológicos avançados.

- **Identificação individual persistente** dos animais ao longo do tempo, para rastreio confiável de
  indivíduos (não apenas “detecção por quadro”), essencial para estudos longitudinais e para
  análise de variabilidade intraindividual.
- **Métricas de interação social e comportamento gregário**, fundamentais para ampliar a
  relevância etológica do sistema (cohesion, distância interindividual, liderança/seguimento,
  alinhamento, aproximações/evitações), tornando o software capaz de responder a perguntas
  científicas mais sofisticadas.
- **Ampliação do software para o período noturno** (baixa luminosidade), permitindo investigar
  alterações comportamentais e etos em condições de escuro/penumbra, com impacto direto na
  interpretação de efeitos farmacológicos e de estressores sobre o ciclo de atividade.

Essas frentes se conectam diretamente ao objetivo de produzir um **artigo técnico-científico
robusto sobre o software** (metodologia, validação, desempenho, replicabilidade, limitações e
casos de uso), e não apenas um relato de “ferramenta auxiliar” do projeto.

---

## 2. Justificativas técnico-científicas e de mérito

### 2.1 Por que a prorrogação excepcional é essencial para atingir excelência

O projeto evoluiu de um pipeline de rastreio orientado a uma pergunta experimental específica
(CBD e estresse) para uma plataforma de análise comportamental baseada em IA com potencial
reutilizável, auditável e ampliável para múltiplas linhas do laboratório.

A prorrogação excepcional é essencial porque, para que o ZebTrack-AI alcance excelência e
utilidade real para a comunidade, é necessário concluir um ciclo completo de engenharia e
validação científica que inclua:

1. **Funções avançadas que surgiram durante o desenvolvimento** (identidade individual,
   interação social/gregarismo e módulo noturno), tornando o sistema apto a responder a
   perguntas etológicas mais exigentes.
2. **Validação rigorosa com múltiplos pesquisadores do grupo**, incluindo testes cruzados
   (diferentes aparatos, diferentes rotinas de gravação, diferentes operadores) para garantir
   replicabilidade.
3. **Padronização de protocolos e documentação** (configuração, aquisição de dados,
   armazenamento, parâmetros, exportação e análise), condição necessária para publicação
   adequada do software como método.
4. **Integração de desempenho e robustez** (velocidade, estabilidade, controle de qualidade dos
   dados, tratamento de casos difíceis), requisito para que o software seja confiável em estudos
   com grandes n e com protocolos longos.

Além disso, surgiu recentemente uma oportunidade técnica relevante: no início deste ano foi
publicado o **YOLOv26**. Isso se alinha diretamente ao objetivo de **acessibilidade** do
ZebTrack-AI, pois pode viabilizar que o pesquisador rode o pipeline com maior eficiência em
seu **próprio computador**, reduzindo a necessidade de placas gráficas dedicadas e de alto
custo (ex.: GPUs NVIDIA ou Intel e/ou soluções específicas pouco disponíveis no contexto de pesquisa no
Brasil). Em um cenário de recursos limitados para aquisição de hardware, essa evolução é
essencial para ampliar o número de pesquisadores que poderão utilizar a ferramenta e para
diminuir o tempo exigido em processamento/iterações.

Em síntese, a prorrogação não é apenas “tempo adicional”, mas a condição necessária para
concluir o software como produto científico validado, elevando a qualidade dos resultados
comportamentais e o alcance do investimento já realizado.

**Evidência de avanço mensurável e a relação com recursos computacionais pagos:**

No período de desenvolvimento, o desempenho do modelo de detecção de zebrafish evoluiu de
forma mensurável na validação (Roboflow), por exemplo ao comparar versões recentes:

- **ZebraFish Detection 14:** mAP@50 90,2%; Precisão 91,6%; Recall 86,6%.
- **ZebraFish Detection 15 (YOLOv11, v15):** mAP@50 96,5%; Precisão 96,4%; Recall 94,1%.

Isso corresponde a ganhos de **+6,3 p.p.** (mAP@50), **+4,8 p.p.** (Precisão) e **+7,5 p.p.**
(Recall), com impacto direto na confiabilidade do rastreio (menos perdas e menos falsos
eventos), o que é decisivo quando o sistema é parte do método experimental (detecção → evento
→ estímulo → logs).

Para alcançar esse patamar, foi necessário sustentar ciclos de melhoria que demandam
infraestrutura: expansão e curadoria de dataset em larga escala, treinamento com mais épocas,
validação frequente e iteração rápida sobre parâmetros e falhas reais do aparato (reflexos,
ondulações, baixa luz, oclusões). Nesse contexto, **assinaturas, créditos e unidades
computacionais** (p.ex., nuvem para treino e ferramentas de produtividade para desenvolvimento)
foram essenciais para manter um ritmo de iteração compatível com o cronograma do projeto.

Esse ponto é ainda mais relevante considerando a realidade de um bolsista no **4º ano de
Medicina**, com carga acadêmica intensa: sem esses recursos, o custo em tempo de treinamento,
debug e reprocessamento tornaria inviável a maturação do software no nível de excelência
necessário para publicação apropriada e adoção por outros pesquisadores.

### 2.2 Por que a não concessão inviabilizaria resultados no nível de excelência esperado

A não continuidade do período prorrogado comprometeria de forma direta e prática:

- **A publicação apropriada de um artigo sobre o software**: sem tempo para implementar e
  validar as funções de alto impacto (ID individual, interação social e módulo noturno), o artigo
  ficaria limitado a uma descrição parcial do pipeline, com menor relevância e menor capacidade
  de generalização.
- **A excelência na análise etológica**: o zebrafish é um modelo com forte componente social e
  com comportamento dependente de condições ambientais e de ciclo claro/escuro. Sem essas
  extensões, o software fica restrito a análises menos completas, reduzindo o valor científico do
  sistema.
- **A validação colaborativa e reprodutibilidade**: concluir apenas com validações internas e
  pontuais limita a confiança nos dados e impede que colegas do grupo adotem a plataforma em
  projetos paralelos, reduzindo o impacto institucional do desenvolvimento.

Assim, a prorrogação excepcional é indispensável para evitar que um avanço metodológico
substantivo se encerre prematuramente, impedindo o pleno aproveitamento da inovação
construída.

---

## 3. Metodologia e plano de execução do período prorrogado

### 3.1 Consolidação e publicação científica do software (ZebTrack-AI)

No período prorrogado, o software será consolidado como método científico por meio de:

- Padronização de entradas/saídas e logs para rastreio e análise (reprodutibilidade e auditoria).
- Organização do fluxo de trabalho (configuração, execução, exportações e relatórios).
- Definição de critérios mínimos de qualidade dos dados (ex.: métricas de consistência do
  rastreio, detecção de perdas de trajetória e alertas).
- Produção de material para publicação: descrição metodológica, experimentos de validação,
  análise de limitações e recomendações de uso.
- Preparação do software para uso por terceiros no formato “modo laboratório”: empacotamento,
  distribuição, *presets* por protocolo e geração de um *bundle* reprodutível (configurações,
  versões e pesos utilizados) para auditoria e replicação.
- Redação de documentação voltada ao público-alvo (pesquisadores e laboratórios), incluindo
  guias de uso, tutoriais do fluxo (wizard → projeto → relatórios) e recomendações de qualidade.

O objetivo é permitir um artigo focado no software como ferramenta científica, com resultados de
validação e aplicabilidade em etologia e neuropsicofarmacologia.

### 3.2 Identificação individual dos animais (rastreamento longitudinal e persistência de identidade)

Para ampliar a capacidade científica do ZebTrack-AI, será desenvolvida uma camada que permita
associar uma **identidade persistente** aos animais ao longo do tempo, essencial para:

- Estudos longitudinais indivíduo-a-indivíduo.
- Redução de ambiguidades em cruzamentos, oclusões e aproximações.
- Extração de métricas individuais confiáveis (velocidade, freezing, padrões espaciais,
  preferências, latências, etc.).

Estratégia de implementação e validação (em alto nível, sem restringir a uma única abordagem):

- Melhorias no rastreio multiobjeto (consistência temporal e tratamento de oclusões).
- Uso de descritores visuais/temporais (quando aplicável) para reduzir trocas de identidade.
- Geração de métricas de qualidade e rotinas de checagem para quantificar a estabilidade de
  identidade ao longo do vídeo.
- Testes controlados com vídeos em condições progressivamente mais difíceis (densidade de
  animais, iluminação, reflexos, ruído, variações de aparato).

### 3.3 Estudos de interação social e comportamento gregário (métricas e validação)

Com a identificação individual e rastreio robusto, será possível ampliar o software para análises
etológicas de maior relevância, com foco em comportamento gregário e interação social.

O plano contempla:

- Definição e implementação de métricas sociais clássicas e aplicáveis ao aparato do laboratório
  (distâncias interindividuais, coesão, vizinhança, aproximação/afastamento, sincronização de
  movimento, liderança/seguimento e padrões de agrupamento).
- Construção de saídas padronizadas para análise estatística longitudinal (R), mantendo
  compatibilidade com estudos anteriores.
- Validação com experimentos de referência do grupo e comparação com análises manuais ou
  semiautomáticas quando necessário.

### 3.4 Módulo de análise em período noturno (baixa luminosidade) e novos etogramas

O período noturno representa uma janela de comportamento relevante e, frequentemente, pouco
explorada por limitações metodológicas. A prorrogação viabiliza:

- Desenvolvimento de um modo de aquisição e/ou processamento para **baixa luminosidade**
  (incluindo ajustes do pipeline e testes de robustez).
- Definição de rotinas para avaliar alterações comportamentais noturnas (atividade, repouso,
  exploração, padrões espaciais e possíveis mudanças de interação social).
- Ampliação do etograma digital com eventos associados ao contexto noturno.

Essa frente é diretamente alinhada ao objetivo de “levar o estudo etológico de zebrafish a outro
nível de excelência, automação e eficácia”, com evidências quantitativas e reprodutíveis.

### 3.5 Validação colaborativa com pesquisadores do grupo e replicabilidade

As novas funções propostas surgiram ao longo do desenvolvimento do software e serão
consolidadas com uma etapa dedicada de validação colaborativa:

- Sessões de testes com colegas pesquisadores do grupo, para avaliar usabilidade e robustez em
  cenários reais (diferentes operadores e rotinas).
- Coleta de feedback estruturado e ajustes de interface/fluxo (sem perder reprodutibilidade).
- Validação de consistência dos resultados e comparação entre execuções.

O objetivo é garantir que o ZebTrack-AI seja efetivamente utilizável, confiável e replicável, e que
as evidências sejam suficientes para suportar publicação metodológica sólida.

Além da validação multioperador, quando aplicável, será conduzida **validação cruzada** com
outros programas/pipelines em vídeos comuns, para quantificar concordância, limites e cenários
de falha (e documentar recomendações de uso).

---

## 4. Cronograma de execução (12 meses)

| Etapas | 2026 |  |  |  |  |  |  |  |  |  | 2027 |  |
| ----- | ---- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---- | --- |
| Atividades/mês | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 1 | 2 |
| Consolidação do software e preparação de manuscrito metodológico | ∙ | ∙ | ∙ | ∙ | ∙ | ∙ |  |  |  |  |  |  |
| Implementação e testes de identificação individual (persistência de identidade) |  | ∙ | ∙ | ∙ | ∙ | ∙ | ∙ |  |  |  |  |  |
| Desenvolvimento de métricas de interação social e comportamento gregário |  |  | ∙ | ∙ | ∙ | ∙ | ∙ | ∙ |  |  |  |  |
| Módulo de análise noturna (baixa luminosidade) + novos etogramas |  |  |  | ∙ | ∙ | ∙ | ∙ | ∙ | ∙ |  |  |  |
| Validação colaborativa com pesquisadores do grupo (replicabilidade/usabilidade) |  |  |  |  |  | ∙ | ∙ | ∙ | ∙ | ∙ |  |  |
| Finalização, submissão e divulgação (software + resultados aplicados) |  |  |  |  |  |  |  |  | ∙ | ∙ | ∙ | ∙ |

---

## 5. Bibliografia

AL-ZOUBI, R. M. et al. Zebrafish model in illuminating the complexities of post-traumatic stress
disorders: a unique research tool. **International Journal of Molecular Sciences**, v. 25, n. 9,
2024.

BORBA, J. V. et al. Towards zebrafish models to unravel translational insights of obsessive
compulsive disorder: A neurobehavioral perspective. **Neuroscience and Biobehavioral Reviews**,
v. 162, 2024.

BOZHKO, D. V. et al. Artificial intelligence-driven phenotyping of zebrafish psychoactive drug
responses. **Progress in Neuro-Psychopharmacology and Biological Psychiatry**, v. 112, 2022.

BROWN, A. E. X.; DE BIVORT, B. Ethology as a physical science. **Nature Physics**, v. 14, 2018.

LUKIVIKOV, D. A. et al. A novel open-access artificial-intelligence-driven platform for CNS drug
discovery utilizing adult zebrafish. **Journal of Neuroscience Methods**, v. 411, 2024.

MATHIS, A. et al. DeepLabCut: markerless pose estimation of user-defined body parts with deep
learning. **Nature Neuroscience**, v. 21, 2018.

PASZKE, A. et al. **PyTorch: An Imperative Style, High-Performance Deep Learning Library**.
arXiv, 2019. Disponível em: <https://arxiv.org/abs/1912.01703>.

PINHEIRO-DA-SILVA, J. et al. ZebTrack: software base para análise comportamental automatizada
em zebrafish. 2017.

PÉREZ-ESCUDERO, A. et al. idTracker: tracking individuals in a group by automatic
identification of unmarked animals. **Nature Methods**, v. 11, 2014.

REDMON, J. et al. You Only Look Once: Unified, Real-Time Object Detection. arXiv, 2015.
Disponível em: <https://arxiv.org/abs/1506.02640>.

SCHNEIDER, C. A.; RASBAND, W. S.; ELICEIRI, K. W. NIH Image to ImageJ: 25 years of image
analysis. **Nature Methods**, v. 9, 2012.

SPENCE, R. et al. The behaviour and ecology of the zebrafish, *Danio rerio*. **Biological Reviews**,
v. 83, 2008.

WANG, L. et al. Advances in zebrafish as a comprehensive model of mental disorders.
**Depression and Anxiety**, v. 2023, 2023.
