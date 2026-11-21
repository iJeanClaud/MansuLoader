# 1. Compila o atualizador independente (MansuLoaderUpdater.exe) em build\
.\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --onefile `
    --windowed `
    --name MansuLoaderUpdater `
    --distpath "build\updater_dist" `
    --icon "assets\mansuloader.ico" `
    updater_main.py

if (-not $?) { exit $LASTEXITCODE }

# 2. Compila o MansuLoader.exe com FFmpeg, ícone, splash e o MansuLoaderUpdater.exe embutidos
.\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --onefile `
    --windowed `
    --name MansuLoader `
    --icon "assets\mansuloader.ico" `
    --splash "assets\splash.png" `
    --add-data "assets;assets" `
    --add-binary "build\updater_dist\MansuLoaderUpdater.exe;." `
    --add-binary "C:\ffmpeg\bin\ffmpeg.exe;." `
    --collect-all customtkinter `
    --collect-all yt_dlp `
    main.py

if (Test-Path "dist\MansuLoaderUpdater.exe") { Remove-Item "dist\MansuLoaderUpdater.exe" -Force }
