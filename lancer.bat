@echo off
setlocal
cd /d "%~dp0"
title Jarvis

rem 1. Python : embarque par l'installateur (python\) ou venv (installer.bat / developpement)
if exist "python\python.exe" (
    set "PY=python\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    call ".venv\Scripts\activate.bat"
    set "PY=python"
) else (
    echo [Jarvis] Ni python\ ni .venv\ : lancez Jarvis-Installateur.exe ou installer.bat une fois.
    pause
    exit /b 1
)

rem 2. Ollama qui tourne, modeles presents (telecharges sinon), voix Kokoro presente
"%PY%" -m jarvis verifier
if errorlevel 1 (
    echo [Jarvis] La verification a echoue, voir les messages ci-dessus.
    pause
    exit /b 1
)

rem 3. Le serveur : il ouvre lui-meme le HUD dans le navigateur par defaut (F pour le plein ecran).
echo [Jarvis] Demarrage du serveur...
"%PY%" -m jarvis
if errorlevel 1 pause
endlocal
