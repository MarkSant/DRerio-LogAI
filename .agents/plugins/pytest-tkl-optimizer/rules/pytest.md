# Diretrizes de Otimização e Execução de Testes Tkinter (Pytest TkL Optimizer)

## 1. Identificação e Isolamento de Testes Tkinter (GUI)

- Todos os testes que instanciam ou interagem com widgets Tkinter/ttk/ttkbootstrap devem ser categorizados com o marcador `@pytest.mark.gui`.
- Testes GUI **DEVEM** ser executados em modo serial (`-n0` ou sem pytest-xdist concorrente na mesma thread/processo Tkinter) para evitar condições de corrida no interpretador Tcl/Tk e corrupção de estado singleton do `ttkbootstrap.Style`.

## 2. Preparação e Gestão do Ambiente de Display (Headless / Virtual)

- **Ambiente Windows:** O Tkinter opera com suporte nativo de janelas. Em sessões headless ou onde o subsistema gráfico não esteja acessível, utilize a detecção defensiva com fallback para mocks (`_can_initialize_tk()`, `MagicMock` root) ou modo headless controlado.
- **Ambiente Linux / Unix / CI:** Em ambientes headless sem display físico, inicialize e gerencie um display virtual X (`Xvfb` via `pyvirtualdisplay` ou export de `DISPLAY=:99`) antes da criação do root Tkinter, evitando exceções do tipo `_tkinter.TclError: no display name`.

## 3. Prevenção de Bloqueios e Loops Infinitos (`mainloop()`)

- **NUNCA** invoque `root.mainloop()` dentro de testes automatizados unitários ou de integração, pois isso bloqueará a execução do pytest indefinidamente.
- Para processar eventos de interface pendentes, renderização de widgets e callbacks assíncronos, utilize de forma controlada:

  ```python
  root.update_idletasks()  # Processa tarefas pendentes de geometria e desenho
  root.update()  # Processa eventos de fila e callbacks do Tkinter
  ```

- Para diálogos modais (`messagebox`, `filedialog`), garanta que sejam interceptados via mocks (`mock_tkinter_dialogs` fixture) para que nunca abram caixas de diálogo bloqueantes na tela.

## 4. Teardown Seguro e Limpeza de Recursos

- **Cancelamento de Callbacks `after()`:** Antes de destruir qualquer janela ou widget, cancele todos os timers e callbacks pendentes com `root.after_cancel()` para evitar vazamento de memória ou erros de execução tardia após o término do teste.
- **Destruição Ordenada:** Feche janelas filhas (`Toplevel`) e destrua os widgets antes de descartar a janela root (`widget.destroy()`, `root.destroy()`).
- **Uso de Fixtures Reutilizáveis:** Utilize fixtures canônicas como `tkinter_root` / `tkinter_session_root` em vez de instanciar múltiplos objetos `tk.Tk()` isolados em cada teste no Windows.
