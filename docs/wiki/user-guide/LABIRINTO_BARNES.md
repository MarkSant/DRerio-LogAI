# Labirinto de Barnes (ratos)

Guia de uso do protocolo de Barnes, introduzido na versão 8.1 (#633). Para os detalhes técnicos,
veja [`docs/tasks/v8.1/barnes/`](../../tasks/v8.1/barnes/).

## 1. Criar o projeto

1. No assistente de criação, na primeira etapa, abra **Perfil do Experimento** e escolha
   **Modelo animal: Roedor (rato ou camundongo)** e **Protocolo: Labirinto de Barnes
   (roedores)**. Ou carregue o template embutido **Barnes maze (rat)**.
2. O Barnes fixa a vista de cima, analisa todo quadro (`analysis_interval_frames = 1`) e já cria
   a janela de análise com a predefinição Barnes v2.
3. Na **Calibração**, informe o **Diâmetro da mesa (cm)** (padrão 184 cm). Ele vale para largura
   e altura.
4. Escolha o peso de detecção do rato. O peso precisa ter as classes `arena`, `experimenter`,
   `rat` e `start_box` com papéis definidos (arena, contexto, sujeito, contexto).

Para um vídeo avulso ou uma sessão ao vivo sem projeto, os mesmos dois campos aparecem no diálogo
de configuração.

## 2. Desenhar a arena com o Assistente Barnes

Na aba **Zonas**, o botão **Assistente Barnes** aparece só em projetos Barnes.

1. **Mesa:** **Detectar mesa (auto)** usa a classe `arena` do peso; se não servir, clique em 5 ou
   mais pontos da borda da mesa.
2. **Toca:** clique no buraco em que o rato consegue entrar (**Clicar na toca**). O app distribui
   os buracos em volta da mesa, encaixa cada um no buraco escuro real e mostra a prévia.
3. **Número de buracos:** o assistente testa 18 e 20 e mostra o resultado ("detectado: N ·
   projeto: M"). A mesa atual do laboratório tem 18. Se a contagem detectada for diferente da do
   projeto, ele pergunta antes de mudar.
4. **Tipo de ensaio:** **Treino** ou **Teste (probe)**, por vídeo.
5. **Aplicar.** São criadas a arena, a ROI `quadrante_alvo` (a fatia com a toca e mais dois
   buracos de cada lado), a ROI `toca` e uma ROI por buraco-isca, nomeada pela distância à toca
   (`buraco_+01`, `buraco_-01`, …, `buraco_oposto`; positivo = sentido horário).
6. **Aplicar a outros vídeos…** copia o desenho e refaz o encaixe em cada vídeo. Na memória
   operacional, em que a toca muda a cada dia, clique a toca de cada vídeo. Uma cópia duvidosa vai
   para revisão manual, e um vídeo com enquadramento diferente não é gravado.

Não renomeie essas ROIs: os nomes são o que as métricas leem.

## 3. Como o app decide encontro e entrada

- **Início:** a caixa de partida e o experimentador saem de cena e o rato está visível.
- **Encontro (nose poke):** o primeiro quadro em que o rato cobre parte do disco da toca.
- **Entrada (quatro patas):** o rato fica majoritariamente sobre a toca e visivelmente menor do
  que no resto do ensaio (parte do corpo já dentro do buraco) por meio segundo, ou some com a
  última posição na toca. Sem entrada, a latência é 240 s, marcada como censurada.

A janela de análise fecha na entrada, não no primeiro toque. Uma janela criada antes da 8.1 (v1)
continua valendo; no editor da janela, **Atualizar para a predefinição Barnes v2…** explica o que
muda antes de trocar.

## 4. Resultados

- **Relatório individual (`.docx`):** a seção do Barnes traz as latências (censuradas aparecem
  como "≥ 240 s"), os erros primários, totais e perseverativos, a estratégia de busca, o tempo no
  quadrante-alvo e, no probe, o score do primeiro buraco, a latência do primeiro erro e as
  tentativas. Inclui um diagrama dos buracos com a ordem das visitas e a trajetória numerada.
- **Planilha (`.xlsx`):** colunas `barnes_*` e a aba `barnes_visits` com a sequência de visitas.
- **Relatórios parcial e unificado:** curvas de aprendizagem por grupo e dia (média ± EPM),
  distribuição das estratégias e comparação do probe. Latências censuradas são contadas à parte.
- **Corrigir a estratégia:** clique com o botão direito no vídeo, na árvore de relatórios, e
  escolha a estratégia. O relatório marca o valor como "corrigido manualmente"; gere o relatório
  de novo depois de corrigir.

## 5. Calibrar contra a pontuação manual

Os limiares de visita e de entrada são provisórios até serem comparados com a pontuação manual
do laboratório. O passo a passo, incluindo o que exportar das planilhas, está em
[`VALIDATION.md`](../../tasks/v8.1/barnes/VALIDATION.md). O comando de partida é:

```bash
python scripts/barnes_validation.py init-mapping --out mapeamento.yaml
```

## 6. Limites conhecidos

- Um ensaio por vídeo.
- Uma arena com um animal (multi-aquário não é suportado no Barnes).
- Se a caixa de detecção inclui a cauda, a entrada pode ser detectada mais tarde ou não ser
  detectada.
- Os padrões do roedor (congelamento 2,0 cm/s por 1,0 s) são provisórios.
