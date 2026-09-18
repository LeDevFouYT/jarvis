"""Mise à jour automatique : à chaque lancement (lancer.bat -> `python -m jarvis verifier`), Jarvis compare sa version à
la dernière release publique sur GitHub (version.json), télécharge le paquet `mise_a_jour.zip`, vérifie son empreinte
SHA-256, et remplace ses fichiers de programme. Jamais touché : config.json, .secrets, passerelle.json, modeles/,
workspace/, memoire/, cache/. Désactivable : config `mise_a_jour.auto = false`. Ignoré dans un dépôt git (développement)."""
import hashlib
import json
import os
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


def remplacer(racine_paquet: Path, dire=print):
    """Remplace les fichiers de programme par ceux du paquet ; les données du client jamais (PROTEGES).

    Audit du 19/09 : `jarvis/` était effacé puis recopié ; un antivirus qui bloque un fichier, un disque plein ou une
    fenêtre fermée au milieu laissait un Jarvis qui ne démarrait plus et ne pouvait même plus se mettre à jour. Et si
    pip échouait, la version était quand même notée « installée ». Désormais :
    - chaque dossier neuf est copié entièrement à côté (`jarvis.nouveau`) avant de toucher à l'ancien, puis échangé
      par deux renommages (quelques millisecondes) ; l'ancien est gardé dans la sauvegarde ;
    - un fichier identique n'est pas réécrit (lancer.bat qui tourne n'est pas remplacé sous ses pieds) ;
    - au moindre échec, pip compris, tout ce qui a été remplacé est remis en place et l'erreur remonte : la version
      locale ne change pas, la mise à jour sera retentée au prochain lancement."""
    import subprocess
    sauvegarde = DOSSIER / "sauvegarde"
    shutil.rmtree(sauvegarde, ignore_errors=True)
    sauvegarde.mkdir(parents=True)
    faits: list[tuple[Path, Path | None]] = []          # (cible remplacée, sa sauvegarde ou None si elle n'existait pas)
    try:
        for element in racine_paquet.iterdir():
            if element.name in PROTEGES or element.name == VERSION_FICHIER.name:
                continue
            cible = RACINE / element.name
            if element.is_dir():
                neuf = RACINE / (element.name + ".nouveau")
                shutil.rmtree(neuf, ignore_errors=True)
                shutil.copytree(element, neuf)
                ancien = sauvegarde / element.name if cible.exists() else None
                if ancien:
                    os.replace(cible, ancien)
                faits.append((cible, ancien))
                os.replace(neuf, cible)
            else:
                if cible.exists() and cible.read_bytes() == element.read_bytes():
                    continue
                ancien = sauvegarde / element.name if cible.exists() else None
                if ancien:
                    shutil.copy2(cible, ancien)
                faits.append((cible, ancien))
                temporaire = cible.with_name(cible.name + ".nouveau")
                shutil.copy2(element, temporaire)
                os.replace(temporaire, cible)
        if (racine_paquet / "requirements.txt").exists() and (RACINE / "python" / "python.exe").exists():
            dire("Dépendances : vérification (une minute si une bibliothèque change)…")
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(RACINE / "requirements.txt"),
                                "--no-warn-script-location", "--disable-pip-version-check"],
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                raise RuntimeError(f"pip a échoué (code {r.returncode})")
    except Exception:
        for cible, ancien in reversed(faits):
            try:
                if cible.is_dir():
                    shutil.rmtree(cible, ignore_errors=True)
                elif cible.exists():
                    cible.unlink()
                if ancien and ancien.exists():
                    os.replace(ancien, cible)
            except OSError:
                pass
        for element in racine_paquet.iterdir():
            shutil.rmtree(RACINE / (element.name + ".nouveau"), ignore_errors=True)
        dire("Mise à jour interrompue : l'ancienne version est remise en place.")
        raise
    shutil.rmtree(sauvegarde, ignore_errors=True)


def installe_depuis_les_sources() -> bool:
    """Une copie du code source (archive GitHub + installer.bat) : ses .py ne sont jamais remplacés par des .pyc
    (audit du 19/09 : la première mise à jour effaçait les modifications du développeur)."""
    return (RACINE / "jarvis" / "__main__.py").exists() and not (RACINE / "python" / "python.exe").exists()


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
    remplacer(racine_paquet, dire)
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
    if installe_depuis_les_sources():
        m = verifier(5)
        if m and plus_recente(m.get("version", "0"), version_locale()):
            dire(f"La version {m['version']} est sortie. Installation depuis le code source : mettez-la à jour vous-même "
                 "(git pull, ou nouvelle archive), vos fichiers ne sont jamais écrasés.")
        return None
    m = verifier()
    if not m or not plus_recente(m.get("version", "0"), version_locale()):
        return None
    try:
        return m["version"] if installer(m, dire) else None
    except Exception as e:
        dire(f"Mise à jour impossible pour l'instant ({type(e).__name__}) : Jarvis démarre avec la version actuelle.")
        return None
