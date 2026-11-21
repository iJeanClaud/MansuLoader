"""Gerenciamento seguro de configurações persistentes do MansuLoader."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

VALID_QUALITIES = ("320", "256", "192", "128")


@dataclass
class AppConfig:
    """Estrutura de configuração salva em disco."""

    download_folder: Optional[str] = None
    audio_quality: str = "320"


def get_config_path() -> Path:
    """Retorna o caminho do arquivo config.json em %APPDATA%\\mansu-loader."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base_dir = Path(appdata) / "mansu-loader"
    else:
        base_dir = Path.home() / ".mansu-loader"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "config.json"


def load_config() -> AppConfig:
    """Carrega a configuração do arquivo JSON com validação segura."""
    config_path = get_config_path()
    if not config_path.exists():
        return AppConfig()

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return AppConfig()

        folder = data.get("download_folder")
        if not isinstance(folder, str) or not folder.strip():
            folder = None

        quality = str(data.get("audio_quality", "320"))
        if quality not in VALID_QUALITIES:
            quality = "320"

        return AppConfig(download_folder=folder, audio_quality=quality)
    except (OSError, ValueError, TypeError):
        return AppConfig()


def save_config(config: AppConfig) -> Path:
    """Salva a configuração atual em disco de forma atômica."""
    config_path = get_config_path()
    quality = config.audio_quality if config.audio_quality in VALID_QUALITIES else "320"
    payload = AppConfig(
        download_folder=config.download_folder,
        audio_quality=quality,
    )
    tmp_path = config_path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(asdict(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_path.replace(config_path)
    return config_path
