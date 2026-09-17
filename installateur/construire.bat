@echo off
rem Construit Jarvis-Installateur.exe (Nuitka, un seul fichier, fenetre graphique) et le paquet de mise a jour.
rem A lancer depuis la racine du depot : installateur\construire.bat [version]   (l'action GitHub fait pareil a chaque push)
setlocal
cd /d "%~dp0\.."
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (echo Le venv manque. & exit /b 1)
set VERSION=%1
if "%VERSION%"=="" set VERSION=1.0.0

rem 1. la charge utile, le code en .pyc, charge.zip et le paquet de mise a jour (installateur\paquet.py)
"%PY%" installateur\paquet.py --version %VERSION% || (echo Charge utile echouee. & exit /b 1)

rem 2. l'exe, compile en natif par Nuitka (MinGW telecharge tout seul la premiere fois, sans admin).
rem    PyInstaller donnait un exe que Defender classait Trojan:Win32/Wacatac.B!ml (faux positif) : plus avec Nuitka.
"%PY%" -m nuitka --onefile --assume-yes-for-downloads --enable-plugin=tk-inter --windows-console-mode=disable ^
  --nofollow-import-to=jarvis --no-deployment-flag=excluded-module-usage --include-data-files=installateur\charge.zip=charge.zip ^
  --output-dir=installateur\dist --output-filename=Jarvis-Installateur.exe --remove-output ^
  --company-name="LeDevFou" --product-name="Jarvis" --file-version=%VERSION%.0 --product-version=%VERSION%.0 ^
  --file-description="Installateur de Jarvis, assistant vocal local" installateur\installateur.py
if errorlevel 1 (echo Construction echouee. & exit /b 1)
echo.
echo Pret : installateur\dist\Jarvis-Installateur.exe
endlocal
