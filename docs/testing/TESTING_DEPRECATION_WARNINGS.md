# Testing with DeprecationWarnings

## Problema Identificado

Ao executar `poetry run pytest -W error::DeprecationWarning`, os testes falhavam com múltiplos erros de `DeprecationWarning` relacionados a `pkg_resources.declare_namespace('sphinxcontrib')`.

### Causa Raiz

O problema **NÃO está no código do ZebTrack**, mas em dependências externas:

```text
zebtrack.analysis.reporter → docxtpl → docxcompose → pkg_resources
```

O módulo `pkg_resources` (parte do `setuptools`) usa `declare_namespace()` que foi deprecado em favor de PEP 420 implicit namespace packages. Especificamente, pacotes `sphinxcontrib-*` ainda usam esta API antiga.

## Solução Implementada

### 1. Filtros de Warnings no `pytest.ini`

Adicionamos filtros específicos para ignorar `DeprecationWarnings` de pacotes externos:

```ini
filterwarnings =
    default
    ignore:Deprecated call to .pkg_resources.declare_namespace.*:DeprecationWarning:pkg_resources.*
    ignore::DeprecationWarning:pkg_resources.*
    ignore::DeprecationWarning:docxcompose.*
    ignore::DeprecationWarning:docxtpl.*
    ignore::DeprecationWarning:sphinxcontrib.*
```

### 2. Limitação Importante

⚠️ **A flag `-W` da linha de comando SOBRESCREVE as configurações do `pytest.ini`.**

Por isso:

- ✅ **CORRETO**: `poetry run pytest` (usa filtros do pytest.ini)
- ❌ **ERRADO**: `poetry run pytest -W error::DeprecationWarning` (ignora pytest.ini)

## Como Testar Corretamente

### Testes Normais

```bash
poetry run pytest
```

Isso executará os testes com os filtros configurados, ignorando warnings de dependências externas.

### Verificar DeprecationWarnings do ZebTrack

Se você quiser garantir que o **código do ZebTrack** não tem `DeprecationWarnings`, adicione ao `pytest.ini`:

```ini
filterwarnings =
    # ... filtros existentes ...
    error::DeprecationWarning:zebtrack.*
```

Isso converterá warnings do nosso código em erros, enquanto mantém os de dependências externas como warnings.

## Por Que Não Podemos Corrigir?

1. **Não controlamos as dependências externas**: `docxtpl`, `docxcompose`, `sphinxcontrib-*`
2. **O problema está no `setuptools`**: A deprecação do `pkg_resources` é uma mudança do ecossistema Python
3. **Não afeta funcionalidade**: São apenas warnings sobre APIs que serão removidas em versões futuras do setuptools

## Alternativas Futuras

1. **Atualizar dependências**: Quando `docxtpl`/`docxcompose` migrarem para APIs modernas
2. **Trocar biblioteca**: Se necessário, considerar alternativas ao `docxtpl` para geração de relatórios
3. **Pin setuptools**: Fixar versão do setuptools antes da remoção de `pkg_resources` (não recomendado)

## Status Atual

- ✅ Testes passam normalmente com `poetry run pytest`
- ✅ Coverage 38%+ (acima do mínimo de 30%)
- ✅ 1141+ testes passando
- ⚠️ 7 warnings de dependências externas (esperado e filtrado)

## Referências

- [PEP 420 - Implicit Namespace Packages](https://peps.python.org/pep-0420/)
- [Setuptools pkg_resources deprecation](https://setuptools.pypa.io/en/latest/pkg_resources.html)
- [pytest filterwarnings](https://docs.pytest.org/en/stable/how-to/capture-warnings.html#controlling-warnings)
