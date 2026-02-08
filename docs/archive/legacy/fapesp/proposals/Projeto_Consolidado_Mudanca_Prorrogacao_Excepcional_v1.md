**EFEITO DO CANABIDIOL SOBRE ESTRESSE E MEMÓRIA AVERSIVA APÓS ESTRESSE AGUDO E INTENSO EM ZEBRAFISH**

**PROPOSTA CONSOLIDADA (MUDANÇA + PRORROGAÇÃO EXCEPCIONAL)**

Projeto de Iniciação Científica em graduação em

Medicina da Universidade Estadual Paulista do

campus de Botucatu – FMB/UNESP

**Bolsista:** Marco Antônio Sant’ Ana Camargos

**Orientadora:** Profª. Drª. Percília Cardoso Giaquinto

**Processo:** 2023/14200-3

**Vigência original da bolsa:** 01/03/2024 à 28/02/2026 (24 meses)

**Período de prorrogação excepcional (12 meses):** 01/03/2026 à 28/02/2027

Botucatu, São Paulo

2026

Processo FAPESP nº 2023/14200-3

---

## Nota explicativa (por que existiam dois documentos)

Foram produzidos dois arquivos por um motivo **administrativo e temporal**:

1) **Proposta de Mudança (2025)**: foi escrita para registrar formalmente uma **mudança/expansão de escopo** ainda dentro da lógica de execução do projeto (ampliação da metodologia e do software), incluindo itens como ampliação do dataset, autodetecção de áreas e interface gráfica.

2) **Proposta de Prorrogação Excepcional (2026)**: foi escrita para justificar um **período adicional além do limite usual de 24 meses**, com foco em consolidar o ZebTrack-AI como **produto científico publicável** (paper de software) e implementar módulos de etologia avançada (identidade individual persistente, interação social/gregarismo e análise noturna).

Na prática, ambas as propostas apontavam para o mesmo objetivo maior: **elevar a excelência metodológica** e maximizar o retorno científico do investimento já realizado. Este documento consolida os dois textos em uma versão única, mais coerente e completa.

---

## Sumário

1. Resumo da proposta consolidada
2. Justificativa técnico-científica (por que a consolidação é necessária)
3. Mudanças e aperfeiçoamentos propostos (escopo do projeto)
   3.1 Ampliação do dataset e treinamento da IA em novas perspectivas
   3.2 Autodetecção de áreas de interesse (redução de etapa manual)
   3.3 Processamento de vídeos pré-gravados (módulo offline/lote)
   3.4 Interface gráfica (GUI) para acessibilidade e replicabilidade
   3.5 Integração com marcadores fisiológicos/genômicos (cortisol, RT-qPCR/ELISA)
4. Plano do período prorrogado (12 meses) – entregáveis de excelência
   4.1 Consolidação e publicação científica do software (ZebTrack-AI)
   4.2 Identificação individual persistente (rastreio longitudinal)
   4.3 Interação social e comportamento gregário (métricas e validação)
   4.4 Módulo noturno (baixa luminosidade) e novos etogramas
   4.5 Validação colaborativa e reprodutibilidade (multioperador)
5. Evidências de avanço mensurável (métricas e infraestrutura)
6. Cronograma consolidado
7. Bibliografia

---

## 1. Resumo da proposta consolidada

Esta proposta consolida, em um único documento, as **mudanças metodológicas** e o **plano do período prorrogado** necessários para concluir o projeto com o nível de excelência esperado.

O eixo experimental (CBD e estresse/TEPT em zebrafish) permaneceu central; porém, ao longo da execução, a pesquisa exigiu o amadurecimento de um eixo metodológico inovador: o desenvolvimento do **ZebTrack-AI** como plataforma prática, reprodutível e escalável para rastreio por IA e análise etológica de *Danio rerio*.

O objetivo é: (i) fortalecer a qualidade dos dados comportamentais (menos falhas, maior robustez a oclusões/baixa luz), (ii) ampliar as possibilidades etológicas (social/gregarismo e noite), (iii) concluir validações e documentação, e (iv) viabilizar a publicação adequada de um **manuscrito metodológico do software**.

---

## 2. Justificativa técnico-científica (por que a consolidação é necessária)

O projeto evoluiu de um pipeline de rastreio ligado a uma pergunta específica para uma plataforma com potencial de uso transversal no laboratório. Essa expansão foi **cientificamente necessária** porque:

- O comportamento do zebrafish é altamente dependente de contexto (ambiente, ciclo claro/escuro) e possui componente social relevante.
- Resultados robustos exigem rastreio confiável em condições reais (reflexos, ondulações, oclusões, variações de aparato e iluminação).
- Para que o software seja publicável como método (e útil a outros pesquisadores), é indispensável concluir um ciclo de engenharia: padronização, documentação, validação multioperador e módulos avançados.

Além disso, surgiu uma oportunidade técnica relevante: a publicação do **YOLOv26** no início deste ano, com potencial para melhorar **acessibilidade** (mais eficiência em hardware local e menor dependência de GPUs caras), o que é particularmente importante no contexto de pesquisa no Brasil.

---

## 3. Mudanças e aperfeiçoamentos propostos (escopo do projeto)

### 3.1 Ampliação do dataset e treinamento da IA em novas perspectivas

- Expansão do dataset para incluir novas condições reais de aquisição e **perspectiva lateral**, além da superior.
- Rotulagem manual de imagens e treino/validação em ciclos, monitorando métricas como mAP@50, precisão e recall.

### 3.2 Autodetecção de áreas de interesse (redução de etapa manual)

- Evolução do pipeline para reconhecer automaticamente áreas/zonas do aquário (reduzindo ajustes manuais).
- Objetivo: aumentar replicabilidade e reduzir variância introduzida por operador.

### 3.3 Processamento de vídeos pré-gravados (módulo offline/lote)

- Implementação de modo para processamento de vídeos já existentes (reprocessamento de acervo e comparação entre protocolos).
- Geração de logs padronizados automaticamente, permitindo auditoria e reanálises rápidas.

### 3.4 Interface gráfica (GUI) para acessibilidade e replicabilidade

- Consolidação de uma interface para configuração e execução do pipeline sem necessidade de linha de comando.
- Objetivo: permitir que pesquisadores do grupo adotem a plataforma com menor curva de aprendizagem.

### 3.5 Integração com marcadores fisiológicos/genômicos (cortisol, RT-qPCR/ELISA)

- Aquisição/uso de kits e rotinas para cortisol e marcadores associados à neuroinflamação (IL-1β, IL-6, IFN-γ, TNF-α, BDNF).
- Integração com o eixo comportamental para fortalecer interpretação translacional.

---

## 4. Plano do período prorrogado (12 meses) – entregáveis de excelência

### 4.1 Consolidação e publicação científica do software (ZebTrack-AI)

- Padronização de entradas/saídas, logs e critérios de qualidade.
- Documentação de configuração, aquisição, armazenamento, parâmetros e exportação.
- Preparação de manuscrito metodológico: validação, desempenho, limitações e casos de uso.

### 4.2 Identificação individual persistente (rastreio longitudinal)

- Desenvolvimento de rotinas para reduzir trocas de identidade e lidar com oclusões.
- Métricas de qualidade para estabilidade de identidade ao longo do vídeo.

### 4.3 Interação social e comportamento gregário (métricas e validação)

- Implementação de métricas sociais aplicáveis ao aparato (distância interindividual, coesão, alinhamento, liderança/seguimento, aproximação/evitação).
- Saídas padronizadas para análise longitudinal em R.

### 4.4 Módulo noturno (baixa luminosidade) e novos etogramas

- Ajustes do pipeline para baixa luminosidade e testes de robustez.
- Avaliação de padrões noturnos (atividade/repouso, exploração e possíveis mudanças sociais).

### 4.5 Validação colaborativa e reprodutibilidade (multioperador)

- Sessões de teste com pesquisadores do grupo, coleta de feedback e ajustes de fluxo.
- Validação cruzada entre operadores e rotinas, garantindo replicabilidade.

---

## 5. Evidências de avanço mensurável (métricas e infraestrutura)

O desenvolvimento recente mostrou ganhos mensuráveis no desempenho do modelo de detecção em validação (Roboflow), por exemplo:

- **ZebraFish Detection 14:** mAP@50 90,2%; Precisão 91,6%; Recall 86,6%.
- **ZebraFish Detection 15 (YOLOv11):** mAP@50 96,5%; Precisão 96,4%; Recall 94,1%.

Isso representa ganhos de **+6,3 p.p.** (mAP@50), **+4,8 p.p.** (Precisão) e **+7,5 p.p.** (Recall), com impacto direto na confiabilidade do rastreio e, portanto, na qualidade do método experimental (detecção → evento → estímulo → logs).

Para sustentar ciclos de melhoria desse tipo, foram necessários recursos para curadoria/expansão de dataset, treinamento, validações frequentes e iteração rápida. Esse ponto é ainda mais importante considerando a realidade do bolsista no **curso de Medicina**, com carga acadêmica intensa: sem infraestrutura e ferramentas de produtividade, o custo em tempo de treino/reprocessamento comprometeria a maturação do software no nível exigido.

---

## 6. Cronograma consolidado

### 6.1 Cronograma do período prorrogado (12 meses: 03/2026–02/2027)

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

## 7. Bibliografia

AL-ZOUBI, R. M. et al. Zebrafish model in illuminating the complexities of post-traumatic stress disorders: a unique research tool. **International Journal of Molecular Sciences**, v. 25, n. 9, 2024.

BORBA, J. V. et al. Towards zebrafish models to unravel translational insights of obsessive compulsive disorder: A neurobehavioral perspective. **Neuroscience and Biobehavioral Reviews**, v. 162, 2024.

BOZHKO, D. V. et al. Artificial intelligence-driven phenotyping of zebrafish psychoactive drug responses. **Progress in Neuro-Psychopharmacology and Biological Psychiatry**, v. 112, 2022.

BROWN, A. E. X.; DE BIVORT, B. Ethology as a physical science. **Nature Physics**, v. 14, 2018.

LIN, T.-Y. et al. **Microsoft COCO: Common Objects in Context**. arXiv, 2014. Disponível em: <https://arxiv.org/abs/1405.0312>.

LUKIVIKOV, D. A. et al. A novel open-access artificial-intelligence-driven platform for CNS drug discovery utilizing adult zebrafish. **Journal of Neuroscience Methods**, v. 411, 2024.

MATHIS, A. et al. DeepLabCut: markerless pose estimation of user-defined body parts with deep learning. **Nature Neuroscience**, v. 21, 2018.

PASZKE, A. et al. **PyTorch: An Imperative Style, High-Performance Deep Learning Library**. arXiv, 2019. Disponível em: <https://arxiv.org/abs/1912.01703>.

PÉREZ-ESCUDERO, A. et al. idTracker: tracking individuals in a group by automatic identification of unmarked animals. **Nature Methods**, v. 11, 2014.

PINHEIRO-DA-SILVA, J. et al. ZebTrack: software base para análise comportamental automatizada em zebrafish. 2017.

REDMON, J. et al. You Only Look Once: Unified, Real-Time Object Detection. arXiv, 2015. Disponível em: <https://arxiv.org/abs/1506.02640>.

WANG, L. et al. Advances in zebrafish as a comprehensive model of mental disorders. **Depression and Anxiety**, v. 2023, 2023.
