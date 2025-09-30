# Contributing Guide

Obrigado por querer contribuir com o ZebTrack-AI! Este guia descreve o fluxo de trabalho, padrões de código e expectativas para pull requests.

## 1. Preparando o ambiente

1. Clone o repositório:
	```powershell
	git clone https://github.com/MarkSant/ZebTrack-AI.git
	cd ZebTrack-AI
	```
2. Instale as dependências com Poetry:
	```powershell
	poetry install
	```
3. Ative o shell virtual (opcional, mas recomendado):
	```powershell
	poetry shell
	```
4. Verifique se a aplicação inicia:
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

## 5. Padrões de commit

- Utilize **Conventional Commits**:
  - `feat: adiciona suporte a XYZ`
  - `fix: corrige progress callback`
  - `docs: atualiza README`
  - `refactor: reorganiza detector`
- Commits devem ser autoexplicativos. Mensagens em português ou inglês são aceitas (não misturar no mesmo PR).

## 6. Estruturando novas features

1. **Planeje**: descreva inputs/outputs, fluxos afetados e cenários negativos.
2. **Implemente**: mantenha mudanças focadas; evite reformatar blocos não relacionados.
3. **Teste**: cubra o caso feliz + 1–2 bordas (ex.: ausência de track_id, arquivo vazio, falta de configuração).
4. **Documente**:
	- Atualize `README.md` se o usuário final for impactado.
	- Ajuste `.github/copilot-instructions.md` para instruir automações.
	- Edite `docs/ARCHITECTURE.md` quando alterar fluxos ou decisões arquiteturais.
	- Cite migrações/configurações novas em `config.yaml` e `tests/test_settings.py`.
5. **Checklist antes do PR**:
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
