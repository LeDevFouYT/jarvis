"""Les panneaux holographiques du HUD : un outil en ouvre un en appelant une des fonctions ci-dessous.

Le HUD (jarvis/hud/panneaux.js) sait dessiner chaque genre et l'anime à l'ouverture :
  texte      un ou plusieurs paragraphes
  liste      des éléments {titre, detail, meta}
  graphique  des jauges {nom, valeur, max, unite, alerte} et, en option, une courbe (liste de nombres)
  images     des images {url, legende}
  frise      des événements datés {quand (horodatage), titre, detail}
  recherche  des résultats web cliquables {titre, domaine, url, extrait}
  page       une page intégrée {url}
  cours      le graphique géant d'une crypto (vidéo 4) : prix, variation, courbe ; grand panneau
  multicours plusieurs graphiques de cours côte à côte (vidéo 4) ; grand panneau
  replay     le replay du portefeuille fictif face au Bitcoin (vidéo 4) ; grand panneau

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


# Le dernier graphique de cours affiché : « regarde ce graphique » confronte ce que la vision lit à ces chiffres-là
# (vu le 17/10 : gemma3 lisait « 20,10 € » sur un Solana à 92,10 €).
DERNIER_GRAPHIQUE: dict = {}


def cours(symbole: str, nom: str, periode: str, libelle: str, prix: dict, serie: list[dict], variation_periode: float | None = None,
          unite: str = "EUR", periodes: list | None = None, depuis: str = "", etat: str = ""):
    """Le graphique géant d'un cours (vidéo 4) : le prix et la variation en très gros, en vert ou en rouge, et la
    courbe des clôtures de la période, terminée par le prix du moment. Assez lisible pour faire une miniature."""
    points = [[b["t"], b["c"]] for b in serie]
    if not points or prix["quand"] > points[-1][0]:
        points.append([int(prix["quand"]), prix["prix"]])
    variation = prix["variation_24h"] if periode == "24h" or variation_periode is None else variation_periode
    if not depuis and periode == "24h":
        depuis = "il y a 24 h"
    DERNIER_GRAPHIQUE.clear()
    DERNIER_GRAPHIQUE.update(nom=nom, symbole=symbole, unite=unite, quand=time.time(), libelle=libelle,
                             valeurs={"prix": prix["prix"], "haut": max(p[1] for p in points), "bas": min(p[1] for p in points),
                                      "variation": abs(variation), "variation_24h": abs(prix["variation_24h"])})
    _diffuser("cours", f"{nom} · {libelle}", symbole=symbole, nom=nom, periode=periode, libelle=libelle,
              prix=prix["prix"], variation=round(variation, 2), variation_24h=round(prix["variation_24h"], 2),
              haut=max(p[1] for p in points), bas=min(p[1] for p in points), points=points,
              source=prix["source"], quand=prix["quand"], unite=unite, periodes=periodes, depuis=depuis, etat=etat)


def multicours(periode: str, libelle: str, graphiques: list[dict], quoi: str = ""):
    """Plusieurs graphiques côte à côte (2 à 6) : {symbole, nom, prix (dict de cours.prix), serie (bougies), variation}."""
    cellules = []
    for g in graphiques:
        points = [[b["t"], b["c"]] for b in g["serie"]]
        if not points or g["prix"]["quand"] > points[-1][0]:
            points.append([int(g["prix"]["quand"]), g["prix"]["prix"]])
        cellules.append({"symbole": g["symbole"], "nom": g["nom"], "prix": g["prix"]["prix"], "variation": round(g["variation"], 2),
                         "unite": g.get("unite", "EUR"),
                         "haut": max(x[1] for x in points), "bas": min(x[1] for x in points), "points": points})
    source = graphiques[0]["prix"]["source"] if graphiques else ""
    quoi = quoi or ("cryptos" if all(g.get("unite", "EUR") == "EUR" and "." not in g["symbole"] and "^" not in g["symbole"] for g in graphiques) else "cours")
    _diffuser("multicours", f"{len(cellules)} {quoi} · {libelle}", periode=periode, libelle=libelle, graphiques=cellules,
              source=source, quand=time.time())
