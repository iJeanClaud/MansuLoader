"""Serviço de validação, pré-visualização e download de áudio do YouTube."""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests
import yt_dlp
from PIL import Image

ALLOWED_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

ALLOWED_THUMB_HOSTS = {
    "i.ytimg.com",
    "i1.ytimg.com",
    "i2.ytimg.com",
    "i3.ytimg.com",
    "i4.ytimg.com",
    "img.youtube.com",
}


class DownloadCancelled(Exception):
    """Exceção levantada quando o usuário cancela o download."""


@dataclass
class VideoInfo:
    """Metadados do vídeo carregados para pré-visualização."""

    video_id: str
    title: str
    channel: str
    duration_seconds: int
    webpage_url: str
    thumbnail_url: Optional[str] = None
    thumbnail_image: Optional[Image.Image] = None


@dataclass
class DownloadProgress:
    """Estado de progresso emitido durante o download e conversão."""

    stage: str
    percent: float
    speed_text: str = ""
    eta_text: str = ""


def validate_youtube_url(url: str) -> tuple[bool, str]:
    """Valida estritamente se a URL pertence ao YouTube e usa HTTP/HTTPS."""
    cleaned = url.strip()
    if not cleaned:
        return False, "Cole um link do YouTube."

    if len(cleaned) > 2048 or any(ch in cleaned for ch in ("\n", "\r", "\x00")):
        return False, "URL inválida."

    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        return False, "A URL deve começar com http:// ou https://."

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_YOUTUBE_HOSTS:
        return False, "Informe uma URL válida do YouTube (youtube.com ou youtu.be)."

    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.strip("/")
        if not video_id:
            return False, "Link youtu.be incompleto."
    else:
        has_watch = parsed.path == "/watch" and "v=" in parsed.query
        has_shorts = parsed.path.startswith("/shorts/") and len(parsed.path) > 8
        has_live = parsed.path.startswith("/live/") and len(parsed.path) > 6
        if not (has_watch or has_shorts or has_live):
            return False, "Cole o link de um vídeo específico do YouTube."

    return True, cleaned


def format_duration(seconds: int) -> str:
    """Formata duração em segundos para HH:MM:SS ou MM:SS."""
    if not seconds or seconds < 0:
        return "00:00"
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def find_ffmpeg() -> Optional[str]:
    """Localiza o executável do FFmpeg embutido, no PATH ou em locais padrão do Windows."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "ffmpeg.exe"
        if bundled.is_file():
            return str(bundled)

    in_path = shutil.which("ffmpeg")
    if in_path:
        return in_path

    candidates = [
        Path(sys.executable).resolve().parent / "ffmpeg.exe",
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nome de arquivo no Windows."""
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
    return sanitized[:160] or "audio_youtube"


def _fetch_thumbnail(url: Optional[str]) -> Optional[Image.Image]:
    """Baixa a thumbnail do vídeo validando host e tipo de conteúdo."""
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_THUMB_HOSTS:
        return None

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            return None
        img = Image.open(io.BytesIO(resp.content))
        return img.convert("RGB")
    except Exception:
        return None


def fetch_video_info(url: str) -> VideoInfo:
    """Obtém metadados e thumbnail do vídeo sem baixar o arquivo."""
    is_valid, result = validate_youtube_url(url)
    if not is_valid:
        raise ValueError(result)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(result, download=False)

    if not isinstance(info, dict):
        raise RuntimeError("Não foi possível obter os dados do vídeo.")

    thumb_url = info.get("thumbnail")
    thumb_img = _fetch_thumbnail(thumb_url)

    return VideoInfo(
        video_id=str(info.get("id") or ""),
        title=str(info.get("title") or "Vídeo sem título"),
        channel=str(info.get("channel") or info.get("uploader") or "Canal desconhecido"),
        duration_seconds=int(info.get("duration") or 0),
        webpage_url=str(info.get("webpage_url") or result),
        thumbnail_url=thumb_url,
        thumbnail_image=thumb_img,
    )


def _format_speed(speed_bps: Optional[float]) -> str:
    if not speed_bps or speed_bps <= 0:
        return ""
    mb_s = speed_bps / (1024 * 1024)
    if mb_s >= 1:
        return f"{mb_s:.1f} MB/s"
    kb_s = speed_bps / 1024
    return f"{kb_s:.0f} KB/s"


def _format_eta(eta_seconds: Optional[float]) -> str:
    if eta_seconds is None or eta_seconds < 0:
        return ""
    return f"ETA {format_duration(int(eta_seconds))}"


def check_existing_mp3(title: str, output_folder: str) -> Optional[Path]:
    """Verifica se o MP3 correspondente ao título já existe na pasta de destino."""
    dest_dir = Path(output_folder).resolve()
    if not dest_dir.is_dir():
        return None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(dest_dir / "%(title).150s.%(ext)s"),
        "windowsfilenames": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        expected = Path(ydl.prepare_filename({"title": title, "ext": "mp3"})).resolve()

    if expected.is_file() and (dest_dir in expected.parents or expected.parent == dest_dir):
        return expected
    return None


def download_mp3(
    url: str,
    output_folder: str,
    quality: str = "320",
    on_progress: Optional[Callable[[DownloadProgress], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Baixa o áudio na maior qualidade disponível e converte para MP3."""
    is_valid, clean_url = validate_youtube_url(url)
    if not is_valid:
        raise ValueError(clean_url)

    dest_dir = Path(output_folder).resolve()
    if not dest_dir.exists() or not dest_dir.is_dir():
        raise FileNotFoundError("A pasta de destino selecionada não existe.")

    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        raise RuntimeError(
            "FFmpeg não encontrado. Instale o FFmpeg ou coloque ffmpeg.exe no PATH para converter para MP3."
        )

    final_file: dict[str, Optional[Path]] = {"path": None}

    def emit(progress: DownloadProgress) -> None:
        if on_progress:
            on_progress(progress)

    def progress_hook(data: dict) -> None:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Download cancelado pelo usuário.")

        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            pct = (downloaded / total) if total > 0 else 0.0
            pct = max(0.0, min(0.95, pct * 0.95))
            emit(
                DownloadProgress(
                    stage=f"Baixando áudio... {int((downloaded / total) * 100) if total else 0}%",
                    percent=pct,
                    speed_text=_format_speed(data.get("speed")),
                    eta_text=_format_eta(data.get("eta")),
                )
            )
        elif status == "finished":
            emit(
                DownloadProgress(
                    stage=f"Convertendo para MP3 ({quality} kbps)...",
                    percent=0.96,
                )
            )

    def postprocessor_hook(data: dict) -> None:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Download cancelado pelo usuário.")
        if data.get("status") == "finished":
            info_dict = data.get("info_dict") or {}
            filepath = info_dict.get("filepath")
            if filepath:
                candidate = Path(filepath).resolve()
                if dest_dir in candidate.parents or candidate.parent == dest_dir:
                    final_file["path"] = candidate

    emit(DownloadProgress(stage="Preparando download...", percent=0.05))

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_path,
        "outtmpl": str(dest_dir / "%(title).150s.%(ext)s"),
        "windowsfilenames": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(clean_url, download=True)
        if final_file["path"] is None and isinstance(info, dict):
            prepared = Path(ydl.prepare_filename(info)).with_suffix(".mp3").resolve()
            if prepared.exists() and (dest_dir in prepared.parents or prepared.parent == dest_dir):
                final_file["path"] = prepared

    if final_file["path"] is None or not final_file["path"].exists():
        # Fallback seguro caso o nome tenha sido ajustado pelo windowsfilenames
        mp3_files = sorted(
            dest_dir.glob("*.mp3"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if mp3_files:
            final_file["path"] = mp3_files[0]
        else:
            raise RuntimeError("A conversão terminou, mas o arquivo MP3 não foi encontrado.")

    emit(DownloadProgress(stage="Concluído!", percent=1.0))
    return final_file["path"]
