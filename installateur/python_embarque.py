"""Prépare installateur/python_embarque/ pour l'installateur Inno Setup : le Python officiel « embeddable » de python.org
(pas de téléchargement chez le client), son fichier ._pth ouvert aux paquets (import site) et au dossier de Jarvis
(..), et get-pip.py à côté.
    python installateur/python_embarque.py"""
import json
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
print(f"Python {VERSION} embarqué prêt : {len(list(CIBLE.iterdir()))} fichiers dans {CIBLE}")
