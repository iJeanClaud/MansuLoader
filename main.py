"""Ponto de entrada do MansuLoader com splash screen compacta e barra de progresso."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk


def _get_asset_path(filename: str) -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "assets" / filename
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parent / "assets" / filename


def _show_splash_and_load() -> type:
    """Exibe uma splash screen compacta enquanto carrega os módulos pesados."""
    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg="#FF3B5C")
    root.attributes("-topmost", True)

    splash_w, splash_h = 440, 294
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - splash_w) // 2)
    y = max(0, (root.winfo_screenheight() - splash_h) // 2)
    root.geometry(f"{splash_w}x{splash_h}+{x}+{y}")

    container = tk.Frame(root, bg="#0F1117")
    container.pack(fill="both", expand=True, padx=1, pady=1)

    splash_path = _get_asset_path("splash.png")
    photo_ref = None
    if splash_path.is_file():
        img = Image.open(splash_path).resize((438, 246), Image.Resampling.LANCZOS)
        photo_ref = ImageTk.PhotoImage(img)
        img_label = tk.Label(container, image=photo_ref, bg="#0F1117", bd=0)
        img_label.image = photo_ref
        img_label.pack(fill="x")

    bottom = tk.Frame(container, bg="#0F1117", height=46)
    bottom.pack(fill="both", expand=True, padx=14, pady=(4, 8))

    status_var = tk.StringVar(value="Inicializando MansuLoader...")
    status_lbl = tk.Label(
        bottom,
        textvariable=status_var,
        bg="#0F1117",
        fg="#9CA3AF",
        font=("Segoe UI", 9),
        anchor="w",
    )
    status_lbl.pack(fill="x", pady=(0, 4))

    bar_w = 410
    canvas = tk.Canvas(
        bottom,
        width=bar_w,
        height=8,
        bg="#1E222E",
        highlightthickness=0,
        bd=0,
    )
    canvas.pack(fill="x")
    fill_rect = canvas.create_rectangle(0, 0, 24, 8, fill="#FF3B5C", width=0)

    state: dict[str, object] = {
        "progress": 0.08,
        "target": 0.15,
        "status": "Inicializando MansuLoader...",
        "app_cls": None,
        "error": None,
        "done": False,
    }

    def load_modules() -> None:
        try:
            state["status"] = "Carregando configurações..."
            state["target"] = 0.30
            import src.config_manager  # noqa: F401

            state["status"] = "Carregando motor de áudio (yt-dlp)..."
            state["target"] = 0.72
            import src.youtube_service  # noqa: F401

            state["status"] = "Carregando interface..."
            state["target"] = 0.95
            from src.ui.app import MansuLoaderApp

            state["app_cls"] = MansuLoaderApp
            state["status"] = "Pronto!"
            state["target"] = 1.0
        except Exception as exc:
            state["error"] = exc
        finally:
            state["done"] = True

    def animate() -> None:
        current = float(state["progress"])
        target = float(state["target"])
        if current < target:
            current = min(target, current + 0.04)
            state["progress"] = current

        status_var.set(str(state["status"]))
        canvas.coords(fill_rect, 0, 0, max(8, int(bar_w * current)), 8)

        if state["done"] and current >= 0.99:
            root.after(120, root.destroy)
            return

        root.after(25, animate)

    threading.Thread(target=load_modules, daemon=True).start()
    root.update()
    try:
        import pyi_splash  # type: ignore[import-not-found]

        pyi_splash.close()
    except Exception:
        pass
    root.after(20, animate)
    root.mainloop()

    if state["error"] is not None:
        raise state["error"]  # type: ignore[misc]
    return state["app_cls"]  # type: ignore[return-value]


def main() -> None:
    from src.logger import log_exception, setup_crash_logging

    setup_crash_logging()
    try:
        app_cls = _show_splash_and_load()
        app = app_cls()
        app.mainloop()
    except Exception as exc:
        log_exception("Erro fatal no aplicativo", exc)
        raise


if __name__ == "__main__":
    main()
