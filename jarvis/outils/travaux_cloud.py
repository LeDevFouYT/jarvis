"""Les travaux lourds d'un client cloud : vidéo, sculpture 3D, miniatures.

Le cerveau d'un client cloud tourne ailleurs ; sa carte graphique, souvent, n'existe pas. Jusqu'au 22/09 ces
trois pouvoirs lui étaient simplement refusés. Ils passent maintenant par la passerelle, comme les images : la
machine de l'auteur calcule, le fichier revient, et le temps est décompté de ses minutes — il paie, il a tout.

Rien ici ne s'exécute chez l'auteur au nom du client : la passerelle ne transmet qu'une description (un texte,
un objet, un sujet) à des outils précis. Aucun ordre, aucun chemin de fichier, aucun code.
"""
import base64
import time
from pathlib import Path

import requests

RAISONS = {402: "votre crédit est épuisé", 429: "vous avez atteint le plafond du jour",
           503: "la machine qui calcule est hors ligne pour le moment", 504: "la machine n'a pas répondu à temps"}


def base_passerelle() -> str:
    from .. import cerveau
    url = cerveau.OLLAMA
    return url[:-len("/ollama")] if url.endswith("/ollama") else url


def demander(genre: str, corps: dict, delai: float) -> dict:
    """Envoie un travail lourd à la passerelle et rend sa réponse. Lève RuntimeError avec une phrase lisible."""
    from .. import cerveau
    r = requests.post(f"{base_passerelle()}/travail/{genre}", headers=cerveau.ENTETES, json=corps, timeout=delai)
    if r.status_code != 200:
        raise RuntimeError(RAISONS.get(r.status_code, f"erreur {r.status_code}"))
    return r.json()


def ecrire(donnees_base64: str, dossier: Path, prefixe: str, extension: str) -> Path:
    """Écrit le fichier reçu et rend son chemin."""
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{prefixe}_{time.strftime('%Y%m%d_%H%M%S')}{extension}"
    chemin.write_bytes(base64.b64decode(donnees_base64))
    return chemin
