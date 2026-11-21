# Script para gerar o executável standalone MansuLoader.exe com FFmpeg e ícone embutidos
.\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --onefile `
    --windowed `
    --name MansuLoader `
    --icon "assets\mansuloader.ico" `
    --splash "assets\splash.png" `
    --add-data "assets;assets" `
    --add-binary "C:\ffmpeg\bin\ffmpeg.exe;." `
    --collect-all customtkinter `
    --collect-all yt_dlp `
    main.py
