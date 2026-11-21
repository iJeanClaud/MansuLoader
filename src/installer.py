"""Instalador inicial do MansuLoader em %APPDATA%\\mansu-loader."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from src.config_manager import AppConfig, load_config, save_config
from src.version import APP_VERSION

UPDATER_EXE_NAME = "MansuLoaderUpdater.exe"
APP_EXE_NAME = "MansuLoader.exe"
INSTALL_MARKER_NAME = "installed.json"


def get_install_dir() -> Path:
    """Retorna o diretório de instalação %APPDATA%\\mansu-loader."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    return base / "mansu-loader"


def get_install_marker_path() -> Path:
    """Retorna o caminho do arquivo que indica que o app já está instalado."""
    return get_install_dir() / INSTALL_MARKER_NAME


def get_installed_app_exe() -> Path:
    """Retorna o caminho do MansuLoader.exe instalado."""
    return get_install_dir() / APP_EXE_NAME


def get_installed_updater_exe() -> Path:
    """Retorna o caminho do MansuLoaderUpdater.exe instalado."""
    return get_install_dir() / UPDATER_EXE_NAME


def is_installed() -> bool:
    """Verifica se o software já está instalado em %APPDATA%\\mansu-loader."""
    marker = get_install_marker_path()
    if not marker.is_file():
        return False
    if getattr(sys, "frozen", False):
        return get_installed_app_exe().is_file()
    return True


def _get_bundled_updater_path() -> Optional[Path]:
    """Localiza o MansuLoaderUpdater.exe embutido no pacote ou em dist/."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / UPDATER_EXE_NAME
        if candidate.is_file():
            return candidate
    local_dist = Path(__file__).resolve().parents[1] / "dist" / UPDATER_EXE_NAME
    if local_dist.is_file():
        return local_dist
    beside_exe = Path(sys.executable).resolve().parent / UPDATER_EXE_NAME
    if beside_exe.is_file():
        return beside_exe
    return None


def _create_desktop_shortcut(target_exe: Path) -> None:
    """Cria atalho do MansuLoader na Área de Trabalho do usuário."""
    if sys.platform != "win32":
        return

    escaped_exe = str(target_exe).replace("'", "''")
    escaped_dir = str(target_exe.parent).replace("'", "''")
    ps_script = (
        "$desktop = [Environment]::GetFolderPath('Desktop'); "
        "$shortcutPath = Join-Path $desktop 'MansuLoader.lnk'; "
        "$shell = New-Object -ComObject WScript.Shell; "
        "$sc = $shell.CreateShortcut($shortcutPath); "
        f"$sc.TargetPath = '{escaped_exe}'; "
        f"$sc.WorkingDirectory = '{escaped_dir}'; "
        f"$sc.IconLocation = '{escaped_exe},0'; "
        "$sc.Description = 'MansuLoader - Baixar músicas do YouTube em MP3'; "
        "$sc.Save()"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        check=False,
        creationflags=creationflags,
    )


def perform_install(on_progress: Optional[Callable[[float, str], None]] = None) -> Path:
    """Executa a instalação em %APPDATA%\\mansu-loader e cria o atalho."""
    def emit(pct: float, msg: str) -> None:
        if on_progress:
            on_progress(pct, msg)

    install_dir = get_install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)

    emit(0.2, "Criando pasta de configurações...")
    cfg = load_config()
    save_config(AppConfig(download_folder=cfg.download_folder, audio_quality=cfg.audio_quality))

    installed_exe = get_installed_app_exe()
    if getattr(sys, "frozen", False):
        emit(0.45, "Instalando MansuLoader.exe...")
        current_exe = Path(sys.executable).resolve()
        if current_exe != installed_exe.resolve():
            shutil.copy2(current_exe, installed_exe)

    emit(0.7, "Instalando módulo de atualização...")
    bundled_updater = _get_bundled_updater_path()
    if bundled_updater is not None and bundled_updater.resolve() != get_installed_updater_exe().resolve():
        shutil.copy2(bundled_updater, get_installed_updater_exe())

    emit(0.85, "Criando atalho na Área de Trabalho...")
    shortcut_target = installed_exe if installed_exe.is_file() else Path(sys.executable).resolve()
    _create_desktop_shortcut(shortcut_target)

    emit(0.95, "Finalizando instalação...")
    marker_data = {
        "installed": True,
        "version": APP_VERSION,
        "install_dir": str(install_dir),
    }
    get_install_marker_path().write_text(
        json.dumps(marker_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    emit(1.0, "Instalação concluída!")
    return installed_exe


def run_installer_ui() -> bool:
    """Exibe a janela do instalador. Retorna True se o usuário clicar em Abrir."""
    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg="#FF3B5C")
    root.attributes("-topmost", True)

    w, h = 440, 230
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - w) // 2)
    y = max(0, (root.winfo_screenheight() - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    box = tk.Frame(root, bg="#171A23")
    box.pack(fill="both", expand=True, padx=1, pady=1)

    title_lbl = tk.Label(
        box,
        text="Instalador do MansuLoader",
        bg="#171A23",
        fg="#F3F4F6",
        font=("Segoe UI", 14, "bold"),
    )
    title_lbl.pack(pady=(22, 6))

    status_var = tk.StringVar(value="Preparando instalação...")
    status_lbl = tk.Label(
        box,
        textvariable=status_var,
        bg="#171A23",
        fg="#9CA3AF",
        font=("Segoe UI", 10),
        wraplength=390,
        justify="center",
    )
    status_lbl.pack(pady=(0, 14), padx=20)

    bar_w = 380
    canvas = tk.Canvas(box, width=bar_w, height=10, bg="#1E222E", highlightthickness=0, bd=0)
    canvas.pack(pady=(0, 18))
    fill_rect = canvas.create_rectangle(0, 0, 12, 10, fill="#FF3B5C", width=0)

    btn_frame = tk.Frame(box, bg="#171A23")
    result = {"open_app": False}

    def on_open() -> None:
        result["open_app"] = True
        root.destroy()

    def on_exit() -> None:
        result["open_app"] = False
        root.destroy()

    open_btn = tk.Button(
        btn_frame,
        text="Abrir",
        width=14,
        bg="#FF3B5C",
        fg="#FFFFFF",
        activebackground="#E02E4D",
        activeforeground="#FFFFFF",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
        command=on_open,
    )
    open_btn.pack(side="left", padx=(0, 10), ipady=5)

    exit_btn = tk.Button(
        btn_frame,
        text="Sair",
        width=14,
        bg="#1E222E",
        fg="#F3F4F6",
        activebackground="#2A3040",
        activeforeground="#FFFFFF",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
        command=on_exit,
    )
    exit_btn.pack(side="left", ipady=5)

    def update_ui(pct: float, msg: str) -> None:
        status_var.set(msg)
        canvas.coords(fill_rect, 0, 0, max(10, int(bar_w * pct)), 10)

    def finish_ok() -> None:
        title_lbl.configure(text="Instalação concluída!", fg="#22C55E")
        status_var.set("Abrindo o MansuLoader...")
        canvas.coords(fill_rect, 0, 0, bar_w, 10)
        result["open_app"] = True
        root.after(600, root.destroy)

    def finish_err(err_msg: str) -> None:
        title_lbl.configure(text="Erro na instalação", fg="#EF4444")
        status_var.set(err_msg[:140])
        open_btn.pack_forget()
        btn_frame.pack(pady=(0, 16))

    def worker() -> None:
        try:
            perform_install(
                on_progress=lambda p, m: root.after(0, lambda pct=p, msg=m: update_ui(pct, msg))
            )
            root.after(0, finish_ok)
        except Exception as exc:
            err = str(exc) or "Falha inesperada na instalação."
            root.after(0, lambda: finish_err(err))

    root.after(120, lambda: threading.Thread(target=worker, daemon=True).start())
    root.mainloop()
    return result["open_app"]
