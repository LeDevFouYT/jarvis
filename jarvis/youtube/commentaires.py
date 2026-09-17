"""Les commentaires d'une vidéo : les lire, repérer ceux qui demandent quelque chose, les regrouper par thème.

1. Les commentaires (du plus récent au plus ancien) viennent de donnees.commentaires.
2. Un filtre simple garde ceux qui demandent quelque chose : une question, « tu peux », « fais une vidéo sur »,
   « tuto », « la suite », « please make »… Sans cerveau, sans erreur de comptage.
3. Le cerveau range les demandes par thème : il rend pour chaque thème les NUMÉROS des commentaires. Les nombres
   sont comptés en Python à partir de ces numéros (un commentaire ne compte qu'une fois, un numéro inventé est
   ignoré) : le cerveau nomme les thèmes, il ne compte pas."""
import json
import re

from . import donnees

_DEMANDE = re.compile(
    r"\?|\b(tu (peux|pourrais|pourras|devrais)|pourriez|pouvez[- ]vous|peux[- ]tu|pourrais[- ]tu|fais (une|un|des|la|le)|"
    r"faites|refais|refaire|j'aimerais|j'aimerai|j'adorerais|ce serait (cool|bien|top|génial)|ça serait|serait (cool|bien|top)|"
    r"svp|stp|s'il (te|vous) pla[iî]t|tuto|tutoriel|la suite|partie 2|une suite|vid[ée]o sur|explique|montre[- ]nous|"
    r"comment (on|tu|vous|faire|il faut)|est[- ]ce qu|please|can you|could you|would love|make a video|do a video|how (do|to))\b",
    re.IGNORECASE)

SCHEMA = {"type": "object", "properties": {"themes": {"type": "array", "items": {"type": "object", "properties": {
    "theme": {"type": "string"}, "commentaires": {"type": "array", "items": {"type": "integer"}}},
    "required": ["theme", "commentaires"]}}}, "required": ["themes"]}

CONSIGNE = ("Tu ranges des commentaires YouTube qui demandent quelque chose au créateur. Chaque ligne commence par son numéro "
            "entre crochets. Réponds en JSON : \"themes\" = 2 à 8 thèmes, chacun avec \"theme\" = 2 à 6 mots en français qui "
            "disent ce qui est demandé (ex. « tutoriel d'installation », « vidéo sur Linux ») et \"commentaires\" = les numéros "
            "des commentaires qui le demandent. Un commentaire va dans un seul thème. Ignore ceux qui ne demandent rien.")


def est_demande(texte: str) -> bool:
    return bool(_DEMANDE.search(texte or ""))


def lire(lien: str, n: int = 200) -> dict:
    vid = donnees.identifiant_video(lien)
    if not vid:
        raise donnees.ErreurYouTube("ce n'est pas un lien de vidéo YouTube")
    return {"id": vid, "titre": donnees.titre_video(vid), "commentaires": donnees.commentaires(vid, n)}


def regrouper(demandes: list[dict]) -> list[dict]:
    """Les thèmes, comptés en Python d'après les numéros rendus par le cerveau."""
    from ..cerveau import CERVEAU
    if not demandes:
        return []
    lignes = "\n".join(f"[{i}] {d['texte'][:220].replace(chr(10), ' ')}" for i, d in enumerate(demandes, 1))
    brut = json.loads(CERVEAU.generer(CONSIGNE, lignes, delai=180, format=SCHEMA))
    pris, themes = set(), []
    for t in brut.get("themes", []):
        numeros = [i for i in dict.fromkeys(t.get("commentaires", [])) if isinstance(i, int) and 1 <= i <= len(demandes) and i not in pris]
        pris.update(numeros)
        if numeros and t.get("theme", "").strip():
            themes.append({"theme": t["theme"].strip(), "nombre": len(numeros),
                           "exemples": [demandes[i - 1]["texte"][:160] for i in numeros[:2]], "numeros": numeros})
    themes.sort(key=lambda t: -t["nombre"])
    return themes


def analyser(lien: str, n: int = 200) -> dict:
    from .analyste import Faits, nombre_fr
    video = lire(lien, n)
    tous = video["commentaires"]
    demandes = [c for c in tous if est_demande(c["texte"])]
    themes = regrouper(demandes[:150])
    f = Faits()
    source = "commentaires publics de la vidéo" + (" (API YouTube Data v3)" if donnees.source() == "api" else " (yt-dlp)")
    f.ajouter("commentaires", f"{nombre_fr(len(tous))} commentaires lus sur « {video['titre']} », dont {nombre_fr(len(demandes))} "
                              f"qui demandent quelque chose.", source, lus=len(tous), demandes=len(demandes))
    for t in themes:
        f.ajouter("demande", f"« {t['theme']} » : {t['nombre']} commentaire(s). Exemple : « {t['exemples'][0]} »", source, nombre=t["nombre"])
    classees = sum(t["nombre"] for t in themes)
    if demandes and classees < len(demandes[:150]):
        f.ajouter("demande", f"{len(demandes[:150]) - classees} demande(s) sans thème commun.", source, sans_theme=len(demandes[:150]) - classees)
    return {"video": {"id": video["id"], "titre": video["titre"]}, "lus": len(tous), "demandes": len(demandes), "themes": themes,
            "faits": f.liste, "derniers": tous[:15]}


def pour_le_cerveau(analyse: dict) -> str:
    lignes = "\n".join(f"{x['id']} {x['texte']}" for x in analyse["faits"])
    return (f"FAITS SUR LES COMMENTAIRES :\n{lignes}\nRÈGLE : dis en 2 à 4 phrases ce que les gens demandent le plus. "
            "Une phrase = un seul fait. Chaque affirmation cite un chiffre recopié tel quel de ces faits, en chiffres ; n'en calcule aucun autre.")
