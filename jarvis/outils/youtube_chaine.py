"""Outil youtube_chaine : l'analyste d'une chaîne YouTube (par son nom ou son @).

Les calculs sont faits en Python (jarvis/youtube/analyste.py) et rendus au cerveau comme un JSON de faits sourcés ;
le cerveau commente en citant un chiffre par affirmation, puis le serveur vérifie chaque chiffre de sa réponse.
Panneaux : le nuage des vidéos (les exceptions brillent) et les barres des vues médianes par jour de publication."""
from ..youtube import acces

NOM = "youtube_chaine"
DESCRIPTION = ("Analyse une chaîne YouTube par son nom ou son @ : médiane des vues des 30 dernières vidéos, vidéos au-dessus de "
               "trois fois la médiane, durées, jours et heures de publication, motifs de titres (et rétention si c'est la chaîne "
               "du compte connecté). À utiliser pour « analyse la chaîne… », « qu'est-ce qui marche sur ma chaîne ».")
PARAMETRES = {
    "chaine": {"type": "string", "description": "Nom de la chaîne, son @ ou son lien ; « ma chaîne » pour celle des Réglages"},
    "nombre": {"type": "integer", "description": "Nombre de vidéos récentes à analyser, 30 par défaut"},
}
DELAI = 180
REQUIS = ["chaine"]

derniere_analyse: dict = {}


def executer(chaine: str, nombre: int = 30) -> str:
    from ..youtube import analyste
    from . import panneaux
    if chaine.strip().lower() in ("ma chaîne", "ma chaine", "moi", "mienne", "la mienne"):
        chaine = acces.REGLAGES.get("ma_chaine", "")
        if not chaine:
            return "Aucune chaîne réglée : indiquez la vôtre dans les Réglages, section YouTube."
    try:
        a = analyste.analyser(chaine, nombre or 30)
    except acces.ErreurYouTube as e:
        return f"Analyse impossible : {e}."
    derniere_analyse.clear()
    derniere_analyse.update(a)
    panneaux.nuage(f"{a['chaine']['titre']} · {len(a['videos'])} dernières vidéos",
                   [{"id": v["id"], "titre": v["titre"], "quand": v["timestamp"], "vues": v["vues"], "brille": v["exception"],
                     "ratio": v["ratio"], "url": f"https://www.youtube.com/watch?v={v['id']}"} for v in a["videos"]],
                   mediane=a["mediane"], source=a["source"])
    panneaux.barres(f"{a['chaine']['titre']} · vues médianes par jour de publication",
                    [{"nom": j["jour"], "valeur": j["mediane"], "detail": f"{j['videos']} vidéo(s)"} for j in a["jours"]],
                    unite="vues")
    return analyste.pour_le_cerveau(a)


def faits() -> list[dict]:
    return derniere_analyse.get("faits", [])
