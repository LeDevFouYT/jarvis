"""Outil heure : la date et l'heure locales, en toutes lettres."""
from datetime import datetime

NOM = "heure"
DESCRIPTION = "Donne la date et l'heure actuelles."
PARAMETRES = {}
REQUIS = []

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def executer() -> str:
    m = datetime.now()
    return f"{JOURS[m.weekday()]} {m.day} {MOIS[m.month - 1]} {m.year}, {m.hour} h {m.minute:02d}"
