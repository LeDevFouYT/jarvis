"""Outil telegram : envoie un message texte ou une image sur le Telegram de monsieur.
Jeton TELEGRAM_TOKEN et identifiant TELEGRAM_CHAT_ID dans .secrets."""
from pathlib import Path

import requests

from .. import compteur
from ..config import SECRETS

NOM = "telegram"
DESCRIPTION = ("Envoie un message texte, et éventuellement une image du disque, sur le Telegram de monsieur. "
               "À utiliser quand il demande de lui envoyer quelque chose sur Telegram ou sur son téléphone.")
PARAMETRES = {
    "texte": {"type": "string", "description": "Le message à envoyer"},
    "image": {"type": "string", "description": "Chemin d'une image à joindre (facultatif)"},
}
REQUIS = ["texte"]


def configure() -> bool:
    return bool(SECRETS.get("TELEGRAM_TOKEN")) and bool(SECRETS.get("TELEGRAM_CHAT_ID"))


def envoyer(texte: str, image: str | None = None) -> str:
    if not configure():
        return "Telegram n'est pas configuré, monsieur : il manque TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID dans .secrets."
    from ..telegram_entrant import api
    base = f"{api()}/bot{SECRETS['TELEGRAM_TOKEN']}"
    chat = SECRETS["TELEGRAM_CHAT_ID"]
    compteur.compter("telegram")
    if image:
        p = Path(image)
        if not p.exists():
            return f"L'image {p.name} est introuvable, monsieur."
        with p.open("rb") as f:
            r = requests.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": texte[:1024]},
                              files={"photo": (p.name, f)}, timeout=30)
    else:
        r = requests.post(f"{base}/sendMessage", json={"chat_id": chat, "text": texte[:4096]}, timeout=20)
    if r.status_code != 200:
        desc = r.json().get("description", "") if "json" in r.headers.get("content-type", "") else ""
        return f"Telegram a refusé l'envoi ({r.status_code}{', ' + desc if desc else ''})."
    return "Message envoyé sur Telegram." if not image else "Image envoyée sur Telegram."


def executer(texte: str, image: str | None = None) -> str:
    return envoyer(texte, image)
