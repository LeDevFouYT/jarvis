"""Outil retenir : ajoute un souvenir durable sur la personne (mémoire longue, memoire/souvenirs.json).
« Retiens que… » est d'habitude pris par les commandes, avant le cerveau ; cet outil couvre les autres tournures
(« n'oublie jamais que mon frère s'appelle Thomas », « souviens-toi de mon anniversaire, c'est le 3 mai »)."""
from datetime import datetime

from .. import memoire

NOM = "retenir"
DESCRIPTION = ("Retient durablement un fait sur la personne (goût, habitude, projet, proche, date importante) pour les "
               "prochaines conversations. Le fait est écrit court, à la troisième personne : « Son frère s'appelle Thomas ».")
PARAMETRES = {"fait": {"type": "string", "description": "Le fait à retenir, en une phrase courte à la troisième personne"}}
REQUIS = ["fait"]


def executer(fait: str) -> str:
    s = memoire.ajouter(fait, f"demandé le {datetime.now():%d/%m/%Y}")
    if not s:
        return "Je n'ai rien retenu : le fait était vide."
    return f"C'est retenu : {s['fait']}."
