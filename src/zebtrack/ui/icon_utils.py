"""
Utilitários para carregar ícones da aplicação DRerio LogAI.
"""

from pathlib import Path

import structlog

log = structlog.get_logger()


def get_icon_path() -> Path | None:
    """
    Obtém o caminho para o ícone da aplicação (.ico).

    Returns:
        Path para o ícone ou None se não encontrado.
    """
    # Tenta localizar o asset relativo ao pacote
    try:
        # Caminho relativo a este módulo (zebtrack/ui/icon_utils.py)
        icon_path = Path(__file__).parent / "assets" / "drerio_logai.ico"

        if icon_path.exists():
            log.debug("icon.path.found", path=str(icon_path))
            return icon_path

        # Fallback: caminho relativo ao diretório de trabalho (desenvolvimento)
        icon_path_dev = Path("src/zebtrack/ui/assets/drerio_logai.ico")
        if icon_path_dev.exists():
            log.debug("icon.path.found_dev", path=str(icon_path_dev))
            return icon_path_dev

        log.warning("icon.path.not_found", attempted_paths=[str(icon_path), str(icon_path_dev)])
        return None

    except Exception as e:
        log.warning("icon.path.error", error=str(e))
        return None


def set_window_icon(window) -> None:
    """
    Define o ícone para uma janela Tkinter.

    Args:
        window: Instância de tk.Tk ou tk.Toplevel
    """
    icon_path = get_icon_path()

    if icon_path is None:
        log.info("icon.set.skipped", reason="Icon file not found")
        return

    try:
        window.iconbitmap(default=str(icon_path))
        log.info(
            "icon.set.success",
            window_title=window.title() if hasattr(window, "title") else "unknown",
        )
    except Exception as e:
        log.warning("icon.set.failed", error=str(e), path=str(icon_path))
