"""Outil rappel : programme un rappel à une heure donnée. À l'heure dite, le serveur le dit à voix haute
et l'envoie sur Telegram. Les rappels sont conservés dans workspace/rappels.json pour survivre à un redémarrage."""
import json
import re
import threading
import time
from datetime import datetime, timedelta

from ..config import RACINE

NOM = "rappel"
DESCRIPTION = ("Programme un rappel qui sera dit à voix haute et envoyé sur Telegram à l'heure indiquée : "
               "une heure (18h30, 9 h, 07:15), « dans 20 minutes », « dans 2 heures », ou « demain à 9h ».")
PARAMETRES = {
    "quand": {"type": "string", "description": "L'heure ou le délai, tel que dit par monsieur"},
    "texte": {"type": "string", "description": "Ce qu'il faut rappeler"},
}
REQUIS = ["quand", "texte"]

FICHIER = RACINE / "workspace" / "rappels.json"
sur_rappel = lambda r: None      # branché par le serveur : parle + Telegram + événement
_rappels: list[dict] = []
_minuteurs: dict[str, threading.Timer] = {}
_verrou = threading.Lock()


NOMBRES = {"une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
           "dix": 10, "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
           "midi": "12h", "minuit": "0h"}


def interpreter(quand: str, maintenant: datetime | None = None) -> datetime:
    maintenant = maintenant or datetime.now()
    q = quand.lower().replace("à", " ").replace("a ", " ").strip()
    for demi in ("une demi-heure", "une demi heure", "demi-heure", "demi heure"):
        q = q.replace(demi, "30 minutes")
    q = q.replace("un quart d'heure", "15 minutes").replace("quart d'heure", "15 minutes")
    for mot, n in NOMBRES.items():
        q = re.sub(rf"\b{mot}\b", str(n), q)
    q = q.replace("12 et 12", "12h30")
    m = re.search(r"dans\s+(\d+)\s*(h|heure|heures|min|minute|minutes|s|seconde|secondes)", q)
    if m:
        n, unite = int(m.group(1)), m.group(2)
        if unite.startswith("h"):
            return maintenant + timedelta(hours=n)
        if unite.startswith("s"):
            return maintenant + timedelta(seconds=n)
        return maintenant + timedelta(minutes=n)
    m = re.search(r"(\d{1,2})\s*(?:h|:)\s*(\d{2})?", q)
    if not m:
        raise ValueError(f"je n'ai pas compris l'heure « {quand} »")
    heure, minute = int(m.group(1)), int(m.group(2) or 0)
    cible = maintenant.replace(hour=heure, minute=minute, second=0, microsecond=0)
    if "demain" in q:
        cible += timedelta(days=1)
    elif cible <= maintenant:
        cible += timedelta(days=1)
    return cible


def _sauver():
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(_rappels, ensure_ascii=False, indent=2), encoding="utf-8")


def _declencher(identifiant: str):
    with _verrou:
        r = next((x for x in _rappels if x["id"] == identifiant), None)
        if r:
            _rappels.remove(r)
            _sauver()
        _minuteurs.pop(identifiant, None)
    if r:
        sur_rappel(r)


def _armer(r: dict):
    delai = max(0.0, r["quand"] - time.time())
    t = threading.Timer(delai, _declencher, args=(r["id"],))
    t.daemon = True
    t.start()
    _minuteurs[r["id"]] = t


def programmer(quand: str, texte: str) -> datetime:
    cible = interpreter(quand)
    r = {"id": f"{int(time.time() * 1000)}", "quand": cible.timestamp(), "texte": texte, "cree": time.time()}
    with _verrou:
        _rappels.append(r)
        _sauver()
        _armer(r)
    return cible


def recharger():
    """Au démarrage : réarme les rappels encore à venir, oublie ceux dépassés."""
    if not FICHIER.exists():
        return
    try:
        anciens = json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return
    with _verrou:
        _rappels.clear()
        for r in anciens:
            if r["quand"] > time.time():
                _rappels.append(r)
                _armer(r)
        _sauver()


def liste() -> list[dict]:
    with _verrou:
        return sorted(_rappels, key=lambda r: r["quand"])


def executer(quand: str, texte: str) -> str:
    cible = programmer(quand, texte)
    from . import panneaux, telegram
    panneaux.frise("Rappels à venir", [{"quand": r["quand"], "titre": r["texte"]} for r in liste()])
    delai = cible - datetime.now()
    minutes = round(delai.total_seconds() / 60)
    dans = f"dans {minutes} minutes" if minutes < 120 else f"dans {minutes // 60} heures"
    jour = "demain" if cible.date() != datetime.now().date() else "aujourd'hui"
    suite = "" if telegram.configure() else " Telegram n'est pas configuré : je le dirai seulement à voix haute."
    return f"Rappel programmé {jour} à {cible.hour} h {cible.minute:02d} ({dans}) : {texte}.{suite}"
