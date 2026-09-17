@echo off
rem Le service Jarvis Cloud tout seul, sans l'interface : passerelle, agent (votre carte sert les clients), tunnel.
rem Lance par Windows a l'ouverture de session une fois "python -m jarvis cloud installer" execute, ou a la main.
setlocal
cd /d "%~dp0"
if exist "python\python.exe" (set "PY=python\python.exe") else (set "PY=.venv\Scripts\python.exe")
"%PY%" -m jarvis cloud
endlocal
