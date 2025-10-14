# Correções do Fluxo de Templates de ROI

## Problemas Identificados e Soluções

### 1. **Template Atual Pré-Populado no Vídeo Único**

**Problema Original:**
Ao abrir o fluxo de vídeo único, o combobox "Template Atual" mostrava automaticamente o nome do último template usado, mesmo que não houvesse nenhum template aplicado ao vídeo atual.

**Causa Raiz:**
A função `_refresh_roi_templates()` sempre selecionava automaticamente o primeiro template da lista quando o combobox estava vazio:
```python
if names:
    self.roi_template_var.set(names[0])  # ❌ Auto-seleção indesejada
```

**Solução Implementada:**
1. Adicionado parâmetro `clear_selection` à função `_refresh_roi_templates()`:
   ```python
   def _refresh_roi_templates(self, clear_selection: bool = False) -> None:
       # ...
       if clear_selection:
           self.roi_template_var.set("")  # ✅ Limpa seleção explicitamente
           return
   ```

2. Modificada a lógica de auto-seleção para só ocorrer quando já havia algo selecionado:
   ```python
   if current_display and names:
       self.roi_template_var.set(names[0])  # ✅ Só auto-seleciona se havia seleção
   else:
       self.roi_template_var.set("")  # ✅ Deixa em branco por padrão
   ```

3. Chamada explícita ao iniciar vídeo único:
   ```python
   def setup_zone_definition_for_single_video(self, video_path: str, config: dict):
       # ...
       self._refresh_roi_templates(clear_selection=True)  # ✅ Força combobox vazio
   ```

---

### 2. **Botão "Importar" Não Aplicava o Template**

**Problema Original:**
Ao clicar em "Importar..." e selecionar um arquivo, o template era adicionado à biblioteca mas NÃO era aplicado automaticamente ao vídeo. O canvas permanecia vazio e a lista não mostrava as zonas, apesar da mensagem de sucesso.

**Causa Raiz:**
A função `_on_import_roi_template()` apenas importava o arquivo para a biblioteca de templates (cópia para `templates/`), mas não aplicava as zonas ao vídeo ativo:
```python
def _on_import_roi_template(self) -> None:
    # ...
    metadata = pm.import_roi_template(file_path)  # ❌ Só copia arquivo
    self._refresh_roi_templates()
    self._select_roi_template(metadata)  # ❌ Só atualiza combobox
    # ❌ Falta aplicar as zonas!
```

**Solução Implementada:**
Criada nova função `_on_import_and_apply_roi_template()` que:

1. **Abre o arquivo de template diretamente**:
   ```python
   import json
   with open(file_path, 'r', encoding='utf-8') as f:
       template_data = json.load(f)
   ```

2. **Converte para ZoneData**:
   ```python
   from zebtrack.core.detector import ZoneData
   template_zone = ZoneData(
       polygon=template_data.get("polygon"),
       roi_polygons=template_data.get("roi_polygons", []),
       roi_names=template_data.get("roi_names", []),
       roi_colors=template_data.get("roi_colors", []),
   )
   ```

3. **Salva no vídeo ativo**:
   ```python
   pm.save_zone_data(
       template_zone,
       video_path=active_video,
       persist=bool(pm.project_path),
   )
   ```

4. **Atualiza o detector e a UI**:
   ```python
   self.controller.setup_detector_zones()
   self.redraw_zones_from_project_data()
   self.update_zone_listbox()
   self._refresh_zone_indicators()
   ```

5. **Opcionalmente importa para biblioteca**:
   ```python
   try:
       metadata = pm.import_roi_template(file_path)
       self._refresh_roi_templates()
       self._select_roi_template(metadata)
   except Exception:
       pass  # Se falhar, pelo menos aplicou as zonas
   ```

---

### 3. **Confusão na Interface do Usuário**

**Problema Original:**
Havia apenas dois botões:
- "Salvar Atual" (claro)
- "Importar..." (ambíguo - importa E aplica? Ou só importa?)

E o combobox era rotulado "Template atual", sugerindo que algo estava aplicado quando na verdade não estava.

**Solução Implementada:**

#### Mudanças no Layout:
```python
# ANTES:
ttk.Label(template_selector, text="Template atual:").pack(...)

# DEPOIS:
ttk.Label(template_selector, text="Templates salvos:").pack(...)  # ✅ Mais claro
```

#### Mudanças nos Botões:
```python
# ANTES:
ttk.Button(..., text="Salvar Atual", ...)
ttk.Button(..., text="Importar...", ...)

# DEPOIS:
ttk.Button(..., text="💾 Salvar Zonas Atuais", ...)
ttk.Button(..., text="📂 Importar e Aplicar Arquivo...", ...)  # ✅ Ação explícita
```

#### Fluxo de Trabalho Agora:

1. **Aplicar template da biblioteca**:
   - Selecionar template no dropdown "Templates salvos"
   - Clicar em "Aplicar"
   - ✅ Zonas aparecem imediatamente no canvas

2. **Importar e aplicar arquivo externo**:
   - Clicar em "📂 Importar e Aplicar Arquivo..."
   - Selecionar arquivo `.json`
   - ✅ Zonas aparecem imediatamente no canvas
   - ✅ Template também é adicionado à biblioteca

3. **Salvar zonas atuais como template**:
   - Desenhar arena/ROIs manualmente
   - Clicar em "💾 Salvar Zonas Atuais"
   - ✅ Salva na biblioteca para reutilização

---

## Melhorias Técnicas

### Refatoração de `_refresh_roi_templates()`
- Parâmetro `clear_selection` permite controle explícito
- Lógica de auto-seleção mais conservadora
- Documentação melhorada

### Nova Função `_on_import_and_apply_roi_template()`
- Combina importação + aplicação em uma única ação
- Tratamento de erro robusto (mesmo se importar falhar, aplica as zonas)
- Logs detalhados para diagnóstico

### Melhoria na Inicialização de Vídeo Único
- `setup_zone_definition_for_single_video()` agora força combobox vazio
- Usuário tem controle explícito sobre quando aplicar templates

---

## Testes

### Cobertura Existente Mantida:
```bash
poetry run pytest tests/test_wizard_templates.py -q
# 8 passed

poetry run pytest tests/test_project_manager.py -q -k template
# 8 passed

poetry run pytest -q
# 340 passed
```

### Cenários de Teste Manual Recomendados:

1. **Vídeo Único - Combobox Vazio:**
   - Abrir fluxo de vídeo único
   - ✅ Verificar que "Templates salvos" está em branco
   - ✅ Verificar que canvas está vazio

2. **Importar e Aplicar:**
   - Clicar em "📂 Importar e Aplicar Arquivo..."
   - Selecionar template válido
   - ✅ Verificar que zonas aparecem no canvas
   - ✅ Verificar que lista mostra arena/ROIs
   - ✅ Verificar que combobox atualiza

3. **Aplicar Template da Biblioteca:**
   - Selecionar template no dropdown
   - Clicar em "Aplicar"
   - ✅ Verificar que zonas aparecem no canvas

4. **Persistência Entre Sessões:**
   - Aplicar template
   - Fechar e reabrir GUI
   - ✅ Verificar que combobox ainda está vazio (não persiste seleção)

---

## Arquivos Modificados

### `src/zebtrack/ui/gui.py`:
- `_refresh_roi_templates()`: Adicionado parâmetro `clear_selection`
- `_on_import_and_apply_roi_template()`: Nova função (142 linhas)
- `setup_zone_definition_for_single_video()`: Chama `_refresh_roi_templates(clear_selection=True)`
- Template UI: Renomeado labels e botões

### `tests/test_gui_zone_config_fixes.py`:
- Atualizado teste de guard para aceitar novos parâmetros de função

---

## Notas de Implementação

### Por que não modificar `_on_import_roi_template()` diretamente?

A função original ainda é útil para casos onde o usuário quer apenas adicionar um template à biblioteca sem aplicá-lo imediatamente. Manter ambas as funções oferece mais flexibilidade.

### Por que carregar o arquivo JSON diretamente?

Evita dependência circular: `import_roi_template()` copia o arquivo mas não retorna `ZoneData`. Carregar diretamente do arquivo é mais direto e evita chamadas adicionais ao `ProjectManager`.

### Por que importar para biblioteca DEPOIS de aplicar?

Se a importação falhar (ex: nome duplicado), o usuário ainda consegue usar as zonas. A importação é um "bônus" para facilitar reutilização futura.

---

## Próximos Passos Recomendados

1. **Adicionar indicador visual** no combobox quando um template está realmente aplicado ao vídeo atual
2. **Permitir "desfazer" aplicação de template** para restaurar zonas anteriores
3. **Preview de template** antes de aplicar (mostrar thumbnail das zonas)
4. **Auto-aplicar último template usado** (opcional, controlado por preferência)

---

## Referências

- Issue original: Relatado pelo usuário em 14/10/2025
- Commit associado: (pendente)
- Documentação relacionada: `docs/REFERENCE_GUIDE.md` (seção Templates de ROI)
