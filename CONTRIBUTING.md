# Contributing Guide

Obrigado por querer contribuir com o ZebTrack-AI! Este guia descreve o fluxo de trabalho, padrões de código e expectativas para pull requests.

## 1. Preparando o ambiente

1. Clone o repositório:

   ```powershell
   git clone https://github.com/MarkSant/ZebTrack-AI.git
   cd ZebTrack-AI
   ```

1. Instale as dependências com Poetry:

   ```powershell
   poetry install
   ```

1. Ative o shell virtual (opcional, mas recomendado):

   ```powershell
   poetry shell
   ```

1. Verifique se a aplicação inicia:

   ```powershell
   poetry run zebtrack
   ```

## 2. Fluxo de desenvolvimento

- Sempre comece criando uma issue/rascunho descrevendo o problema ou feature.
- Crie um branch descritivo a partir de `main`:
  - `feat/<area>-<resumo>` para novas funcionalidades.
  - `fix/<area>-<bug>` para correções.
  - `docs/<topico>` para documentação.
- Desenvolva incrementalmente, mantendo commits pequenos e focados.
- Abra o pull request assim que tiver um rascunho funcional; use a checklist abaixo.

## 3. Estilo de código

- **Formatação & lint:** use Ruff (`poetry run ruff check .`) com `line-length = 88`.
- **Type hints:** exigidos para novos módulos/funções públicas.
- **Docstrings curtas:** use estilo Google ou NumPy quando a função não for autoexplicativa.
- **Logging:** utilize `structlog.get_logger()` e o padrão `dominio.acao.resultado` (por exemplo, `controller.processing.success`).
- **Configuração:** nenhum valor hardcoded; importe `from zebtrack import settings` e/ou leia do projeto via `ProjectManager`.
- **Threads/UI:** todo update de GUI deve ser agendado com `root.after(0, ...)`.

## 4. Testes

- Execute a suíte completa antes de abrir o PR:

  ```powershell
  poetry run pytest -q
  ```

- Adicione testes para novas funcionalidades ou coberturas regressivas.
- Atualize cenários críticos:
  - `tests/test_overlay_integration.py` para mudanças em overlays/GUI.
  - `tests/test_interval_frames_config.py` para persistência de intervalos.
  - `tests/test_recorder.py` ao mexer no esquema Parquet.
- Se a mudança alterar comportamentos de análise/reporting, considere fixtures sintéticas adicionais em `tests/analysis/`.
- Scripts legados de geração Wizard v1.5 foram removidos; para reproduzir cenários manuais, utilize os utilitários atuais em `tests/manual/` ou crie fixtures explícitas em pytest.

### 4.1. GUI Test Best Practices

**CRITICAL: GUI tests MUST run with serial execution (`-n0`).**

Why:

- `ttkbootstrap.Style` maintains global state (singleton) that is NOT thread-safe
- When pytest-xdist runs tests in parallel workers, simultaneous Style instantiation causes TclError failures
- Tkinter/Tcl interpreters conflict between processes

Correct execution:

```powershell
# Run all GUI tests (serial)
poetry run pytest -m gui -n0

# Run specific GUI test file (serial)
poetry run pytest tests/ui/wizard/test_wizard_confirmation.py -n0

# Use helper script (Windows)
.\scripts\run_gui_tests.ps1
```

Incorrect execution (will fail):

```powershell
# ❌ Missing -n0, uses default -n=auto (parallel)
poetry run pytest -m gui

# ❌ Default run excludes GUI tests
poetry run pytest
```

Writing GUI tests:

1. **Mark ALL GUI tests** with `@pytest.mark.gui` decorator at class or function level
2. **Use fixtures** from `conftest.py`:
   - `tkinter_root`: Provides configured Tk() root with cleanup
   - `wizard_dependencies`: Mocked wizard components
3. **Cleanup**: Destroy widgets explicitly or rely on fixture cleanup
4. **Avoid global state**: Don't modify ttkbootstrap.Style directly; use fixture-provided roots
5. **Document requirements**: Add docstring explaining serial execution need

Example GUI test structure:

```python
"""
GUI Test for MyComponent

CRITICAL: Run with -n0 (serial execution) to avoid ttkbootstrap.Style conflicts.
Correct: poetry run pytest -m gui -n0
"""
import pytest
from zebtrack.ui.components import MyComponent

@pytest.mark.gui
class TestMyComponent:
    def test_creation(self, tkinter_root):
        component = MyComponent(tkinter_root)
        assert component.winfo_exists()
```

Troubleshooting TclError:

1. Verify Tkinter works: `poetry run python -c "import tkinter; root = tkinter.Tk(); print('OK'); root.destroy()"`
2. Run test in isolation: `poetry run pytest path/to/test.py::test_name -n0 -v`
3. Check for missing `@pytest.mark.gui` marker
4. Ensure not using `-n auto` or parallel execution

References:

- `README_TESTS.md`: Full troubleshooting guide
- `pytest.ini`: Default exclusion of GUI tests
- `.github/workflows/ci.yml`: CI configuration (excludes GUI tests)

## 5. Padrões de commit

- Utilize **Conventional Commits**:
  - `feat: adiciona suporte a XYZ`
  - `fix: corrige progress callback`
  - `docs: atualiza README`
  - `refactor: reorganiza detector`
- Commits devem ser autoexplicativos. Mensagens em português ou inglês são aceitas (não misturar no mesmo PR).

## 6. Estruturando novas features

1. **Planeje**: descreva inputs/outputs, fluxos afetados e cenários negativos.
1. **Implemente**: mantenha mudanças focadas; evite reformatar blocos não relacionados.
1. **Teste**: cubra o caso feliz + 1-2 bordas (ex.: ausência de track_id, arquivo vazio, falta de configuração).
1. **Documente**:

   - Atualize `README.md` se o usuário final for impactado.
   - Ajuste `.github/copilot-instructions.md` para instruir automações.
   - Edite `docs/architecture/ARCHITECTURE.md` quando alterar fluxos ou decisões arquiteturais.
   - Cite migrações/configurações novas em `config.yaml` e `tests/test_settings.py`.

1. **Checklist antes do PR**:

   - [ ] Lint (`poetry run ruff check .`)
   - [ ] Testes (`poetry run pytest -q`)
   - [ ] Documentação atualizada
   - [ ] Capturas de tela/GIF quando relevante à UI

## 7. Processo de revisão

- Preencha a descrição do PR com contexto, abordagem e pontos para revisão.
- Referencie issues/decisões para rastreabilidade (`Closes #123`).
- Mantenha o PR abaixo de ~500 linhas alteradas quando possível; grandes refactors devem ser fracionados.
- Responda feedbacks em até 5 dias úteis.

## 8. Código de conduta

Este projeto adota o [Código de Conduta](CODE_OF_CONDUCT.md). A participação implica concordância com seus termos.

Ficamos felizes em receber novas ideias, correções e melhorias! Abra uma issue caso algo não esteja claro no processo.
