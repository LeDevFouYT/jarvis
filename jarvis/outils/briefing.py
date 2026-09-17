"""Outil briefing : le point du matin, en faits sourcés (jarvis/youtube/briefing.py). Pas de météo, pas de lieu.
Panneaux : la liste des faits, les barres des vues gagnées depuis le relevé précédent, la liste des demandes."""

NOM = "briefing"
DESCRIPTION = ("Fait le briefing : la chaîne YouTube depuis hier (abonnés, vues gagnées, nouvelles vidéos), les nouveaux "
               "commentaires qui demandent quelque chose, un concurrent en forme, les rappels du jour et l'état de la machine. "
               "À utiliser pour « briefing », « fais-moi le point », « quoi de neuf ce matin ».")
PARAMETRES = {}
DELAI = 180
REQUIS = []

dernier: dict = {}


def executer() -> str:
    from ..youtube import briefing
    from . import panneaux
    b = briefing.briefing()
    dernier.clear()
    dernier.update(b)
    panneaux.liste("Briefing", [{"titre": f["texte"], "detail": f["source"], "meta": f["sujet"]} for f in b["faits"]])
    if b["gains"]:
        panneaux.barres("Vues gagnées depuis le dernier relevé", b["gains"], unite="vues")
    if b["demandes"]:
        panneaux.liste("Nouvelles demandes dans les commentaires", b["demandes"])
    return briefing.pour_le_cerveau(b)


def faits() -> list[dict]:
    return dernier.get("faits", [])
