"""Préparation au lancement et installation.
  python -m jarvis verifier    Ollama tourne (sinon lancé), modèles présents (sinon téléchargés), Kokoro présent.
                               Appelé par lancer.bat avant le serveur. Code de sortie 1 si quelque chose manque.
  python -m jarvis installer   Détecte la VRAM et choisit les modèles dans config.json. Appelé par installer.bat."""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import requests

from .config import RACINE, SECRETS

CONFIG_PATH = RACINE / "config.json"
KOKORO = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


def _config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _dire(texte: str):
    print(f"[Jarvis] {texte}", flush=True)


# --- Ollama ---------------------------------------------------------------------------------
def ollama_repond(url: str) -> bool:
    try:
        requests.get(f"{url}/api/tags", timeout=3)
        return True
    except requests.RequestException:
        return False


def _exe_ollama() -> str | None:
    """La commande ollama : dans le PATH, ou à l'endroit où son installateur la met (le PATH de ce processus ne voit
    pas une installation faite à l'instant)."""
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return shutil.which("ollama") or (str(local) if local.exists() else None)


def installer_ollama() -> bool:
    """L'installateur officiel d'Ollama, avec sa propre fenêtre de progression, sans droits administrateur."""
    setup = RACINE / "workspace" / "OllamaSetup.exe"
    setup.parent.mkdir(parents=True, exist_ok=True)
    _dire("Ollama, qui fait tourner le cerveau sur la carte graphique, n'est pas installé : téléchargement depuis ollama.com.")
    try:
        urllib.request.urlretrieve("https://ollama.com/download/OllamaSetup.exe", setup)
        _dire("Installation d'Ollama (sa fenêtre de progression s'affiche, une minute).")
        subprocess.run([str(setup), "/SILENT", "/NORESTART"], timeout=900)
    except Exception as e:
        _dire(f"Installation d'Ollama impossible ({type(e).__name__}) : installez-le depuis ollama.com puis relancez.")
        return False
    finally:
        setup.unlink(missing_ok=True)
    return bool(_exe_ollama())


def demarrer_ollama(url: str, installer_si_absent: bool = False) -> bool:
    if ollama_repond(url):
        return True
    if not _exe_ollama() and not (installer_si_absent and installer_ollama()):
        _dire("Ollama n'est pas installé (commande « ollama » introuvable). Installez-le depuis ollama.com puis relancez.")
        return False
    if ollama_repond(url):                      # son installateur le démarre tout seul
        return True
    _dire("Ollama ne tourne pas : je le démarre.")
    subprocess.Popen([_exe_ollama(), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(30):
        time.sleep(1)
        if ollama_repond(url):
            return True
    _dire("Ollama ne répond pas après 30 secondes.")
    return False


def modeles_presents(url: str) -> set[str]:
    noms = set()
    for m in requests.get(f"{url}/api/tags", timeout=10).json().get("models", []):
        noms.add(m["name"])
        noms.add(m["name"].split(":")[0])
    return noms


def telecharger_modele(url: str, nom: str) -> bool:
    _dire(f"Le modèle {nom} manque : téléchargement par Ollama (plusieurs Go, une seule fois).")
    try:
        with requests.post(f"{url}/api/pull", json={"model": nom, "stream": True}, stream=True, timeout=None) as r:
            dernier = ""
            for ligne in r.iter_lines():
                if not ligne:
                    continue
                j = json.loads(ligne)
                if "error" in j:
                    _dire(f"Ollama a échoué pour {nom} : {j['error']}")
                    return False
                total, fait = j.get("total"), j.get("completed")
                statut = j.get("status", "")
                if total and fait:
                    statut = f"{statut} {100 * fait / total:5.1f} %"
                if statut != dernier:
                    print(f"\r    {nom} : {statut:<60}", end="", flush=True)
                    dernier = statut
        print()
        return True
    except requests.RequestException as e:
        _dire(f"Téléchargement de {nom} impossible : {e}")
        return False


# --- Kokoro ----------------------------------------------------------------------------------
def telecharger_kokoro() -> bool:
    dossier = RACINE / "modeles" / "kokoro"
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, url in KOKORO.items():
        cible = dossier / nom
        if cible.exists() and cible.stat().st_size > 1_000_000:
            continue
        _dire(f"La voix Kokoro manque : téléchargement de {nom} (une seule fois).")
        try:
            def progres(blocs, taille, total):
                if total > 0:
                    print(f"\r    {nom} : {100 * min(blocs * taille, total) / total:5.1f} %", end="", flush=True)
            urllib.request.urlretrieve(url, cible, progres)
            print()
        except Exception as e:
            _dire(f"Téléchargement de {nom} impossible : {e}")
            return False
    return True


# --- vérification avant lancement -------------------------------------------------------------
def _reparer_cloud_force(c: dict) -> dict:
    """Jusqu'à la v1.0.20, l'installateur comparait la mémoire vidéo au Mo près : une carte « 8 Go » (8 188 Mo annoncés,
    RTX 4070 portable) était mise en mode cloud payant, jeton à acheter. La mise à jour remplace le code mais jamais
    config.json : ici, un mode cloud sans aucun jeton, sur une machine qui peut tourner en local, repasse en local."""
    cloud = c.get("cerveau", {}).get("cloud", {})
    if c.get("cerveau", {}).get("mode") != "cloud" or cloud.get("jeton") or SECRETS.get("CLOUD_TOKEN"):
        return c
    try:
        from . import machine
        examen = machine.examiner(str(RACINE))
    except Exception:
        return c
    if examen["verdict"] == "cloud":
        return c
    machine.appliquer(c, examen)
    CONFIG_PATH.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _dire(f"{examen['gpu']['nom']} : cette carte fait tourner Jarvis en local, gratuitement. Le mode cloud (jeton payant) "
          f"avait été choisi par erreur à l'installation ; c'est corrigé (cerveau {c['cerveau']['modele']}).")
    return c


def verifier() -> int:
    # 0. la mise à jour automatique (release publique GitHub), avant tout le reste
    try:
        from . import mise_a_jour
        v = mise_a_jour.au_lancement(_dire)
        if v:
            _dire(f"Jarvis est passé en version {v}.")
            if not os.environ.get("JARVIS_APRES_MAJ"):
                # ce processus a encore l'ancien code en mémoire : la suite de la vérification (réparations comprises)
                # tourne dans un processus neuf, avec le code qui vient d'arriver
                return subprocess.call([sys.executable, "-m", "jarvis", "verifier"], cwd=str(RACINE),
                                       env={**os.environ, "JARVIS_APRES_MAJ": "1"})
    except Exception as e:
        _dire(f"Vérification des mises à jour impossible ({type(e).__name__}).")
    c = _reparer_cloud_force(_config())
    if c["cerveau"].get("mode", "local") == "cloud":
        _dire(f"Cerveau distant : {c['cerveau']['cloud'].get('url')} (le compteur de sorties Internet le montrera).")
        url = c["ollama"]["url"]
        if not demarrer_ollama(url):
            _dire("Ollama local absent : la vision restera indisponible.")
        else:
            manquants = [c["vision"]["modele"]] if c["vision"]["modele"] not in modeles_presents(url) else []
            for m in manquants:
                telecharger_modele(url, m)
    else:
        url = c["ollama"]["url"]
        if not demarrer_ollama(url, installer_si_absent=True):
            return 1
        presents = modeles_presents(url)
        for nom in (c["cerveau"]["modele"], c["vision"]["modele"]):
            if nom not in presents and not telecharger_modele(url, nom):
                return 1
    # la mémoire longue : son petit modèle de plongements (610 Mo, sur le processeur). Sans lui, repli sur les mots.
    mem = c.get("memoire", {})
    if mem.get("actif", True) and ollama_repond(c["ollama"]["url"]):
        modele_memoire = mem.get("modele_plongements", "qwen3-embedding:0.6b")
        if modele_memoire not in modeles_presents(c["ollama"]["url"]):
            telecharger_modele(c["ollama"]["url"], modele_memoire)
    if not telecharger_kokoro():
        return 1
    _dire(f"Prêt : cerveau {c['cerveau']['modele']} ({c['cerveau'].get('mode', 'local')}), "
          f"vision {c['vision']['modele']}, voix {c['voix']['moteur']}.")
    return 0


# --- installation : VRAM et choix des modèles ---------------------------------------------------
def vram_mo() -> int | None:
    try:
        sortie = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        return max(int(x) for x in sortie) if sortie else None
    except Exception:
        return None


def installer() -> int:
    """Même examen que Jarvis-Installateur.exe (jarvis/machine.py), en ligne de commande."""
    from . import machine
    c = _config()
    examen = machine.examiner(str(RACINE))
    for ligne in machine.resume(examen).splitlines():
        _dire(ligne)
    if examen["verdict"] == "cloud":
        _dire("Mode cloud : mettez l'URL de la passerelle dans config.json (cerveau.cloud.url) et votre jeton "
              "dans .secrets (CLOUD_TOKEN=). L'écoute et la voix restent locales.")
    machine.appliquer(c, examen)
    CONFIG_PATH.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _dire(f"config.json réglé : cerveau {c['cerveau']['modele']} en mode {c['cerveau']['mode']}, vision {c['vision']['modele']}.")
    return 0


if __name__ == "__main__":
    sys.exit(verifier() if (len(sys.argv) < 2 or sys.argv[1] == "verifier") else installer())
