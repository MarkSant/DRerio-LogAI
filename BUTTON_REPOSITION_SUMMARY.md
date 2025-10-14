# Reposicionamento dos Botões de Edição de ROI/Arena

## Data
14 de Outubro de 2025

## Solicitação
Ajustar a posição dos botões "✅ Salvar Edição" e "❌ Descartar" para aparecerem logo abaixo da lista de zonas (Zonas Definidas) e acima da área de parâmetros de intersecção de ROIs (Regra de Inclusão em ROI).

## Mudança Implementada

### Posição Anterior
```
📹 Selecionar Vídeo para Desenho
    ↓
🏟 Zonas Definidas (lista de áreas)
    ↓
⚙️ Regra de Inclusão em ROI (parâmetros)
    ↓
[muito abaixo, próximo ao botão de análise]
✅ Salvar Edição | ❌ Descartar
```

### Posição Atual
```
📹 Selecionar Vídeo para Desenho
    ↓
🏟 Zonas Definidas (lista de áreas)
    ↓
✅ Salvar Edição | ❌ Descartar  ← NOVA POSIÇÃO
    ↓
⚙️ Regra de Inclusão em ROI (parâmetros)
```

## Arquivos Modificados

### `src/zebtrack/ui/gui.py`

**Método:** `_create_zone_control_widgets()`

**Mudanças:**

1. **Movido o bloco `interactive_buttons_frame`** de após o painel "ROI Inclusion Rule" para **imediatamente após** o scrollbar da lista de zonas (zona_listbox)

2. **Removida a definição duplicada** que estava no final

3. **Mantido o comportamento dinâmico**: O frame continua sendo criado mas não empacotado inicialmente. É empacotado dinamicamente quando o usuário entra no modo de edição (via `_enter_edit_mode()` → linha ~5342)

## Código Modificado

```python
# Após scrollbar.pack(side="right", fill="y") da zone_list_frame:

# --- Interactive Buttons (initially hidden) ---
# Positioned right after zone list, before ROI Inclusion Rule Panel
self.interactive_buttons_frame = ttk.Frame(self.zone_controls_frame)
self.save_arena_btn = ttk.Button(
    self.interactive_buttons_frame,
    text="✅ Salvar Edição",
    command=self._on_save_arena,
)
self.save_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
self.discard_arena_btn = ttk.Button(
    self.interactive_buttons_frame,
    text="❌ Descartar",
    command=self._on_discard_arena,
)
self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
# This frame is packed later when needed (via pack() in _enter_edit_mode)

# --- ROI Inclusion Rule Panel ---
self.roi_inclusion_frame = ttk.LabelFrame(...)
```

## Ordem de Criação dos Componentes

1. **Drawing Actions** (botões Desenhar Arena, Desenhar ROI)
2. **ROI Templates** (salvar/importar templates)
3. **Video Selector** (seletor de vídeo para desenho)
4. **Zone List** (lista de zonas definidas)
5. **Interactive Buttons** ← **NOVA POSIÇÃO**
6. **ROI Inclusion Rule Panel** (parâmetros de intersecção)

## Comportamento Dinâmico Preservado

Os botões continuam funcionando da mesma forma:

- **Invisíveis por padrão**: O `interactive_buttons_frame` não tem `.pack()` chamado em `_create_zone_control_widgets()`
- **Aparecem ao editar**: Quando usuário clica "Edit" em arena ou ROI, `_enter_edit_mode()` chama `self.interactive_buttons_frame.pack(fill="x", padx=5, pady=5)`
- **Desaparecem ao salvar/descartar**: `_exit_edit_mode()` chama `self.interactive_buttons_frame.pack_forget()`

## Testes

### Testes Criados

**Arquivo:** `tests/test_interactive_buttons_position.py`

1. **`test_interactive_buttons_positioned_after_zone_list()`**
   - ✅ Verifica que a seção Interactive Buttons vem após Zone List
   - ✅ Verifica que vem antes de ROI Inclusion Rule Panel
   - ✅ Confirma que não há definição duplicada

2. **`test_interactive_buttons_not_packed_initially()`**
   - ✅ Verifica que o frame não é empacotado em `_create_zone_control_widgets`
   - ✅ Confirma que é empacotado dinamicamente depois
   - ✅ Verifica que botões internos são empacotados dentro do frame

### Testes de Regressão

```bash
poetry run pytest tests/test_gui_zone_config_fixes.py -v
# ✅ 5/5 passed

poetry run pytest tests/test_interactive_buttons_position.py -v
# ✅ 2/2 passed
```

## Benefícios da Nova Posição

1. **Proximidade Contextual**: Botões aparecem logo após a lista de zonas que está sendo editada
2. **Fluxo Visual Lógico**: Usuário vê a zona → edita → salva, tudo na mesma região vertical
3. **Menos Rolagem**: Não precisa rolar para baixo para encontrar os botões
4. **Separação Clara**: Parâmetros de análise (ROI Inclusion) ficam claramente separados dos controles de edição

## Estrutura Visual Final

```
┌─────────────────────────────────────┐
│ 🎨 Drawing Actions                  │
│   [Desenhar Arena] [Desenhar ROI]   │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ 📋 ROI Templates                    │
│   [💾 Salvar] [📂 Importar]         │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ 📹 Selecionar Vídeo para Desenho    │
│   [Árvore de vídeos...]             │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ 🏟 Zonas Definidas                  │
│   Arena Principal  | Arena | 🟦     │
│   ROI Norte        | ROI   | 🟢     │
│   ROI Sul          | ROI   | 🔴     │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ ✅ Salvar Edição | ❌ Descartar     │  ← AQUI!
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ ⚙️ Regra de Inclusão em ROI         │
│   Regra: [bbox_intersects ▼]       │
│   [Parâmetros específicos...]       │
│   [Aplicar Configurações]           │
└─────────────────────────────────────┘
```

## Notas de Implementação

- **Sem Breaking Changes**: Todas as referências a `self.interactive_buttons_frame` continuam funcionando
- **Sem Mudanças de Lógica**: Apenas mudou a posição de criação do frame, não o comportamento
- **Compatibilidade Total**: Código de edição (`_enter_edit_mode`, `_exit_edit_mode`, etc.) não foi modificado

## Referências

- **Solicitação**: "preciso que vc ajuste a posição do botão que salva as edições das rois. [...] logo abaixo da lista de áreas e suas propriedades., e acima da área em que se definem parametros de intersecção de rois e boxes."
- **Arquivo Principal**: `src/zebtrack/ui/gui.py` (linhas ~4340-4360)
- **Testes**: `tests/test_interactive_buttons_position.py`
- **Status**: ✅ Implementado e Testado
