"""Serviço seguro de verificação e aplicação de atualizações via GitHub."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

from src.version import APP_VERSION, DEFAULT_DOWNLOAD_URL, VERSION_JSON_URL

ALLOWED_UPDATE_HOSTS = {
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}

SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass
class UpdateInfo:
    """Dados de uma atualização disponível."""

    current_version: str
    latest_version: str
    download_url: str
    notes: str = ""


def parse_version(version_str: str) -> Optional[tuple[int, int, int]]:
    """Converte uma string '1.2.3' ou 'v1.2.3' em tupla numérica comparável."""
    match = SEMVER_PATTERN.match(version_str.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_newer_version(latest: str, current: str = APP_VERSION) -> bool:
    """Retorna True se 'latest' for estritamente maior que 'current'."""
    latest_t = parse_version(latest)
    current_t = parse_version(current)
    if latest_t is None or current_t is None:
        return False
    return latest_t > current_t


def validate_update_url(url: str) -> bool:
    """Garante que a URL de atualização usa HTTPS e pertence ao GitHub oficial."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host in ALLOWED_UPDATE_HOSTS


def check_for_update(timeout: int = 6) -> Optional[UpdateInfo]:
    """Consulta o version.json na branch main do GitHub e retorna UpdateInfo se houver novidade."""
    try:
        resp = requests.get(
            VERSION_JSON_URL,
            timeout=timeout,
            headers={"Cache-Control": "no-cache"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return None

        latest_version = str(data.get("version") or "").strip().lstrip("v")
        if not is_newer_version(latest_version, APP_VERSION):
            return None

        download_url = str(data.get("download_url") or DEFAULT_DOWNLOAD_URL).strip()
        if not validate_update_url(download_url):
            return None

        notes = str(data.get("notes") or "").strip()
        return UpdateInfo(
            current_version=APP_VERSION,
            latest_version=latest_version,
            download_url=download_url,
            notes=notes,
        )
    except Exception:
        return None


def download_update(
    download_url: str,
    on_progress: Optional[Callable[[float], None]] = None,
) -> Path:
    """Baixa o novo executável para a pasta temporária validando o cabeçalho PE (MZ)."""
    if not validate_update_url(download_url):
        raise ValueError("URL de atualização não autorizada.")

    temp_dir = Path(tempfile.gettempdir())
    target_path = temp_dir / "MansuLoader_update.exe"

    with requests.get(download_url, stream=True, timeout=60, allow_redirects=True) as resp:
        resp.raise_for_status()
        if not validate_update_url(resp.url):
            raise ValueError("Redirecionamento para domínio não autorizado.")

        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with target_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)
                if on_progress and total > 0:
                    on_progress(min(1.0, downloaded / total))

    if not target_path.exists() or target_path.stat().st_size < 1_000_000:
        raise RuntimeError("Arquivo de atualização incompleto ou inválido.")

    with target_path.open("rb") as fh:
        magic = fh.read(2)
    if magic != b"MZ":
        target_path.unlink(missing_ok=True)
        raise RuntimeError("O arquivo baixado não é um executável Windows válido.")

    return target_path


def launch_updater_and_exit(new_exe_path: Path) -> bool:
    """Substitui o .exe atual após fechar e reinicia o aplicativo automaticamente."""
    if not getattr(sys, "frozen", False):
        return False

    current_exe = Path(sys.executable).resolve()
    bat_path = Path(tempfile.gettempdir()) / "mansuloader_updater.bat"
    pid = os.getpid()

    script = (
        "@echo off\n"
        "setlocal\n"
        f":waitloop\n"
        f"tasklist /FI \"PID eq {pid}\" 2>NUL | find /I \"{pid}\" >NUL\n"
        "if not errorlevel 1 (\n"
        "  timeout /t 1 /nobreak >NUL\n"
        "  goto waitloop\n"
        ")\n"
        f"move /Y \"{new_exe_path}\" \"{current_exe}\" >NUL\n"
        f"start \"\" \"{current_exe}\"\n"
        "del \"%~f0\"\n"
    )
    bat_path.write_text(script, encoding="utf-8")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=creationflags,
        close_fds=True,
    )
    return True
