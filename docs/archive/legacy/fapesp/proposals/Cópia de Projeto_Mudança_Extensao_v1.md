**EFEITO DO CANABIDIOL SOBRE ESTRESSE E MEMÓRIA AVERSIVA  APÓS ESTRESSE AGUDO E INTENSO EM ZEBRAFISH**

**PROPOSTA DE MUDANÇA**

Projeto de Iniciação Científica em graduação em

Medicina da Universidade Estadual Paulista do

campus de Botucatu – FMB/UNESP

**Bolsista:** Marco Antônio Sant’ Ana Camargos

**Orientadora:** Profª. Drª. Percília Cardoso Giaquinto

**Processo:** 2023/14200-3

Botucatu, São Paulo

2025
Processo FAPESP nº 2023/14200-3

Sumário

1\. Resumo do projeto proposto .............................................................................. 3 2\. Metodologia....................................................................................................... 3 2.1 Ampliação do Dataset e Treinamento da IA em Novas Perspectivas ............. 3 2.2 Implementação de Autodetecção de Áreas de Interesse.............................. 4 2.3 Adaptação para Vídeos Pré-Gravados ......................................................... 4 2.4 Desenvolvimento de Interface Gráfica (GUI)................................................ 4 2.5 Conclusão do Projeto Inicial e Etapas Finais................................................ 4 3\. Cronograma de execução................................................................................... 5 4\. Bibliografia......................................................................................................... 5
Processo FAPESP nº 2023/14200-3

1\. Resumo da proposta de mudança

Esta mudança em projeto propõe a ampliação das técnicas empregadas para análise do  comportamento de zebrafish, com foco em Inteligência Artificial (IA) e novas aplicações  laboratoriais. Primeiramente, será expandido o conjunto de dados para o treinamento da IA em  diferentes ângulos de gravação, possibilitando o reconhecimento dos animais tanto na perspectiva  superior quanto lateral (LUKOVIKOV et al., 2024). Em seguida, a IA será adaptada para  autodetecção de áreas de interesse, reduzindo o trabalho manual e aprimorando a precisão das  análises.

Outra meta relevante é a criação de um módulo capaz de processar vídeos previamente  gravados, permitindo comparações entre protocolos distintos e dispensando ajustes específicos  de gravação. Além disso, o projeto prevê o desenvolvimento de uma interface gráfica (GUI) em  Python, tornando acessíveis a configuração e a execução de rastreamentos comportamentais a  usuários sem domínio em programação (PASZKE et al., 2019).

Para complementar, serão adquiridos kits laboratoriais específicos para mensurar  cortisol e genes associados à neuroinflamação (IL-1β, IL-6, IFN-γ, TNF-α, BDNF), viabilizando  análises de RT-qPCR e ELISA. Com isso, busca-se correlacionar dados comportamentais e  fisiológicos coletados e, ao final, redigir artigos científicos e compartilhar resultados em eventos  acadêmicos.

Por fim, o pesquisador almeja aprofundar seu conhecimento em neurologia e psiquiatria  (AL-ZOUBI et al., 2024\) por meio de estágio internacional (BEPE), integrando a formação médica  e a pesquisa translacional em *Danio rerio*, promovendo avanços na compreensão de desordens  como a Síndrome do Estresse Pós-Traumático.

2\. Metodologia

2.1 Ampliação do Dataset e Treinamento da IA em Novas Perspectivas

Inicialmente, o pesquisador irá ampliar sua base bibliográfica para buscar novas  referências no campo de aprimoramento e treinamento de IA, a fim de exponenciar o trabalho já  feito e elevar a qualidade dos programas já desenvolvidos. Concomitantemente, novas imagens  serão adquiridas em novas gravações de testes e em gravações de outros experimentos para  adicionar a perspectiva lateral dos animais ao aprendizado da IA (BOZHKO et al., 2022), em  seguida, as imagens serão rotuladas com anotações manuais, definindo caixas delimitadoras e  parâmetros de classe, segundo protocolo semelhante ao já aplicado para a perspectiva superior (LIN et al., 2014).

Uma vez ampliado o dataset, o modelo será reprogramado para incorporar o novo dataset.  Ciclos de 50 a 100 épocas de treinamento serão conduzidos, com validação cruzada para evitar  overfitting. A cada 10 épocas, a acurácia e o recall serão verificados, de tal modo que métricas  como mAP (mean Average Precision), precision e recall serão analisadas e comparadas (REDMON et al., 2015). Caso os resultados indiquem instabilidade, parâmetros como taxa de  aprendizado ou profundidade das camadas da rede serão ajustados.
Processo FAPESP nº 2023/14200-3

2.2 Implementação de Autodetecção de Áreas de Interesse

A IA e o programa que a controla serão adaptados e treinados para reconhecer  automaticamente as áreas de teste nos aquários, eliminando a necessidade de ajustar  parâmetros manualmente. Uma abordagem de aprendizado contínuo será aplicada, em que o  modelo atual é refinado com os dados anotados em diferentes formatos de aquário, assegurando  a flexibilidade de seu uso e precisão na detecção (BORBA et al., 2024).

2.3 Adaptação para Vídeos Pré-Gravados

Um novo módulo será incluído no programa desenvolvido a fim de que ele seja capaz de  aceitar múltiplos formatos de vídeo gravados *a priori*, gerando arquivos de log padronizados  automaticamente. Esse software executará o rastreamento quadro a quadro em vídeos já  existentes, permitindo estudos comparativos entre dados pré e pós-tratamento ou protocolos de  estresse distintos (WANG et al., 2023).

Importa informar que, uma vez adaptada e treinada a IA para reconhecer áreas de interesse nos aquários, os pesquisadores poderão processar qualquer experimento prévio que tenha sido  efetuado ou reavaliar informações de experimentos em progresso, sem a necessidade de adequar  o ângulo de gravação ou formato do aquário.

2.4 Desenvolvimento de Interface Gráfica (GUI)

A interface será elaborada em Python (PyQt ou Tkinter), com menus de configuração para  seleção de dataset, ângulo de gravação e parâmetros de exportação, além de permitir a  configuração de parâmetros outros, análise de dados e construção de arquitetura de  armazenagem de dados.

Além disso, para dispensar o uso de linha de comando, o software oferecerá  configurações personalizáveis de FPS, duração da gravação e tolerância de detecção sem  requerer conhecimentos avançados de programação.

2.5 Conclusão do Projeto Inicial e Etapas Finais

Com a reserva técnica ampliada e a extensão do tempo de pesquisa, serão adquiridos kits  específicos para dosagens de cortisol e análise de genes associados à neuroinflamação (IL-1β,  IL-6, IFN-γ, TNF-α, BDNF). Serão realizadas análises de RT-qPCR e ELISA, correlacionando  marcadores fisiológicos e comportamentais com as amostras já coletadas e preservadas em  congelamento.

Outrossim, os dados consolidados (comportamentais e moleculares) serão processados em  softwares estatísticos (R ou SPSS), para análise, interpretação e redação de artigos, publicizando  os atuais achados. Igualmente, a metodologia criada até aqui e os softwares já desenvolvidos serão preparados para publicação o quanto antes de modo a ser possível divulgar os resultados  em eventos acadêmicos e disponibilizar a tecnologia para mais departamentos no país que  utilizem *Danio rerio* em pesquisas comportamentais. Os novos dados obtidos e a aprimoração  dos softwares feitos dentro desta extensão do projeto e da pesquisa serão preparados para  divulgação e disponibilização o quanto antes.

Digno de nota, também, é a intenção do pesquisador de ampliar sua experiência e base de  conhecimentos no campo da neurologia, psiquiatria e neuroinflamação em um possível estágio  fora do país com especialistas na área de tratamento de pacientes com Síndrome do Estresse  Pós-Traumático, Cannabis e outros possíveis fármacos e doenças mentais correlacionadas com
Processo FAPESP nº 2023/14200-3

o uso da Bolsa Estágio de Pesquisa no Exterior (BEPE), avançando ainda mais na compreensão,  aprimoramento e análise do modelo a proposto de modo translacional aos animais, unindo sua  atual formação em Medicina e a pesquisa em Medicina Translacional com *Danio rerio.*

3\. Cronograma de execução

| Etapas  | 2025  |  |  |  |  |  |  |  |  |  | 2026 |  |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| Atividades/mês  | 3  | 4  | 5  | 6  | 7  | 8  | 9  | 10  | 11  | 12  | 1  | 2 |
| Análise dados já coletados e publicação  | ∙  | ∙  | ∙  | ∙  | ∙  | ∙ |  |  |  |  |  |  |
| Aprimoramento da bibliografia  | ∙  | ∙ |   |  |  |  |  |  |  |  |  |  |
| Ampliação do dataset  |  | ∙  | ∙  | ∙ |   |   |   |  |  |  |  |  |
| Treinamento da IA  |  |  |  | ∙  | ∙  | ∙  | ∙  |  |   |  |  |  |
| Adaptação de código para processar arquivos  |  |  |  |  |  | ∙  | ∙  | ∙  | ∙  | ∙ |  |  |
| Adaptação de código para nova interface  gráfica  |  |  |  |  |  |  |  | ∙  | ∙  | ∙ |   |  |
| Novas Publicações sobre aprimoramentos e  resultados |  |  |  |  |  |  |  |  |   | ∙  | ∙  | ∙ |

4\. Bibliografia

AL-ZOUBI, R. M. et al. Zebrafish model in illuminating the complexities of post-traumatic stress  disorders: a unique research tool. **International Journal of Molecular Sciences**, v. 25, n. 9, 2024\.

BORBA, J. V. et al. Towards zebrafish models to unravel translational insights of obsessive compulsive disorder: A neurobehavioral perspective. **Neuroscience and Biobehavioral Reviews**,  v. 162, 2024\.

BOZHKO, D. V. et al. Artificial intelligence-driven phenotyping of zebrafish psychoactive drug  responses. **Progress in Neuro-Psychopharmacology and Biological Psychiatry**, v. 112, p.  110405, jan. 2022\.

LIN, T.-Y. et al. **Microsoft COCO: Common Objects in Context**. arXiv, , 2014\. Disponível em:  \<https://arxiv.org/abs/1405.0312\>. Acesso em: 18 fev. 2025
Processo FAPESP nº 2023/14200-3

LUKOVIKOV, D. A. et al. A novel open-access artificial-intelligence-driven platform for CNS drug  discovery utilizing adult zebrafish. **Journal of Neuroscience Methods**, v. 411, p. 110256, nov.  2024\.

PASZKE, A. et al. **PyTorch: An Imperative Style, High-Performance Deep Learning Library**. arXiv,  , 2019\. Disponível em: \<https://arxiv.org/abs/1912.01703\>. Acesso em: 18 fev. 2025

REDMON, J. et al. **You Only Look Once: Unified, Real-Time Object Detection**. arXiv, , 2015\.  Disponível em: \<https://arxiv.org/abs/1506.02640\>. Acesso em: 16 fev. 2025

WANG, L. et al. Advances in zebrafish as a comprehensive model of mental disorders. **Depression  and Anxiety**, v. 2023, 2023\.
