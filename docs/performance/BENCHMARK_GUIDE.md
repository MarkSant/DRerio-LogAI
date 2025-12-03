# Pytest Benchmark - Guia de Uso

## Instalação

O `pytest-benchmark` já está instalado como dependência de desenvolvimento:

```bash
poetry install
```

## Como Executar Benchmarks

### Comando Básico

```bash
poetry run pytest tests/benchmarks/ -m benchmark -n0 --benchmark-only
```

**Flags importantes:**

- `-m benchmark`: Executa apenas testes marcados com `@pytest.mark.benchmark`
- `-n0`: **OBRIGATÓRIO** - Desabilita paralelização (pytest-xdist)
- `--benchmark-only`: Executa apenas benchmarks, sem testes normais

### Desabilitar Coverage

Para resultados mais limpos, desabilite o coverage:

```bash
poetry run pytest tests/benchmarks/ -m benchmark -n0 --benchmark-only --no-cov
```

### Customizar Colunas de Resultado

```bash
poetry run pytest tests/benchmarks/ -m benchmark -n0 --benchmark-only \
    --benchmark-columns=min,max,mean,stddev,median,ops
```

### Salvar Resultados

```bash
# Salvar resultados em JSON
poetry run pytest tests/benchmarks/ -m benchmark -n0 --benchmark-only \
    --benchmark-save=my_benchmark

# Comparar com resultados anteriores
poetry run pytest tests/benchmarks/ -m benchmark -n0 --benchmark-only \
    --benchmark-compare=my_benchmark
```

## Como Criar Benchmarks

### Estrutura Básica

```python
import pytest

@pytest.mark.benchmark
def test_my_benchmark(benchmark):
    """Descrição do benchmark."""

    def my_function():
        # Código a ser medido
        return some_computation()

    result = benchmark(my_function)
    assert result is not None  # Validação opcional
```

### Exemplo Completo

```python
import numpy as np
import pytest

@pytest.mark.benchmark
def test_benchmark_array_operations(benchmark):
    """Benchmark para operações com arrays NumPy."""

    def array_operation():
        arr = np.random.rand(1000, 1000)
        return arr.mean() + arr.std()

    result = benchmark(array_operation)
    assert isinstance(result, float)
```

### Com Setup/Teardown

```python
@pytest.mark.benchmark
def test_benchmark_with_setup(benchmark):
    """Benchmark com setup que não é medido."""

    # Setup (não é medido)
    data = np.random.rand(10000)

    def process_data():
        # Apenas isso é medido
        return data.sum()

    result = benchmark(process_data)
    assert result > 0
```

## Configuração Avançada

### Customizar Número de Rodadas

```python
@pytest.mark.benchmark(
    min_rounds=10,
    max_time=2.0,
    warmup=True
)
def test_benchmark_custom(benchmark):
    result = benchmark(lambda: expensive_operation())
    assert result
```

### Usar Fixture como Setup

```python
@pytest.fixture
def sample_data():
    return np.random.rand(1000, 1000)

@pytest.mark.benchmark
def test_benchmark_with_fixture(benchmark, sample_data):
    result = benchmark(lambda: sample_data.mean())
    assert result is not None
```

## Interpretação dos Resultados

```text
Name (time in us)                     Min        Max      Mean    StdDev    Median      OPS
test_benchmark_list_comprehension  507.30   1,481.60   647.90    155.36    599.10  1,543.46
test_benchmark_numpy_operations  8,700.90  15,301.80  9,840.31  1,004.80  9,608.40    101.62
```

- **Min/Max**: Tempo mínimo/máximo de execução
- **Mean**: Tempo médio
- **StdDev**: Desvio padrão (menor = mais consistente)
- **Median**: Mediana (menos afetada por outliers)
- **OPS**: Operações por segundo (maior = mais rápido)

## Localização dos Arquivos

```text
tests/
└── benchmarks/
    ├── __init__.py
    └── test_benchmark_example.py    # Exemplos de benchmarks
```

## Boas Práticas

### ✅ DO

- Use `@pytest.mark.benchmark` em todos os testes de benchmark
- Crie diretório separado `tests/benchmarks/`
- Meça apenas a operação crítica (não inclua setup no benchmark)
- Execute com `-n0` (sem paralelização)
- Documente o que está sendo medido

### ❌ DON'T

- Não execute benchmarks em paralelo (`-n auto`)
- Não inclua operações de setup dentro do benchmark
- Não compare resultados de máquinas diferentes
- Não use fixtures pesadas sem `@pytest.mark.usefixtures`

## Troubleshooting

### Erro: "Can't have both --benchmark-only and --benchmark-disable"

**Causa**: pytest-xdist está ativado (paralelização).

**Solução**: Use `-n0`:

```bash
poetry run pytest tests/benchmarks/ -m benchmark -n0 --benchmark-only
```

### Erro: "Benchmark fixture was not used"

**Causa**: A fixture `benchmark` não foi utilizada no teste.

**Solução**: Use `benchmark(function)` ou remova o marker:

```python
@pytest.mark.benchmark
def test_my_benchmark(benchmark):
    result = benchmark(lambda: my_function())  # ✅ Correto
```

### Coverage Warnings

**Causa**: Coverage está tentando medir código que não foi executado.

**Solução**: Desabilite coverage para benchmarks:

```bash
poetry run pytest tests/benchmarks/ -m benchmark -n0 --benchmark-only --no-cov
```

## Referências

- [pytest-benchmark Documentation](https://pytest-benchmark.readthedocs.io/)
- [Pytest Markers](https://docs.pytest.org/en/stable/how-to/mark.html)
- Exemplos: `tests/benchmarks/test_benchmark_example.py`
