"""Outil rappel : programme un rappel à une heure donnée. À l'heure dite, le serveur le dit à voix haute
et l'envoie sur Telegram. Les rappels sont conservés dans workspace/rappels.json pour survivre à un redémarrage."""
import json
import re
import threading
import time
import unicodedata
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


# Les heures dites en français. Vu à l'audit du 19/09 : « dix-huit heures » donnait 8 h le lendemain (« dix » et
# « huit » remplacés séparément), « 18 heures 30 » donnait 18 h, « dans 1h30 » une heure, « 7 h du soir » 7 h du matin.
_UNITES = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9}
_SPECIAUX = {"dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16}
_DIZAINES = {"vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50}
JOURS_NOMS = _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _normaliser_heure(texte: str) -> str:
    t = unicodedata.normalize("NFD", (texte or "").lower().replace("’", "'"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", t)              # dix-huit, vingt-deux, apres-midi
    return re.sub(r"\s+", " ", t).strip()


def _nombres_en_chiffres(t: str) -> str:
    """« dix huit heures trente cinq » -> « 18 heures 35 » ; « vingt et une » -> « 21 »."""
    mots, sortie, i = t.split(" "), [], 0
    while i < len(mots):
        m = mots[i]
        if m in _DIZAINES:
            n = _DIZAINES[m]
            j = i + 1
            if j < len(mots) and mots[j] == "et" and j + 1 < len(mots) and mots[j + 1] in ("un", "une"):
                n, j = n + 1, j + 2
            elif j < len(mots) and mots[j] in _UNITES and mots[j] not in ("un", "une", "zero"):
                n, j = n + _UNITES[mots[j]], j + 1
            sortie.append(str(n))
            i = j
        elif m == "dix" and i + 1 < len(mots) and mots[i + 1] in ("sept", "huit", "neuf"):
            sortie.append(str(10 + _UNITES[mots[i + 1]]))
            i += 2
        elif m in _SPECIAUX:
            sortie.append(str(_SPECIAUX[m]))
            i += 1
        elif m in _UNITES and m not in ("un", "une"):
            sortie.append(str(_UNITES[m]))
            i += 1
        elif m in ("un", "une") and i + 1 < len(mots) and mots[i + 1].startswith(("heure", "minute", "seconde", "h", "quart", "demi")):
            sortie.append("1")
            i += 1
        else:
            sortie.append(m)
            i += 1
    return " ".join(sortie)


def interpreter(quand: str, maintenant: datetime | None = None) -> datetime:
    maintenant = maintenant or datetime.now()
    q = _nombres_en_chiffres(_normaliser_heure(quand))
    q = re.sub(r"\bmidi\b", "12 h", q)
    q = re.sub(r"\bminuit\b", "0 h", q)
    q = q.replace("demi heure", "30 minutes").replace("quart d'heure", "15 minutes").replace("quart d heure", "15 minutes")
    q = re.sub(r"\b1 30 minutes\b", "30 minutes", q)          # « une demi-heure »
    q = re.sub(r"\b1 15 minutes\b", "15 minutes", q)          # « un quart d'heure »

    # 1. un délai : « dans 20 minutes », « dans 1h30 », « dans une heure et demie », « dans 2 heures 15 »
    m = re.search(r"\bdans\s+(\d+)\s*(heures?|h)(?:\s*(\d{1,2})\s*(?:min(?:utes?)?)?)?(\s+et\s+(demie?|quart))?", q)
    if m:
        minutes = int(m.group(1)) * 60 + int(m.group(3) or 0) + {"demie": 30, "demi": 30, "quart": 15}.get(m.group(5) or "", 0)
        return maintenant + timedelta(minutes=minutes)
    m = re.search(r"\bdans\s+(\d+)\s*(min|minutes?|mn|s|sec|secondes?)\b", q)
    if m:
        n = int(m.group(1))
        return maintenant + (timedelta(seconds=n) if m.group(2).startswith("s") else timedelta(minutes=n))

    # 2. une heure : « 18h30 », « 18 heures 30 », « 7 h du soir », « 9 heures et quart », « 8 h moins le quart », « 07:15 »
    m = re.search(r"\b(\d{1,2})\s*(heures?|h|:)\s*(\d{1,2})?(?:\s*(?:min(?:utes?)?))?", q)
    if not m:
        raise ValueError(f"je n'ai pas compris l'heure « {quand} »")
    heure, minute = int(m.group(1)), int(m.group(3) or 0)
    ecrit_24h = m.group(2) == ":" or m.group(1).startswith("0")      # « 07:15 » : une heure écrite, pas dite
    reste = q[m.end():]
    if not m.group(3):
        if re.match(r"\s*et\s+demie?\b", reste):
            minute = 30
        elif re.match(r"\s*et\s+quart\b", reste):
            minute = 15
        elif re.match(r"\s*moins\s+(le\s+)?quart\b", reste):
            heure, minute = heure - 1, 45
    soir = re.search(r"\b(du soir|de l'?apres midi|de l'?aprem|ce soir|cet apres midi)\b", q)
    matin = re.search(r"\b(du matin|ce matin)\b", q)
    if soir and heure < 12:
        heure += 12
    if not 0 <= heure <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"l'heure « {quand} » n'existe pas")
    cible = maintenant.replace(hour=heure, minute=minute, second=0, microsecond=0)

    # 3. le jour : « demain », « après-demain », « lundi », « le 25 »
    jour_dit = True
    if re.search(r"\bapres demain\b", q):
        cible += timedelta(days=2)
    elif re.search(r"\bdemain\b", q):
        cible += timedelta(days=1)
    elif any(re.search(rf"\b{j}\b", q) for j in _JOURS):
        j = next(i for i, nom in enumerate(_JOURS) if re.search(rf"\b{nom}\b", q))
        ecart = (j - maintenant.weekday()) % 7
        cible += timedelta(days=ecart or (7 if cible <= maintenant else 0))
    elif (d := re.search(r"\ble (\d{1,2})\b(?!\s*(?:h|heures?|:))", q)):
        jour = int(d.group(1))
        annee, mois = maintenant.year, maintenant.month
        for _ in range(3):
            try:
                essai = cible.replace(year=annee, month=mois, day=jour)
            except ValueError:
                essai = None
            if essai and essai > maintenant:
                cible = essai
                break
            mois, annee = (1, annee + 1) if mois == 12 else (mois + 1, annee)
        else:
            raise ValueError(f"je n'ai pas compris le jour « {quand} »")
    else:
        jour_dit = False
    if not jour_dit and cible <= maintenant:
        # « à 7 heures » dit à 17 h : 19 h aujourd'hui plutôt que 7 h demain, sauf si « du matin » est dit
        if not matin and not soir and not ecrit_24h and 1 <= heure <= 11 and cible + timedelta(hours=12) > maintenant:
            cible += timedelta(hours=12)
        else:
            cible += timedelta(days=1)
    return cible


def _sauver():
    # fichier temporaire puis remplacement : une coupure pendant l'écriture ne perd plus tous les rappels
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    temporaire = FICHIER.with_suffix(".tmp")
    temporaire.write_text(json.dumps(_rappels, ensure_ascii=False, indent=2), encoding="utf-8")
    temporaire.replace(FICHIER)


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


RETARD_MAX = 12 * 3600      # un rappel manqué depuis moins de 12 h est dit au démarrage, les plus vieux sont oubliés


def recharger():
    """Au démarrage : réarme les rappels encore à venir. Ceux manqués pendant que Jarvis était éteint (moins de 12 h)
    sont dits tout de suite, marqués « en retard » ; avant le 19/09 ils disparaissaient sans un mot."""
    if not FICHIER.exists():
        return
    try:
        anciens = json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return
    manques = []
    with _verrou:
        _rappels.clear()
        for r in anciens:
            if r["quand"] > time.time():
                _rappels.append(r)
                _armer(r)
            elif time.time() - r["quand"] < RETARD_MAX:
                manques.append({**r, "en_retard": True})
        _sauver()
    for r in manques:
        # recharger() tourne à l'import, avant que le serveur branche sur_rappel : on le cherche au moment de dire
        t = threading.Timer(8.0, lambda r=r: sur_rappel(r))     # le temps que la voix et Telegram soient prêts
        t.daemon = True
        t.start()


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
    ecart = (cible.date() - datetime.now().date()).days
    jour = {0: "aujourd'hui", 1: "demain", 2: "après-demain"}.get(ecart, f"{JOURS_NOMS[cible.weekday()]} {cible.day}")
    suite = "" if telegram.configure() else " Telegram n'est pas configuré : je le dirai seulement à voix haute."
    return f"Rappel programmé {jour} à {cible.hour} h {cible.minute:02d} ({dans}) : {texte}.{suite}"
