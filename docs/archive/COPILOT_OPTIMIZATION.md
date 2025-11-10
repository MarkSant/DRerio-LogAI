# ZebTrack-AI: Guia de Otimização para GitHub Copilot

## 🚀 Sistema de Otimização Implementado

Este documento descreve o sistema completo de otimização criado para maximizar a eficiência do GitHub Copilot no ZebTrack-AI.

## 📁 Arquivos Criados/Atualizados

### 1. **`.copilot-context.yaml`** (Auto-gerado)
Arquivo de navegação rápida com:
- Índice de arquivos principais
- Árvores de decisão para tarefas comuns
- Comandos copy-paste prontos
- Anti-padrões (o que NUNCA fazer)
- Pipeline de dados

**Regenerar**: `poetry run python scripts/generate_copilot_context.py`

### 2. **`scripts/generate_copilot_context.py`** (Novo)
Script que analisa o codebase e gera automaticamente:
- Mapa arquitetural
- Índice de classes e métodos principais
- Árvores de decisão personalizadas
- Referências rápidas

### 3. **`scripts/validate_docs.py`** (Novo)
Validador de consistência que verifica:
- ✅ Settings documentados no REFERENCE_GUIDE
- ✅ Ausência de imports singleton proibidos
- ✅ Docstrings em classes principais
- ✅ Atualização do `.copilot-context.yaml`

### 4. **`.github/copilot-instructions.md`** (Atualizado)
Playbook otimizado com:
- 🎯 Quick Navigation Index
- ⚡ Fast Decision Trees
- 📋 Arquivo único de referência
- Instruções de leitura única

### 5. **`.pre-commit-config.yaml`** (Atualizado)
Hooks automáticos:
- `validate-docs`: Roda em cada commit
- `update-copilot-context`: Roda em cada push

### 6. **`.github/workflows/ci.yml`** (Atualizado)
CI com validação automática:
- Valida consistência de docs
- Regenera `.copilot-context.yaml`
- Falha se contexto estiver desatualizado

### 7. **`.vscode/launch.json`** (Atualizado)
Debug profiles especializados:
- **Wizard Debug**: Debug do wizard de 5 etapas
- **Processing Debug**: Debug do pipeline de processamento
- **Smoke Tests**: Testes rápidos (< 30s)
- **GUI Tests**: Testes Tkinter single-threaded

### 8. **`tests/test_smoke.py`** (Novo)
Suite de smoke tests para feedback rápido:
- Valida imports principais
- Verifica inicialização de serviços
- Detecta anti-padrões (singleton imports)
- Executa em < 30 segundos

### 9. **`pytest.ini`** (Atualizado)
Novo marker: `smoke` para testes rápidos

## 🔄 Workflow Automatizado

### Pre-commit (Local)
```bash
# Instalar hooks
poetry run pre-commit install

# Executar manualmente
poetry run pre-commit run --all-files
```

**O que acontece:**
1. Ruff lint + format
2. Validação de docs (`validate_docs.py`)
3. Atualização do contexto (push only)

### CI (GitHub Actions)
**No lint job:**
1. Valida documentação
2. Regenera `.copilot-context.yaml`
3. Verifica se o arquivo está atualizado

**Falha se:**
- Settings não documentados
- Import singleton encontrado
- Classes sem docstrings
- Contexto desatualizado

## 📊 Comandos Rápidos

### Desenvolvimento
```powershell
# Feedback imediato (< 30s)
poetry run pytest -m smoke

# Testes rápidos
poetry run pytest -q

# Testes GUI
poetry run pytest -m gui -n0

# Atualizar contexto
poetry run python scripts/generate_copilot_context.py

# Validar docs
poetry run python scripts/validate_docs.py
```

### Debug
Use profiles do VS Code:
- `F5` → "ZebTrack: Run Application"
- `F5` → "ZebTrack: Debug Wizard Flow"
- `F5` → "ZebTrack: Smoke Test"

## 🎯 Como o Copilot Usa Isso

### 1. **Primeira Consulta**
Copilot lê `.copilot-context.yaml` para:
- Encontrar arquivos rapidamente
- Decidir o que ler
- Evitar buscas desnecessárias

### 2. **Decision Trees**
Exemplo: "Adicionar nova feature de UI"
```yaml
adding_ui_feature:
  - "1. Check ui/widgets/ for reusable components"
  - "2. Update MainViewModel with constructor injection"
  - "3. Use root.after(0, ...) for async updates"
  - "4. Add integration test"
```

### 3. **Anti-padrões**
Copilot evita automaticamente:
```yaml
forbidden:
  - "from zebtrack import settings  # Use constructor injection"
  - "Direct state mutation  # Use StateManager"
  - "Blocking UI thread  # Use root.after()"
```

## 📈 Métricas de Otimização

### Antes
- ❌ Múltiplas leituras de arquivos
- ❌ Buscas exploratórias
- ❌ Contexto impreciso
- ❌ Tokens desperdiçados

### Depois
- ✅ Leitura direta via índice
- ✅ Decision trees guiam ações
- ✅ Contexto sempre atualizado
- ✅ Redução ~40-60% de tokens

## 🔧 Manutenção

### Quando Atualizar Manualmente
Rode após mudanças arquiteturais significativas:
```powershell
poetry run python scripts/generate_copilot_context.py
```

### Automático
O sistema atualiza automaticamente:
- ✅ Em cada `git push` (pre-commit hook)
- ✅ No CI (GitHub Actions)
- ✅ Valida em cada commit

### Adicionar Novos Padrões
Edite `scripts/generate_copilot_context.py`:
```python
def build_decision_trees() -> dict[str, Any]:
    return {
        "nova_tarefa": [
            "1. Passo específico",
            "2. Comando exato",
            "3. Arquivo para editar",
        ]
    }
```

## 🎓 Boas Práticas

### Para Desenvolvedores
1. **Sempre rode smoke tests** antes de commit
2. **Use debug profiles** do VS Code
3. **Consulte decision trees** no `.copilot-context.yaml`
4. **Não ignore warnings** do `validate_docs.py`

### Para o Copilot
1. **Leia `.copilot-context.yaml` primeiro**
2. **Use índices de arquivo** para navegação direta
3. **Siga decision trees** para tarefas padrão
4. **Evite anti-padrões** listados

## 📚 Referências Rápidas

### Arquivos Principais
- Entry Point: `src/zebtrack/__main__.py:140-280`
- Main UI: `src/zebtrack/ui/gui.py`
- Settings: `src/zebtrack/settings.py`
- Detector: `src/zebtrack/core/detector_service.py`

### Documentação Crítica
- `docs/ARCHITECTURE.md` - Visão geral
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - Padrões DI
- `.github/copilot-instructions.md` - Playbook completo
- `.copilot-context.yaml` - Navegação rápida

## 🚦 Status de Saúde

Execute para verificar:
```powershell
# Validação completa
poetry run python scripts/validate_docs.py

# Smoke tests
poetry run pytest -m smoke

# Pre-commit checks
poetry run pre-commit run --all-files
```

**Sistema saudável se:**
- ✅ Nenhum erro no validate_docs
- ✅ Smoke tests passam
- ✅ Pre-commit limpo
- ✅ CI verde

## 🎉 Resultado Final

Um sistema que:
1. ✅ **Auto-documenta** a arquitetura
2. ✅ **Valida automaticamente** consistência
3. ✅ **Atualiza-se sozinho** via hooks
4. ✅ **Guia o Copilot** com precisão
5. ✅ **Reduz tokens** significativamente
6. ✅ **Acelera desenvolvimento** com feedback rápido

---

**Última atualização**: Sistema implementado em 01/11/2025
**Versão**: 1.0.0
