"""Outil miniatures : trois miniatures YouTube 1280×720 pour une vidéo, dessinées par ComfyUI, avec un titre court
incrusté en gros caractères. Rangées dans workspace/miniatures/ et affichées en panneau.

1. le cerveau écrit trois prompts d'image différents (gros plan, scène, contraste) et un titre de 2 à 5 mots, sauf
   si la personne a donné le titre ;
2. ComfyUI dessine les trois images (1024×576, 8 pas, agrandies en 1280×720) (le cerveau est déchargé avant, les modèles ComfyUI libérés après) ;
3. Pillow incruste le titre : capitales, contour noir épais, ombre, un bandeau sombre dégradé, une mise en page par
   miniature (bas gauche, haut gauche, bas droite) pour comparer.

Réponse directe : « je lance les miniatures », l'annonce vient quand elles sont prêtes (événement miniatures)."""
import io
import json
import logging
import random
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import CONFIG, RACINE

NOM = "miniatures"
DESCRIPTION = ("Crée trois miniatures YouTube (1280×720) pour une vidéo : trois images dessinées sur la machine avec un titre court "
               "incrusté en gros caractères, à comparer. Compte une à deux minutes.")
PARAMETRES = {
    "sujet": {"type": "string", "description": "De quoi parle la vidéo, en quelques mots"},
    "titre": {"type": "string", "description": "Le texte à incruster, 2 à 5 mots, seulement si la personne l'a donné"},
}
REQUIS = ["sujet"]
DIRECT = True

DOSSIER = RACINE / "workspace" / "miniatures"
LARGEUR, HAUTEUR = 1280, 720
# rendu à 1024×576 puis agrandi : mesuré le 17/09 sur la RTX 5080 (NVFP4, pilote 576.88), 17 s par image au lieu de 43 s
# en 1280×720 et 12 pas ; le bf16 (12 Go) sature la carte et ne finit pas. Réglable : comfyui.miniatures.
RENDU = CONFIG.get("comfyui", {}).get("miniatures", {})
POLICES = ["C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/arialbd.ttf"]
MISES_EN_PAGE = ["bas_gauche", "haut_gauche", "bas_droite"]
sur_evenement = lambda e: None
journal = logging.getLogger("miniatures")
_verrou = threading.Lock()

SCHEMA = {"type": "object", "properties": {
    "titre": {"type": "string"},
    "prompts": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3}},
    "required": ["titre", "prompts"]}

CONSIGNE = ("Tu prépares les miniatures YouTube d'une vidéo. Réponds en JSON. \"titre\" : 2 à 5 mots en français, percutants, "
            "sans ponctuation finale, à incruster sur l'image (reprends exactement le titre imposé s'il y en a un). "
            "\"prompts\" : exactement 3 descriptions d'image EN ANGLAIS, chacune 30 à 60 mots, très différentes : "
            "1) un gros plan expressif sur le sujet, 2) une scène large et spectaculaire, 3) une composition très contrastée "
            "avec un seul objet fort. Style photo de miniature YouTube : couleurs saturées, éclairage dramatique, fond simple, "
            "sujet d'un côté pour laisser de la place au texte, aucune lettre ni texte ni logo dans l'image.")


def _police(taille: int) -> ImageFont.FreeTypeFont:
    for chemin in POLICES:
        if Path(chemin).exists():
            return ImageFont.truetype(chemin, taille)
    return ImageFont.load_default(taille)


def _couper(titre: str, dessin: ImageDraw.ImageDraw, police, largeur_max: int) -> list[str]:
    """Deux lignes au plus, coupées au mot le plus équilibré."""
    mots = titre.split()
    if len(mots) < 2 or dessin.textlength(titre, font=police) <= largeur_max:
        return [titre]
    coupes = [(" ".join(mots[:i]), " ".join(mots[i:])) for i in range(1, len(mots))]
    return list(min(coupes, key=lambda c: max(dessin.textlength(c[0], font=police), dessin.textlength(c[1], font=police))))


def incruster(image: Image.Image, titre: str, mise_en_page: str = "bas_gauche") -> Image.Image:
    image = image.convert("RGB").resize((LARGEUR, HAUTEUR), Image.LANCZOS)
    titre = " ".join(titre.upper().split()).replace(" %", " %").replace(" !", " !").replace(" ?", " ?")
    dessin = ImageDraw.Draw(image)
    marge, largeur_max = 56, int(LARGEUR * 0.62)
    taille = 150
    while taille > 60:
        police = _police(taille)
        lignes = _couper(titre, dessin, police, largeur_max)
        if len(lignes) <= 2 and max(dessin.textlength(l, font=police) for l in lignes) <= largeur_max:
            break
        taille -= 6
    police = _police(taille)
    lignes = _couper(titre, dessin, police, largeur_max)
    hauteur_ligne = int(taille * 1.02)
    bloc_h = hauteur_ligne * len(lignes)
    haut = mise_en_page.startswith("haut")
    droite = mise_en_page.endswith("droite")
    y0 = marge if haut else HAUTEUR - marge - bloc_h

    # un dégradé sombre du côté du texte : lisible sur n'importe quelle image
    voile = Image.new("L", (LARGEUR, HAUTEUR), 0)
    vd = ImageDraw.Draw(voile)
    for i in range(HAUTEUR):
        d = (HAUTEUR - i) if haut else i
        vd.line([(0, i), (LARGEUR, i)], fill=int(max(0, 190 * (d / HAUTEUR - 0.35) / 0.65)))
    image = Image.composite(Image.new("RGB", image.size, (0, 0, 0)), image, voile)

    ombre = Image.new("L", image.size, 0)
    od = ImageDraw.Draw(ombre)
    dessin = ImageDraw.Draw(image)
    epaisseur = max(6, taille // 14)
    for n, ligne in enumerate(lignes):
        largeur_ligne = dessin.textlength(ligne, font=police)
        x = LARGEUR - marge - largeur_ligne if droite else marge
        y = y0 + n * hauteur_ligne
        od.text((x + 10, y + 12), ligne, font=police, fill=220, stroke_width=epaisseur, stroke_fill=220)
    image = Image.composite(Image.new("RGB", image.size, (0, 0, 0)), image, ombre.filter(ImageFilter.GaussianBlur(10)))
    dessin = ImageDraw.Draw(image)
    for n, ligne in enumerate(lignes):
        largeur_ligne = dessin.textlength(ligne, font=police)
        x = LARGEUR - marge - largeur_ligne if droite else marge
        y = y0 + n * hauteur_ligne
        couleur = (255, 214, 0) if n == len(lignes) - 1 and len(lignes) > 1 else (255, 255, 255)
        dessin.text((x, y), ligne, font=police, fill=couleur, stroke_width=epaisseur, stroke_fill=(0, 0, 0))
    return image


def idees(sujet: str, titre: str = "") -> dict:
    from ..cerveau import CERVEAU
    impose = f"\nTitre imposé : {titre}" if titre else ""
    d = json.loads(CERVEAU.generer(CONSIGNE, f"Sujet de la vidéo : {sujet}{impose}", delai=120, format=SCHEMA))
    prompts = [p.strip() for p in d.get("prompts", []) if p.strip()][:3]
    if len(prompts) < 3:
        raise RuntimeError("le cerveau n'a pas proposé trois images")
    return {"titre": (titre or d.get("titre", "")).strip().rstrip(".!") or sujet[:30], "prompts": prompts}


def _dessiner(prompts: list[str], chrono: dict) -> list[Image.Image]:
    """Les trois images dans la file de ComfyUI, puis récupérées une à une."""
    from . import generer_image as G
    G.liberer_avant()
    files = []
    for prompt in prompts:
        w = G._preparer(prompt + ", youtube thumbnail style, no text", "paysage")
        for noeud in w.values():
            if noeud["class_type"] == "EmptyLatentImage":
                noeud["inputs"]["width"], noeud["inputs"]["height"] = RENDU.get("largeur", 1024), RENDU.get("hauteur", 576)
            if noeud["class_type"] == "KSampler":
                noeud["inputs"]["seed"] = random.randint(1, 2 ** 31)
                noeud["inputs"]["steps"] = RENDU.get("pas", 8)
        r = requests.post(f"{G.URL}/prompt", json={"prompt": w, "client_id": uuid.uuid4().hex}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI a refusé le workflow ({r.status_code})")
        files.append(r.json()["prompt_id"])
    images = []
    t = time.time()
    for prompt_id in files:
        sorties = G._attendre(prompt_id, 600)
        if sorties is None:
            raise RuntimeError("ComfyUI n'a pas terminé en dix minutes")
        for sortie in sorties.values():
            for im in sortie.get("images", [])[:1]:
                rep = requests.get(f"{G.URL}/view", params={"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                                            "type": im.get("type", "output")}, timeout=30)
                rep.raise_for_status()
                images.append(Image.open(io.BytesIO(rep.content)))
    chrono["dessin"] = round(time.time() - t, 1)
    return images


def creer(sujet: str, titre: str = "", progression=lambda etape: None) -> dict:
    """Le travail complet (utilisé aussi par le test) : rend {titre, prompts, chemins, urls, chrono}."""
    from . import generer_image as G
    from ..cerveau import CERVEAU
    chrono = {}
    t = time.time()
    progression("le cerveau cherche le titre et trois idées d'image")
    d = idees(sujet, titre)
    chrono["idees"] = round(time.time() - t, 1)
    if not G._lancer_comfyui():
        raise RuntimeError("ComfyUI n'est pas lancé")
    if not G._verrou.acquire(timeout=600):
        raise RuntimeError("une autre image est en cours")
    try:
        t = time.time()
        CERVEAU.decharger()
        chrono["dechargement_cerveau"] = round(time.time() - t, 1)
        progression("ComfyUI dessine les trois images")
        images = _dessiner(d["prompts"], chrono)
    finally:
        try:
            requests.post(f"{G.URL}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
        except requests.RequestException:
            pass
        G._verrou.release()
        t = time.time()
        threading.Thread(target=CERVEAU.charger, daemon=True).start()
    progression("incrustation du titre")
    DOSSIER.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    chemins = []
    for n, (image, mise_en_page) in enumerate(zip(images, MISES_EN_PAGE), 1):
        chemin = DOSSIER / f"miniature_{horodatage}_{n}.png"
        incruster(image, d["titre"], mise_en_page).save(chemin)
        chemins.append(chemin)
    return {**d, "chemins": [str(c) for c in chemins], "urls": [f"/workspace/miniatures/{c.name}" for c in chemins], "chrono": chrono}


def _executer_cloud(sujet: str, titre: str) -> str:
    """Mode cloud : les trois miniatures sont dessinées sur la machine de l'auteur et reviennent ici.

    Mêmes événements et même panneau que le chemin local : de l'extérieur, rien ne distingue les deux.
    """
    import base64
    from . import travaux_cloud

    def travail():
        debut = time.time()
        try:
            sur_evenement({"type": "miniatures_debut", "t": time.time(), "sujet": sujet})
            sortie = travaux_cloud.demander("miniatures", {"sujet": sujet, "titre": titre}, delai=1200)
            DOSSIER.mkdir(parents=True, exist_ok=True)
            chemins, urls = [], []
            for n, image in enumerate(sortie.get("images", []), start=1):
                chemin = DOSSIER / f"miniature_{datetime.now():%Y%m%d_%H%M%S}_{n}.png"
                chemin.write_bytes(base64.b64decode(image))
                chemins.append(str(chemin))
                urls.append(f"/workspace/miniatures/{chemin.name}")
            from . import panneaux
            panneaux.images(f"Miniatures · {titre or sujet}",
                            [{"url": u, "legende": f"variante {n}"} for n, u in enumerate(urls, 1)])
            sur_evenement({"type": "miniatures", "t": time.time(), "titre": titre or sujet, "chemins": chemins,
                           "urls": urls, "prompts": [], "duree": round(time.time() - debut, 1),
                           "chrono": {"distant": sortie.get("secondes")}, "source": ""})
        except Exception as e:
            sur_evenement({"type": "miniatures_erreur", "t": time.time(), "message": str(e), "source": ""})

    threading.Thread(target=travail, daemon=True, name="miniatures-cloud").start()
    return "Je les prépare sur la machine distante, monsieur. Comptez deux minutes."


def executer(sujet: str, titre: str = "") -> str:
    from .. import cerveau, outils
    from ..cerveau import TITRE
    from . import generer_image as G
    if cerveau.MODE == "cloud":                 # pas de carte ici : la machine de l'auteur dessine, c'est facturé
        return _executer_cloud(sujet, titre)
    if not G.comfyui_present() and not G.REGLAGES.get("lanceur"):
        return "ComfyUI n'est pas lancé. Demandez-moi d'ouvrir ComfyUI, puis réessayez."
    if not _verrou.acquire(blocking=False):
        return "Je dessine déjà des miniatures, un instant."
    source = outils.source_courante()

    def travail():
        debut = time.time()
        try:
            sur_evenement({"type": "miniatures_debut", "t": time.time(), "sujet": sujet})
            r = creer(sujet, titre, lambda etape: sur_evenement({"type": "miniatures_etape", "t": time.time(), "etape": etape}))
            from . import panneaux
            panneaux.images(f"Miniatures · {r['titre']}", [{"url": u, "legende": f"variante {n} · {m.replace('_', ' ')}"}
                                                           for n, (u, m) in enumerate(zip(r["urls"], MISES_EN_PAGE), 1)])
            sur_evenement({"type": "miniatures", "t": time.time(), "titre": r["titre"], "chemins": r["chemins"], "urls": r["urls"],
                           "prompts": r["prompts"], "duree": round(time.time() - debut, 1), "chrono": r["chrono"], "source": source})
        except Exception as e:
            journal.exception("miniatures")
            sur_evenement({"type": "miniatures_erreur", "t": time.time(), "message": f"{type(e).__name__} : {e}", "source": source})
        finally:
            _verrou.release()

    threading.Thread(target=travail, daemon=True, name="miniatures-fond").start()
    return f"Je prépare trois miniatures, {TITRE} : un titre, trois images dessinées ici, puis le texte incrusté. Comptez une à deux minutes."
