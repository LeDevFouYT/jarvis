"""Outil youtube_commentaires : les commentaires d'une vidéo, et les demandes regroupées par thème et comptées.
Le comptage est fait en Python (jarvis/youtube/commentaires.py) ; panneau liste des demandes."""
from ..youtube import acces

NOM = "youtube_commentaires"
DESCRIPTION = ("Lit les commentaires d'une vidéo YouTube (par son lien) et regroupe par thème ce que les gens demandent, avec le "
               "nombre de commentaires par thème. action « demandes » (par défaut) ou « lire » pour les derniers commentaires.")
PARAMETRES = {
    "video": {"type": "string", "description": "Le lien de la vidéo YouTube ou son identifiant"},
    "action": {"type": "string", "enum": ["demandes", "lire"], "description": "demandes (regroupées et comptées) ou lire"},
}
DELAI = 180
REQUIS = ["video"]

derniere_analyse: dict = {}


def executer(video: str, action: str = "demandes") -> str:
    from ..youtube import commentaires
    from ..youtube.analyste import nombre_fr
    from . import panneaux
    try:
        if action == "lire":
            v = commentaires.lire(video, 30)
            panneaux.liste(f"Commentaires · {v['titre'][:60]}", [{"titre": c["texte"][:140], "detail": c["auteur"],
                                                                  "meta": f"{c['likes']} ♥"} for c in v["commentaires"][:30]],
                           vide="Aucun commentaire.")
            return f"{len(v['commentaires'])} derniers commentaires affichés. Les trois plus récents : " + " ; ".join(
                f"{c['auteur']} : « {c['texte'][:120]} »" for c in v["commentaires"][:3])
        a = commentaires.analyser(video, 300)
    except acces.ErreurYouTube as e:
        return f"Lecture des commentaires impossible : {e}."
    derniere_analyse.clear()
    derniere_analyse.update(a)
    panneaux.liste(f"Demandes · {a['video']['titre'][:50]} · {a['demandes']} sur {nombre_fr(a['lus'])} commentaires",
                   [{"titre": t["theme"], "detail": "« " + t["exemples"][0] + " »", "meta": str(t["nombre"])} for t in a["themes"]],
                   vide="Aucune demande dans les commentaires lus.")
    return commentaires.pour_le_cerveau(a)


def faits() -> list[dict]:
    return derniere_analyse.get("faits", [])
