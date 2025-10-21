# Correção Final: Largura do Painel Esquerdo

**Data**: 2025-10-21  
**Iteração**: 2 (correção da correção anterior)

## Problema Identificado

Após a primeira correção que resolveu o `AttributeError`, o painel esquerdo ainda abria muito estreito, ocultando o botão "Iniciar Análise de Vídeo Único" e a barra de rolagem. O usuário precisava arrastar manualmente a borda direita do painel para visualizar todos os controles.

### Evidências
- **Imagem 1**: Painel esquerdo muito estreito ao abrir, botão parcialmente oculto
- **Imagem 2**: Painel após ajuste manual, mostrando o botão completo

## Análise do Problema

### Causas Identificadas

1. **Largura insuficiente**: A posição do sash estava configurada em 420px, mas o botão "Iniciar Análise de Vídeo Único" necessita de mais espaço

2. **Mínimo muito baixo**: O constraint mínimo estava em 380px, permitindo que o painel encolhesse demais

3. **Timing de configuração**: O sash position era definido ANTES da criação dos widgets, causando inconsistências no cálculo de geometria

## Soluções Implementadas

### 1. Aumento da Largura Inicial do Painel

**Arquivo**: `src/zebtrack/ui/gui.py`

**Mudanças**:
```python
# ANTES: 420px
main_pane.sashpos(0, 420)

# DEPOIS: 480px
main_pane.sashpos(0, 480)
```

**Justificativa**: 480px garante espaço suficiente para o botão "Iniciar Análise de Vídeo Único" e outros controles, sem necessidade de ajuste manual.

### 2. Aumento do Limite Mínimo

**Arquivo**: `src/zebtrack/ui/gui.py`

**Mudanças**:
```python
# ANTES: Mínimo de 380px
if current_pos < 380:
    main_pane.sashpos(0, 380)

# DEPOIS: Mínimo de 450px
if current_pos < 450:
    main_pane.sashpos(0, 450)
```

**Justificativa**: 450px é o mínimo absoluto para exibir todos os controles sem cortes. Usuários podem reduzir até esse ponto, mas não menos.

### 3. Reordenação da Configuração do Sash

**Arquivo**: `src/zebtrack/ui/gui.py`

**Mudanças**:
- **ANTES**: `_set_initial_sash()` era chamado ANTES da criação do `ZoneControlsWidget`
- **DEPOIS**: `_set_initial_sash()` é chamado APÓS a criação de TODOS os widgets, ao final do método `_create_roi_analysis_tab()`

**Código**:
```python
# 7. Subscribe to events
self._subscribe_zone_component_events()

# 8. Set initial sash position AFTER all widgets are created
def _set_initial_sash():
    try:
        main_pane.update_idletasks()
        main_pane.sashpos(0, 480)
    except Exception:
        pass

# Try multiple times with increasing delays
main_pane.after(10, _set_initial_sash)
main_pane.after(50, _set_initial_sash)
main_pane.after(100, _set_initial_sash)
main_pane.after(200, _set_initial_sash)  # Nova tentativa adicional
```

**Justificativa**: 
- Configurar o sash após criar widgets garante que a geometria está calculada
- Múltiplas tentativas com delays crescentes (10, 50, 100, 200ms) garantem que a configuração "pegue" mesmo em sistemas mais lentos
- `update_idletasks()` força o cálculo de geometria antes de definir a posição

## Arquivos Modificados

1. **`src/zebtrack/ui/gui.py`**
   - Aumentada largura inicial: 420px → 480px
   - Aumentado limite mínimo: 380px → 450px
   - Movida configuração do sash para após criação dos widgets
   - Adicionada tentativa extra com delay de 200ms

## Script de Teste

Criado `scripts/test_panel_width.py` para testar visualmente o layout:

```bash
poetry run python scripts/test_panel_width.py
```

O script:
- Cria uma janela que simula o layout do tab de zonas
- Mostra a largura atual do painel em tempo real
- Permite verificar se o botão está totalmente visível
- Útil para testes futuros de ajustes de layout

## Comportamento Esperado

### ✅ Após a Correção

1. **Ao abrir a janela de análise de vídeo único**:
   - Painel esquerdo abre com 480px de largura
   - Todos os botões são visíveis, incluindo "Iniciar Análise de Vídeo Único"
   - Barra de rolagem está acessível
   - Nenhum ajuste manual necessário

2. **Durante o redimensionamento**:
   - Usuário pode reduzir o painel até 450px (mínimo forçado)
   - Abaixo de 450px, o sistema força o painel de volta a 450px
   - Garante que controles sempre permaneçam acessíveis

3. **Robustez**:
   - Configuração aplicada 4 vezes com delays diferentes
   - Funciona mesmo em sistemas mais lentos
   - Geometria calculada corretamente após criação dos widgets

## Testes Realizados

- ✅ Linter (Ruff): Sem erros
- ✅ Sintaxe: Verificada e válida
- ✅ Testes existentes: Continuam passando
- ⚠️ Teste visual: Requer validação manual pelo usuário

## Próximos Passos (Opcional)

Se o problema persistir, considerar:

1. **Ajuste adicional de largura**: Aumentar para 500px se necessário
2. **Botão mais compacto**: Reduzir texto do botão ou usar ícone
3. **Layout alternativo**: Reorganizar controles verticalmente
4. **Configuração persistente**: Salvar preferência de largura do usuário

## Notas Técnicas

- **PanedWindow behavior**: Tkinter PanedWindow pode ter comportamentos inconsistentes com timing de geometria
- **Solution pattern**: Múltiplas tentativas com delays é uma solução robusta e comprovada
- **Minimum constraint**: O evento `<Configure>` garante que o mínimo seja respeitado durante redimensionamento
- **Weight ratio**: Left panel (weight=1) vs Right panel (weight=4) mantém proporção 1:4 após ajustes manuais
