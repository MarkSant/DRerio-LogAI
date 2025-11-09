# Refatoração ZebTrack-AI - Referência Rápida

## 📋 Arquivo Principal

**Para Coordenação Completa**: `AGENT_ORCHESTRATION_GUIDE.md`

## 🚀 Início Rápido para Coordenador

### Passo 1: Criar Branch da Fase 1

```bash
git checkout main
git pull origin main
git checkout -b refactor/phase-1-critical-fixes
git push origin refactor/phase-1-critical-fixes
```

### Passo 2: Atribuir Agentes

**IMPORTANTE**: Agent-5 deve começar PRIMEIRO e ser mergeado antes dos outros.

#### Instruções para Agent-5 (PRIORITÁRIO)

```bash
# Envie este link ao Agent-5:
# Ver seção "Agent-5: Custom Exception Hierarchy" em AGENT_ORCHESTRATION_GUIDE.md
# Linhas ~100-180

# Resumo da tarefa:
# - Criar hierarquia de exceções customizadas (15+ classes)
# - Arquivo: src/zebtrack/exceptions.py
# - Testes: tests/test_exceptions.py
# - Tempo: 2 dias
# - Branch: task/p1-t5-custom-exceptions
# - PR para: refactor/phase-1-critical-fixes
```

#### Após P1-T5 Mergeado, Atribuir em Paralelo

**Agent-1 (Exception Handling)** + **Agent-2 (Resource Management)**:

```bash
# Ambos podem trabalhar simultaneamente após P1-T5 mergeado
# Ver seções "Agent-1" e "Agent-2" em AGENT_ORCHESTRATION_GUIDE.md
```

**Agent-3 (Settings Injection)** + **Agent-4 (CI Fixes)**:

```bash
# Podem trabalhar simultaneamente, INDEPENDENTES de P1-T5
# Ver seções "Agent-3" e "Agent-4" em AGENT_ORCHESTRATION_GUIDE.md
```

### Passo 3: Ordem de Merge Fase 1

```text
1. P1-T5 (Agent-5) ← PRIMEIRO
2. P1-T4 (Agent-4) ← Paralelo com #3
3. P1-T3 (Agent-3) ← Paralelo com #2
4. P1-T1 (Agent-1) ← Após P1-T5
5. P1-T2 (Agent-2) ← Após P1-T5
6. Merge refactor/phase-1-critical-fixes → main
```

### Passo 4: Iniciar Fase 2

```bash
git checkout main
git pull origin main
git checkout -b refactor/phase-2-god-objects
git push origin refactor/phase-2-god-objects

# Atribuir Agent-6 e Agent-7 em paralelo
# Ver "FASE 2" em AGENT_ORCHESTRATION_GUIDE.md
```

## 📊 Visão Geral das Fases

| Fase | Tarefas | Agentes | Tempo | Paralelização Máxima |
|------|---------|---------|-------|----------------------|
| 1 | 5 | Agent-1 a Agent-5 | 2 semanas | 4 agentes (após Agent-5) |
| 2 | 3 | Agent-6 a Agent-8 | 2 semanas | 2 agentes |
| 3 | 4 | Agent-9 a Agent-12 | 2 semanas | 4 agentes |
| 4 | 3 | Agent-13 a Agent-15 | 1 semana | 3 agentes |

**Total**: 15 tarefas, 15 agentes, 7 semanas (ou ~4 semanas com paralelização)

## 🎯 Grupos de Trabalho Paralelo

### Fase 1: 5 Tarefas

**Onda 1** (2 dias):

- Agent-5 (Custom Exceptions) ← BLOQUEANTE

**Onda 2** (3 dias) - Iniciar após P1-T5 mergeado:

- Agent-1 (Exception Handling) ← Depende de P1-T5
- Agent-2 (Resource Management) ← Depende de P1-T5

**Onda 2 Paralela** (2 dias) - Pode iniciar imediatamente:

- Agent-3 (Settings Injection) ← Independente
- Agent-4 (CI Fixes) ← Independente

### Fase 2: 3 Tarefas

**Onda 1** (4 dias):

- Agent-6 (HardwareCoordinator)
- Agent-7 (AnalysisCoordinator)

**Onda 2** (3 dias) - Após Onda 1 mergeada:

- Agent-8 (MainViewModel Refactor)

### Fase 3: 4 Tarefas

**Onda 1** (4 dias) - TODAS EM PARALELO:

- Agent-9 (Test Isolation)
- Agent-10 (Coverage 80%)
- Agent-11 (Integration Tests)
- Agent-12 (Code Quality)

### Fase 4: 3 Tarefas

**Onda 1** (3 dias) - TODAS EM PARALELO:

- Agent-13 (Performance)
- Agent-14 (DevOps Tooling)
- Agent-15 (Documentation) ← Merge por último

## ✅ Checklist do Coordenador

### Antes de Iniciar

- [ ] Repositório clonado e atualizado
- [ ] Poetry instalado
- [ ] GitHub CLI configurado (`gh auth login`)
- [ ] Todos os agentes têm acesso ao repositório

### Fase 1

- [ ] Branch `refactor/phase-1-critical-fixes` criada
- [ ] Agent-5 iniciou trabalho (P1-T5)
- [ ] PR P1-T5 revisado e mergeado
- [ ] Agent-1, Agent-2, Agent-3, Agent-4 iniciaram trabalho
- [ ] Todos os 5 PRs revisados e mergeados na ordem correta
- [ ] Branch `refactor/phase-1-critical-fixes` mergeada em `main`
- [ ] CI passing em `main`

### Fase 2

- [ ] Branch `refactor/phase-2-god-objects` criada a partir da `main` atualizada
- [ ] Agent-6 e Agent-7 iniciaram trabalho
- [ ] PRs P2-T1 e P2-T2 revisados e mergeados
- [ ] Agent-8 iniciou trabalho
- [ ] PR P2-T3 revisado e mergeado
- [ ] MainViewModel < 2000 linhas confirmado
- [ ] Branch mergeada em `main`

### Fase 3

- [ ] Branch `refactor/phase-3-testing-quality` criada
- [ ] Todos os 4 agentes iniciaram trabalho simultaneamente
- [ ] Todos os 4 PRs revisados e mergeados
- [ ] Coverage ≥80% confirmado
- [ ] Branch mergeada em `main`

### Fase 4

- [ ] Branch `refactor/phase-4-performance-docs` criada
- [ ] Todos os 3 agentes iniciaram trabalho
- [ ] PRs P4-T1 e P4-T2 mergeados
- [ ] PR P4-T3 (Documentation) mergeado POR ÚLTIMO
- [ ] Toda documentação validada
- [ ] Branch mergeada em `main`

### Finalização

- [ ] Todas as 4 fases completas
- [ ] CI/CD passing
- [ ] Todas as métricas atingidas (ver abaixo)
- [ ] Release notes criadas

## 📈 Métricas de Sucesso

| Métrica | Antes | Meta | Como Verificar |
|---------|-------|------|----------------|
| MainViewModel linhas | 5,383 | <2,000 | `wc -l src/zebtrack/core/main_view_model.py` |
| Deps MainViewModel | 11 | ≤7 | Contar params em `__init__` |
| Test Coverage | 70% | 80% | `poetry run pytest --cov=zebtrack` |
| Erros Ruff | 0 | 0 | `poetry run ruff check .` |
| Custom Exceptions | 8 | 15+ | Contar em `src/zebtrack/exceptions.py` |
| Singleton Imports | 2 | 0 | `grep -r "from zebtrack import settings" src/` |
| Docs Obsoletos | ~50 | <10 | Contar `.md` fora de `docs/archive/` |

## 🔧 Comandos Úteis para Coordenador

### Monitorar Progresso

```bash
# Ver todas as branches
git branch -a | grep task/

# Ver PRs abertos para uma fase
gh pr list --base refactor/phase-1-critical-fixes

# Ver status de um PR
gh pr view 123

# Ver diff de uma branch
git diff refactor/phase-1-critical-fixes...main --stat
```

### Revisar PRs

```bash
# Fazer checkout de um PR
gh pr checkout 123

# Executar testes
poetry run pytest -q

# Verificar linting
poetry run ruff check .

# Ver mudanças
git diff main...HEAD --stat
```

### Mergear PRs

```bash
# Mergear com squash (recomendado)
gh pr merge 123 --squash --delete-branch

# Ou via interface web
gh pr view 123 --web
```

### Mergear Branch de Fase em Main

```bash
# Após todas as tarefas da fase mergeadas
git checkout main
git pull origin main
git merge refactor/phase-1-critical-fixes --squash

git commit -m "feat: Complete Phase 1 refactoring - Critical Fixes

Phase 1 deliverables:
- ✅ Custom exception hierarchy (15+ exceptions)
- ✅ Broad exception handling replaced (30+ sites)
- ✅ Context managers for Camera and Recorder
- ✅ Settings injection 100% complete
- ✅ CI YAML syntax fixed

Refs: #phase-1"

git push origin main

# Deletar branch de fase
git push origin --delete refactor/phase-1-critical-fixes
```

## 🆘 Troubleshooting Rápido

### PR com Conflitos

```bash
# Agent deve atualizar sua branch
git checkout task/pX-tY-name
git fetch origin
git merge origin/refactor/phase-X-name
# Resolver conflitos
git commit
git push
```

### Testes Falhando no CI mas Passando Localmente

```bash
# Verificar versão do Python
python --version  # Deve ser 3.12+

# Limpar cache e reinstalar
poetry env remove --all
poetry install
poetry run pytest --cache-clear
poetry run pytest -q
```

### Agent Bloqueado Esperando Merge

```bash
# Priorizar review e merge do PR bloqueante
# Comunicar aos agents dependentes quando estiver pronto
```

## 📞 Comunicação com Agentes

### Template de Atribuição de Tarefa

```text
Olá Agent-X,

Você foi atribuído à tarefa PX-TY: [NOME DA TAREFA]

📋 Instruções:
1. Abra o arquivo: AGENT_ORCHESTRATION_GUIDE.md
2. Busque por: "Agent-X: [NOME DA TAREFA]"
3. Siga todos os comandos listados na sua seção

⏰ Tempo estimado: X dias

🔗 Dependências:
- [Lista de dependências se houver]
- Pode trabalhar em paralelo com: [Lista de agentes paralelos]

✅ Critérios de aceitação:
- [Lista dos principais critérios]

🚦 Status:
- [ ] Branch criada
- [ ] Implementação completa
- [ ] Testes passando
- [ ] Linting OK
- [ ] PR criado
- [ ] PR aprovado
- [ ] PR mergeado

Qualquer dúvida, consulte a seção de troubleshooting no guia ou me contate.

Bom trabalho!
```

### Template de Aprovação de PR

```text
✅ PR Aprovado - PX-TY

Revisão completa:
- ✅ Código segue padrões do projeto
- ✅ Testes passando (poetry run pytest -q)
- ✅ Linting OK (poetry run ruff check .)
- ✅ Documentação atualizada
- ✅ Critérios de aceitação atingidos

Pronto para merge. Bom trabalho!
```

## 📚 Recursos Adicionais

- **Guia Completo**: `AGENT_ORCHESTRATION_GUIDE.md`
- **Arquitetura**: `docs/ARCHITECTURE.md`
- **Testes**: `docs/TESTING_GUIDE.md`
- **Contribuição**: `CONTRIBUTING.md`

## 🎯 Meta Final

Ao final das 4 fases:

- ✅ Codebase refatorado e limpo
- ✅ MainViewModel reduzido de 5,383 → <2,000 linhas
- ✅ Exceções customizadas em toda a aplicação
- ✅ Context managers para todos os recursos
- ✅ Settings injection 100% completo
- ✅ Test coverage ≥80%
- ✅ Documentação curada e organizada
- ✅ Zero erros Ruff
- ✅ CI/CD passando
- ✅ Performance otimizado
- ✅ DevOps tooling configurado

**Projeto pronto para produção e manutenção sustentável!**

---

**Última Atualização**: 9 de Novembro de 2025
**Versão**: 1.0
