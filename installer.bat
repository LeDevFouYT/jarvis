@echo off
setlocal
cd /d "%~dp0"
title Installation de Jarvis
echo [Jarvis] Installation dans %CD%

rem 1. Python 3.12
python --version 2>nul | find "3.12" >nul
if errorlevel 1 (
    py -3.12 --version >nul 2>&1 || (
        echo [Jarvis] Python 3.12 est introuvable. Installez-le depuis python.org, sans droits administrateur, puis relancez.
        pause
        exit /b 1
    )
    set PY=py -3.12
) else (
    set PY=python
)

rem 2. Le venv et les dependances
if not exist ".venv\Scripts\python.exe" (
    echo [Jarvis] Creation du venv...
    %PY% -m venv .venv || (echo [Jarvis] Impossible de creer le venv. & pause & exit /b 1)
)
echo [Jarvis] Installation des dependances (quelques minutes la premiere fois)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo [Jarvis] pip a echoue. & pause & exit /b 1)

rem 3. Les fichiers de configuration
if not exist "config.json" (
    copy /y "config.example.json" "config.json" >nul
    echo [Jarvis] config.json cree a partir de config.example.json
)
if not exist ".secrets" (
    copy /y ".secrets.example" ".secrets" >nul
    echo [Jarvis] .secrets cree : y mettre les cles ElevenLabs et Telegram si vous les utilisez
)

rem 4. La carte graphique et le choix des modeles
".venv\Scripts\python.exe" -m jarvis installer

echo.
echo [Jarvis] Installation terminee. Double-cliquez lancer.bat : les modeles se telechargent au premier lancement.
pause
endlocal
