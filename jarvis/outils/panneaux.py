"""Les panneaux holographiques du HUD : un outil en ouvre un en appelant une des fonctions ci-dessous.

Le HUD (jarvis/hud/panneaux.js) sait dessiner chaque genre et l'anime à l'ouverture :
  texte      un ou plusieurs paragraphes
  liste      des éléments {titre, detail, meta}
  graphique  des jauges {nom, valeur, max, unite, alerte} et, en option, une courbe (liste de nombres)
  images     des images {url, legende}
  frise      des événements datés {quand (horodatage), titre, detail}
  recherche  des résultats web cliquables {titre, domaine, url, extrait}
  page       une page intégrée {url}

Hors du serveur (tests en ligne de commande), rien n'est diffusé : l'outil marche pareil."""
import time


def _diffuser(genre: str, titre: str, **contenu):
    from . import sur_evenement           # lu à l'appel : c'est le serveur qui le branche au démarrage
    sur_evenement({"type": "panneau", "t": time.time(), "genre": genre, "titre": titre, **contenu})


def texte(titre: str, paragraphes: list[str] | str, source: str = ""):
    if isinstance(paragraphes, str):
        paragraphes = [p for p in paragraphes.split("\n") if p.strip()]
    _diffuser("texte", titre, paragraphes=paragraphes, source=source)


def liste(titre: str, elements: list[dict], vide: str = "Rien à afficher.", cle: str = ""):
    """`cle` : un panneau de même clé déjà ouvert est remplacé (une vérification qui se complète)."""
    _diffuser("liste", titre, elements=elements, vide=vide, cle=cle)


def graphique(titre: str, jauges: list[dict], courbe: list[float] | None = None, legende_courbe: str = ""):
    _diffuser("graphique", titre, jauges=jauges, courbe=courbe or [], legende_courbe=legende_courbe)


def images(titre: str, images: list[dict]):
    _diffuser("images", titre, images=images)


def nuage(titre: str, points: list[dict], mediane: float | None = None, source: str = ""):
    """Un nuage de vidéos : {quand (horodatage), vues, titre, brille (au-dessus de 3 fois la médiane), ratio, url}.
    Vues en échelle logarithmique, ligne de la médiane et de trois fois la médiane."""
    _diffuser("nuage", titre, points=points, mediane=mediane, source=source)


def barres(titre: str, barres: list[dict], unite: str = ""):
    """Des barres horizontales {nom, valeur, detail, brille}."""
    _diffuser("barres", titre, barres=barres, unite=unite)


def frise(titre: str, evenements: list[dict], vide: str = "Rien de prévu.", video: dict | None = None):
    """Événements datés {quand, titre, detail}. Avec `video` {id, duree, resume, lien} : des instants {t (secondes),
    titre, url} placés sur la durée de la vidéo ; un clic ouvre la vidéo intégrée à cet instant."""
    _diffuser("frise", titre, evenements=evenements, vide=vide, video=video)
