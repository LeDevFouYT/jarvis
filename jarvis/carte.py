"""Le verrou de la carte graphique (v3, corrigé le 20/09).

Un seul gros modèle à la fois sur les 16 Go. Sans ce verrou, le cerveau revenait tout seul pendant un rendu :
après chaque échange, la mémoire longue réchauffe le modèle (`CERVEAU.rechauffer`), et pendant que Wan 2.2
calculait une vidéo, qwen3:14b reprenait ses 10 Go — il ne restait plus que 720 Mo, et le rendu de 40 s durait
une demi-heure (répétition générale du 20/09).

Règle : un travail lourd (image, hologramme, vidéo) **occupe** la carte ; tant qu'elle est occupée, le cerveau
refuse de se recharger. Il revient de lui-même quand le travail la rend.
"""
import threading
import time

_verrou = threading.Lock()
_occupant = {"nom": "", "depuis": 0.0}


def occuper(nom: str) -> None:
    with _verrou:
        _occupant.update(nom=nom, depuis=time.time())


def liberer(nom: str = "") -> None:
    with _verrou:
        if not nom or _occupant["nom"] == nom:
            _occupant.update(nom="", depuis=0.0)


def occupee() -> str:
    """Le nom du travail qui tient la carte, ou une chaîne vide. Un occupant oublié est relâché au bout d'une heure."""
    with _verrou:
        if _occupant["nom"] and time.time() - _occupant["depuis"] > 3600:
            _occupant.update(nom="", depuis=0.0)
        return _occupant["nom"]


class Occupation:
    """`with carte.Occupation("vidéo"):` — la carte est rendue quoi qu'il arrive."""

    def __init__(self, nom: str):
        self.nom = nom

    def __enter__(self):
        occuper(self.nom)
        return self

    def __exit__(self, *e):
        liberer(self.nom)
        return False
