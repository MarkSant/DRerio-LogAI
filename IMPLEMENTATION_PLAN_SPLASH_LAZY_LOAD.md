# Plano de Execução: Splash Screen + Lazy-Loading do Recorder

**Objetivo:** Melhorar UX na inicialização do ZebTrack-AI implementando:
1. ✅ Splash screen com logo e indicador de progresso
2. ✅ Lazy-loading do Recorder (economiza ~2.3 segundos)
3. ✅ Esconder janela principal até estar completamente carregada

**Benefício esperado:** Reduzir tempo percebido de inicialização de ~6.5s para ~4s + feedback visual profissional

---

## 📋 FASE 1: Criar Splash Screen Component

### Tarefa 1.1: Criar módulo de splash screen

**Arquivo:** `src/zebtrack/ui/splash_screen.py`

**Código completo:**

```python
"""Splash screen for ZebTrack-AI startup."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

import structlog

log = structlog.get_logger()


class SplashScreen:
    """Professional splash screen with logo and loading indicator.

    Displays the DRerio LogAI logo with a progress bar and status text
    during application initialization.
    """

    def __init__(self):
        """Create and display splash screen."""
        self.splash = tk.Toplevel()
        self.splash.overrideredirect(True)  # Remove window decorations

        # Get screen dimensions for centering
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()

        # Splash dimensions
        splash_width = 500
        splash_height = 400

        # Calculate position for center of screen
        x = (screen_width - splash_width) // 2
        y = (screen_height - splash_height) // 2

        self.splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")

        # Set background color
        self.splash.configure(bg="#1e1e2e")  # Dark elegant background

        # Main container
        container = tk.Frame(self.splash, bg="#1e1e2e")
        container.pack(expand=True, fill=tk.BOTH, padx=40, pady=40)

        # Logo image (try PNG first, fallback to text)
        logo_frame = tk.Frame(container, bg="#1e1e2e")
        logo_frame.pack(pady=(0, 30))

        self._logo_label = self._create_logo(logo_frame)

        # Application title
        title_label = tk.Label(
            container,
            text="DRerio LogAI",
            font=("Segoe UI", 28, "bold"),
            bg="#1e1e2e",
            fg="#ffffff"
        )
        title_label.pack(pady=(0, 5))

        # Subtitle
        subtitle_label = tk.Label(
            container,
            text="Zebrafish Tracking & Analysis",
            font=("Segoe UI", 11),
            bg="#1e1e2e",
            fg="#a0a0a0"
        )
        subtitle_label.pack(pady=(0, 40))

        # Loading indicator (indeterminate progress bar)
        progress_frame = tk.Frame(container, bg="#1e1e2e")
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode="indeterminate",
            length=400
        )
        self.progress_bar.pack()
        self.progress_bar.start(10)  # Animate every 10ms

        # Status label
        self.status_var = tk.StringVar(value="Inicializando...")
        self.status_label = tk.Label(
            container,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            bg="#1e1e2e",
            fg="#a0a0a0"
        )
        self.status_label.pack()

        # Version/info label (small footer)
        version_label = tk.Label(
            container,
            text="Powered by YOLO + ByteTrack",
            font=("Segoe UI", 8),
            bg="#1e1e2e",
            fg="#505050"
        )
        version_label.pack(side=tk.BOTTOM)

        # Make splash stay on top
        self.splash.attributes("-topmost", True)

        # Update to show splash immediately
        self.splash.update()

        log.info("splash.created", width=splash_width, height=splash_height)

    def _create_logo(self, parent):
        """Try to load logo image, fallback to text if not found."""
        try:
            # Try to find logo PNG
            possible_paths = [
                Path(__file__).parent / "assets" / "logo_welcome.png",
                Path("src/zebtrack/ui/assets/logo_welcome.png"),
            ]

            logo_path = None
            for path in possible_paths:
                if path.exists():
                    logo_path = path
                    break

            if logo_path:
                # Load and display image
                from PIL import Image, ImageTk

                img = Image.open(logo_path)
                # Resize to reasonable splash size (keep aspect ratio)
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)

                label = tk.Label(parent, image=photo, bg="#1e1e2e")
                label.image = photo  # Keep reference
                label.pack()

                log.info("splash.logo.loaded", path=str(logo_path))
                return label
            else:
                raise FileNotFoundError("Logo not found")

        except Exception as e:
            # Fallback to text logo
            log.info("splash.logo.fallback", reason=str(e))
            label = tk.Label(
                parent,
                text="🐟",
                font=("Segoe UI", 72),
                bg="#1e1e2e",
                fg="#4a9eff"
            )
            label.pack()
            return label

    def update_status(self, message: str) -> None:
        """Update status message.

        Args:
            message: Status text to display
        """
        self.status_var.set(message)
        self.splash.update()
        log.debug("splash.status.updated", message=message)

    def destroy(self) -> None:
        """Close and destroy splash screen."""
        try:
            self.progress_bar.stop()
            self.splash.destroy()
            log.info("splash.destroyed")
        except Exception as e:
            log.warning("splash.destroy.failed", error=str(e))


def create_splash() -> SplashScreen:
    """Factory function to create splash screen.

    Returns:
        SplashScreen instance
    """
    return SplashScreen()
```

**Validação:** Arquivo criado com classe `SplashScreen` completa ✅

---

## 📋 FASE 2: Implementar Lazy-Loading do Recorder

### Tarefa 2.1: Criar RecorderFactory

**Arquivo:** `src/zebtrack/io/recorder_factory.py`

**Código completo:**

```python
"""Factory for lazy-loading Recorder with heavy dependencies."""

import structlog

log = structlog.get_logger()


class RecorderFactory:
    """Factory that delays Recorder instantiation until first use.

    This avoids importing heavy dependencies (pandas, pyarrow) during startup.
    The Recorder is created on first access, typically when user starts analysis.
    """

    def __init__(self, settings_obj):
        """Initialize factory with settings.

        Args:
            settings_obj: Settings instance to pass to Recorder
        """
        self._settings_obj = settings_obj
        self._recorder = None
        self._initialized = False
        log.info("recorder_factory.created", lazy_load=True)

    def get_recorder(self):
        """Get Recorder instance, creating it lazily on first access.

        Returns:
            Recorder instance
        """
        if not self._initialized:
            log.info("recorder_factory.initializing", first_access=True)
            import time
            _t0 = time.perf_counter()

            # Import only when needed (heavy: pandas + pyarrow)
            from zebtrack.io.recorder import Recorder

            self._recorder = Recorder(settings_obj=self._settings_obj)
            elapsed_ms = int((time.perf_counter() - _t0) * 1000)

            self._initialized = True
            log.info("recorder_factory.initialized", elapsed_ms=elapsed_ms)

        return self._recorder

    @property
    def recorder(self):
        """Property access to recorder (lazy-loads on first access)."""
        return self.get_recorder()

    def __getattr__(self, name):
        """Delegate all other attributes to the underlying recorder.

        This makes RecorderFactory transparent - callers can use it
        as if it were a Recorder directly.
        """
        return getattr(self.get_recorder(), name)
```

**Validação:** Arquivo criado com `RecorderFactory` delegando métodos ✅

### Tarefa 2.2: Modificar __main__.py para usar RecorderFactory

**Arquivo:** `src/zebtrack/__main__.py`

**Localização:** Linha ~265 (seção de Video processing service)

**Buscar por:**
```python
        # Video processing service
        _t0 = time.perf_counter()
        from zebtrack.core.video_processing_service import VideoProcessingService
        from zebtrack.io.recorder import Recorder

        # Initialize recorder with settings
        recorder = Recorder(settings_obj=settings_obj)
        log.info("timing.recorder_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))
```

**Substituir por:**
```python
        # Video processing service
        _t0 = time.perf_counter()
        from zebtrack.core.video_processing_service import VideoProcessingService
        from zebtrack.io.recorder_factory import RecorderFactory

        # Create recorder factory (lazy-loads on first use)
        recorder_factory = RecorderFactory(settings_obj=settings_obj)
        log.info("timing.recorder_factory_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))
```

**Localização 2:** Linha ~280 (passando recorder para video_processing_service)

**Buscar por:**
```python
        video_processing_service = VideoProcessingService(
            detector=None,  # Lazy-initialized by detector_service.initialize_detector()
            recorder=recorder,
```

**Substituir por:**
```python
        video_processing_service = VideoProcessingService(
            detector=None,  # Lazy-initialized by detector_service.initialize_detector()
            recorder=recorder_factory,  # Lazy-loads when first used
```

**Localização 3:** Linha ~320 (passando para outros coordinators)

**Buscar todas ocorrências de:**
```python
recorder=recorder,
```

**Substituir por:**
```python
recorder=recorder_factory,
```

**Validação:**
- RecorderFactory usado no lugar de Recorder direto ✅
- Import de recorder.py removido do topo ✅
- Tempo de init cai de ~2300ms para <5ms ✅

---

## 📋 FASE 3: Integrar Splash Screen no __main__.py

### Tarefa 3.1: Modificar main() para usar splash

**Arquivo:** `src/zebtrack/__main__.py`

**Localização:** Linha ~189 (logo após `try:`)

**Buscar por:**
```python
    try:
        # Create Tkinter root
        root = tk.Tk()

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(root)
        maximize_window(root)
```

**Substituir por:**
```python
    try:
        # Create splash screen FIRST (lightweight, shows immediately)
        from zebtrack.ui.splash_screen import create_splash

        splash = create_splash()
        splash.update_status("Carregando configurações...")

        # Create Tkinter root (hidden during init)
        root = tk.Tk()
        root.withdraw()  # Hide main window while loading

        # Set application icon (for when window shows)
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(root)
```

### Tarefa 3.2: Adicionar atualizações de status no splash

**Inserir após cada etapa principal:**

**Após StateManager (linha ~201):**
```python
        state_manager = StateManager(enable_history=True, max_history_size=100)
        ui_coordinator = UICoordinator(root=root, event_bus=event_bus)

        splash.update_status("Carregando sistema de modelos...")
```

**Após ModelService (linha ~211):**
```python
        model_service = ModelService(weight_manager)
        log.info("timing.model_service", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Inicializando gerenciador de projetos...")
```

**Após ProjectManager (linha ~226):**
```python
        project_manager = ProjectManager(state_manager=state_manager, settings_obj=settings_obj)
        log.info("timing.project_manager_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Configurando detector...")
```

**Após DetectorService (linha ~250):**
```python
        detector_service = DetectorService(...)
        log.info("timing.detector_service", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Preparando processamento de vídeo...")
```

**Após RecorderFactory (linha ~268):**
```python
        recorder_factory = RecorderFactory(settings_obj=settings_obj)
        log.info("timing.recorder_factory_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Criando interface gráfica...")
```

**Antes de MainViewModel (linha ~343):**
```python
        _t0 = time.perf_counter()
        from zebtrack.core.main_view_model import MainViewModel

        splash.update_status("Finalizando inicialização...")
```

### Tarefa 3.3: Fechar splash e mostrar janela principal

**Localização:** Linha ~373 (antes de `controller.run()`)

**Buscar por:**
```python
        # Bind events and run
        controller.bind_events()
        controller.run()
```

**Substituir por:**
```python
        # Bind events
        controller.bind_events()

        # Close splash and show main window
        splash.update_status("Pronto!")
        root.update()  # Force update to ensure all widgets are rendered

        # Small delay to let user see "Pronto!" message
        root.after(200, lambda: (
            splash.destroy(),
            maximize_window(root),
            root.deiconify()  # Show main window
        ))

        # Run main loop
        controller.run()
```

**Validação:**
- Splash aparece imediatamente ✅
- Status atualiza durante carregamento ✅
- Splash fecha e janela principal aparece pronta ✅

---

## 📋 FASE 4: Tratamento de Erros

### Tarefa 4.1: Adicionar try/except para falhas no splash

**Localização:** No bloco `except Exception:` existente (linha ~377)

**Buscar por:**
```python
    except Exception:
        log.critical("unhandled.exception", exc_info=True)
        messagebox.showerror("Fatal Error", "A fatal error occurred. See analysis.log for details.")
```

**Substituir por:**
```python
    except Exception:
        log.critical("unhandled.exception", exc_info=True)

        # Try to close splash if it exists
        try:
            if 'splash' in locals():
                splash.destroy()
        except Exception:
            pass

        # Show main window if hidden
        try:
            if 'root' in locals():
                root.deiconify()
        except Exception:
            pass

        messagebox.showerror("Fatal Error", "A fatal error occurred. See analysis.log for details.")
```

**Validação:** Erros durante init não deixam splash travado ✅

---

## 📋 FASE 5: Testes e Validação

### Tarefa 5.1: Teste de inicialização normal

**Executar:**
```powershell
poetry run python -m zebtrack
```

**Validar:**
- ✅ Splash aparece imediatamente (< 100ms)
- ✅ Logo é exibida (PNG ou emoji fallback)
- ✅ Barra de progresso anima (círculo rodando)
- ✅ Status atualiza em cada etapa
- ✅ Splash fecha após "Pronto!"
- ✅ Janela principal aparece maximizada e completa
- ✅ Tempo total percebido reduzido (~4-5s)

### Tarefa 5.2: Teste de lazy-loading do Recorder

**Verificar nos logs:**
```
[info] recorder_factory.created lazy_load=True
# ... depois, quando análise inicia ...
[info] recorder_factory.initializing first_access=True
[info] recorder_factory.initialized elapsed_ms=2XXX
```

**Validar:**
- ✅ Recorder NÃO é importado durante startup
- ✅ Recorder é criado quando usuário inicia análise
- ✅ Tempo de startup reduzido em ~2.3 segundos

### Tarefa 5.3: Teste de erro durante inicialização

**Simular erro (temporariamente quebrar config.yaml):**
```yaml
# Adicionar linha inválida para forçar erro
invalid_key_test: [1, 2, error
```

**Executar:**
```powershell
poetry run python -m zebtrack
```

**Validar:**
- ✅ Splash é fechado mesmo com erro
- ✅ Mensagem de erro é exibida
- ✅ Programa não fica travado

**Reverter mudança no config.yaml após teste**

### Tarefa 5.4: Teste de análise de vídeo (verifica Recorder lazy-load)

**Passos:**
1. Iniciar programa
2. Criar novo projeto
3. Configurar vídeo
4. Iniciar análise

**Validar:**
- ✅ Recorder é carregado apenas ao iniciar análise
- ✅ Log mostra `recorder_factory.initialized` no momento correto
- ✅ Análise funciona normalmente

---

## 📋 FASE 6: Executar Suite de Testes

### Tarefa 6.1: Testes rápidos

```powershell
poetry run pytest -q
```

**Validar:**
- ✅ Todos os testes passam (~1586 testes)
- ✅ Nenhuma regressão introduzida

### Tarefa 6.2: Testes de GUI (se aplicável)

```powershell
poetry run pytest -m gui -n0
```

**Validar:**
- ✅ Testes de GUI ainda passam
- ✅ Splash não interfere com testes automatizados

---

## 📋 FASE 7: Documentação

### Tarefa 7.1: Atualizar CHANGELOG.md

**Adicionar:**
```markdown
## [Unreleased]

### Added
- Splash screen profissional com logo e indicador de progresso durante inicialização
- Lazy-loading do Recorder para reduzir tempo de startup em ~2.3 segundos

### Changed
- Janela principal agora aparece apenas quando completamente carregada (melhor UX)
- Tempo de inicialização percebido reduzido de ~6.5s para ~4s

### Technical
- Novo módulo `ui/splash_screen.py` para tela de carregamento
- Novo módulo `io/recorder_factory.py` para lazy-loading de dependências pesadas
- Modificado `__main__.py` para usar splash screen e RecorderFactory
```

### Tarefa 7.2: Atualizar docs/PERFORMANCE_TUNING.md

**Adicionar seção:**
```markdown
## Startup Optimization

### Lazy-Loading Pattern

Heavy dependencies (pandas, pyarrow) are now lazy-loaded via `RecorderFactory`:
- Recorder only imported when first analysis starts
- Saves ~2.3 seconds during startup
- Transparent to calling code (duck-typing via `__getattr__`)

### Splash Screen

Professional loading experience:
- Immediate visual feedback (< 100ms)
- Progress indication with status updates
- Hides main window construction complexity
```

---

## ✅ Checklist de Execução

Antes de considerar concluído, verificar:

- [ ] `src/zebtrack/ui/splash_screen.py` criado
- [ ] `src/zebtrack/io/recorder_factory.py` criado
- [ ] `src/zebtrack/__main__.py` modificado (3 localizações)
- [ ] Splash aparece em < 100ms
- [ ] Status atualiza durante init
- [ ] Janela principal aparece completa e maximizada
- [ ] Recorder é lazy-loaded (log confirma)
- [ ] Tempo de startup reduzido (~4s vs ~6.5s)
- [ ] Testes passam (`pytest -q`)
- [ ] Sem regressões em funcionalidade existente
- [ ] CHANGELOG.md atualizado
- [ ] Documentação atualizada

---

## 🎯 Resultados Esperados

**Antes:**
```
0.0s → Tela preta aparece
6.5s → Interface completa aparece
```

**Depois:**
```
0.0s → Splash com logo aparece
4.0s → Interface completa aparece (splash fecha)
```

**Ganhos:**
- ⚡ **40% mais rápido** (2.5s economizados)
- 😊 **UX profissional** (feedback visual imediato)
- 🎨 **Sem tela preta** (splash elegante desde o início)
- 📦 **Código mais limpo** (lazy-loading de dependências pesadas)

---

## 🔧 Rollback (se necessário)

Se algo der errado:

1. **Reverter __main__.py:**
   ```bash
   git checkout src/zebtrack/__main__.py
   ```

2. **Remover novos arquivos:**
   ```bash
   rm src/zebtrack/ui/splash_screen.py
   rm src/zebtrack/io/recorder_factory.py
   ```

3. **Reverter comportamento original:**
   - Janela aparece imediatamente (com tela preta)
   - Recorder importado no startup
   - Tempo de init volta para ~6.5s

---

**Plano criado em:** 2025-11-10
**Autor:** GitHub Copilot
**Versão:** 1.0
