"""L'agent « maison » : la carte graphique de cette machine sert les clients cloud de Jarvis.
Il tourne dans le Jarvis de l'auteur (config `maison.actif`), ou seul avec `python -m jarvis maison`.
Aucun port ouvert ici : l'agent va chercher le travail sur la passerelle (GET /maison/travail, longue attente),
l'exécute sur l'Ollama local (cerveau qwen3 ou vision gemma3, selon la requête), et rapporte le résultat
(POST /maison/resultat/<id>) avec les secondes à facturer (temps Ollama sans le chargement du modèle).
Passerelle et secret : config `maison.passerelle` et `MAISON_SECRET` dans .secrets."""
import logging
import threading
import time

import requests

from .config import CONFIG, SECRETS

REGLAGES = CONFIG.get("maison", {})
PASSERELLE = REGLAGES.get("passerelle", "").rstrip("/")
SECRET = SECRETS.get("MAISON_SECRET", "") or REGLAGES.get("secret", "")
OLLAMA = CONFIG["ollama"]["url"]
MODELES_AUTORISES = set(REGLAGES.get("modeles", [CONFIG["cerveau"]["modele"], CONFIG["vision"]["modele"]]))
LIMITE_OCTETS = 48 * 1024 * 1024        # au-delà, le JSON de la passerelle devient déraisonnable
journal = logging.getLogger("maison")


def _carte(nom: str):
    """Un seul gros modèle à la fois sur la carte, client ou pas : le cerveau rend la place et revient après."""
    from . import carte
    from .cerveau import CERVEAU
    CERVEAU.decharger()
    return carte.Occupation(nom)
sur_evenement = lambda e: None
etat = {"actif": False, "en_ligne": False, "travaux": 0, "secondes": 0.0, "dernier": None, "erreur": None}


def _executer(travail: dict) -> dict:
    if "image" in travail:
        return _dessiner(travail["image"])
    for genre, faire in LOURDS.items():                # vidéo, sculpture 3D, miniatures : la carte d'ici, payée
        if genre in travail:
            return faire(travail[genre])
    corps = dict(travail.get("chat") or {})
    if corps.get("model") not in MODELES_AUTORISES:
        return {"error": f"modèle non servi ici : {corps.get('model')}"}
    corps["stream"] = False
    # court : le modèle quitte la carte peu après la réponse, l'auteur garde sa VRAM pour lui
    corps["keep_alive"] = CONFIG.get("service_cloud", {}).get("keep_alive", "2m")
    t = time.time()
    try:
        r = requests.post(f"{OLLAMA}/api/chat", json=corps, timeout=600)
        r.raise_for_status()
        sortie = r.json()
    except Exception as e:
        return {"error": f"{type(e).__name__} : {e}"}
    facture = max(0, sortie.get("total_duration", 0) - sortie.get("load_duration", 0)) / 1e9 or (time.time() - t)
    sortie["secondes_facturees"] = round(facture, 3)
    return sortie


def _dessiner(demande: dict) -> dict:
    """Une image pour un client : le workflow tourne sur le ComfyUI de cette machine (lancé au besoin).
    Cerveau déchargé avant, ComfyUI libéré après : rien ne reste en VRAM. Renvoie le PNG en base64."""
    import base64
    from .outils import generer_image
    t = time.time()
    try:
        png, secondes = generer_image.generer_pour_cloud(demande.get("prompt", ""), demande.get("format", "carre"))
    except Exception as e:
        return {"error": f"{type(e).__name__} : {e}", "secondes_facturees": round(time.time() - t, 1)}
    return {"png": base64.b64encode(png).decode(), "secondes": round(secondes, 1), "secondes_facturees": round(secondes, 3)}


def _fichier_rendu(chemin, secondes: float, cle: str, extra: dict | None = None) -> dict:
    """Un fichier produit ici, rendu au client en base64. Au-delà de la taille limite, on refuse proprement
    plutôt que d'étouffer la passerelle avec cent mégaoctets de JSON."""
    import base64
    from pathlib import Path as _P
    donnees = _P(chemin).read_bytes()
    if len(donnees) > LIMITE_OCTETS:
        return {"error": f"fichier trop lourd ({len(donnees) // 1048576} Mo) pour être envoyé",
                "secondes_facturees": round(secondes, 3)}
    return {cle: base64.b64encode(donnees).decode(), "octets": len(donnees),
            "secondes": round(secondes, 1), "secondes_facturees": round(secondes, 3), **(extra or {})}


def _tourner_video(demande: dict) -> dict:
    """Une vidéo pour un client : Wan 2.2 sur la carte d'ici. Quatre à cinq minutes, facturées au temps réel."""
    from .outils import generer_video
    t = time.time()
    try:
        with _carte("vidéo d'un client"):
            chemin = generer_video.rendre(demande.get("prompt", ""), float(demande.get("secondes", 4)))
    except Exception as e:
        return {"error": f"{type(e).__name__} : {e}", "secondes_facturees": round(time.time() - t, 1)}
    return _fichier_rendu(chemin, time.time() - t, "mp4")


def _sculpter(demande: dict) -> dict:
    """Une sculpture 3D pour un client : image puis Hunyuan3D, rendue en .glb."""
    from .outils import hologramme
    t = time.time()
    try:
        with _carte("sculpture d'un client"):
            chemin = hologramme.sculpter(demande.get("objet", ""), demande.get("prompt", ""))
    except Exception as e:
        return {"error": f"{type(e).__name__} : {e}", "secondes_facturees": round(time.time() - t, 1)}
    return _fichier_rendu(chemin, time.time() - t, "glb", {"objet": demande.get("objet", "")})


def _miniatures(demande: dict) -> dict:
    """Trois miniatures pour un client : mêmes images que celles de l'auteur, titre incrusté compris."""
    import base64
    from pathlib import Path as _P
    from .outils import miniatures
    t = time.time()
    try:
        with _carte("miniatures d'un client"):
            resultat = miniatures.creer(demande.get("sujet", ""), demande.get("titre", ""))
            chemins = resultat.get("chemins", [])
    except Exception as e:
        return {"error": f"{type(e).__name__} : {e}", "secondes_facturees": round(time.time() - t, 1)}
    images = [base64.b64encode(_P(c).read_bytes()).decode() for c in chemins]
    poids = sum(len(x) for x in images)
    if poids > LIMITE_OCTETS:
        return {"error": "miniatures trop lourdes pour être envoyées", "secondes_facturees": round(time.time() - t, 1)}
    return {"images": images, "secondes": round(time.time() - t, 1), "secondes_facturees": round(time.time() - t, 3)}


LOURDS = {"video": _tourner_video, "modele3d": _sculpter, "miniatures": _miniatures}


def boucle(arret: threading.Event):
    entetes = {"X-Maison": SECRET}
    etat["actif"] = True
    while not arret.is_set():
        try:
            r = requests.get(f"{PASSERELLE}/maison/travail", headers=entetes, timeout=40)
            etat["en_ligne"], etat["erreur"] = True, None
            if r.status_code == 204 or not r.content:
                continue
            if r.status_code != 200:
                etat["erreur"] = f"passerelle : {r.status_code}"
                time.sleep(5)
                continue
            travail = r.json()
            identifiant = travail.get("id")
            modele = (travail.get("chat") or {}).get("model", "?")
            sur_evenement({"type": "maison_travail", "t": time.time(), "modele": modele})
            sortie = _executer(travail)
            requests.post(f"{PASSERELLE}/maison/resultat/{identifiant}", headers=entetes, json=sortie, timeout=30)
            etat["travaux"] += 1
            etat["secondes"] += float(sortie.get("secondes_facturees", 0) or 0)
            etat["dernier"] = time.time()
            journal.info("travail %s (%s) : %.1f s", identifiant, modele, sortie.get("secondes_facturees", 0))
            sur_evenement({"type": "maison_fait", "t": time.time(), "modele": modele,
                           "secondes": sortie.get("secondes_facturees", 0), "erreur": sortie.get("error")})
        except requests.RequestException as e:
            etat["en_ligne"], etat["erreur"] = False, f"{type(e).__name__}"
            arret.wait(10)
        except Exception as e:
            etat["erreur"] = f"{type(e).__name__} : {e}"
            journal.exception("agent maison")
            arret.wait(5)
    etat["actif"] = False


def demarrer() -> threading.Event | None:
    """Lance l'agent en fond si config `maison.actif`, la passerelle et le secret sont renseignés."""
    if not REGLAGES.get("actif") or not PASSERELLE or not SECRET:
        return None
    arret = threading.Event()
    threading.Thread(target=boucle, args=(arret,), daemon=True, name="maison").start()
    return arret


if __name__ == "__main__":
    if not PASSERELLE or not SECRET:
        raise SystemExit("config maison.passerelle et MAISON_SECRET (.secrets) sont nécessaires")
    print(f"Agent maison : {PASSERELLE}, modèles servis {sorted(MODELES_AUTORISES)}. Ctrl+C pour arrêter.")
    a = threading.Event()
    try:
        boucle(a)
    except KeyboardInterrupt:
        a.set()
