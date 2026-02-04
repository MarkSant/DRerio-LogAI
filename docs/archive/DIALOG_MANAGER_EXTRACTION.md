# DialogManager - Extração de Métodos de Diálogo do gui.py

**Data**: 2025-11-05
**Tarefa**: Phase 2, Task 2.1 - Extração de DialogManager
**Status**: ✅ Concluído

## Resumo

Criado o arquivo `src/zebtrack/ui/components/dialog_manager.py` com 711 linhas e 32 métodos extraídos de `gui.py`, centralizando toda a lógica de diálogos e interação com o usuário.

## Estrutura do Arquivo

### 1. MessageBox Wrappers (8 métodos)

Métodos que encapsulam `tkinter.messagebox`:

| Método | Descrição | Retorno |
| -------- | ----------- | --------- |
| `show_error(title, message)` | Exibe messagebox de erro | None |
| `show_warning(title, message)` | Exibe messagebox de aviso | None |
| `show_info(title, message)` | Exibe messagebox de informação | None |
| `ask_ok_cancel(title, message)` | Diálogo OK/Cancelar | bool |
| `ask_yes_no(title, message, icon)` | Diálogo Sim/Não | bool |
| `ask_yes_no_cancel(title, message, icon)` | Diálogo Sim/Não/Cancelar | bool \| None |

### 2. File Dialogs (5 métodos)

Métodos que encapsulam `tkinter.filedialog`:

| Método | Descrição | Retorno |
| -------- | ----------- | --------- |
| `ask_directory(title, initial_dir)` | Seleciona diretório | str |
| `ask_open_filename(title, filetypes, initial_dir)` | Seleciona arquivo único | str |
| `ask_open_filenames(title, filetypes, initial_dir)` | Seleciona múltiplos arquivos | tuple[str, ...] |
| `ask_save_filename(**options)` | Seleciona local para salvar | str |
| `ask_string(title, prompt, initialvalue)` | Input de string | str \| None |

### 3. Custom Dialogs - Calibration (2 métodos)

| Método | Descrição |
| -------- | ----------- |
| `open_global_calibration_window()` | Abre CalibrationDialog para calibração global |
| `open_project_calibration_window()` | Abre CalibrationDialog para projeto específico |

### 4. Custom Dialogs - ROI Templates (3 métodos)

| Método | Descrição | Retorno |
| -------- | ----------- | --------- |
| `show_template_save_dialog(...)` | Abre SaveROITemplateDialog | dict \| None |
| `import_roi_template()` | Importa template para biblioteca | None |
| `import_and_apply_roi_template()` | Importa e aplica template ao vídeo | None |

### 5. Custom Dialogs - Analysis (3 métodos)

| Método | Descrição | Retorno |
| -------- | ----------- | --------- |
| `open_center_periphery_dialog()` | Abre CenterPeripheryDialog | dict \| None |
| `open_template_rois_dialog()` | Abre TemplateDialog | dict \| None |
| `open_single_video_config_dialog()` | Abre SingleVideoConfigDialog | dict \| None |

### 6. Custom Dialogs - Project & Recording (4 métodos)

| Método | Descrição | Retorno |
| -------- | ----------- | --------- |
| `show_pending_videos_dialog(...)` | Exibe diálogo hierárquico de vídeos pendentes | dict \| None |
| `ask_recording_details_unified()` | Solicita detalhes de gravação (dia/grupo/sujeito) | dict \| None |
| `ask_missing_metadata(experiment_id)` | Solicita metadata faltante | dict \| None |
| `open_project_workflow()` | Workflow de abertura de projeto | None |

### 7. Confirmation Dialogs (4 métodos)

Métodos especializados para confirmações específicas:

| Método | Descrição | Retorno |
| -------- | ----------- | --------- |
| `confirm_delete_roi_template(...)` | Confirma deleção de template | bool |
| `confirm_remove_roi(roi_name)` | Confirma remoção de ROI | bool |
| `confirm_save_polygon_before_analysis()` | Confirma salvar polígono antes de análise | bool \| None |
| `offer_zone_reuse(current, source)` | Oferece reutilizar zonas de outro vídeo | bool |

### 8. Notification Dialogs (2 métodos)

| Método | Descrição |
| -------- | ----------- |
| `show_external_trigger_notice(session_label, **details)` | Exibe aviso de trigger externo |
| `clear_external_trigger_notice()` | Limpa aviso de trigger |

### 9. Utility Methods (2 métodos)

| Método | Descrição |
| -------- | ----------- |
| `show_progress_bar()` | Exibe barra de progresso |
| `open_path_in_explorer(target_path)` | Abre path no explorador de arquivos |

## Estatísticas

- **Total de linhas**: 711
- **Total de métodos**: 32 (incluindo `__init__`)
- **Categorias**: 9 grupos funcionais
- **Dialogs customizados gerenciados**: 9 classes diferentes

## Padrões de Design

### 1. Encapsulamento

Todos os diálogos são acessados através do DialogManager, evitando chamadas diretas a `messagebox`, `filedialog`, etc. em `gui.py`.

### 2. Type Hints

Todos os métodos possuem type hints completos para parâmetros e retornos.

### 3. Docstrings

Cada método possui docstring detalhado no formato Google-style com:

- Descrição clara
- Args documentados
- Returns documentados

### 4. Organização por Categoria

Métodos agrupados por funcionalidade com separadores visuais para facilitar navegação.

### 5. Delegação

DialogManager mantém referência ao `gui` para:

- Acessar `gui.root` (parent de dialogs)
- Acessar `gui.controller` (acesso a serviços)
- Chamar métodos de refresh de UI após operações

## Dependências

### Imports Externos

- `os`, `subprocess`, `sys`: Utilitários do sistema
- `pathlib.Path`: Manipulação de paths
- `tkinter.{filedialog, messagebox, simpledialog}`: Diálogos nativos
- `typing.Any`: Type hints
- `structlog`: Logging estruturado

### Imports Internos

- `zebtrack.ui.dialogs.*`: 8 classes de dialogs customizados
  - CalibrationDialog
  - CenterPeripheryDialog
  - MissingMetadataDialog
  - PendingVideosDialog
  - SaveROITemplateDialog
  - SingleVideoConfigDialog
  - StartRecordingDialog
  - TemplateDialog

## Próximos Passos

### Fase de Refatoração (Task 2.2)

Após criar DialogManager, o próximo passo é **refatorar gui.py** para usar este manager:

1. **Adicionar DialogManager ao gui.py**:

   ```python
   # Em ApplicationGUI.__init__():
   self.dialog_manager = DialogManager(self)
   ```

2. **Substituir chamadas diretas** por delegação:

   ```python
   # ANTES:
   messagebox.showerror("Erro", "Mensagem")

   # DEPOIS:
   self.dialog_manager.show_error("Erro", "Mensagem")
   ```

3. **Métodos a refatorar em gui.py** (~15-20 métodos):
   - `_on_save_roi_template()` (linha ~5407)
   - `_on_delete_roi_template()` (linha ~5649)
   - `_on_import_roi_template()` (linha ~5713)
   - `_on_import_and_apply_roi_template()` (linha ~5742)
   - `_maybe_offer_zone_reuse()` (linha ~3837)
   - `_run_center_periphery_analysis()` (linha ~6529)
   - `_create_template_rois()` (linha ~6546)
   - `_on_analyze_single_video_clicked()` (linha ~7172)
   - `_on_start_single_video_processing_clicked()` (linha ~7382)
   - `_open_project_workflow()` (linha ~7164)
   - E outros métodos que usam dialogs

4. **Backward Compatibility Properties**:
   Adicionar properties ao gui.py para manter compatibilidade:

   ```python
   @property
   def show_error(self):
       return self.dialog_manager.show_error

   # ... outros wrappers
   ```

5. **Remover métodos antigos**:
   Após garantir que toda a refatoração está completa e testada, remover os métodos originais de gui.py.

## Testes

### Verificações Realizadas

- ✅ Linting: `poetry run ruff check` passou sem erros
- ✅ Import: Módulo adicionado ao `__init__.py`
- ✅ Estrutura: 711 linhas, 32 métodos conforme planejado

### Testes Pendentes

- ⏳ Unit tests para DialogManager
- ⏳ Integration tests após refatoração de gui.py
- ⏳ Verificação de coverage

## Benefícios Alcançados

1. **Redução de Complexidade**:
   - Separa lógica de diálogos do God Object gui.py
   - ~282 linhas diretas + ~430 linhas de código relacionado

2. **Manutenibilidade**:
   - Ponto único para gerenciar todos os diálogos
   - Facilita mudanças futuras (ex: trocar messagebox por dialog customizado)

3. **Testabilidade**:
   - DialogManager pode ser testado isoladamente
   - Fácil criar mocks para testes de gui.py

4. **Reusabilidade**:
   - Dialogs podem ser reutilizados em outros componentes
   - Padrões consistentes de confirmação e feedback

5. **Type Safety**:
   - Type hints completos facilitam IDE autocomplete
   - Reduz erros de tipo em tempo de desenvolvimento

## Referências

- Documento de análise: `docs/EXTRACTION_ANALYSIS_PHASE2.md`
- Arquivo original: `src/zebtrack/ui/gui.py`
- Arquivo criado: `src/zebtrack/ui/components/dialog_manager.py`
- Task tracking: Phase 2, Task 2.1
