"""Outil voir_ecran : capture l'écran demandé, le décrit avec le modèle de vision d'Ollama.
Alternance VRAM : cerveau déchargé (keep_alive 0), vision chargée puis déchargée (keep_alive 0),
cerveau rechargé après. Réponse directe : l'outil répond tout de suite « je regarde », le travail se fait
en fond, la description (déjà en français) est dite par le serveur dès qu'elle arrive (événement `vision`),
sans rappeler le cerveau pendant que la VRAM est occupée. Délais mesurés et diffusés (`vision_fin`)."""
import logging
import threading
import time

from .. import vision

NOM = "voir_ecran"
DESCRIPTION = ("Regarde l'écran de l'ordinateur (principal ou secondaire) et décrit ce qui s'y passe, "
               "ou lit un texte affiché. À utiliser quand monsieur demande ce qu'il fait, ce qu'il regarde, "
               "ou de lire quelque chose à l'écran. La description arrive une minute plus tard.")
PARAMETRES = {
    "ecran": {"type": "string", "enum": ["principal", "secondaire", "tous"], "description": "Quel écran capturer"},
    "question": {"type": "string", "description": "Ce qu'il faut regarder ou lire (facultatif)"},
}
REQUIS = []
DIRECT = True

sur_evenement = lambda e: None
journal = logging.getLogger("voir_ecran")
_verrou = threading.Lock()
dernier_chrono: dict = {}


def executer(ecran: str = "principal", question: str = "") -> str:
    from ..cerveau import CERVEAU
    if not vision.modele_present():
        return (f"Le modèle de vision {vision.MODELE} n'est pas installé, monsieur. "
                f"Lancez : ollama pull {vision.MODELE}")
    if not _verrou.acquire(blocking=False):
        return "Je suis déjà en train de regarder l'écran, monsieur."
    ecran = ecran or "principal"
    from . import source_courante
    demande = source_courante()                 # « telegram » : la description repart au téléphone, pas à la maison
    consigne = question or "Décrivez ce que la personne est en train de faire à l'écran."

    def travail():
        chrono = {}
        debut = time.time()
        libelle = ecran
        try:
            sur_evenement({"type": "vision_debut", "t": time.time(), "ecran": ecran})
            t = time.time()
            CERVEAU.decharger()
            chrono["dechargement_cerveau"] = round(time.time() - t, 2)
            t = time.time()
            image, libelle = vision.capturer(ecran)
            chrono["capture"] = round(time.time() - t, 2)
            t = time.time()
            description = vision.decrire_image(consigne, image)
            chrono["vision"] = round(time.time() - t, 2)
            chrono["total_description"] = round(time.time() - debut, 2)
            journal.info("description de %s en %.1f s", libelle, chrono["vision"])
            sur_evenement({"type": "vision", "t": time.time(), "ecran": libelle, "texte": description,
                           "duree": chrono["total_description"], "demande": demande})
        except Exception as e:
            journal.exception("vision")
            sur_evenement({"type": "vision_erreur", "t": time.time(), "message": f"{type(e).__name__} : {e}", "demande": demande})
        finally:
            t = time.time()
            try:
                CERVEAU.charger()
            except Exception:
                journal.exception("rechargement du cerveau")
            chrono["rechargement_cerveau"] = round(time.time() - t, 2)
            chrono["total_cycle"] = round(time.time() - debut, 2)
            dernier_chrono.clear()
            dernier_chrono.update(chrono)
            sur_evenement({"type": "vision_fin", "t": time.time(), "chrono": dict(chrono), "ecran": libelle})
            _verrou.release()

    threading.Thread(target=travail, daemon=True, name="vision-fond").start()
    return "Je regarde votre écran, monsieur. Un instant, je vous dis ce que je vois dès que c'est prêt."
