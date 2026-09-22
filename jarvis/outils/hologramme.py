"""Outil hologramme (v3, consigne 4) : « montre-moi un dragon » → une image sur fond neutre (ComfyUI), puis un
maillage 3D (Hunyuan3D-2, D:/ia3d/gen3d.py sur le python de ComfyUI), affiché en hologramme dans le HUD.

Mémoire vidéo, en alternance stricte (une seule chose à la fois sur la carte) : cerveau déchargé → ComfyUI dessine →
modèles ComfyUI libérés → Hunyuan3D dans son propre processus, qui s'arrête à la fin → cerveau rechargé.

Cache : un objet déjà sculpté est réaffiché tout de suite (workspace/hologrammes/<objet>.glb), sans rien recalculer.
Le chrono complet (dessin, sculpture, rechargement du cerveau) part dans l'événement `hologramme` pour le HUD."""
import json
import logging
import os
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

from ..config import CONFIG, RACINE
from . import generer_image

NOM = "hologramme"
DESCRIPTION = ("Montre un objet en hologramme 3D dans l'interface (« montre-moi un dragon », « affiche-moi une épée »). "
               "L'objet est dessiné puis sculpté en 3D sur cette machine. Compte deux à trois minutes la première fois, "
               "immédiat si l'objet a déjà été montré. À n'utiliser que pour un objet à voir en volume, pas pour des "
               "fichiers, des photos ou des informations.")
PARAMETRES = {
    "objet": {"type": "string", "description": "L'objet à montrer, en français, deux ou trois mots au plus (« un dragon », « une épée »)"},
    "prompt": {"type": "string", "description": "Description de l'objet en anglais pour le dessin (sans décor ni fond)"},
}
REQUIS = ["objet"]
DIRECT = True                      # la phrase est dite telle quelle ; le reste se fait en tâche de fond

REGLAGES = CONFIG.get("hologramme", {})
DOSSIER = RACINE / "workspace" / "hologrammes"
IA3D = Path(REGLAGES.get("ia3d", "D:/ia3d"))
PYTHON_3D = Path(REGLAGES.get("python", CONFIG.get("chemins", {}).get("comfyui", "F:/ComfyUI") + "/venv/Scripts/python.exe"))
FACES = int(REGLAGES.get("faces", 30000))          # 30 000 : assez fin pour l'hologramme, léger pour le HUD
OCTREE = int(REGLAGES.get("octree", 192))          # 192 : sculpture rapide (256 = plus fin, plus lent)
DELAI_3D = int(REGLAGES.get("delai_s", 900))
# Les poids du sculpteur : 3 minutes de chargement depuis le disque dur (mesuré le 20/09), 20 s depuis un SSD.
# Seule la partie « forme » sert ici (4,6 Go) ; la texture (8,3 Go) reste sur l'autre disque.
MODELES_3D = Path(REGLAGES.get("modeles", "F:/ia3d-rapide"))
sur_evenement = lambda e: None
_verrou = threading.Lock()
journal = logging.getLogger("hologramme")

_PROMPT = ("{sujet}, single object, centered, whole object visible, plain neutral light grey background, "
           "studio product photograph, soft even lighting, no shadow, no text, sharp focus, high detail")


def nom_fichier(objet: str) -> str:
    """« une Épée de chevalier ! » → « epee-de-chevalier » (le nom du fichier en cache)."""
    t = unicodedata.normalize("NFD", objet.lower().replace("'", " "))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"^(?:un|une|des|le|la|les|l)\s+", "", t.strip())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60] or "objet"


def en_cache(objet: str) -> Path | None:
    chemin = DOSSIER / f"{nom_fichier(objet)}.glb"
    return chemin if chemin.exists() else None


def outils_3d_presents() -> tuple[bool, str]:
    if not (IA3D / "gen3d.py").exists():
        return False, f"le sculpteur 3D est introuvable ({IA3D}/gen3d.py)"
    if not PYTHON_3D.exists():
        return False, f"le Python de ComfyUI est introuvable ({PYTHON_3D})"
    return True, ""


def _sculpter(image: Path, sortie: Path, chrono: dict):
    """Hunyuan3D dans son propre processus : il prend la carte, puis la rend entièrement en s'arrêtant."""
    t = time.time()
    travail = DOSSIER / "travail"
    travail.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if (MODELES_3D / "tencent").exists():
        env["HY3DGEN_MODELS"] = str(MODELES_3D)
    r = subprocess.run([str(PYTHON_3D), str(IA3D / "gen3d.py"), str(image), "--sortie", str(travail),
                        "--faces", str(FACES), "--octree", str(OCTREE)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=DELAI_3D,
                       cwd=str(IA3D), env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for ligne in (r.stdout or "").splitlines():                # gen3d.py dit ce qu'il a passé à charger et à sculpter
        m = re.search(r"mod.le charg. en (\d+) s", ligne)
        if m:
            chrono["chargement_modele_3d"] = int(m.group(1))
        m = re.search(r"(\d+) faces, (\d+) s", ligne)
        if m:
            chrono["faces"], chrono["sculpture_seule"] = int(m.group(1)), int(m.group(2))
    produit = travail / (image.stem + ".glb")
    if not produit.exists():
        detail = (r.stderr or r.stdout or "").strip().splitlines()
        raise RuntimeError("la sculpture 3D a échoué : " + (detail[-1][:200] if detail else "aucun maillage produit"))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_bytes(produit.read_bytes())
    produit.unlink(missing_ok=True)
    (travail / (image.stem + "_detoure.png")).unlink(missing_ok=True)
    chrono["sculpture"] = round(time.time() - t, 2)
    chrono["taille_mo"] = round(sortie.stat().st_size / 1e6, 2)


MESURES = RACINE / "workspace" / "mesures" / "hologrammes.json"


def _noter_mesure(objet: str, chrono: dict):
    """Le chrono complet de chaque sculpture, gardé pour l'écran des tests et la doc."""
    try:
        MESURES.parent.mkdir(parents=True, exist_ok=True)
        liste = json.loads(MESURES.read_text(encoding="utf-8")) if MESURES.exists() else []
        liste.append({"objet": objet, "quand": time.strftime("%Y-%m-%d %H:%M"), **chrono})
        MESURES.write_text(json.dumps(liste[-50:], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _montrer(chemin: Path, objet: str, chrono: dict, depuis_cache: bool, demande: str = ""):
    sur_evenement({"type": "hologramme", "t": time.time(), "objet": objet, "fichier": chemin.name,
                   "url": f"/workspace/hologrammes/{chemin.name}", "cache": depuis_cache,
                   "chrono": dict(chrono), "demande": demande})


def executer(objet: str, prompt: str = "") -> str:
    from .. import carte, cerveau
    from ..cerveau import CERVEAU
    from . import source_courante
    objet = (objet or "").strip()
    if not objet:
        return "Quel objet dois-je afficher, monsieur ?"
    debut = time.time()
    chemin = DOSSIER / f"{nom_fichier(objet)}.glb"
    demande = source_courante()
    if chemin.exists():
        _montrer(chemin, objet, {"total": round(time.time() - debut, 2), "cache": True}, True, demande)
        return f"Voici {objet}, monsieur."
    if cerveau.MODE == "cloud":
        return "La sculpture 3D demande la carte graphique de cette machine : elle n'est pas disponible en mode cloud."
    ok, raison = outils_3d_presents()
    if not ok:
        return f"Je ne peux pas sculpter d'hologramme : {raison}."
    if not generer_image.comfyui_present():
        return "ComfyUI n'est pas lancé. Demandez-moi d'ouvrir ComfyUI, puis réessayez."
    if not _verrou.acquire(blocking=False):
        return "Je sculpte déjà un hologramme, monsieur."

    def travail():
        chrono = {}
        try:
            sur_evenement({"type": "hologramme_etape", "t": time.time(), "objet": objet, "etape": "dessin"})
            t = time.time()
            carte.occuper("hologramme")                              # un seul gros modèle à la fois sur la carte
            CERVEAU.decharger()                       # la carte pour ComfyUI seul
            generer_image.liberer_avant()
            chrono["dechargement_cerveau"] = round(time.time() - t, 2)
            t = time.time()
            image = generer_image.dessiner(_PROMPT.format(sujet=prompt or objet), "carre", delai=600)
            chrono["dessin"] = round(time.time() - t, 2)
            sur_evenement({"type": "hologramme_etape", "t": time.time(), "objet": objet, "etape": "sculpture"})
            generer_image.liberer_avant()             # ComfyUI rend la carte à Hunyuan3D
            time.sleep(1)
            _sculpter(image, chemin, chrono)
            chrono["total"] = round(time.time() - debut, 2)
            _noter_mesure(objet, chrono)
            _montrer(chemin, objet, chrono, False, demande)
        except Exception as e:
            journal.exception("hologramme")
            sur_evenement({"type": "hologramme_erreur", "t": time.time(), "objet": objet,
                           "message": f"{type(e).__name__} : {e}", "demande": demande})
        finally:
            try:
                carte.liberer("hologramme")                         # la carte est rendue : le cerveau peut revenir
                t = time.time()
                CERVEAU.charger()
                chrono["rechargement_cerveau"] = round(time.time() - t, 2)
            except Exception:
                journal.exception("rechargement du cerveau après l'hologramme")
            finally:
                chrono["total_cycle"] = round(time.time() - debut, 2)
                sur_evenement({"type": "hologramme_fin", "t": time.time(), "objet": objet, "chrono": dict(chrono)})
                _verrou.release()

    threading.Thread(target=travail, daemon=True, name="hologramme").start()
    return (f"Je prépare l'hologramme, monsieur. Comptez deux à trois minutes : {objet} sera d'abord dessiné, "
            "puis sculpté en volume.")
