"""Interface moderna em CustomTkinter para o MansuLoader."""

from __future__ import annotations

import ctypes
import gc
import os
import sys
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from src.config_manager import AppConfig, load_config, save_config
from src.logger import log_exception
from src.update_service import (
    UpdateInfo,
    check_for_update,
    download_update,
    launch_updater_and_exit,
)
from src.version import APP_VERSION
from src.youtube_service import (
    DownloadCancelled,
    DownloadProgress,
    VideoInfo,
    check_existing_mp3,
    download_mp3,
    fetch_video_info,
    find_ffmpeg,
    format_duration,
    validate_youtube_url,
)

# Paleta moderna inspirada em apps de áudio/streaming
BG_APP = "#0F1117"
BG_CARD = "#171A23"
BG_CARD_ALT = "#1E222E"
BORDER_SUBTLE = "#2A3040"
ACCENT = "#FF3B5C"
ACCENT_HOVER = "#E02E4D"
ACCENT_SOFT = "#2D1821"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
ERROR = "#EF4444"
TEXT_PRIMARY = "#F3F4F6"
TEXT_SECONDARY = "#9CA3AF"
TEXT_MUTED = "#6B7280"

QUALITY_LABELS = {
    "320 kbps (Máxima)": "320",
    "256 kbps (Alta)": "256",
    "192 kbps (Média)": "192",
    "128 kbps (Compacta)": "128",
}
QUALITY_TO_LABEL = {v: k for k, v in QUALITY_LABELS.items()}


def _get_asset_path(filename: str) -> Path:
    """Retorna o caminho de um recurso em assets/ (dev ou empacotado via PyInstaller)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "assets" / filename
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[2] / "assets" / filename


def _round_corners(image: Image.Image, radius: int = 16) -> Image.Image:
    """Aplica cantos arredondados à imagem da thumbnail."""
    resized = image.resize((224, 126), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", resized.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, resized.size[0], resized.size[1]), radius=radius, fill=255)
    resized.putalpha(mask)
    return resized


class MansuLoaderApp(ctk.CTk):
    """Janela principal do aplicativo MansuLoader."""

    WINDOW_WIDTH = 780

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"MansuLoader v{APP_VERSION} — YouTube para MP3")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.configure(fg_color=BORDER_SUBTLE)

        self.config_data: AppConfig = load_config()
        self.current_video: Optional[VideoInfo] = None
        self.is_fetching: bool = False
        self.is_downloading: bool = False
        self.cancel_event = threading.Event()
        self._debounce_job: Optional[str] = None
        self._status_reset_job: Optional[str] = None
        self._fetch_token: int = 0
        self._thumb_ctk: Optional[ctk.CTkImage] = None
        self._app_icon_ctk: Optional[ctk.CTkImage] = None
        self._tk_icon_photo: Optional[ImageTk.PhotoImage] = None
        self._minimizing: bool = False
        self._drag_x: int = 0
        self._drag_y: int = 0

        ico_path = _get_asset_path("mansuloader.ico")
        if ico_path.is_file():
            try:
                self.iconbitmap(str(ico_path))
            except Exception:
                pass

        png_path = _get_asset_path("mansuloader.png")
        if png_path.is_file():
            try:
                hi_icon = Image.open(png_path).resize((64, 64), Image.Resampling.LANCZOS)
                self._tk_icon_photo = ImageTk.PhotoImage(hi_icon)
                self.iconphoto(True, self._tk_icon_photo)
            except Exception:
                pass

        self._build_ui()
        self._refresh_folder_display()
        self._check_ffmpeg_banner()
        self._center_window()

        self.bind("<Map>", self._on_map)
        self.report_callback_exception = self._on_tk_exception
        # Evita que o GC do Python colete objetos Tcl/Tk em threads secundárias
        gc.disable()
        self.after(4000, self._run_main_thread_gc)
        self.after(20, self._apply_appwindow_style)
        self.after(60, self._bring_to_front)

    def _run_main_thread_gc(self) -> None:
        """Executa coleta de lixo exclusivamente na thread principal da UI."""
        try:
            gc.collect()
        except Exception:
            pass
        if self.winfo_exists():
            self.after(4000, self._run_main_thread_gc)

    def _on_tk_exception(self, exc_type, exc_value, exc_tb) -> None:
        """Captura exceções de callbacks do Tkinter sem derrubar a interface."""
        import traceback

        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_exception(f"Erro em callback da interface:\n{details}")
        try:
            self._set_status("Ocorreu um erro interno (registrado no log).", ERROR)
        except Exception:
            pass

    def _center_window(self) -> None:
        """Calcula o tamanho ideal (incluindo botão de cancelar) e centraliza na tela."""
        self.cancel_btn.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.update_idletasks()
        width = max(self.WINDOW_WIDTH, self.winfo_reqwidth())
        height = max(590, self.winfo_reqheight() + 16)
        self.cancel_btn.grid_forget()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _apply_appwindow_style(self) -> None:
        """Mantém o app visível na barra de tarefas e ativo em primeiro plano."""
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            gwl_exstyle = -20
            ws_ex_appwindow = 0x00040000
            ws_ex_toolwindow = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            style = (style & ~ws_ex_toolwindow) | ws_ex_appwindow
            ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style)
            self.withdraw()
            self.after(10, self._restore_and_focus)
        except Exception:
            self._bring_to_front()

    def _restore_and_focus(self) -> None:
        self.deiconify()
        self._bring_to_front()

    def _bring_to_front(self) -> None:
        """Traz a janela para frente de outras janelas e foca o aplicativo."""
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            if sys.platform == "win32":
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            self.after(150, lambda: self.attributes("-topmost", False))
            self.url_entry.focus_set()
        except Exception:
            pass

    def _minimize_window(self) -> None:
        self._minimizing = True
        self.overrideredirect(False)
        self.iconify()

    def _on_map(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        if self._minimizing and self.state() == "normal":
            self._minimizing = False
            self.overrideredirect(True)
            self.after(10, self._apply_appwindow_style)

    def _start_drag(self, event) -> None:
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        root_container = ctk.CTkFrame(
            self,
            fg_color=BG_APP,
            corner_radius=0,
        )
        root_container.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        root_container.grid_columnconfigure(0, weight=1)

        # Barra de título integrada (apenas Minimizar e Fechar)
        titlebar = ctk.CTkFrame(root_container, fg_color="#131620", corner_radius=0, height=38)
        titlebar.grid(row=0, column=0, sticky="ew")
        titlebar.grid_propagate(False)
        titlebar.grid_columnconfigure(0, weight=1)

        titlebar.bind("<ButtonPress-1>", self._start_drag)
        titlebar.bind("<B1-Motion>", self._on_drag)

        tb_left = ctk.CTkFrame(titlebar, fg_color="transparent")
        tb_left.grid(row=0, column=0, sticky="w", padx=14)
        tb_left.bind("<ButtonPress-1>", self._start_drag)
        tb_left.bind("<B1-Motion>", self._on_drag)

        png_path = _get_asset_path("mansuloader.png")
        if png_path.is_file():
            try:
                icon_img = Image.open(png_path)
                self._app_icon_ctk = ctk.CTkImage(
                    light_image=icon_img,
                    dark_image=icon_img,
                    size=(18, 18),
                )
                tb_icon = ctk.CTkLabel(tb_left, image=self._app_icon_ctk, text="")
                tb_icon.pack(side="left", padx=(0, 8), pady=8)
                tb_icon.bind("<ButtonPress-1>", self._start_drag)
                tb_icon.bind("<B1-Motion>", self._on_drag)
            except Exception:
                pass

        tb_title = ctk.CTkLabel(
            tb_left,
            text=f"MansuLoader v{APP_VERSION} — YouTube para MP3",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
        )
        tb_title.pack(side="left", pady=8)
        tb_title.bind("<ButtonPress-1>", self._start_drag)
        tb_title.bind("<B1-Motion>", self._on_drag)

        tb_controls = ctk.CTkFrame(titlebar, fg_color="transparent")
        tb_controls.grid(row=0, column=1, sticky="e")

        min_btn = ctk.CTkButton(
            tb_controls,
            text="—",
            width=44,
            height=38,
            corner_radius=0,
            fg_color="transparent",
            hover_color="#232838",
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._minimize_window,
        )
        min_btn.pack(side="left")

        close_btn = ctk.CTkButton(
            tb_controls,
            text="✕",
            width=46,
            height=38,
            corner_radius=0,
            fg_color="transparent",
            hover_color=ERROR,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy,
        )
        close_btn.pack(side="left")

        # Cabeçalho
        header = ctk.CTkFrame(root_container, fg_color="transparent")
        header.grid(row=1, column=0, sticky="ew", padx=24, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="w")

        badge = ctk.CTkLabel(
            title_row,
            text="MP3",
            fg_color=ACCENT,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            width=46,
            height=26,
        )
        badge.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            title_row,
            text="MansuLoader",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Baixe músicas do YouTube em MP3 na máxima qualidade com pré-visualização instantânea",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SECONDARY,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.ffmpeg_badge = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=8,
            padx=10,
            pady=4,
        )
        self.ffmpeg_badge.grid(row=0, column=1, rowspan=2, sticky="e")

        # Card 1: Campo de URL
        url_card = ctk.CTkFrame(
            root_container,
            fg_color=BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        url_card.grid(row=2, column=0, sticky="ew", padx=24, pady=(6, 10))
        url_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            url_card,
            text="Link do YouTube",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6))

        self.url_var = ctk.StringVar()
        self.url_var.trace_add("write", self._on_url_changed)

        self.url_entry = ctk.CTkEntry(
            url_card,
            textvariable=self.url_var,
            placeholder_text="Cole aqui o link do vídeo (ex: https://www.youtube.com/watch?v=...)",
            height=42,
            corner_radius=10,
            fg_color=BG_CARD_ALT,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=13),
        )
        self.url_entry.grid(row=1, column=0, sticky="ew", padx=(16, 10), pady=(0, 14))
        self.url_entry.bind("<Return>", lambda _e: self._trigger_preview(immediate=True))

        self.download_btn = ctk.CTkButton(
            url_card,
            text="Baixar MP3",
            width=140,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled",
            command=self._start_download,
        )
        self.download_btn.grid(row=1, column=1, padx=(0, 16), pady=(0, 14))

        # Card 2: Pré-visualização do Vídeo
        self.preview_card = ctk.CTkFrame(
            root_container,
            fg_color=BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER_SUBTLE,
            height=162,
        )
        self.preview_card.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 10))
        self.preview_card.grid_propagate(False)
        self.preview_card.grid_columnconfigure(1, weight=1)

        self.thumb_label = ctk.CTkLabel(
            self.preview_card,
            text="Pré-visualização\ndo MP3",
            width=224,
            height=126,
            fg_color=BG_CARD_ALT,
            corner_radius=12,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
        )
        self.thumb_label.grid(row=0, column=0, rowspan=3, padx=16, pady=18, sticky="w")

        self.preview_title = ctk.CTkLabel(
            self.preview_card,
            text="Cole um link acima para carregar a pré-visualização",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
            justify="left",
            wraplength=420,
        )
        self.preview_title.grid(row=0, column=1, sticky="sw", padx=(0, 16), pady=(22, 4))

        self.preview_channel = ctk.CTkLabel(
            self.preview_card,
            text="O título, canal, duração e capa aparecerão aqui automaticamente.",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self.preview_channel.grid(row=1, column=1, sticky="nw", padx=(0, 16), pady=2)

        self.preview_meta = ctk.CTkLabel(
            self.preview_card,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ACCENT,
            anchor="w",
        )
        self.preview_meta.grid(row=2, column=1, sticky="nw", padx=(0, 16), pady=(4, 16))

        # Card 3: Qualidade e Pasta Personalizada
        settings_card = ctk.CTkFrame(
            root_container,
            fg_color=BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        settings_card.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 10))
        settings_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            settings_card,
            text="Qualidade do MP3:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(16, 10), pady=(14, 8))

        initial_label = QUALITY_TO_LABEL.get(self.config_data.audio_quality, "320 kbps (Máxima)")
        self.quality_var = ctk.StringVar(value=initial_label)
        self.quality_menu = ctk.CTkOptionMenu(
            settings_card,
            values=list(QUALITY_LABELS.keys()),
            variable=self.quality_var,
            width=210,
            height=34,
            corner_radius=8,
            fg_color=BG_CARD_ALT,
            button_color="#2A3040",
            button_hover_color="#374151",
            text_color=TEXT_PRIMARY,
            command=self._on_quality_change,
        )
        self.quality_menu.grid(row=0, column=1, sticky="w", pady=(14, 8))

        ctk.CTkLabel(
            settings_card,
            text="Salvar em:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=1, column=0, sticky="w", padx=(16, 10), pady=(4, 14))

        self.folder_label = ctk.CTkLabel(
            settings_card,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.folder_label.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(4, 14))

        folder_btns = ctk.CTkFrame(settings_card, fg_color="transparent")
        folder_btns.grid(row=1, column=2, sticky="e", padx=(0, 16), pady=(4, 14))

        self.choose_folder_btn = ctk.CTkButton(
            folder_btns,
            text="Alterar pasta",
            width=110,
            height=32,
            corner_radius=8,
            fg_color=BG_CARD_ALT,
            hover_color="#2A3040",
            border_width=1,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._choose_folder,
        )
        self.choose_folder_btn.pack(side="left", padx=(0, 6))

        self.open_folder_btn = ctk.CTkButton(
            folder_btns,
            text="Abrir",
            width=66,
            height=32,
            corner_radius=8,
            fg_color=BG_CARD_ALT,
            hover_color="#2A3040",
            border_width=1,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=12),
            command=self._open_destination_folder,
        )
        self.open_folder_btn.pack(side="left")

        # Card 4: Barra de Status e Ação
        action_card = ctk.CTkFrame(
            root_container,
            fg_color=BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        action_card.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 20))
        action_card.grid_columnconfigure(0, weight=1)

        status_row = ctk.CTkFrame(action_card, fg_color="transparent")
        status_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        status_row.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status_row,
            text="Pronto para baixar",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="w")

        self.metrics_label = ctk.CTkLabel(
            status_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SECONDARY,
            anchor="e",
        )
        self.metrics_label.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            action_card,
            height=12,
            corner_radius=6,
            fg_color=BG_CARD_ALT,
            progress_color=ACCENT,
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        self.progress_bar.set(0)

        self.cancel_btn = ctk.CTkButton(
            action_card,
            text="Cancelar download",
            height=36,
            corner_radius=8,
            fg_color=BG_CARD_ALT,
            hover_color="#3B1D24",
            border_width=1,
            border_color=ERROR,
            text_color=ERROR,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._cancel_download,
        )
        # Exibido apenas durante o download

    def _check_ffmpeg_banner(self) -> None:
        if find_ffmpeg():
            self.ffmpeg_badge.configure(
                text="FFmpeg OK",
                fg_color="#142B1E",
                text_color=SUCCESS,
            )
        else:
            self.ffmpeg_badge.configure(
                text="FFmpeg ausente",
                fg_color="#332211",
                text_color=WARNING,
            )

    def _refresh_folder_display(self) -> None:
        folder = self.config_data.download_folder
        if folder and Path(folder).is_dir():
            display = folder if len(folder) <= 52 else f"...{folder[-49:]}"
            self.folder_label.configure(text=display, text_color=TEXT_SECONDARY)
            self.open_folder_btn.configure(state="normal")
        else:
            self.folder_label.configure(
                text="Nenhuma pasta definida (será solicitada ao baixar)",
                text_color=WARNING,
            )
            self.open_folder_btn.configure(state="disabled")

    def _on_quality_change(self, selected_label: str) -> None:
        quality = QUALITY_LABELS.get(selected_label, "320")
        self.config_data.audio_quality = quality
        save_config(self.config_data)
        if self.current_video:
            duration_str = format_duration(self.current_video.duration_seconds)
            self.preview_meta.configure(
                text=f"⏱ {duration_str}   •   Formato: MP3 ({quality} kbps)"
            )

    def _choose_folder(self) -> Optional[str]:
        initial = self.config_data.download_folder
        if not initial or not Path(initial).is_dir():
            initial = str(Path.home() / "Music")
        selected = filedialog.askdirectory(
            title="Selecione a pasta para salvar os arquivos MP3",
            initialdir=initial,
        )
        if selected:
            self.config_data.download_folder = selected
            save_config(self.config_data)
            self._refresh_folder_display()
            return selected
        return None

    def _open_destination_folder(self) -> None:
        folder = self.config_data.download_folder
        if folder and Path(folder).is_dir():
            os.startfile(folder)

    def _on_url_changed(self, *_args) -> None:
        if self._debounce_job is not None:
            self.after_cancel(self._debounce_job)
            self._debounce_job = None

        url = self.url_var.get().strip()
        if not url:
            self._reset_preview()
            return

        is_valid, _ = validate_youtube_url(url)
        if is_valid:
            self._debounce_job = self.after(450, lambda: self._trigger_preview(immediate=True))

    def _clear_thumb(self, placeholder: str) -> None:
        """Remove a thumbnail do CTkLabel sem deixar referência pendente no Tk."""
        old_thumb = self._thumb_ctk
        try:
            if hasattr(self.thumb_label, "_label"):
                self.thumb_label._label.configure(image="")
            self.thumb_label.configure(image=None, text=placeholder)
        except Exception:
            pass
        self._thumb_ctk = None
        del old_thumb

    def _reset_preview(self) -> None:
        self.current_video = None
        self._clear_thumb("Pré-visualização\ndo MP3")

        self.preview_title.configure(
            text="Cole um link acima para carregar a pré-visualização",
            text_color=TEXT_SECONDARY,
        )
        self.preview_channel.configure(
            text="O título, canal, duração e capa aparecerão aqui automaticamente.",
            text_color=TEXT_MUTED,
        )
        self.preview_meta.configure(text="")
        if not self.is_downloading:
            self.download_btn.configure(state="disabled")

    def _trigger_preview(self, immediate: bool = False) -> None:
        if self.is_downloading:
            return
        url = self.url_var.get().strip()
        is_valid, msg = validate_youtube_url(url)
        if not is_valid:
            if immediate:
                self._show_preview_error(msg)
            return

        self._fetch_token += 1
        token = self._fetch_token
        self.is_fetching = True
        self.download_btn.configure(state="disabled")
        self.preview_title.configure(text="Carregando pré-visualização...", text_color=TEXT_PRIMARY)
        self.preview_channel.configure(text="Buscando metadados e capa do vídeo...", text_color=TEXT_SECONDARY)
        self.preview_meta.configure(text="")
        self._set_status("Buscando informações do vídeo...", TEXT_SECONDARY)

        threading.Thread(
            target=self._fetch_worker,
            args=(url, token),
            daemon=True,
        ).start()

    def _fetch_worker(self, url: str, token: int) -> None:
        try:
            info = fetch_video_info(url)
            self.after(0, lambda: self._on_fetch_success(info, token))
        except Exception as exc:
            log_exception("Erro ao buscar informações do vídeo", exc)
            err_msg = str(exc) or "Não foi possível carregar o vídeo."
            self.after(0, lambda: self._on_fetch_error(err_msg, token))

    def _on_fetch_success(self, info: VideoInfo, token: int) -> None:
        if token != self._fetch_token:
            return
        self.is_fetching = False
        self.current_video = info

        if info.thumbnail_image is not None:
            old_thumb = self._thumb_ctk
            rounded = _round_corners(info.thumbnail_image, radius=12)
            new_thumb = ctk.CTkImage(light_image=rounded, dark_image=rounded, size=(224, 126))
            self.thumb_label.configure(image=new_thumb, text="")
            self._thumb_ctk = new_thumb
            del old_thumb
        else:
            self._clear_thumb("Sem capa")

        self.preview_title.configure(text=info.title, text_color=TEXT_PRIMARY)
        self.preview_channel.configure(text=f"Canal: {info.channel}", text_color=TEXT_SECONDARY)
        quality = QUALITY_LABELS.get(self.quality_var.get(), "320")
        self.preview_meta.configure(
            text=f"⏱ {format_duration(info.duration_seconds)}   •   Formato: MP3 ({quality} kbps)"
        )
        self.download_btn.configure(state="normal")
        self._set_status("Pré-visualização carregada. Pronto para baixar!", SUCCESS)

    def _on_fetch_error(self, message: str, token: int) -> None:
        if token != self._fetch_token:
            return
        self.is_fetching = False
        self._show_preview_error(message)

    def _show_preview_error(self, message: str) -> None:
        self.current_video = None
        self._clear_thumb("Erro")
        self.preview_title.configure(text="Não foi possível carregar o vídeo", text_color=ERROR)
        self.preview_channel.configure(text=message[:160], text_color=TEXT_SECONDARY)
        self.preview_meta.configure(text="")
        self.download_btn.configure(state="disabled")
        self._set_status("Verifique o link informado.", ERROR)

    def _start_download(self) -> None:
        if self.is_downloading or not self.current_video:
            return

        folder = self.config_data.download_folder
        if not folder or not Path(folder).is_dir():
            self._set_status("Selecione uma pasta para salvar o arquivo MP3...", WARNING)
            folder = self._choose_folder()
            if not folder:
                self._set_status("Download cancelado: nenhuma pasta selecionada.", WARNING)
                return

        existing_file = check_existing_mp3(self.current_video.title, folder)
        if existing_file is not None:
            self._set_status("Arquivo já existe na pasta de destino.", WARNING, auto_clear_ms=10000)
            self._show_already_exists_notice(existing_file.name)
            return

        quality = QUALITY_LABELS.get(self.quality_var.get(), "320")
        self.is_downloading = True
        self.cancel_event.clear()

        self.download_btn.configure(state="disabled", text="Baixando...")
        self.url_entry.configure(state="disabled")
        self.quality_menu.configure(state="disabled")
        self.choose_folder_btn.configure(state="disabled")
        self.cancel_btn.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.progress_bar.set(0.02)
        self.metrics_label.configure(text="")

        url = self.current_video.webpage_url
        title = self.current_video.title

        threading.Thread(
            target=self._download_worker,
            args=(url, folder, quality, title),
            daemon=True,
        ).start()

    def _download_worker(self, url: str, folder: str, quality: str, title: str) -> None:
        try:
            saved_path = download_mp3(
                url=url,
                output_folder=folder,
                quality=quality,
                on_progress=lambda p: self.after(0, lambda prog=p: self._on_download_progress(prog)),
                cancel_event=self.cancel_event,
            )
            self.after(0, lambda: self._on_download_complete(saved_path, title, quality))
        except DownloadCancelled:
            self.after(0, self._on_download_cancelled)
        except Exception as exc:
            log_exception("Erro durante o download/conversão MP3", exc)
            err_msg = str(exc) or "Erro inesperado durante o download."
            self.after(0, lambda: self._on_download_error(err_msg))

    def _on_download_progress(self, progress: DownloadProgress) -> None:
        if not self.is_downloading:
            return
        self.progress_bar.set(progress.percent)
        self._set_status(progress.stage, TEXT_PRIMARY)
        parts = [p for p in (progress.speed_text, progress.eta_text) if p]
        self.metrics_label.configure(text=" • ".join(parts))

    def _on_download_complete(self, saved_path: Path, title: str, quality: str) -> None:
        self._finish_download_state()
        self.progress_bar.set(0)
        self.metrics_label.configure(text="")
        self.url_var.set("")
        self._reset_preview()
        self._set_status(f"Concluído! Salvo: {saved_path.name}", SUCCESS, auto_clear_ms=10000)
        self._show_completion_notice(saved_path.name)

    def _show_completion_notice(self, filename: str) -> None:
        """Exibe aviso de download concluído com botão Ok e fechamento automático em 5s."""
        short_name = filename if len(filename) <= 48 else f"{filename[:45]}..."
        self._show_auto_close_notice(
            window_title="Download concluído",
            header_text="Download concluído!",
            header_color=SUCCESS,
            body_text=f"O arquivo já terminou de baixar:\n{short_name}",
            seconds=5,
        )

    def _show_already_exists_notice(self, filename: str) -> None:
        """Exibe aviso quando o arquivo MP3 já existe na pasta, com timer de 20s."""
        short_name = filename if len(filename) <= 48 else f"{filename[:45]}..."
        self._show_auto_close_notice(
            window_title="Arquivo já existe",
            header_text="Arquivo já existe!",
            header_color=WARNING,
            body_text=f"Esta música já existe na pasta selecionada:\n{short_name}",
            seconds=20,
        )

    def _show_auto_close_notice(
        self,
        window_title: str,
        header_text: str,
        header_color: str,
        body_text: str,
        seconds: int,
    ) -> None:
        """Exibe janela de aviso modal com botão Ok e fechamento automático."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(window_title)
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_CARD)
        dialog.transient(self)
        dialog.grab_set()

        dlg_w, dlg_h = 410, 195
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dlg_w) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dlg_h) // 2)
        dialog.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")

        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text=header_text,
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=header_color,
        ).grid(row=0, column=0, padx=20, pady=(20, 6))

        ctk.CTkLabel(
            dialog,
            text=body_text,
            font=ctk.CTkFont(size=13),
            text_color=TEXT_PRIMARY,
            justify="center",
            wraplength=360,
        ).grid(row=1, column=0, padx=20, pady=(0, 8))

        countdown_label = ctk.CTkLabel(
            dialog,
            text=f"Fechando automaticamente em {seconds}s...",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        )
        countdown_label.grid(row=2, column=0, padx=20, pady=(0, 12))

        timer_id: list[Optional[str]] = [None]

        def close_dialog() -> None:
            if timer_id[0] is not None:
                try:
                    dialog.after_cancel(timer_id[0])
                except Exception:
                    pass
                timer_id[0] = None
            if dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()

        ok_btn = ctk.CTkButton(
            dialog,
            text="Ok",
            width=120,
            height=36,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=close_dialog,
        )
        ok_btn.grid(row=3, column=0, pady=(0, 18))
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

        def tick(remaining: int) -> None:
            if not dialog.winfo_exists():
                return
            if remaining <= 0:
                close_dialog()
                return
            countdown_label.configure(text=f"Fechando automaticamente em {remaining}s...")
            timer_id[0] = dialog.after(1000, lambda: tick(remaining - 1))

        timer_id[0] = dialog.after(1000, lambda: tick(seconds - 1))

    def _on_download_cancelled(self) -> None:
        self._finish_download_state()
        self.progress_bar.set(0)
        self.metrics_label.configure(text="")
        self._set_status("Download cancelado.", WARNING)

    def _on_download_error(self, message: str) -> None:
        self._finish_download_state()
        self.progress_bar.set(0)
        self.metrics_label.configure(text="")
        self._set_status(f"Erro: {message}", ERROR)

    def _finish_download_state(self) -> None:
        self.is_downloading = False
        self.cancel_btn.grid_forget()
        self.url_entry.configure(state="normal")
        self.quality_menu.configure(state="normal")
        self.choose_folder_btn.configure(state="normal")
        self.download_btn.configure(
            text="Baixar MP3",
            state="normal" if self.current_video else "disabled",
        )

    def _cancel_download(self) -> None:
        if self.is_downloading:
            self.cancel_event.set()
            self._set_status("Cancelando download...", WARNING)

    def _set_status(
        self,
        text: str,
        color: str = TEXT_PRIMARY,
        auto_clear_ms: Optional[int] = None,
    ) -> None:
        if self._status_reset_job is not None:
            try:
                self.after_cancel(self._status_reset_job)
            except Exception:
                pass
            self._status_reset_job = None

        self.status_label.configure(text=text, text_color=color)
        if auto_clear_ms is not None:
            self._status_reset_job = self.after(
                auto_clear_ms,
                lambda: self.status_label.configure(
                    text="Pronto para baixar",
                    text_color=TEXT_PRIMARY,
                )
                if not self.is_downloading and not self.is_fetching
                else None,
            )

    def _check_updates_on_startup(self) -> None:
        """Verifica em segundo plano se existe uma nova versão na branch main."""
        threading.Thread(target=self._update_check_worker, daemon=True).start()

    def _update_check_worker(self) -> None:
        info = check_for_update()
        if info is not None:
            self.after(0, lambda: self._show_update_dialog(info))

    def _show_update_dialog(self, info: UpdateInfo) -> None:
        """Exibe aviso obrigatório de atualização: usuário só pode escolher Atualizar ou Sair."""
        dialog = ctk.CTkToplevel(self)
        dialog.overrideredirect(True)
        dialog.resizable(False, False)
        dialog.configure(fg_color=ACCENT)
        dialog.transient(self)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        dlg_w, dlg_h = 440, 250
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dlg_w) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dlg_h) // 2)
        dialog.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")

        box = ctk.CTkFrame(dialog, fg_color=BG_CARD, corner_radius=0)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            box,
            text="Atualização disponível!",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=22, pady=(20, 6))

        notes_line = f"\n{info.notes}" if info.notes else ""
        ctk.CTkLabel(
            box,
            text=(
                f"Uma nova versão (v{info.latest_version}) foi publicada.\n"
                f"Versão atual: v{info.current_version}{notes_line}"
            ),
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SECONDARY,
            justify="center",
            wraplength=390,
        ).grid(row=1, column=0, padx=22, pady=(0, 12))

        status_lbl = ctk.CTkLabel(
            box,
            text="Escolha uma opção para continuar:",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        )
        status_lbl.grid(row=2, column=0, padx=22, pady=(0, 6))

        upd_progress = ctk.CTkProgressBar(
            box,
            height=10,
            corner_radius=5,
            fg_color=BG_CARD_ALT,
            progress_color=ACCENT,
        )
        upd_progress.set(0)

        btn_frame = ctk.CTkFrame(box, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=(8, 20))

        def on_exit() -> None:
            if dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()
            self.destroy()

        def on_update() -> None:
            update_btn.configure(state="disabled", text="Atualizando...")
            exit_btn.configure(state="disabled")
            upd_progress.grid(row=3, column=0, sticky="ew", padx=26, pady=(0, 10))
            status_lbl.configure(text="Baixando atualização...", text_color=TEXT_PRIMARY)

            def worker() -> None:
                try:
                    new_exe = download_update(
                        info.download_url,
                        on_progress=lambda p: dialog.after(
                            0,
                            lambda prog=p: (
                                upd_progress.set(prog),
                                status_lbl.configure(
                                    text=f"Baixando atualização... {int(prog * 100)}%"
                                ),
                            ),
                        ),
                    )
                    launched = launch_updater_and_exit(new_exe)
                    if launched:
                        dialog.after(0, on_exit)
                    else:
                        dialog.after(
                            0,
                            lambda: (
                                status_lbl.configure(
                                    text=f"Baixado em: {new_exe.name}. Execute o novo .exe.",
                                    text_color=SUCCESS,
                                ),
                                exit_btn.configure(state="normal"),
                            ),
                        )
                except Exception as exc:
                    err = str(exc) or "Falha ao baixar atualização."
                    dialog.after(
                        0,
                        lambda: (
                            status_lbl.configure(text=f"Erro: {err[:90]}", text_color=ERROR),
                            update_btn.configure(state="normal", text="Atualizar"),
                            exit_btn.configure(state="normal"),
                        ),
                    )

            threading.Thread(target=worker, daemon=True).start()

        update_btn = ctk.CTkButton(
            btn_frame,
            text="Atualizar",
            width=136,
            height=38,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=on_update,
        )
        update_btn.pack(side="left", padx=(0, 10))

        exit_btn = ctk.CTkButton(
            btn_frame,
            text="Sair",
            width=120,
            height=38,
            corner_radius=8,
            fg_color=BG_CARD_ALT,
            hover_color="#3B1D24",
            border_width=1,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=on_exit,
        )
        exit_btn.pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
