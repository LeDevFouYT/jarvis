"""Une action qui attend un « oui » : fermer une application qui a du travail non enregistré, par exemple.
L'outil appelle `demander`, Jarvis pose la question, et la phrase suivante « oui » ou « non » est traitée par le
serveur avant le cerveau (commandes.analyser). Une seule confirmation à la fois, valable 60 secondes."""
import threading
import time

_verrou = threading.Lock()
_attente: dict | None = None
demandes = 0                        # compte les questions posées : le cerveau dit la question telle quelle
sur_evenement = lambda e: None      # branché par le serveur
DELAI = 60
# question venue du téléphone : `boutons_telegram(question, delai)` envoie « Oui » / « Non » (branché par le serveur)
boutons_telegram = None


def demander(question: str, action, refus: str = "Très bien, je n'y touche pas.", delai: float = DELAI) -> str:
    """Enregistre l'action et rend la question à dire. Depuis Telegram, la question part avec deux boutons."""
    global _attente, demandes
    with _verrou:
        demandes += 1
        _attente = {"question": question, "action": action, "refus": refus, "expire": time.time() + delai}
    sur_evenement({"type": "confirmation_demandee", "t": time.time(), "question": question, "delai": delai})
    from . import outils
    if outils.source_courante() == "telegram" and boutons_telegram:
        boutons_telegram(question, delai)
    return question


def en_attente() -> bool:
    with _verrou:
        return _attente is not None and _attente["expire"] > time.time()


def confirmer() -> str:
    global _attente
    with _verrou:
        a, _attente = _attente, None
    if not a or a["expire"] < time.time():
        return "Il n'y avait rien à confirmer."
    sur_evenement({"type": "confirmation_reponse", "t": time.time(), "reponse": "oui"})
    try:
        return a["action"]()
    except Exception as e:
        return f"L'action a échoué : {type(e).__name__}."


def refuser() -> str:
    global _attente
    with _verrou:
        a, _attente = _attente, None
    sur_evenement({"type": "confirmation_reponse", "t": time.time(), "reponse": "non"})
    return a["refus"] if a else "Il n'y avait rien à annuler."
