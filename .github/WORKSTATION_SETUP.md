# Workstation Setup Guide

Este guia explica como configurar rapidamente um novo workstation com todas as otimizações e personalizações do ZebTrack-AI.

## 🚀 Quick Setup (5 minutos)

### 1. Clone e Instale Dependências

```powershell
# Clone o repositório
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# Instale Poetry (se necessário)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Instale dependências
poetry install

# Ative o ambiente virtual
poetry shell
```

### 2. Configure Pre-commit Hooks

```powershell
# Instala hooks automaticamente
poetry run pre-commit install

# Testa instalação (opcional)
poetry run pre-commit run --all-files
```

### 3. Gere Contexto Inicial do Copilot

```powershell
# Gera .copilot-context.yaml
poetry run python scripts/generate_copilot_context.py

# Valida configuração
poetry run python scripts/validate_docs.py
```

### 4. Teste a Instalação

```powershell
# Smoke tests (< 30s)
poetry run pytest -m smoke

# Roda aplicação
poetry run zebtrack
```

## 🎯 Workstation Pronto

Seu workstation agora tem:

- ✅ **Pre-commit hooks** configurados
- ✅ **Contexto do Copilot** gerado
- ✅ **Debug profiles** do VS Code
- ✅ **Smoke tests** funcionando
- ✅ **Validação automática** ativa

## 📁 Arquivos de Configuração Sincronizados

Estes arquivos são sincronizados via Git e restauram sua configuração:

### Otimização do Copilot

- `.copilot-context.yaml` - Mapa de navegação (auto-gerado)
- `.github/copilot-instructions.md` - Playbook otimizado
- `scripts/generate_copilot_context.py` - Gerador de contexto
- `scripts/validate_docs.py` - Validador de consistência

### Automação

- `.pre-commit-config.yaml` - Hooks de validação
- `.github/workflows/ci.yml` - CI/CD com validações

### Debug e Testes

- `.vscode/launch.json` - Debug profiles especializados
- `pytest.ini` - Configuração de testes com marker `smoke`
- `tests/test_smoke.py` - Suite de smoke tests

### Documentação

- `docs/COPILOT_OPTIMIZATION.md` - Guia completo
- `docs/COPILOT_QUICK_START.md` - Referência rápida
- `docs/COPILOT_OPTIMIZATION_IMPLEMENTATION.md` - Log de implementação

## 🔧 Comandos Essenciais

### Desenvolvimento Diário

```powershell
# Feedback rápido
poetry run pytest -m smoke

# Rodar aplicação
poetry run zebtrack

# Testes completos
poetry run pytest -q

# Lint e format
poetry run ruff check .
poetry run ruff format .
```

### Manutenção

```powershell
# Atualizar contexto do Copilot
poetry run python scripts/generate_copilot_context.py

# Validar documentação
poetry run python scripts/validate_docs.py

# Rodar todos os pre-commit checks
poetry run pre-commit run --all-files
```

### Debug no VS Code

1. Abra VS Code no diretório do projeto
2. Pressione `F5` ou vá em "Run and Debug"
3. Escolha um profile:
   - **ZebTrack: Run App** - Rodar aplicação
   - **ZebTrack: Debug Wizard Flow** - Debug do wizard
   - **ZebTrack: Debug Processing Pipeline** - Debug de processamento
   - **ZebTrack: Smoke Test** - Rodar smoke tests
   - **ZebTrack: Debug Current Test File** - Debug de teste específico

## 🆘 Troubleshooting

### Contexto Desatualizado

```powershell
poetry run python scripts/generate_copilot_context.py
```

### Pre-commit Hooks Não Funcionam

```powershell
poetry run pre-commit install
poetry run pre-commit run --all-files
```

### Smoke Tests Falham

```powershell
# Ver detalhes
poetry run pytest -m smoke -v

# Verificar ambiente
poetry run python --version
poetry --version
```

### Dependências Desatualizadas

```powershell
# Atualizar lock file
poetry lock --no-update

# Reinstalar
poetry install
```

## 📚 Documentação Adicional

- **Arquitetura**: `docs/ARCHITECTURE.md`
- **Guia de Contribuição**: `CONTRIBUTING.md`
- **Dependency Injection**: `docs/DEPENDENCY_INJECTION_GUIDE.md`
- **Otimização Copilot**: `docs/COPILOT_OPTIMIZATION.md`

## 🎓 Best Practices

1. **Sempre rode smoke tests** antes de commit
2. **Use debug profiles** em vez de print debugging
3. **Consulte `.copilot-context.yaml`** para navegação rápida
4. **Mantenha hooks ativos** com `pre-commit install`
5. **Valide docs** periodicamente com `validate_docs.py`

## ⚙️ Configurações Opcionais

### Configurar Git

```powershell
git config --local user.name "Seu Nome"
git config --local user.email "seu@email.com"
```

### Configurar VS Code

As configurações do launch.json já estão sincronizadas. Para personalizar:

1. Abra `.vscode/launch.json`
2. Adicione/modifique profiles conforme necessário
3. Commit para sincronizar com outros workstations

### Variáveis de Ambiente

Se necessário, crie um `config.local.yaml`:

```yaml
# Sobrescreve config.yaml localmente
# Não é commitado (está no .gitignore)
processing:
  batch_size: 16  # Exemplo de override
```

## ✅ Checklist de Setup Completo

- [ ] Repositório clonado
- [ ] Poetry instalado e dependências baixadas
- [ ] Pre-commit hooks instalados
- [ ] Contexto do Copilot gerado
- [ ] Smoke tests passando
- [ ] Aplicação rodando
- [ ] Debug profiles testados (opcional)
- [ ] Git configurado (nome e email)

## 🎉 Setup Concluído

Seu workstation está completamente configurado e pronto para desenvolvimento eficiente com todas as otimizações do GitHub Copilot.

Para dúvidas, consulte:

- `docs/COPILOT_QUICK_START.md` - Guia rápido
- `docs/COPILOT_OPTIMIZATION.md` - Documentação completa

---

**Última atualização**: 01/11/2025
**Tempo estimado de setup**: 5 minutos
