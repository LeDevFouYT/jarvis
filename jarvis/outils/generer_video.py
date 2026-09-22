"""Outil generer_video (v3, consigne 8) : « fais-moi une vidéo de… » → Wan 2.2 (TI2V-5B) dans ComfyUI, 4 à 5 s,
jouée dans un panneau du HUD.

Réponse immédiate (« je la tourne, comptez une minute et demie »), puis le travail continue en tâche de fond :
l'avancement remonte au HUD par la prise websocket de ComfyUI (barre de progression holographique), et la vidéo
finie est rangée dans workspace/videos/ puis affichée.

Mémoire vidéo, en alternance stricte : cerveau déchargé → ComfyUI seul (le modèle pèse 10 Go) → modèles libérés →
cerveau rechargé. Rien ne reste sur la carte à la fin.
"""
import json
import logging
import random
import shutil
import threading
import time
import uuid
from pathlib import Path

import requests

from ..config import CONFIG, RACINE
from . import generer_image

NOM = "generer_video"
DESCRIPTION = ("Tourne une petite vidéo (4 à 5 secondes, sans son) à partir d'une description, avec le modèle Wan 2.2 "
               "sur cette machine, et la joue dans l'interface. Compte une minute et demie. Pour « fais-moi une vidéo "
               "de… », « filme… ». Ce n'est pas un montage : c'est une image animée, courte.")
PARAMETRES = {
    "prompt": {"type": "string", "description": "Ce qu'on doit voir, en anglais, au présent, avec le mouvement précis "
                                                "(« an iron man suit taking off, thrusters firing, camera tilting up »). "
                                                "Traduire le mouvement exactement : décoller = taking off / lifting off."},
    "secondes": {"type": "number", "description": "Durée voulue, 3 à 5 secondes (4 par défaut)"},
}
REQUIS = ["prompt"]
DIRECT = True

REGLAGES = CONFIG.get("video_ia", {})
URL = REGLAGES.get("url", CONFIG.get("comfyui", {}).get("url", "http://127.0.0.1:8188"))
MODELE = REGLAGES.get("modele", "wan2.2_ti2v_5B_fp16.safetensors")
ENCODEUR = REGLAGES.get("encodeur", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
VAE = REGLAGES.get("vae", "wan2.2_vae.safetensors")
# Wan veut des dimensions multiples de 32 : en 704x400, l'image sortait verdâtre et pâteuse (vu le 20/09).
LARGEUR, HAUTEUR = int(REGLAGES.get("largeur", 832)), int(REGLAGES.get("hauteur", 480))
PAS = int(REGLAGES.get("pas", 20))   # 20 pas : l'image reste nette jusqu'au bout (12 bavaient)
SORTIE = RACINE / "workspace" / "videos"
COMFY_SORTIE = Path(REGLAGES.get("comfy_sortie", CONFIG.get("chemins", {}).get("comfyui", "F:/ComfyUI") + "/output"))
DELAI = int(REGLAGES.get("delai_s", 900))
# le négatif officiel de Wan (chinois + anglais) : ce qu'il faut éviter dans l'image
NEGATIF = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，"
           "残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，"
           "三条腿，背景人很多，倒着走, text, watermark, logo, low quality, blurry")

# ce qu'on ajoute à la demande : Wan rend mieux quand on lui décrit aussi l'image et le mouvement
FINITION = ", cinematic lighting, slow camera movement, realistic, film look, high detail, sharp focus"
PAR_IMAGE = bool(REGLAGES.get("par_image", True))    # dessiner d'abord, animer ensuite : la qualité n'a rien à voir

MESURES = RACINE / "workspace" / "mesures" / "videos.json"

sur_evenement = lambda e: None
_verrou = threading.Lock()
journal = logging.getLogger("generer_video")


def _noter(chrono: dict, prompt: str):
    try:
        MESURES.parent.mkdir(parents=True, exist_ok=True)
        liste = json.loads(MESURES.read_text(encoding="utf-8")) if MESURES.exists() else []
        liste.append({"quand": time.strftime("%Y-%m-%d %H:%M"), "prompt": prompt[:80], **chrono})
        MESURES.write_text(json.dumps(liste[-30:], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def attente_probable() -> float:
    """Ce que Jarvis annonce : la médiane de ses dernières vidéos, pas une promesse en l'air."""
    try:
        totaux = sorted(m["total"] for m in json.loads(MESURES.read_text(encoding="utf-8")) if m.get("total"))
        if totaux:
            return totaux[len(totaux) // 2]
    except (OSError, ValueError, KeyError):
        pass
    return 150.0


def phrase_attente(secondes: float) -> str:
    if secondes < 105:
        return "Comptez une minute et demie."
    if secondes < 150:
        return "Comptez deux minutes."
    if secondes < 210:
        return "Comptez deux bonnes minutes."
    if secondes < 280:
        return "Comptez trois minutes : le modèle doit d'abord être lu sur le disque."
    return f"Comptez environ {round(secondes / 60)} minutes."


def graphe(prompt: str, secondes: float, graine: int, image: str = "") -> dict:
    """Le gabarit officiel « Wan 2.2 5B » de ComfyUI. Avec `image`, c'est une image qu'on anime (bien meilleur) ;
    sans elle, Wan invente tout à partir du texte, et ça part souvent n'importe où (constaté le 20/09)."""
    longueur = ((int(secondes * 24)) // 4) * 4 + 1              # Wan : 4k+1 images, à 24 i/s
    graphe_complet = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODELE, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": ENCODEUR, "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image or "aucune.png"}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt + FINITION}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEGATIF}},
        "8": {"class_type": "Wan22ImageToVideoLatent",
              "inputs": dict({"vae": ["3", 0], "width": LARGEUR, "height": HAUTEUR, "length": longueur, "batch_size": 1},
                             **({"start_image": ["4", 0]} if image else {}))},
        "9": {"class_type": "KSampler", "inputs": {"model": ["5", 0], "positive": ["6", 0], "negative": ["7", 0],
                                                   "latent_image": ["8", 0], "seed": graine, "steps": PAS, "cfg": 5.0,
                                                   "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": 24}},
        "12": {"class_type": "SaveVideo", "inputs": {"video": ["11", 0], "filename_prefix": "jarvis_video",
                                                     "format": "mp4", "codec": "h264"}},
    }
    if not image:
        graphe_complet.pop("4")
    return graphe_complet


def _suivre(client: str, prompt_id: str, surAvance, delai: float) -> None:
    """Écoute la prise websocket de ComfyUI et rapporte l'avancement (pas de rendu, étape en cours)."""
    import websockets.sync.client as ws
    adresse = URL.replace("http://", "ws://").replace("https://", "wss://") + f"/ws?clientId={client}"
    fin = time.time() + delai
    with ws.connect(adresse, open_timeout=15) as prise:
        while time.time() < fin:
            try:
                message = prise.recv(timeout=max(1.0, fin - time.time()))
            except TimeoutError:
                return
            if not isinstance(message, str):
                continue                                        # les aperçus d'image : on les ignore
            m = json.loads(message)
            d = m.get("data", {})
            if m.get("type") == "progress" and d.get("max"):
                surAvance(d["value"] / d["max"] * 100, "rendu")
            elif m.get("type") == "executing" and d.get("node") is None and d.get("prompt_id") == prompt_id:
                surAvance(100, "fini")
                return
            elif m.get("type") == "executing" and d.get("node"):
                surAvance(None, {"2": "lecture du texte", "9": "rendu", "10": "images", "11": "assemblage",
                                 "12": "enregistrement"}.get(str(d["node"]), "préparation"))


def _deposer(image: Path) -> str:
    """Met l'image dans l'entrée de ComfyUI (par son API : il peut tourner ailleurs)."""
    with open(image, "rb") as f:
        r = requests.post(f"{URL}/upload/image", files={"image": (image.name, f, "image/png")},
                          data={"overwrite": "true"}, timeout=60)
    r.raise_for_status()
    d = r.json()
    return (d.get("subfolder") + "/" if d.get("subfolder") else "") + d["name"]


def _recuperer(prompt_id: str) -> Path:
    """La vidéo produite par ComfyUI, copiée dans workspace/videos/."""
    h = requests.get(f"{URL}/history/{prompt_id}", timeout=20).json().get(prompt_id, {})
    for sortie in h.get("outputs", {}).values():
        # SaveVideo range le mp4 sous « images » (avec animated: [true]), pas sous « videos » (vu le 20/09)
        fichiers = [v for v in (sortie.get("videos") or []) + (sortie.get("gifs") or []) + (sortie.get("images") or [])
                    if str(v.get("filename", "")).lower().endswith((".mp4", ".webm", ".webp", ".gif"))]
        for v in fichiers:
            source = COMFY_SORTIE / (v.get("subfolder") or "") / v["filename"]
            SORTIE.mkdir(parents=True, exist_ok=True)
            cible = SORTIE / f"video_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
            if source.exists():
                shutil.copy2(source, cible)
            else:                                               # ComfyUI ailleurs : on passe par son API
                r = requests.get(f"{URL}/view", params={"filename": v["filename"], "subfolder": v.get("subfolder", ""),
                                                        "type": v.get("type", "output")}, timeout=120)
                r.raise_for_status()
                cible.write_bytes(r.content)
            return cible
    raise RuntimeError("ComfyUI n'a produit aucune vidéo")


def executer(prompt: str, secondes: float = 4.0) -> str:
    from .. import carte, cerveau
    from ..cerveau import CERVEAU
    from . import source_courante
    prompt = (prompt or "").strip()
    if not prompt:
        return "Que dois-je filmer, monsieur ?"
    if cerveau.MODE == "cloud":
        return "Tourner une vidéo demande la carte graphique de cette machine : impossible en mode cloud."
    if not generer_image.comfyui_present():
        return "ComfyUI n'est pas lancé. Demandez-moi d'ouvrir ComfyUI, puis réessayez."
    if not _verrou.acquire(blocking=False):
        return "Je tourne déjà une vidéo, monsieur."
    secondes = max(3.0, min(5.0, float(secondes or 4)))
    demande = source_courante()
    debut = time.time()
    client = uuid.uuid4().hex

    def travail():
        chrono = {}
        try:
            sur_evenement({"type": "video_debut", "t": time.time(), "prompt": prompt, "secondes": secondes,
                           "demande": demande})
            t = time.time()
            carte.occuper("vidéo")                              # un seul gros modèle à la fois sur la carte
            CERVEAU.decharger()                                  # la carte pour Wan seul (10 Go de poids)
            generer_image.liberer_avant()
            chrono["dechargement_cerveau"] = round(time.time() - t, 2)
            # d'abord une vraie image (20 s) : Wan anime bien mieux une image qu'un texte seul
            image_comfy = ""
            if PAR_IMAGE:
                try:
                    sur_evenement({"type": "video_avance", "t": time.time(), "pourcent": None, "etape": "premier plan"})
                    dessin = generer_image.dessiner(prompt + FINITION, "paysage", delai=300)
                    image_comfy = _deposer(dessin)
                    chrono["image"] = round(time.time() - t, 1)
                except Exception as e:                            # pas d'image : Wan se débrouillera avec le texte
                    journal.warning("vidéo : pas d'image de départ (%s)", e)
            t = time.time()
            r = requests.post(f"{URL}/prompt", json={"prompt": graphe(prompt, secondes, random.randint(1, 2 ** 31),
                                                                     image_comfy),
                                                     "client_id": client}, timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI a refusé le graphe Wan ({r.status_code}) : {r.text[:200]}")
            prompt_id = r.json()["prompt_id"]
            dernier = [0.0]

            def avance(pourcent, etape):
                if pourcent is not None:
                    if pourcent - dernier[0] < 2 and pourcent < 100:
                        return
                    dernier[0] = pourcent
                sur_evenement({"type": "video_avance", "t": time.time(), "pourcent": pourcent, "etape": etape,
                               "secondes_ecoulees": round(time.time() - debut, 1)})

            premier = [0.0]                                      # quand le premier pas de rendu arrive : modèle chargé

            def avance_mesuree(pourcent, etape):
                if pourcent is not None and not premier[0]:
                    premier[0] = time.time()
                    chrono["chargement_modele"] = round(premier[0] - t, 1)
                avance(pourcent, etape)

            _suivre(client, prompt_id, avance_mesuree, DELAI)
            chemin = _recuperer(prompt_id)
            chrono["rendu"] = round(time.time() - (premier[0] or t), 1)
            chrono["comfyui"] = round(time.time() - t, 2)
            chrono["total"] = round(time.time() - debut, 2)
            _noter(chrono, prompt)
            journal.info("vidéo %s en %.0f s (chargement %s s, rendu %s s)", chemin.name, chrono["total"],
                         chrono.get("chargement_modele"), chrono.get("rendu"))
            sur_evenement({"type": "video_prete", "t": time.time(), "prompt": prompt, "chemin": str(chemin),
                           "url": f"/workspace/videos/{chemin.name}", "duree": round(secondes, 1),
                           "chrono": dict(chrono), "demande": demande})
        except Exception as e:
            journal.exception("vidéo")
            sur_evenement({"type": "video_ia_erreur", "t": time.time(), "message": f"{type(e).__name__} : {e}",
                           "demande": demande})
        finally:
            try:
                generer_image.liberer_avant()                    # Wan rend la carte
                carte.liberer("vidéo")                           # et le cerveau a de nouveau le droit d'y revenir
                t = time.time()
                CERVEAU.charger()
                chrono["rechargement_cerveau"] = round(time.time() - t, 2)
            except Exception:
                journal.exception("rechargement du cerveau après la vidéo")
            finally:
                sur_evenement({"type": "video_ia_fin", "t": time.time(), "chrono": dict(chrono)})
                _verrou.release()

    threading.Thread(target=travail, daemon=True, name="video-ia").start()
    return "Je la tourne, monsieur. " + phrase_attente(attente_probable())
