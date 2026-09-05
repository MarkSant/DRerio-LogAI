# Protocolo de teste dos fluxos ao vivo

Como testar os vídeos ao vivo sem regredir os pré-gravados.

## Por que existe este documento

Os dois fluxos pré-gravados — vídeo único e projeto — foram validados de ponta a
ponta na v6.1.0. A rodada anterior de testes ao vivo quebrou os dois e forçou um
reteste completo, através de quatro PRs de conserto (#522, #523, #524, #527).

Não foi descuido. O PR #521 corrigiu o fluxo ao vivo avulso e, para isso, tocou
em arquivos de UI **compartilhados**. Ele declarava compatibilidade por defaults,
e estava certo no nível da assinatura Python. **Defaults compatíveis protegem a
assinatura da função, não o estado do processo.**

O mecanismo real é vazamento de estado: os quatro fluxos dividem um único objeto
`Settings` pela vida do app. Os diálogos ad-hoc escrevem as escolhas da execução
nele e nunca restauram, então o fluxo que roda **depois**, na mesma sessão,
herda os números do anterior. O #524 mediu num projeto real: **7 de 9 parâmetros
de análise mudaram**, alterando tempo de freezing, curvas, distância e
velocidade, sem aviso nenhum.

## A regra que muda tudo

**Nunca reinicie o app entre a sessão ao vivo e a conferência do pré-gravado.**

O vazamento só existe dentro de uma mesma sessão do processo. Reiniciar entre os
testes esconde exatamente a classe de bug que queimou a rodada anterior — e faz
o teste passar enquanto o problema segue lá.

## Antes de começar

```bash
source scripts/wt-env.sh
```

Uma vez por shell, antes do primeiro `pytest`/`mypy`/`ruff` e antes de qualquer
`git commit`/`git push`. Sem isso o `.pth` do venv principal roda o código da
`main` de dentro do worktree, e a suíte fica verde sem exercitar a sua branch.

Guarde fora do repositório os artefatos reais da v6.1.0 — um `<video>_results/`
de vídeo único e um de projeto. São a referência de comparação dos passos 3 e 4.

## A rede automática

Rode antes e depois de cada mudança em caminho ao vivo:

```bash
pytest tests/integration/test_flow_isolation.py tests/integration/test_prerecorded_golden.py tests/quality/test_shared_settings_mutations.py -m "" -q
```

| Arquivo | O que reprova |
| --- | --- |
| `test_prerecorded_golden.py` | Os números do pré-gravado mudaram |
| `test_flow_isolation.py` | Uma execução ao vivo mudou o que o pré-gravado calcula |
| `test_shared_settings_mutations.py` | Apareceu uma escrita NOVA no `Settings` compartilhado |

Se o golden ficar vermelho, há duas leituras e elas pedem ações opostas:

- **Você mudou o comportamento de análise de propósito.** Re-grave com
  `ZEBTRACK_UPDATE_GOLDEN=1` e deixe os números novos aparecerem no diff.
- **Você não mudou.** Então vazou algo. Comece por `test_flow_isolation.py`.

Re-gravar o golden é um ato deliberado e revisável. Um golden re-gravado por
reflexo não protege nada.

## Roteiro por rodada de teste ao vivo

Como a câmera é real, a sessão ao vivo não é reproduzível: valida-se por
observação. O que é reproduzível é o pré-gravado — e o teste que importa é a
transição entre os dois.

1. **Abra o app uma vez.**

2. **Rode a sessão ao vivo avulsa** (botão "Analisar Câmera ao Vivo"). Confira:
   - a pasta de saída em `~/ZebTrack/live_analysis_sessions/<id>_<timestamp>/`;
   - `3_CoordMovimento_*.parquet` com linhas;
   - `6_FrameLedger_*` e o `_anchor.json` ao lado;
   - o `.docx` com métricas em **cm** — ou, sem escala conhecida, com o aviso
     carimbado dentro do relatório;
   - o `.xlsx`.

3. **Sem fechar o app**, rode em seguida um vídeo pré-gravado já validado na
   v6.1.0. Compare o `.xlsx` com o artefato guardado.
   **Qualquer diferença numérica é vazamento**, e o culpado é o passo 2.

4. **Sem fechar o app**, abra um projeto pré-gravado validado e confira:
   - a aba Zonas mostra as zonas **do projeto**, não as da sessão ao vivo;
   - a aba "AI Model Config." reconhece que há projeto aberto;
   - os números do relatório batem com o marco.

5. Só então feche o app.

Os passos 3 e 4 não são zelo excessivo: são as reproduções literais dos
defeitos #524 e #523.

## Disciplina de escopo nos PRs ao vivo

**Um PR ao vivo não altera arquivo compartilhado.** Se a correção exigir mexer em
um destes, isso vira um PR separado, com os testes do pré-gravado rodados antes
e depois:

- `ui/components/single_video_workflow.py`
- `ui/components/zone_controls.py`
- `ui/components/behavioral_config_widget.py`
- `ui/components/canvas_manager.py`
- `ui/components/analysis_display.py`
- `ui/components/dialog_manager.py`
- `ui/components/event_dispatcher.py`
- `ui/builders/analysis_widgets.py`
- `ui/event_bus_v2.py`

### A armadilha do fluxo ao vivo avulso

`ui/components/single_video_workflow.py` tem nome de pré-gravado e serve os dois.
`on_auto_detect_clicked` → `_route_live_auto_detect` chama
`live_calibration_coordinator.run_live_calibration` quando o projeto é live **ou
quando não há projeto nenhum** — e uma sessão ao vivo avulsa tem
`project_type() is None`. É o primeiro botão que você vai encostar, e ele atinge
os dois fluxos.

Outros compartilhamentos que não parecem compartilhados:

- `zone_controls.py` carrega o banner de gravação pendente ao vivo dentro do
  painel de zonas do pré-gravado.
- `behavioral_config_widget.py` é embutido pelo `LiveAnalysisDialog` **e** pelo
  `SingleVideoConfigDialog`.
- `Recorder` é singleton de DI do lado ao vivo, mas instância nova dentro do
  worker no pré-gravado.

### A cada mudança

```bash
python scripts/impact_analyzer.py <tipo> <nome>
```

Obrigatório por CLAUDE.md. A descoberta de testes dele é **textual**, não
semântica — é ponto de partida, não garantia.

Depois de tocar arquivo compartilhado, rode as quatro fatias de domínio:

```bash
pytest -m gui -n0
```

```bash
pytest -k "multi_aquarium or partitioned" -q
```

```bash
pytest tests/test_processing*.py tests/test_recorder.py -q
```

```bash
pytest tests/test_event*.py tests/coordinators/ -q
```

Ao tocar um módulo do catálogo de mutação:

```bash
python scripts/mutation_check.py --all
```

## Assimetrias conhecidas (registradas, não corrigidas)

Todas mudam números se corrigidas. Encare cada uma como trabalho de fluxo ao
vivo, com a rede já no lugar — não como conserto de passagem.

- **`sharp_turn_threshold_deg_s` nunca afetou a contagem de curvas.**
  `AnalysisService.run_full_analysis` não aceita o parâmetro e chama
  `calculate_sharp_turns(90.0)` com literal (`analysis_service.py:311`). O valor
  configurado viaja por outra rota até o `ReporterContext`, então o `.docx` pode
  exibir 20 °/s ao lado de uma contagem calculada a 90. Pinado por
  `test_sharp_turn_threshold_is_a_known_blind_spot`.
- **A pós-análise ao vivo não usa o snapshot do projeto.**
  `live_analysis_post_processor.py` monta `AnalysisService(settings_obj=self.settings)`
  — o objeto vivo e mutado. `build_project_settings_snapshot` tem três call
  sites, nenhum no fluxo ao vivo: uma sessão ao vivo **dentro de projeto** analisa
  com as settings globais, não com as do projeto.
- **`should_capture_masks` nunca é chamado no pipeline ao vivo** — `seg_overlap`
  numa sessão ao vivo sempre degrada para `bbox_intersects`.
- **Os intervalos de processamento ao vivo não passam pelo resolver** — leem
  direto de `project_data`/config.

## Código morto que parece ponto de convergência

Não construa nada em cima destes:

- `VideoProcessingService.process_frame_source()` — zero chamadores em `src/` e
  em `tests/`. Parece o ponto onde os dois fluxos se encontram; não é.
- `io/live_stream_source.py` e `io/frame_source_factory.py` — sem chamador de
  produção.

Na prática existem **três** laços de tracking separados:
`_WorkerProcess._process_single_video` (lote pré-gravado),
`VideoProcessingService.process_single_video` (em processo) e
`frame_processing_pipeline.py` (ao vivo).
