"""Outil generer_image : envoie un prompt à ComfyUI (API locale), attend l'image, l'enregistre dans
workspace/images/ et diffuse son chemin sur /events pour le HUD.
VRAM : cerveau déchargé avant, modèles ComfyUI libérés après (/free), cerveau rechargé après.
Si la génération dépasse le délai, l'outil rend la main et le reste se termine en tâche de fond."""
import json
import logging
import random
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests

from ..config import CONFIG, RACINE

NOM = "generer_image"
DESCRIPTION = ("Génère une image avec ComfyUI à partir d'une description en anglais (le prompt). "
               "L'image est enregistrée et affichée dans l'interface. Compte une à deux minutes.")
PARAMETRES = {
    "prompt": {"type": "string", "description": "Description de l'image, en anglais, détaillée"},
    "format": {"type": "string", "enum": ["carre", "portrait", "paysage"], "description": "Format de l'image"},
}
REQUIS = ["prompt"]
DIRECT = True   # la phrase renvoyée est dite telle quelle ; le cerveau n'est rechargé qu'après l'image

REGLAGES = CONFIG.get("comfyui", {})
URL = REGLAGES.get("url", "http://127.0.0.1:8188")
WORKFLOW = Path(__file__).parent / "workflows" / REGLAGES.get("workflow", "zimage.json")
IMAGES = RACINE / "workspace" / "images"
FORMATS = {"carre": (1024, 1024), "portrait": (832, 1216), "paysage": (1216, 832)}
DELAI_OUTIL = 50          # secondes avant de rendre la main (la limite commune est 60)
sur_evenement = lambda e: None
_verrou = threading.Lock()
journal = logging.getLogger("generer_image")


def comfyui_present() -> bool:
    try:
        requests.get(f"{URL}/system_stats", timeout=2)
        return True
    except requests.RequestException:
        return False


def _preparer(prompt: str, format_: str) -> dict:
    w = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    for noeud in w.values():
        titre = noeud.get("_meta", {}).get("title", "").upper()
        if noeud["class_type"] == "CLIPTextEncode" and "POSITIF" in titre:
            noeud["inputs"]["text"] = prompt
        if noeud["class_type"] == "KSampler":
            noeud["inputs"]["seed"] = random.randint(1, 2 ** 31)
        if noeud["class_type"] == "EmptyLatentImage":
            noeud["inputs"]["width"], noeud["inputs"]["height"] = FORMATS.get(format_, FORMATS["carre"])
    return w


def _attendre(prompt_id: str, delai: float) -> dict | None:
    fin = time.time() + delai
    while time.time() < fin:
        h = requests.get(f"{URL}/history/{prompt_id}", timeout=10).json()
        if prompt_id in h:
            statut = h[prompt_id].get("status", {})
            if statut.get("status_str") == "error":
                raise RuntimeError("ComfyUI a signalé une erreur dans le workflow")
            if h[prompt_id].get("outputs"):
                return h[prompt_id]["outputs"]
        time.sleep(1)
    return None


def _recuperer(sorties: dict) -> Path:
    for sortie in sorties.values():
        for im in sortie.get("images", []):
            r = requests.get(f"{URL}/view", params={"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                                    "type": im.get("type", "output")}, timeout=30)
            r.raise_for_status()
            IMAGES.mkdir(parents=True, exist_ok=True)
            chemin = IMAGES / f"image_{datetime.now():%Y%m%d_%H%M%S}.png"
            chemin.write_bytes(r.content)
            return chemin
    raise RuntimeError("ComfyUI n'a produit aucune image")


def _liberer_et_recharger(chrono: dict, debut: float):
    from ..cerveau import CERVEAU
    try:
        requests.post(f"{URL}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
    except requests.RequestException:
        pass
    t = time.time()
    CERVEAU.charger()
    chrono["rechargement_cerveau"] = round(time.time() - t, 2)
    chrono["total_cycle"] = round(time.time() - debut, 2)


def liberer_avant():
    """ComfyUI garde en mémoire vidéo les modèles des autres applications qui s'en servent (mesuré le 16/09 : ~10 Go
    d'un autre workflow restés chargés). Sans ce vidage AVANT de dessiner, une miniature 1280×720 prenait 106 s puis
    la suivante ne finissait plus ; ComfyUI traite ce drapeau juste avant le prochain travail de sa file."""
    try:
        requests.post(f"{URL}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
    except requests.RequestException:
        pass


def _lancer_comfyui() -> bool:
    """Démarre ComfyUI (config comfyui.lanceur) s'il ne tourne pas, attend jusqu'à 90 s qu'il réponde."""
    if comfyui_present():
        return True
    lanceur = REGLAGES.get("lanceur", "")
    if not lanceur or not Path(lanceur).exists():
        return False
    import subprocess
    subprocess.Popen(["cmd", "/c", str(lanceur)], cwd=str(Path(lanceur).parent),
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        time.sleep(1)
        if comfyui_present():
            return True
    return False


def generer_pour_cloud(prompt: str, format_: str = "carre") -> tuple[bytes, float]:
    """Pour l'agent maison : dessine ici pour un client distant et renvoie (PNG, secondes de calcul).
    ComfyUI lancé au besoin, cerveau déchargé avant, modèles ComfyUI libérés après."""
    from ..cerveau import CERVEAU
    if not _lancer_comfyui():
        raise RuntimeError("ComfyUI indisponible sur la machine")
    if not _verrou.acquire(timeout=600):
        raise RuntimeError("une autre image est en cours")
    try:
        CERVEAU.decharger()
        liberer_avant()
        r = requests.post(f"{URL}/prompt", json={"prompt": _preparer(prompt, format_), "client_id": uuid.uuid4().hex}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI a refusé le workflow ({r.status_code})")
        prompt_id = r.json()["prompt_id"]
        t = time.time()
        sorties = _attendre(prompt_id, 600)
        if sorties is None:
            raise RuntimeError("ComfyUI n'a pas terminé en dix minutes")
        secondes = time.time() - t
        for sortie in sorties.values():
            for im in sortie.get("images", []):
                rep = requests.get(f"{URL}/view", params={"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                                          "type": im.get("type", "output")}, timeout=30)
                rep.raise_for_status()
                journal.info("image cloud en %.1f s", secondes)
                return rep.content, secondes
        raise RuntimeError("ComfyUI n'a produit aucune image")
    finally:
        try:
            requests.post(f"{URL}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
        except requests.RequestException:
            pass
        _verrou.release()


def _executer_cloud(prompt: str, format_: str) -> str:
    """Mode cloud du client : l'image est dessinée sur la machine de l'auteur via la passerelle, en fond."""
    from .. import cerveau
    base = cerveau.OLLAMA[:-len("/ollama")] if cerveau.OLLAMA.endswith("/ollama") else cerveau.OLLAMA

    def travail():
        import base64
        chrono = {}
        t = time.time()
        try:
            sur_evenement({"type": "image_debut", "t": time.time(), "prompt": prompt})
            r = requests.post(f"{base}/image", headers=cerveau.ENTETES, json={"prompt": prompt, "format": format_}, timeout=660)
            if r.status_code != 200:
                raison = {402: "crédit épuisé", 429: "plafond du jour atteint", 503: "cerveau distant hors ligne"}.get(r.status_code, f"erreur {r.status_code}")
                raise RuntimeError(raison)
            png = base64.b64decode(r.json()["png"])
            IMAGES.mkdir(parents=True, exist_ok=True)
            chemin = IMAGES / f"image_{datetime.now():%Y%m%d_%H%M%S}.png"
            chemin.write_bytes(png)
            chrono["generation"] = round(time.time() - t, 2)
            sur_evenement({"type": "image", "t": time.time(), "chemin": str(chemin), "url": f"/workspace/images/{chemin.name}",
                           "prompt": prompt, "duree": chrono["generation"]})
        except Exception as e:
            journal.exception("image cloud")
            sur_evenement({"type": "image_erreur", "t": time.time(), "message": f"{type(e).__name__} : {e}"})
        finally:
            chrono["total_cycle"] = round(time.time() - t, 2)
            sur_evenement({"type": "image_fin", "t": time.time(), "chrono": chrono})

    threading.Thread(target=travail, daemon=True, name="image-cloud").start()
    return "Je lance le dessin sur le cerveau distant. Comptez une à deux minutes : l'image s'affichera dans l'interface et je vous préviendrai."


def executer(prompt: str, format: str = "carre") -> str:
    from .. import cerveau
    from ..cerveau import CERVEAU
    if cerveau.MODE == "cloud":
        return _executer_cloud(prompt, format)
    if not comfyui_present():
        return "ComfyUI n'est pas lancé. Demandez-moi d'ouvrir ComfyUI, puis réessayez."
    if not _verrou.acquire(blocking=False):
        return "Une image est déjà en cours de génération, monsieur."
    debut = time.time()
    chrono = {}
    client = uuid.uuid4().hex
    try:
        sur_evenement({"type": "image_debut", "t": time.time(), "prompt": prompt})
        t0 = time.time()
        CERVEAU.decharger()
        liberer_avant()
        chrono["dechargement_cerveau"] = round(time.time() - t0, 2)
        r = requests.post(f"{URL}/prompt", json={"prompt": _preparer(prompt, format), "client_id": client}, timeout=30)
        if r.status_code != 200:
            detail = r.text[:200]
            try:
                detail = r.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(f"ComfyUI a refusé le workflow : {detail}")
        prompt_id = r.json()["prompt_id"]
    except Exception:
        _verrou.release()
        journal.exception("envoi du workflow")
        threading.Thread(target=_liberer_et_recharger, args=(chrono, debut), daemon=True).start()
        raise

    def terminer():
        t = time.time()
        try:
            sorties = _attendre(prompt_id, 600)
            if sorties is None:
                raise RuntimeError("ComfyUI n'a pas terminé en dix minutes")
            chemin = _recuperer(sorties)
            chrono["generation"] = round(time.time() - t, 2)
            journal.info("image %s en %.1f s", chemin.name, chrono["generation"])
            sur_evenement({"type": "image", "t": time.time(), "chemin": str(chemin),
                           "url": f"/workspace/images/{chemin.name}", "prompt": prompt,
                           "duree": chrono["generation"]})
        except Exception as e:
            journal.exception("génération")
            sur_evenement({"type": "image_erreur", "t": time.time(), "message": f"{type(e).__name__} : {e}"})
        finally:
            _liberer_et_recharger(chrono, debut)
            sur_evenement({"type": "image_fin", "t": time.time(), "chrono": dict(chrono)})
            _verrou.release()

    threading.Thread(target=terminer, daemon=True, name="image-fond").start()
    return ("Je lance le dessin, monsieur. Comptez une à deux minutes : l'image s'affichera dans l'interface "
            "et je vous préviendrai.")
