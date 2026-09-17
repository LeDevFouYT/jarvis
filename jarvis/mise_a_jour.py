"""Mise à jour automatique : à chaque lancement (lancer.bat -> `python -m jarvis verifier`), Jarvis compare sa version à
la dernière release publique sur GitHub (version.json), télécharge le paquet `mise_a_jour.zip`, vérifie son empreinte
SHA-256, et remplace ses fichiers de programme. Jamais touché : config.json, .secrets, passerelle.json, modeles/,
workspace/, memoire/, cache/. Désactivable : config `mise_a_jour.auto = false`. Ignoré dans un dépôt git (développement)."""
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

import requests

from .config import CONFIG, RACINE

MANIFESTE = CONFIG.get("mise_a_jour", {}).get("manifeste",
                                             "https://github.com/LeDevFouYT/jarvis/releases/latest/download/version.json")
VERSION_FICHIER = RACINE / "version.json"
DOSSIER = RACINE / "workspace" / "mise_a_jour"
PROTEGES = {"config.json", ".secrets", ".youtube_oauth.json", "passerelle.json", "passerelle.sqlite", "modeles", "workspace", "memoire", "cache",
            "python", ".venv", "outils_externes", "installation.log"}


def version_locale() -> str:
    try:
        return json.loads(VERSION_FICHIER.read_text(encoding="utf-8")).get("version", "0")
    except Exception:
        return "0"


def _cle(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).split("."))


def plus_recente(distante: str, locale: str) -> bool:
    return _cle(distante) > _cle(locale)


def verifier(delai: float = 10) -> dict | None:
    """Le manifeste distant, ou None s'il est injoignable."""
    try:
        r = requests.get(MANIFESTE, timeout=delai)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def installer(manifeste: dict, dire=print) -> bool:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    zip_local = DOSSIER / "mise_a_jour.zip"
    dire(f"Mise à jour {manifeste['version']} : téléchargement…")
    with requests.get(manifeste["zip"], stream=True, timeout=60) as r:
        r.raise_for_status()
        h = hashlib.sha256()
        with zip_local.open("wb") as f:
            for morceau in r.iter_content(1 << 20):
                f.write(morceau)
                h.update(morceau)
    if manifeste.get("sha256") and h.hexdigest() != manifeste["sha256"]:
        dire("Empreinte du paquet incorrecte : mise à jour refusée.")
        return False
    extrait = DOSSIER / "extrait"
    if extrait.exists():
        shutil.rmtree(extrait)
    with zipfile.ZipFile(zip_local) as z:
        z.extractall(extrait)
    racine_paquet = extrait / "charge" if (extrait / "charge").exists() else extrait
    # les fichiers de programme sont remplacés ; les données du client jamais
    for element in racine_paquet.iterdir():
        if element.name in PROTEGES:
            continue
        cible = RACINE / element.name
        if element.is_dir():
            if cible.exists():
                shutil.rmtree(cible)
            shutil.copytree(element, cible)
        else:
            shutil.copy2(element, cible)
    nouvelles_deps = (racine_paquet / "requirements.txt")
    if nouvelles_deps.exists() and (RACINE / "python" / "python.exe").exists():
        import subprocess
        dire("Dépendances : vérification…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(RACINE / "requirements.txt"),
                        "--no-warn-script-location"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    VERSION_FICHIER.write_text(json.dumps({"version": manifeste["version"], "installee": time.time(),
                                           "notes": manifeste.get("notes", "")}, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(extrait, ignore_errors=True)
    zip_local.unlink(missing_ok=True)
    dire(f"Mise à jour {manifeste['version']} installée.")
    return True


def au_lancement(dire=print) -> str | None:
    """Appelé par `python -m jarvis verifier`. Retourne la version installée s'il y a eu mise à jour."""
    if (RACINE / ".git").exists() or not CONFIG.get("mise_a_jour", {}).get("auto", True):
        return None
    m = verifier()
    if not m or not plus_recente(m.get("version", "0"), version_locale()):
        return None
    try:
        return m["version"] if installer(m, dire) else None
    except Exception as e:
        dire(f"Mise à jour impossible pour l'instant ({type(e).__name__}) : Jarvis démarre avec la version actuelle.")
        return None
