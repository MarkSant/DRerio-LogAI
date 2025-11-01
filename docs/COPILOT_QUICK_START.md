# Sistema de Otimização do GitHub Copilot

## 🚀 Quick Start

### Para Desenvolvedores

```powershell
# 1. Feedback rápido (< 30s)
poetry run pytest -m smoke

# 2. Atualizar contexto do Copilot
poetry run python scripts/generate_copilot_context.py

# 3. Validar documentação
poetry run python scripts/validate_docs.py

# 4. Instalar pre-commit hooks
poetry run pre-commit install
```

### Para o GitHub Copilot

**Sempre consulte `.copilot-context.yaml` primeiro!**

Este arquivo contém:
- ✅ Índice de arquivos principais
- ✅ Árvores de decisão para tarefas comuns
- ✅ Comandos prontos
- ✅ Anti-padrões a evitar

## 📁 Arquivos do Sistema

| Arquivo | Propósito | Atualização |
|---------|-----------|-------------|
| `.copilot-context.yaml` | Navegação rápida e decisões | Script + pre-push |
| `.github/copilot-instructions.md` | Playbook completo | Manual |
| `scripts/generate_copilot_context.py` | Gerador de contexto | N/A |
| `scripts/validate_docs.py` | Validador de consistência | N/A |
| `tests/test_smoke.py` | Testes rápidos | Manual |
| `.vscode/launch.json` | Profiles de debug | Manual |

## 🎯 Workflows

### Desenvolvimento Local

```powershell
# 1. Fazer mudanças
# 2. Rodar smoke tests
poetry run pytest -m smoke

# 3. Commit (pre-commit roda automaticamente)
git add .
git commit -m "feat: ..."

# 4. Push (atualiza contexto automaticamente)
git push
```

### CI/CD (Automático)

```yaml
lint job:
  - Valida docs → validate_docs.py
  - Gera contexto → generate_copilot_context.py
  - Verifica se está atualizado
  - Falha se inconsistente
```

## 📚 Guias Rápidos

### Adicionar Nova Feature

Consulte `.copilot-context.yaml` → Seção `adding_*_feature`

**UI:**
```yaml
1. Check ui/widgets/
2. Update MainViewModel
3. Use root.after()
4. Add integration test
```

**Processing:**
```yaml
1. Check core/detector_service.py
2. Inject settings_obj
3. Update schema if needed
4. Run pytest -q
```

### Debug

**Profiles disponíveis (F5 no VS Code):**
- `ZebTrack: Run Application` - Rodar app
- `ZebTrack: Debug Wizard Flow` - Debug do wizard
- `ZebTrack: Smoke Test` - Testes rápidos

### Resolver Erros de Validação

```powershell
# Ver problemas
poetry run python scripts/validate_docs.py

# Tipos de problemas:
# 1. Settings não documentados → Update docs/REFERENCE_GUIDE.md
# 2. Singleton import → Use constructor injection
# 3. Docstring faltando → Add docstring
# 4. Contexto desatualizado → Run generate_copilot_context.py
```

## ⚡ Comandos Essenciais

```powershell
# Testes
poetry run pytest -m smoke          # < 30s, crítico
poetry run pytest -q                # Fast suite
poetry run pytest -m gui -n0        # GUI tests
poetry run pytest --cov=zebtrack    # Coverage

# Qualidade
poetry run ruff check .             # Lint
poetry run ruff format .            # Format
poetry run pre-commit run --all     # Pre-commit

# Contexto
poetry run python scripts/generate_copilot_context.py    # Atualizar
poetry run python scripts/validate_docs.py               # Validar
```

## 🔍 Decision Trees

### "Como adicionar uma config?"

1. Edit `src/zebtrack/settings.py`
2. Add field to `config.yaml`
3. Pass via constructor from `__main__.py`
4. Document in `docs/REFERENCE_GUIDE.md`
5. NEVER use `from zebtrack import settings`

### "Como debugar UI?"

1. Check structlog output
2. Verify `StateManager.update_ui_state()`
3. Check `root.after()` scheduling
4. Run: `poetry run pytest -m gui -n0`

### "Como debugar processing?"

1. Check detector_service zone scaling
2. Verify ProcessingWorker thread
3. Validate Recorder schema
4. Run: `poetry run pytest -q`

## 🚫 Anti-Padrões (NUNCA FAÇA)

```python
# ❌ Singleton import
from zebtrack import settings

# ✅ Constructor injection
def __init__(self, settings_obj: Settings):
    self.settings = settings_obj

# ❌ Direct state mutation
self.some_state = True

# ✅ Use StateManager
state_manager.update_ui_state(some_state=True)

# ❌ Block UI thread
result = long_operation()

# ✅ Use root.after()
root.after(0, long_operation)
```

## 📊 Métricas de Sucesso

### Sistema Saudável

```powershell
# Todos devem passar:
poetry run python scripts/validate_docs.py  # Exit 0
poetry run pytest -m smoke                   # 100% pass
poetry run pre-commit run --all-files        # Exit 0
```

### Indicadores

- ✅ Smoke tests < 30s
- ✅ Validação docs sem erros
- ✅ Pre-commit limpo
- ✅ CI verde

## 🔄 Automação

### Quando é Ativada

| Evento | Ação | Tool |
|--------|------|------|
| `git commit` | Valida docs | pre-commit hook |
| `git push` | Atualiza contexto | pre-commit hook |
| CI (lint job) | Valida + gera contexto | GitHub Actions |
| Manual | A qualquer momento | Scripts |

### Forçar Atualização

```powershell
# Se contexto estiver desatualizado
poetry run python scripts/generate_copilot_context.py

# Se hooks não rodarem
poetry run pre-commit run --all-files
```

## 🎓 Best Practices

### Para Desenvolvedores

1. ✅ Sempre rode smoke tests antes de commit
2. ✅ Use debug profiles do VS Code
3. ✅ Consulte decision trees no `.copilot-context.yaml`
4. ✅ Não ignore warnings do validate_docs
5. ✅ Mantenha docstrings atualizadas

### Para o GitHub Copilot

1. ✅ Leia `.copilot-context.yaml` PRIMEIRO
2. ✅ Use índices de arquivo para navegação direta
3. ✅ Siga decision trees para tarefas padrão
4. ✅ Evite anti-padrões listados
5. ✅ Prefira leituras diretas vs. buscas exploratórias

## 📖 Documentação Completa

- `docs/COPILOT_OPTIMIZATION.md` - Guia completo do sistema
- `.github/copilot-instructions.md` - Playbook do Copilot
- `.copilot-context.yaml` - Navegação rápida (auto-gerado)
- `docs/ARCHITECTURE.md` - Arquitetura geral
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - Padrões DI

## 🆘 Troubleshooting

### Contexto Desatualizado

```powershell
poetry run python scripts/generate_copilot_context.py
git add .copilot-context.yaml
git commit -m "chore: update copilot context"
```

### Validação Falha no CI

```powershell
# Local
poetry run python scripts/validate_docs.py

# Corrija os problemas reportados
# Commit e push
```

### Smoke Tests Falhando

```powershell
# Ver detalhes
poetry run pytest -m smoke -v

# Corrigir testes ou código
# Smoke tests devem sempre passar rapidamente
```

---

**Sistema implementado**: 01/11/2025
**Versão**: 1.0.0
**Manutenção**: Automática via hooks + CI
