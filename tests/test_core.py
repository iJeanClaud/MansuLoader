"""Testes automatizados para configuração e validação do MansuLoader."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.config_manager import AppConfig, load_config, save_config
from src.update_service import is_newer_version, parse_version, validate_update_url
from src.youtube_service import (
    check_existing_mp3,
    find_ffmpeg,
    format_duration,
    validate_youtube_url,
)


class TestConfigManager(unittest.TestCase):
    def test_save_and_load_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            with patch("src.config_manager.get_config_path", return_value=cfg_file):
                saved = save_config(AppConfig(download_folder=tmpdir, audio_quality="320"))
                self.assertEqual(saved, cfg_file)
                loaded = load_config()
                self.assertEqual(loaded.download_folder, tmpdir)
                self.assertEqual(loaded.audio_quality, "320")

    def test_corrupted_config_returns_defaults(self) -> None:
        with TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            cfg_file.write_text("{invalid json", encoding="utf-8")
            with patch("src.config_manager.get_config_path", return_value=cfg_file):
                loaded = load_config()
                self.assertIsNone(loaded.download_folder)
                self.assertEqual(loaded.audio_quality, "320")

    def test_invalid_quality_falls_back_to_320(self) -> None:
        with TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            cfg_file.write_text(json.dumps({"download_folder": tmpdir, "audio_quality": "999"}), encoding="utf-8")
            with patch("src.config_manager.get_config_path", return_value=cfg_file):
                loaded = load_config()
                self.assertEqual(loaded.audio_quality, "320")


class TestYouTubeService(unittest.TestCase):
    def test_valid_youtube_urls(self) -> None:
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/abcdefghijk",
        ]
        for url in valid_urls:
            ok, _ = validate_youtube_url(url)
            self.assertTrue(ok, f"Deveria aceitar: {url}")

    def test_rejects_non_youtube_or_unsafe_urls(self) -> None:
        invalid_urls = [
            "",
            "file:///C:/Windows/System32/cmd.exe",
            "https://evil.com/watch?v=123",
            "javascript:alert(1)",
            "https://www.youtube.com/",
            "https://www.youtube.com/watch?v=abc\nrm -rf /",
        ]
        for url in invalid_urls:
            ok, _ = validate_youtube_url(url)
            self.assertFalse(ok, f"Deveria rejeitar: {url}")

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_find_ffmpeg_returns_existing_path_when_installed(self) -> None:
        ff = find_ffmpeg()
        self.assertIsNotNone(ff)
        self.assertTrue(Path(ff).is_file())

    def test_check_existing_mp3_detects_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / "Minha Musica Legal.mp3"
            existing.write_bytes(b"mp3data")
            found = check_existing_mp3("Minha Musica Legal", tmpdir)
            self.assertEqual(found, existing.resolve())
            missing = check_existing_mp3("Outra Musica", tmpdir)
            self.assertIsNone(missing)


class TestUpdateService(unittest.TestCase):
    def test_version_comparison(self) -> None:
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertTrue(is_newer_version("1.0.1", "1.0.0"))
        self.assertTrue(is_newer_version("2.0.0", "1.9.9"))
        self.assertFalse(is_newer_version("1.0.0", "1.0.0"))
        self.assertFalse(is_newer_version("0.9.9", "1.0.0"))

    def test_validate_update_url(self) -> None:
        self.assertTrue(
            validate_update_url(
                "https://github.com/iJeanClaud/MansuLoader/releases/latest/download/MansuLoader.exe"
            )
        )
        self.assertFalse(validate_update_url("http://github.com/iJeanClaud/MansuLoader"))
        self.assertFalse(validate_update_url("https://evil.com/MansuLoader.exe"))


if __name__ == "__main__":
    unittest.main()
