@echo off
rem Construit Jarvis-Installateur.exe (Inno Setup) et le paquet de mise a jour, comme l'action GitHub a chaque push.
rem A lancer depuis la racine du depot : installateur\construire.bat [version]   (Inno Setup 6 doit etre installe)
rem L'ancien exe Nuitka etait classe Trojan:Win32/Wacatac.B!ml par Defender et 10 antivirus (faux positif, 18/09).
setlocal
cd /d "%~dp0\.."
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (echo Le venv manque. & exit /b 1)
set VERSION=%1
if "%VERSION%"=="" set VERSION=1.0.0
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (echo Inno Setup 6 introuvable : jrsoftware.org/isdl.php & exit /b 1)

rem 1. la charge utile (le code en .pyc) et le paquet de mise a jour
"%PY%" installateur\paquet.py --version %VERSION% || (echo Charge utile echouee. & exit /b 1)
rem 2. le Python officiel embarque, et get-pip.py
"%PY%" installateur\python_embarque.py || (echo Python embarque echoue. & exit /b 1)
rem 3. l'installateur
"%ISCC%" /Q /DVersion=%VERSION% installateur\jarvis.iss || (echo Inno Setup a echoue. & exit /b 1)
echo.
echo Pret : installateur\dist\Jarvis-Installateur.exe
endlocal
