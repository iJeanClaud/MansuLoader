"""Aplicativo independente de atualização do MansuLoader (MansuLoaderUpdater.exe)."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

ALLOWED_UPDATE_HOSTS = {
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


def _validate_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host in ALLOWED_UPDATE_HOSTS


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        process_query_limited_info = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_info, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == 259  # STILL_ACTIVE
    return False


def _wait_for_process_exit(pid: int, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while _is_pid_running(pid) and time.monotonic() < deadline:
        time.sleep(0.25)
    time.sleep(0.4)


def _download_and_replace(
    url: str,
    target_exe: Path,
    pid: int,
    new_version: str,
    on_progress: Callable[[float, str], None],
) -> None:
    if not _validate_url(url):
        raise ValueError("URL de atualização não autorizada.")

    on_progress(0.05, "Aguardando fechamento do MansuLoader...")
    _wait_for_process_exit(pid)

    target_exe.parent.mkdir(parents=True, exist_ok=True)
    temp_new = target_exe.with_name("MansuLoader_new.exe")
    temp_old = target_exe.with_name("MansuLoader_old.exe")
    temp_new.unlink(missing_ok=True)
    temp_old.unlink(missing_ok=True)

    on_progress(0.1, "Baixando nova versão...")
    with requests.get(url, stream=True, timeout=60, allow_redirects=True) as resp:
        resp.raise_for_status()
        if not _validate_url(resp.url):
            raise ValueError("Redirecionamento para domínio não autorizado.")

        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with temp_new.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = 0.1 + min(0.8, (downloaded / total) * 0.8)
                    on_progress(pct, f"Baixando atualização... {int((downloaded / total) * 100)}%")

    if not temp_new.exists() or temp_new.stat().st_size < 1_000_000:
        temp_new.unlink(missing_ok=True)
        raise RuntimeError("O arquivo baixado está incompleto.")

    with temp_new.open("rb") as fh:
        if fh.read(2) != b"MZ":
            temp_new.unlink(missing_ok=True)
            raise RuntimeError("O arquivo baixado não é um executável Windows válido.")

    on_progress(0.95, "Substituindo executável...")
    if target_exe.exists():
        target_exe.replace(temp_old)
    temp_new.replace(target_exe)
    temp_old.unlink(missing_ok=True)

    marker = target_exe.parent / "installed.json"
    marker_data = {
        "installed": True,
        "version": new_version,
        "install_dir": str(target_exe.parent),
    }
    marker.write_text(json.dumps(marker_data, indent=2, ensure_ascii=False), encoding="utf-8")
    on_progress(1.0, "Software atualizado com sucesso!")


def run_updater_ui(url: str, target_exe: Path, pid: int, new_version: str) -> None:
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
        text="Atualizando MansuLoader...",
        bg="#171A23",
        fg="#F3F4F6",
        font=("Segoe UI", 14, "bold"),
    )
    title_lbl.pack(pady=(22, 6))

    status_var = tk.StringVar(value="Iniciando atualização...")
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
    fill_rect = canvas.create_rectangle(0, 0, 14, 10, fill="#FF3B5C", width=0)

    btn_frame = tk.Frame(box, bg="#171A23")

    def on_open() -> None:
        if target_exe.is_file():
            subprocess.Popen([str(target_exe)], close_fds=True)
        root.destroy()

    def on_exit() -> None:
        root.destroy()

    open_btn = tk.Button(
        btn_frame,
        text="Abrir programa",
        width=16,
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
        width=12,
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
        title_lbl.configure(text="Atualização concluída!", fg="#22C55E")
        ver_text = f" (v{new_version})" if new_version else ""
        status_var.set(f"O software foi atualizado com sucesso{ver_text}. Abrindo...")
        canvas.coords(fill_rect, 0, 0, bar_w, 10)
        root.after(700, on_open)

    def finish_err(err_msg: str) -> None:
        title_lbl.configure(text="Erro na atualização", fg="#EF4444")
        status_var.set(err_msg[:150])
        open_btn.pack_forget()
        btn_frame.pack(pady=(0, 16))

    def worker() -> None:
        try:
            _download_and_replace(
                url=url,
                target_exe=target_exe,
                pid=pid,
                new_version=new_version,
                on_progress=lambda p, m: root.after(0, lambda pct=p, msg=m: update_ui(pct, msg)),
            )
            root.after(0, finish_ok)
        except Exception as exc:
            err = str(exc) or "Falha inesperada ao atualizar."
            root.after(0, lambda: finish_err(err))

    root.after(120, lambda: threading.Thread(target=worker, daemon=True).start())
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualizador do MansuLoader")
    parser.add_argument("--url", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--version", default="")
    args = parser.parse_args()
    run_updater_ui(
        url=args.url,
        target_exe=Path(args.target).resolve(),
        pid=args.pid,
        new_version=args.version,
    )


if __name__ == "__main__":
    main()
