# Plano: Processamento Sequencial de Multi-Aquários

**Status**: ✅ IMPLEMENTADO (Dec 21, 2025)

## Resumo

Adicionar opção para processar aquários sequencialmente (2 passagens pelo vídeo) ao invés de simultaneamente (1 passagem), reutilizando a lógica single-aquarium existente.

## Requisitos Confirmados

1. **Modo Sequencial**: Processar vídeo INTEIRO para aquário 1, depois processar INTEIRO novamente para aquário 2
2. **Toggle Location**: Na aba de Zonas/Configuração (ZoneControls)
3. **Transição**: Automática entre aquários (sem intervenção do usuário)

## Arquitetura da Solução

### Estratégia Principal

Reutilizar o fluxo single-aquarium existente, chamando-o 2 vezes:

```
MultiAquariumZoneData → AquariumData[0].to_zone_data() → ZoneData → detect() → resultados aquário 0
                      → AquariumData[1].to_zone_data() → ZoneData → detect() → resultados aquário 1
```

### Fluxo de Dados

```
┌─ Modo Paralelo (atual) ─────────────────────────────────────────────┐
│ 1 passagem pelo vídeo                                               │
│ detect_partitioned_optimized() → dict[aq_id, detections]            │
│ write_partitioned_detection_data() → arquivos separados             │
└─────────────────────────────────────────────────────────────────────┘

┌─ Modo Sequencial (novo) ────────────────────────────────────────────┐
│ Passagem 1: Aquário 0                                               │
│   zone_data = multi_zone_data.to_zone_data(0)                       │
│   detect(frame) → detecções single-aquarium                         │
│   write_detection_data() → aquarium_0/                              │
│                                                                      │
│ Passagem 2: Aquário 1 (automático)                                  │
│   zone_data = multi_zone_data.to_zone_data(1)                       │
│   detect(frame) → detecções single-aquarium                         │
│   write_detection_data() → aquarium_1/                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Arquivos Modificados

1. `src/zebtrack/ui/events.py` - Novo evento `ZONE_PROCESSING_MODE_CHANGED`
2. `src/zebtrack/core/detector.py` - Novo campo `sequential_processing`
3. `src/zebtrack/core/zone_manager.py` - Serialização atualizada
4. `src/zebtrack/ui/components/zone_controls.py` - Toggle UI (radio buttons)
5. `src/zebtrack/ui/components/canvas_manager.py` - Método `update_processing_mode()`
6. `src/zebtrack/ui/components/event_dispatcher.py` - Subscrição de evento
7. `src/zebtrack/coordinators/processing_coordinator.py` - Lógica de processamento sequencial

---

## Estrutura de Output

### Modo Paralelo (atual)
```
video_results/
├── aquarium_0/
│   └── 3_CoordMovimento_video.parquet
└── aquarium_1/
    └── 3_CoordMovimento_video.parquet
```

### Modo Sequencial (novo) - Mesma estrutura!
```
video_results/
├── aquarium_0/
│   ├── 3_CoordMovimento_video.parquet  (passagem 1)
│   ├── 4_Relatorio_video_aq0.docx
│   ├── 4_Relatorio_video_aq0.xlsx
│   └── video_aq0_summary.parquet
└── aquarium_1/
    ├── 3_CoordMovimento_video.parquet  (passagem 2)
    ├── 4_Relatorio_video_aq1.docx
    ├── 4_Relatorio_video_aq1.xlsx
    └── video_aq1_summary.parquet
```

---

## Considerações

### Vantagens do Modo Sequencial
- Usa 100% dos recursos para cada aquário
- Menor uso de memória (1 ByteTracker por vez)
- Mais fácil de debugar (1 fluxo por vez)
- Reutiliza código existente (single-aquarium)

### Desvantagens
- 2x tempo total de processamento
- Lê o vídeo 2 vezes do disco

### Compatibilidade
- Default: `sequential_processing=False` (comportamento atual mantido)
- Projetos existentes não são afetados
- Toggle só aparece quando multi-aquarium está ativo
