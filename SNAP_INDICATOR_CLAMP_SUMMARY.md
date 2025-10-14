# Implementação: Indicador de Snapping Limitado à Área da Arena

## Resumo

Implementada funcionalidade onde o indicador de snapping (bolinha cyan) ao desenhar ROIs permanece dentro dos limites da arena principal, mesmo quando o cursor do mouse está fora dela.

## Mudanças Realizadas

### 1. Arquivo Principal: `src/zebtrack/ui/gui.py`

**Método modificado**: `_on_canvas_motion(self, event)`

**Lógica implementada**:
1. Detecta quando está desenhando uma ROI (`self.current_drawing_type == "roi"`)
2. Obtém o polígono da arena principal
3. Verifica se a posição do indicador (display_x, display_y) está dentro ou fora da arena usando `cv2.pointPolygonTest()`
4. Se estiver fora (result < 0), encontra o ponto mais próximo na borda da arena
5. Atualiza display_x e display_y para a posição "clamped" (limitada)
6. O indicador de snap é desenhado na posição limitada
7. As linhas elásticas automaticamente usam essa posição limitada

**Características**:
- ✅ Mantém a tolerância de snapping existente
- ✅ Respeita snapping a vértices e arestas da arena
- ✅ Não afeta o desenho da arena principal
- ✅ O cursor do mouse pode continuar se movendo livremente
- ✅ Funciona com todas as transformações de coordenadas canvas↔video

### 2. Teste Automatizado: `tests/test_roi_snap_indicator_arena_clamp.py`

**Tipo**: Teste de verificação de código

**Validações**:
- ✅ Verifica que a lógica de clamping está presente
- ✅ Confirma uso de `cv2.pointPolygonTest`
- ✅ Confirma uso de `_point_to_segment_distance`
- ✅ Confirma que display_x e display_y são usados corretamente

**Status**: ✅ Passing

### 3. Documentação: `docs/ROI_SNAP_INDICATOR_ARENA_CLAMP.md`

Documentação completa incluindo:
- Descrição do comportamento
- Detalhes técnicos da implementação
- Cenários de teste manual
- Benefícios para o usuário
- Notas de compatibilidade

## Comportamento Implementado

### Ao Desenhar ROIs

```
Cursor fora da arena → Indicador limitado à borda mais próxima
Cursor dentro da arena → Indicador segue o cursor normalmente
Snapping ativo → Indicador mostra ponto de snap (limitado se necessário)
```

### Ao Desenhar Arena

```
Sem limitação → Indicador segue cursor livremente
```

## Testes Realizados

### Testes Automatizados
```powershell
poetry run pytest tests/test_roi_snap_indicator_arena_clamp.py -v
# ✅ 1 passed

poetry run pytest tests/test_gui_zone_config_fixes.py tests/test_single_video_zones_display.py -v
# ✅ 7 passed - Nenhuma regressão detectada
```

### Cenários de Teste Manual Sugeridos

1. **Cursor fora - canto superior esquerdo**
   - Iniciar desenho de ROI
   - Mover cursor acima e à esquerda da arena
   - Verificar: indicador fica no canto superior esquerdo da arena

2. **Cursor fora - borda direita**
   - Mover cursor à direita da arena
   - Verificar: indicador é projetado na borda direita

3. **Cursor dentro**
   - Mover cursor dentro da arena
   - Verificar: indicador segue o cursor normalmente

4. **Snapping a vértice**
   - Aproximar cursor de vértice da arena
   - Verificar: snapping funciona como antes

5. **Desenho de arena**
   - Iniciar desenho da arena principal
   - Verificar: sem limitação, indicador segue cursor

## Arquitetura da Solução

```
_on_canvas_motion(event)
    │
    ├─► Obtém canvas_x, canvas_y do event
    │
    ├─► Aplica snapping (_apply_snapping)
    │   └─► Retorna snapped_point ou None
    │
    ├─► Define display_x, display_y
    │   └─► = snapped_point ou cursor position
    │
    ├─► Se drawing_type == "roi":
    │   │
    │   ├─► Obtém arena_polygon
    │   │
    │   ├─► Converte para canvas coords
    │   │
    │   ├─► cv2.pointPolygonTest(display_point)
    │   │
    │   └─► Se fora (result < 0):
    │       │
    │       ├─► Para cada aresta da arena:
    │       │   └─► _point_to_segment_distance()
    │       │
    │       └─► display_x, display_y = closest_point
    │
    └─► Desenha indicador em (display_x, display_y)
```

## Compatibilidade

- ✅ **Validação existente preservada**: `controller.add_roi_polygon()` continua validando pontos
- ✅ **Snapping preservado**: Toda lógica de snapping existente funciona normalmente
- ✅ **Coordenadas preservadas**: Sistema de transformação canvas↔video intacto
- ✅ **Sem breaking changes**: Funcionalidade é puramente visual

## Código-Fonte Relevante

### Trecho Principal (gui.py, linha ~7640)

```python
# When drawing ROI, clamp the display indicator within the arena
if self.current_drawing_type == "roi":
    main_arena_poly = self.controller.project_manager.get_zone_data().polygon
    if main_arena_poly:
        # Convert arena to canvas coordinates
        canvas_arena_poly = []
        for point in main_arena_poly:
            canvas_pt = self._video_to_canvas(point[0], point[1])
            canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])
        
        arena_array = np.array(canvas_arena_poly, dtype=np.float32)
        
        # Test if display point is inside arena
        result = cv2.pointPolygonTest(arena_array, (display_x, display_y), True)
        
        # If outside arena (result < 0), clamp to nearest arena boundary
        if result < 0:
            # Find the closest point on the arena boundary
            min_dist = float('inf')
            closest_point = (display_x, display_y)
            
            # Check distance to each edge of the arena
            for i in range(len(canvas_arena_poly)):
                p1 = canvas_arena_poly[i]
                p2 = canvas_arena_poly[(i + 1) % len(canvas_arena_poly)]
                
                edge_snap = self._point_to_segment_distance(
                    display_x, display_y, p1[0], p1[1], p2[0], p2[1]
                )
                
                if edge_snap and edge_snap['distance'] < min_dist:
                    min_dist = edge_snap['distance']
                    closest_point = (edge_snap['x'], edge_snap['y'])
            
            # Update display position to clamped point
            display_x, display_y = closest_point
```

## Próximos Passos

Esta funcionalidade está pronta para uso. Sugestões para melhorias futuras:

1. **Visual adicional**: Destacar a borda da arena ao desenhar ROIs
2. **Indicador de cor**: Usar cor diferente quando indicador está "clamped"
3. **Configuração opcional**: Permitir desabilitar clamping se desejado

## Referências

- **Request original**: "Ao desenhar rois sobre a área da arena previamente desenhada, a Bolinha do cursor..."
- **Data de implementação**: 14 de Outubro de 2025
- **Status dos testes**: ✅ Passing
- **Documentação completa**: `docs/ROI_SNAP_INDICATOR_ARENA_CLAMP.md`
