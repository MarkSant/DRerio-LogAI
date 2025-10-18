# Guia de Testes - ZebTrack-AI

## Visão Geral

Os testes do ZebTrack-AI foram organizados para melhor performance e compatibilidade cross-platform (Windows/Linux/macOS).

## Marcadores de Teste (Test Markers)

### Tipos de Marcadores

- **`@pytest.mark.gui`**: Testes que usam componentes Tkinter
  - Rodam sequencialmente (não paralelizados)
  - Compatíveis com Windows (não requerem virtual display)
  - Exemplo: Tests do wizard, análise de UI

- **`@pytest.mark.slow`**: Testes que demoram > 1 segundo
  - Envolvem operações de I/O lentas ou sleeps necessários
  - Excluídos da execução padrão (para CI/desenvolvimento rápido)
  - Exemplo: Testes de cache com sleep de filesystem

- **`@pytest.mark.integration`**: Testes de integração entre componentes
  - Testam múltiplos módulos trabalhando juntos
  - Podem ser mais lentos que testes unitários

- **`@pytest.mark.unit`**: Testes unitários puros
  - Testam uma única função/classe isoladamente
  - Rápidos e independentes

- **`@pytest.mark.ttkbootstrap_singleton`**: Testes afetados pelo Style singleton do ttkbootstrap
  - Devem ser executados em isolamento
  - Excluídos da execução padrão
  - Exemplo: `tests/ui/test_components.py` (22 testes)
  - **Problema conhecido**: O singleton do ttkbootstrap mantém referências a Tk instances antigas
  - **Solução**: Rodar em isolamento: `poetry run pytest tests/ui/test_components.py`

## Comandos de Execução

### Execução Padrão (Rápida)
```powershell
# Executa apenas testes rápidos e não-GUI em paralelo
# Exclui: GUI, slow e ttkbootstrap_singleton
poetry run pytest

# Equivalente a:
poetry run pytest -m "not (gui or slow or ttkbootstrap_singleton)"
```

**Resultado esperado**: ~540 testes em ~55 segundos

### Executar Testes GUI
```powershell
# Testes GUI rodam sequencialmente (sem paralelização)
poetry run pytest -m gui -n0
```

### Executar Testes Slow
```powershell
# Inclui testes que demoram mais tempo
poetry run pytest -m slow -n0
```

### Executar Testes ttkbootstrap (Isoladamente)
```powershell
# IMPORTANTE: Esses testes DEVEM ser executados em isolamento
poetry run pytest tests/ui/test_components.py
```

**Resultado esperado**: 22 testes em ~2.5 segundos

### Executar Todos os Testes
```powershell
# Para validação completa antes de commit/release
# Atenção: Rode em 3 etapas separadas devido ao ttkbootstrap

# 1. Testes rápidos
poetry run pytest -m "not (gui or slow or ttkbootstrap_singleton)"

# 2. Testes GUI
poetry run pytest -m "gui and not ttkbootstrap_singleton" -n0

# 3. Testes ttkbootstrap (isolados)
poetry run pytest tests/ui/test_components.py

# 4. Testes slow (opcional)
poetry run pytest -m slow
```

### Executar Testes Sem Cobertura (Mais Rápido)
```powershell
poetry run pytest --no-cov
```

### Execução Sequencial (Debugging)
```powershell
# Útil para debugar problemas de paralelização
poetry run pytest -n0
```

## Estrutura de Testes

```
tests/
├── conftest.py              # Fixtures compartilhadas (tkinter_root, etc.)
├── pytest.ini               # Configuração de markers
│
├── test_*.py               # Testes de nível superior
├── core/                   # Testes do módulo core
├── analysis/               # Testes de análise comportamental
├── ui/                     # Testes de componentes UI
├── integration/            # Testes de integração end-to-end
└── fixtures/               # Fixtures e dados de teste

```

## Compatibilidade Cross-Platform

### Windows
- ✅ Tkinter funciona nativamente (sem virtual display)
- ✅ Testes GUI rodam normalmente
- ⚠️ Alguns sleeps podem variar por resolução de timestamp do filesystem

### Linux
- ✅ Usa `pyvirtualdisplay` automaticamente para testes GUI headless
- ✅ Funciona em CI/CD sem display gráfico
- ✅ Resolução de timestamp mais precisa

### macOS
- ✅ Tkinter funciona nativamente
- ✅ Não requer virtual display

## Troubleshooting

### Erro: "pyvirtualdisplay não encontrado" (Linux)
```powershell
poetry install  # Reinstala dependências incluindo pyvirtualdisplay
```

### Testes GUI falhando no Windows
- Certifique-se de que não está rodando via SSH sem X11 forwarding
- Verifique se o display está acessível

### Testes muito lentos
```powershell
# Execute apenas testes rápidos
poetry run pytest -m "not slow"

# Ou desabilite cobertura
poetry run pytest --no-cov
```

### Problemas com pytest-xdist (paralelização)
```powershell
# Force execução sequencial
poetry run pytest -n0
```

## Performance

### Tempo de Execução Esperado

| Modo | Tempo Aproximado | Comando |
|------|------------------|---------|
| **Padrão (rápido)** | 1-2 minutos | `poetry run pytest` |
| **Com GUI** | 3-5 minutos | `poetry run pytest -m gui -n0` |
| **Com slow** | 5-8 minutos | `poetry run pytest -m slow` |
| **Completo** | 8-12 minutos | `poetry run pytest -m "" -n0` |

### Otimizações Aplicadas

1. ✅ Testes GUI marcados e isolados da paralelização
2. ✅ Sleeps desnecessariamente longos reduzidos (10s → 1s onde aplicável)
3. ✅ Testes lentos marcados e excluídos da execução padrão
4. ✅ Paralelização automática para testes não-GUI (`-n=auto`)
5. ✅ Fixture tkinter_root otimizada para cada plataforma

## Boas Práticas

### Ao Escrever Novos Testes

1. **Marque apropriadamente**:
   ```python
   @pytest.mark.gui
   def test_wizard_ui():
       # Testa componentes Tkinter
       pass

   @pytest.mark.slow
   def test_video_processing():
       # Processa vídeo completo
       pass

   @pytest.mark.integration
   def test_end_to_end_workflow():
       # Testa fluxo completo
       pass
   ```

2. **Evite sleeps longos**:
   ```python
   # ❌ Ruim
   time.sleep(10)

   # ✅ Bom - use threading.Event
   event.wait(timeout=1.0)

   # ✅ Ou use sleeps curtos
   time.sleep(0.1)
   ```

3. **Isole testes GUI**:
   - Use fixtures para criar/destruir widgets Tkinter
   - Sempre marque com `@pytest.mark.gui`
   - Teste lógica separadamente dos componentes visuais quando possível

4. **Prefira mocks para I/O**:
   ```python
   # ✅ Bom - mock em vez de I/O real
   @patch("pathlib.Path.read_text")
   def test_load_config(mock_read):
       mock_read.return_value = "config content"
       # Teste rápido sem tocar disco
   ```

## Referências

- [pytest documentation](https://docs.pytest.org/)
- [pytest-xdist](https://pytest-xdist.readthedocs.io/)
- [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html)
