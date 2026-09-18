"""Prépare installateur/python_embarque/ pour l'installateur Inno Setup : le Python officiel « embeddable » de python.org
(pas de téléchargement chez le client), son fichier ._pth ouvert aux paquets (import site) et au dossier de Jarvis
(..), et get-pip.py à côté.
    python installateur/python_embarque.py"""
import json
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
CIBLE = ICI / "python_embarque"
VERSION = json.loads((ICI / "parametres.json").read_text(encoding="utf-8")).get("python_version", "3.12.10")
URL = f"https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-amd64.zip"
URL_GETPIP = "https://bootstrap.pypa.io/get-pip.py"

if CIBLE.exists():
    shutil.rmtree(CIBLE)
CIBLE.mkdir()
archive = ICI / "python-embed.zip"
urllib.request.urlretrieve(URL, archive)
with zipfile.ZipFile(archive) as z:
    z.extractall(CIBLE)
archive.unlink()
pth = next(CIBLE.glob("python3*._pth"))
pth.write_text(pth.read_text(encoding="utf-8").replace("#import site", "import site") + "\n..\n", encoding="utf-8")
urllib.request.urlretrieve(URL_GETPIP, CIBLE / "get-pip.py")
# Le runtime C++ de Visual Studio : Whisper (ctranslate2) et la voix (onnxruntime) importent MSVCP140.dll et
# MSVCP140_1.dll, que le Python embarqué n'a pas. Sans « Visual C++ Redistributable » sur le PC (un Windows neuf),
# Jarvis était sourd et muet. Posés à côté de python.exe (dossier de l'application, cherché avant System32), comme
# Microsoft l'autorise (déploiement local de l'application).
systeme = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
for dll in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll", "vcomp140.dll"):
    if (systeme / dll).exists() and not (CIBLE / dll).exists():
        shutil.copy2(systeme / dll, CIBLE / dll)
manquants = [d for d in ("msvcp140.dll", "msvcp140_1.dll") if not (CIBLE / d).exists()]
if manquants:
    raise SystemExit(f"runtime C++ introuvable sur la machine de construction : {manquants}")
print(f"Python {VERSION} embarqué prêt : {len(list(CIBLE.iterdir()))} fichiers dans {CIBLE}")
