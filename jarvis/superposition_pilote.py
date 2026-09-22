"""Le pilote de la superposition (v3, consigne 9) : allumer et éteindre la fenêtre qui flotte par-dessus Windows.

La fenêtre tourne dans son propre processus (jarvis/superposition.py) : si elle tombe, Jarvis continue de parler.
Ce module la lance, la surveille, et l'arrête. `config.json` → `superposition.actif` : au démarrage, s'il vaut vrai,
le serveur la rallume (elle reste donc un choix, jamais une surprise).
"""
import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import CONFIG, RACINE

PROCESSUS: subprocess.Popen | None = None
_verrou = threading.Lock()
journal = logging.getLogger("superposition")


def actif() -> bool:
    return PROCESSUS is not None and PROCESSUS.poll() is None


def _python() -> str:
    """Le Python qui a tkinter : celui de Jarvis s'il l'a, sinon celui du système (l'embarqué ne l'a pas)."""
    for chemin in (sys.executable, str(RACINE / ".venv" / "Scripts" / "pythonw.exe")):
        if not chemin:
            continue
        sans_fenetre = chemin.replace("python.exe", "pythonw.exe")
        essai = sans_fenetre if Path(sans_fenetre).exists() else chemin
        try:
            r = subprocess.run([essai.replace("pythonw.exe", "python.exe"), "-c", "import tkinter"],
                               capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode == 0:
                return essai
        except (OSError, subprocess.SubprocessError):
            continue
    return ""


def disponible() -> tuple[bool, str]:
    if not _python():
        return False, "ce Python n'a pas tkinter (la superposition a besoin d'une fenêtre)"
    return True, ""


def definir(marche: bool, port: int = 8765) -> tuple[bool, str]:
    """Allume ou éteint la superposition. Rend (réussi, explication)."""
    global PROCESSUS
    with _verrou:
        if not marche:
            if actif():
                PROCESSUS.terminate()
                try:
                    PROCESSUS.wait(5)
                except subprocess.TimeoutExpired:
                    PROCESSUS.kill()
            PROCESSUS = None
            _memoriser(False)
            return True, "éteinte"
        if actif():
            return True, "déjà là"
        ok, raison = disponible()
        if not ok:
            return False, raison
        PROCESSUS = subprocess.Popen([_python(), "-m", "jarvis.superposition", "--serveur", f"http://127.0.0.1:{port}"],
                                     cwd=str(RACINE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        time.sleep(1.2)
        if not actif():
            return False, "la fenêtre s'est fermée aussitôt"
        _memoriser(True)
        return True, "allumée"


def _memoriser(marche: bool):
    try:
        CONFIG.setdefault("superposition", {})["actif"] = marche
        chemin = RACINE / "config.json"
        fichier = json.loads(chemin.read_text(encoding="utf-8"))
        fichier.setdefault("superposition", {})["actif"] = marche
        chemin.write_text(json.dumps(fichier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError):
        journal.warning("impossible de mémoriser l'état de la superposition")


def au_demarrage(port: int = 8765):
    """Rallumée au lancement seulement si elle était allumée (jamais une surprise)."""
    if CONFIG.get("superposition", {}).get("actif"):
        definir(True, port)
