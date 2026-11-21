"""Ponto de entrada do MansuLoader: instalador inicial, splash screen e pré-verificação de atualização."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Optional

from PIL import Image, ImageTk


def _get_asset_path(filename: str) -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "assets" / filename
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parent / "assets" / filename


def _close_pyi_splash() -> None:
    try:
        import pyi_splash  # type: ignore[import-not-found]

        pyi_splash.close()
    except Exception:
        pass


def _show_splash_and_load() -> tuple[Optional[type], Optional[object]]:
    """Exibe splash screen compacta enquanto carrega módulos e verifica atualização."""
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
        "update_info": None,
        "error": None,
        "done": False,
    }

    def load_modules() -> None:
        try:
            state["status"] = "Verificando atualizações..."
            state["target"] = 0.30
            from src.update_service import check_for_update

            update_info = check_for_update()
            if update_info is not None:
                state["update_info"] = update_info
                state["status"] = "Atualização disponível!"
                state["target"] = 1.0
                return

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
    _close_pyi_splash()
    root.after(20, animate)
    root.mainloop()

    if state["error"] is not None:
        raise state["error"]  # type: ignore[misc]
    return state["app_cls"], state["update_info"]  # type: ignore[return-value]


def _show_prelaunch_update_prompt(update_info) -> bool:
    """Exibe aviso antes de abrir o app. Retorna True se o usuário escolher Atualizar."""
    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg="#FF3B5C")
    root.attributes("-topmost", True)

    w, h = 420, 215
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - w) // 2)
    y = max(0, (root.winfo_screenheight() - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    box = tk.Frame(root, bg="#171A23")
    box.pack(fill="both", expand=True, padx=1, pady=1)

    tk.Label(
        box,
        text="Atualização disponível",
        bg="#171A23",
        fg="#F3F4F6",
        font=("Segoe UI", 15, "bold"),
    ).pack(pady=(22, 10))

    tk.Label(
        box,
        text=(
            f"Uma nova versão (v{update_info.latest_version}) está disponível.\n"
            f"Versão atual: v{update_info.current_version}"
        ),
        bg="#171A23",
        fg="#9CA3AF",
        font=("Segoe UI", 10),
        justify="center",
    ).pack(pady=(0, 8))

    tk.Label(
        box,
        text="Como deseja prosseguir?",
        bg="#171A23",
        fg="#6B7280",
        font=("Segoe UI", 9),
    ).pack(pady=(0, 16))

    choice = {"update": False}

    def on_update() -> None:
        choice["update"] = True
        root.destroy()

    def on_exit() -> None:
        choice["update"] = False
        root.destroy()

    btn_frame = tk.Frame(box, bg="#171A23")
    btn_frame.pack(pady=(0, 18))

    tk.Button(
        btn_frame,
        text="Atualizar",
        width=14,
        bg="#FF3B5C",
        fg="#FFFFFF",
        activebackground="#E02E4D",
        activeforeground="#FFFFFF",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
        command=on_update,
    ).pack(side="left", padx=(0, 10), ipady=5)

    tk.Button(
        btn_frame,
        text="Sair",
        width=12,
        bg="#1E222E",
        fg="#F3F4F6",
        activebackground="#2A3040",
        activeforeground="#FFFFFF",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
        command=on_exit,
    ).pack(side="left", ipady=5)

    root.mainloop()
    return choice["update"]


def _launch_external_updater(update_info) -> None:
    """Inicia o MansuLoaderUpdater.exe e encerra o processo atual."""
    from src.installer import get_installed_app_exe, get_installed_updater_exe

    updater_exe = get_installed_updater_exe()
    target_exe = (
        Path(sys.executable).resolve()
        if getattr(sys, "frozen", False)
        else get_installed_app_exe()
    )

    if updater_exe.is_file():
        subprocess.Popen(
            [
                str(updater_exe),
                "--url",
                update_info.download_url,
                "--target",
                str(target_exe),
                "--pid",
                str(os.getpid()),
                "--version",
                update_info.latest_version,
            ],
            close_fds=True,
        )
    else:
        updater_script = Path(__file__).resolve().parent / "updater_main.py"
        if updater_script.is_file():
            subprocess.Popen(
                [
                    sys.executable,
                    str(updater_script),
                    "--url",
                    update_info.download_url,
                    "--target",
                    str(target_exe),
                    "--pid",
                    str(os.getpid()),
                    "--version",
                    update_info.latest_version,
                ],
                close_fds=True,
            )


def main() -> None:
    from src.installer import get_installed_app_exe, is_installed, run_installer_ui
    from src.logger import log_exception, setup_crash_logging

    setup_crash_logging()
    try:
        if not is_installed():
            _close_pyi_splash()
            should_open = run_installer_ui()
            if should_open:
                installed_exe = get_installed_app_exe()
                if getattr(sys, "frozen", False) and installed_exe.is_file():
                    subprocess.Popen([str(installed_exe)], close_fds=True)
                    return
            else:
                return
        elif getattr(sys, "frozen", False):
            installed_exe = get_installed_app_exe().resolve()
            current_exe = Path(sys.executable).resolve()
            if installed_exe.is_file() and current_exe != installed_exe:
                _close_pyi_splash()
                subprocess.Popen([str(installed_exe)], close_fds=True)
                return

        app_cls, update_info = _show_splash_and_load()
        if update_info is not None:
            wants_update = _show_prelaunch_update_prompt(update_info)
            if wants_update:
                _launch_external_updater(update_info)
            return

        if app_cls is not None:
            app = app_cls()
            app.mainloop()
    except Exception as exc:
        log_exception("Erro fatal no aplicativo", exc)
        raise


if __name__ == "__main__":
    main()
