"""Outil webcam : une image prise par la webcam, décrite par le modèle de vision d'Ollama.

Même alternance de mémoire vidéo que voir_ecran : l'image est prise d'abord (une seconde), puis le cerveau est
déchargé, la vision chargée puis déchargée, le cerveau rechargé. Réponse directe : « je regarde » tout de suite, la
description est dite dès qu'elle arrive (événement `vision`, source webcam).

Vie privée : l'image reste en mémoire. Elle n'est jamais écrite sur le disque, sauf si la personne demande de la
garder (`enregistrer`) : elle va alors dans workspace/webcam/. Le HUD la reçoit en data: URL par la liaison locale.

Capture par DirectShow (PyAV, format dshow) sur le périphérique `webcam.peripherique` de config.json, ou le premier
périphérique vidéo trouvé. Essai sans webcam : JARVIS_WEBCAM_IMAGE=chemin d'une image (annoncée comme image d'essai)."""
import base64
import io
import logging
import os
import threading
import time
from datetime import datetime

from .. import vision
from ..config import CONFIG, RACINE

NOM = "webcam"
DESCRIPTION = ("Regarde par la webcam et décrit ce qu'elle voit : la personne, ce qu'elle tient ou montre, la pièce. "
               "À utiliser quand on dit « regarde-moi », « tu me vois ? », « qu'est-ce que je tiens ? », « regarde par la webcam ». "
               "L'image n'est pas enregistrée, sauf si la personne demande de la garder.")
PARAMETRES = {
    "question": {"type": "string", "description": "Ce qu'il faut regarder ou la question posée (facultatif)"},
    "enregistrer": {"type": "boolean", "description": "Vrai seulement si la personne demande de garder la photo"},
}
REQUIS = []
DIRECT = True

REGLAGES = CONFIG.setdefault("webcam", {})
DOSSIER = RACINE / "workspace" / "webcam"
sur_evenement = lambda e: None
journal = logging.getLogger("webcam")
_verrou = threading.Lock()


def peripheriques() -> list[str]:
    """Les périphériques vidéo DirectShow (PyAV les écrit dans son journal quand on demande la liste)."""
    import av
    lignes = []
    ancien = av.logging.get_level()
    av.logging.set_level(av.logging.INFO)
    try:
        with av.logging.Capture(local=False) as journal_av:
            try:
                av.open("dummy", format="dshow", options={"list_devices": "true"})
            except Exception:
                pass
        lignes = [message for _, nom, message in journal_av if nom == "dshow"]
    finally:
        av.logging.set_level(ancien)
    noms, dernier = [], None
    for ligne in lignes:
        ligne = ligne.strip()
        if ligne.startswith('"') and ligne.endswith('"'):
            dernier = ligne.strip('"')
        elif dernier and ligne.startswith("("):
            if "audio" not in ligne:
                noms.append(dernier)
            dernier = None
    return noms


def capturer(peripherique: str | None = None, trames_ignorees: int = 6) -> tuple[bytes, str]:
    """Rend (JPEG, libellé). Les premières trames sont sautées : l'exposition automatique se règle."""
    import av
    from PIL import Image
    essai = os.environ.get("JARVIS_WEBCAM_IMAGE")
    if essai:
        image, libelle = Image.open(essai).convert("RGB"), "l'image d'essai (pas de webcam branchée)"
    else:
        # une vraie webcam passe avant les caméras virtuelles (OBS ne diffuse que si sa caméra virtuelle est démarrée)
        tous = peripheriques()
        nom = peripherique or REGLAGES.get("peripherique") or next(iter(sorted(tous, key=lambda n: "virtual" in n.lower())), None)
        if not nom:
            raise RuntimeError("aucune webcam trouvée")
        image = None
        try:
            conteneur = av.open(f"video={nom}", format="dshow", options={"rtbufsize": "64M"})
        except OSError as e:
            if "obs" in nom.lower():
                raise RuntimeError("la caméra virtuelle d'OBS ne diffuse pas : dans OBS, cliquez sur « Démarrer la caméra virtuelle », "
                                   "ou branchez une webcam") from e
            raise RuntimeError(f"la webcam « {nom} » ne répond pas : elle est peut-être utilisée par une autre application") from e
        with conteneur:
            for i, trame in enumerate(conteneur.decode(video=0)):
                if i >= trames_ignorees:
                    image = trame.to_image().convert("RGB")
                    break
        if image is None:
            raise RuntimeError("la webcam n'a envoyé aucune image")
        libelle = f"la webcam ({nom})"
    largeur = int(CONFIG.get("vision", {}).get("largeur_max", 1280))
    if image.width > largeur:
        image = image.resize((largeur, int(image.height * largeur / image.width)))
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", quality=85)
    return tampon.getvalue(), libelle


def executer(question: str = "", enregistrer: bool = False) -> str:
    from ..cerveau import CERVEAU, TITRE
    if not vision.modele_present():
        return f"Le modèle de vision {vision.MODELE} n'est pas installé. Lancez : ollama pull {vision.MODELE}"
    if not _verrou.acquire(blocking=False):
        return "Je suis déjà en train de regarder."
    try:
        jpeg, libelle = capturer()
    except Exception as e:
        _verrou.release()
        message = str(e) if isinstance(e, RuntimeError) else f"la webcam ne répond pas ({type(e).__name__})"
        return f"Je ne peux pas regarder : {message}."
    url = ""
    if enregistrer:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        chemin = DOSSIER / f"webcam_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        chemin.write_bytes(jpeg)
        url = f"/workspace/webcam/{chemin.name}"
    image_b64 = base64.b64encode(jpeg).decode()
    consigne = question or "Que voyez-vous ?"
    from .. import outils
    demande = outils.source_courante()

    def travail():
        chrono, debut = {}, time.time()
        try:
            sur_evenement({"type": "vision_debut", "t": time.time(), "ecran": libelle, "source": "webcam"})
            t = time.time()
            CERVEAU.decharger()
            chrono["dechargement_cerveau"] = round(time.time() - t, 2)
            t = time.time()
            description = vision.decrire_image(consigne, image_b64, vision.CONSIGNE_WEBCAM)
            chrono["vision"] = round(time.time() - t, 2)
            chrono["total_description"] = round(time.time() - debut, 2)
            sur_evenement({"type": "vision", "t": time.time(), "ecran": libelle, "source": "webcam", "texte": description,
                           "duree": chrono["total_description"], "image": url or f"data:image/jpeg;base64,{image_b64}",
                           "enregistree": bool(url), "demande": demande})
        except Exception as e:
            journal.exception("webcam")
            sur_evenement({"type": "vision_erreur", "t": time.time(), "message": f"{type(e).__name__} : {e}", "source": "webcam"})
        finally:
            t = time.time()
            try:
                CERVEAU.charger()
            except Exception:
                journal.exception("rechargement du cerveau")
            chrono["rechargement_cerveau"] = round(time.time() - t, 2)
            chrono["total_cycle"] = round(time.time() - debut, 2)
            sur_evenement({"type": "vision_fin", "t": time.time(), "chrono": dict(chrono), "ecran": libelle, "source": "webcam"})
            _verrou.release()

    threading.Thread(target=travail, daemon=True, name="webcam-fond").start()
    garde = " Je garde la photo." if url else ""
    return f"Je regarde par la webcam, {TITRE}.{garde} Je vous dis ce que je vois dans un instant."
