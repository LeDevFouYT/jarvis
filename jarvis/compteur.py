"""Compteur des requêtes sorties sur Internet depuis le lancement. Affiché dans le HUD pendant la démo :
0 tant qu'ElevenLabs, Telegram et le cerveau distant ne sont pas utilisés. Tout le reste est local."""
import threading
import time

sorties = 0
details: dict[str, int] = {}
_verrou = threading.Lock()
sur_evenement = lambda e: None   # branché par le serveur


def compter(service: str) -> int:
    global sorties
    with _verrou:
        sorties += 1
        details[service] = details.get(service, 0) + 1
        total = sorties
    sur_evenement({"type": "sortie_internet", "t": time.time(), "service": service, "total": total})
    return total


connexions: set[str] = set()     # connexions tenues ouvertes (écoute du bot Telegram) : montrées, pas comptées en boucle


def ouvrir_connexion(service: str):
    with _verrou:
        nouveau = service not in connexions
        connexions.add(service)
    if nouveau:
        sur_evenement({"type": "connexion_ouverte", "t": time.time(), "service": service})


def fermer_connexion(service: str):
    with _verrou:
        connexions.discard(service)
    sur_evenement({"type": "connexion_fermee", "t": time.time(), "service": service})


def etat() -> dict:
    with _verrou:
        return {"total": sorties, "details": dict(details), "connexions": sorted(connexions)}
