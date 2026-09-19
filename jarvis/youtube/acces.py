"""L'accès à YouTube : l'API Data v3 avec la clé des Réglages, YouTube Analytics avec OAuth.

- Cache SQLite (cache/youtube.sqlite) : une réponse identique n'est pas redemandée avant son expiration.
- Quota : chaque appel réel ajoute son coût (search = 100 unités, le reste 1) au compteur du jour. Le jour du quota
  est celui de Google (heure du Pacifique) : il repart à zéro à 9 h, heure de Paris. Au-delà de la limite réglée
  (10 000 par défaut), Jarvis refuse l'appel plutôt que de se faire couper.
- Chaque appel réel compte une sortie Internet (compteur du HUD) ; une réponse servie par le cache n'en compte pas.
- La table `releves` garde un instantané par jour (chaîne, vidéos) : le briefing compare avec la veille.

Essais : JARVIS_YOUTUBE_API et JARVIS_YOUTUBE_ANALYTICS remplacent les adresses de Google (faux serveur local)."""
import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from .. import compteur
from ..config import CONFIG, RACINE, SECRETS

CACHE = RACINE / "cache" / "youtube.sqlite"
REGLAGES = CONFIG.setdefault("youtube", {})
COUTS = {"search": 100}
PACIFIQUE, PARIS = ZoneInfo("America/Los_Angeles"), ZoneInfo("Europe/Paris")
_verrou = threading.RLock()


class ErreurYouTube(RuntimeError):
    pass


def api() -> str:
    return (os.environ.get("JARVIS_YOUTUBE_API") or "https://www.googleapis.com/youtube/v3").rstrip("/")


def api_analytics() -> str:
    return (os.environ.get("JARVIS_YOUTUBE_ANALYTICS") or "https://youtubeanalytics.googleapis.com/v2").rstrip("/")


def cle() -> str:
    return SECRETS.get("YOUTUBE_API_KEY", "")


def limite() -> int:
    return int(REGLAGES.get("quota_jour", 10000))


# --------------------------------------------------------------------------------------------- base locale
def _base() -> sqlite3.Connection:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(CACHE), timeout=10)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS reponses (cle TEXT PRIMARY KEY, corps TEXT, expire REAL);
        CREATE TABLE IF NOT EXISTS quota (jour TEXT PRIMARY KEY, unites INTEGER, appels INTEGER);
        CREATE TABLE IF NOT EXISTS releves (sujet TEXT, jour TEXT, donnees TEXT, PRIMARY KEY (sujet, jour));
        CREATE TABLE IF NOT EXISTS vus (sujet TEXT, id TEXT, quand REAL, PRIMARY KEY (sujet, id));
    """)
    return c


@contextlib.contextmanager
def connexion():
    """Une connexion validée puis FERMÉE : sous Windows, une connexion oubliée verrouille le fichier de la base."""
    c = _base()
    try:
        with c:
            yield c
    finally:
        c.close()


def jour_quota() -> str:
    return datetime.now(PACIFIQUE).strftime("%Y-%m-%d")


def quota() -> dict:
    with _verrou, connexion() as c:
        ligne = c.execute("SELECT unites, appels FROM quota WHERE jour = ?", (jour_quota(),)).fetchone() or (0, 0)
    return {"utilise": ligne[0], "appels": ligne[1], "limite": limite(), "reste": max(0, limite() - ligne[0]),
            "remise": "9 h, heure de Paris (minuit en Californie)"}


def _ajouter_quota(unites: int):
    with _verrou, connexion() as c:
        c.execute("INSERT INTO quota (jour, unites, appels) VALUES (?, ?, 1) ON CONFLICT(jour) DO UPDATE SET "
                  "unites = unites + excluded.unites, appels = appels + 1", (jour_quota(), unites))


def releve(sujet: str, jour: str, donnees: dict | None = None) -> dict | None:
    """Lit (sans `donnees`) ou écrit l'instantané d'un sujet pour un jour (heure de Paris)."""
    with _verrou, connexion() as c:
        if donnees is None:
            ligne = c.execute("SELECT donnees FROM releves WHERE sujet = ? AND jour = ?", (sujet, jour)).fetchone()
            return json.loads(ligne[0]) if ligne else None
        c.execute("INSERT OR REPLACE INTO releves VALUES (?, ?, ?)", (sujet, jour, json.dumps(donnees, ensure_ascii=False)))
        return donnees


def dernier_releve_avant(sujet: str, jour: str) -> tuple[str, dict] | None:
    with _verrou, connexion() as c:
        ligne = c.execute("SELECT jour, donnees FROM releves WHERE sujet = ? AND jour < ? ORDER BY jour DESC LIMIT 1",
                          (sujet, jour)).fetchone()
    return (ligne[0], json.loads(ligne[1])) if ligne else None


def deja_vus(sujet: str, ids: list[str], marquer: bool = True) -> set[str]:
    """Les identifiants déjà vus (commentaires lus par un briefing précédent), puis les marque vus (sauf marquer=False)."""
    with _verrou, connexion() as c:
        vus = {r[0] for r in c.execute(f"SELECT id FROM vus WHERE sujet = ? AND id IN ({','.join('?' * len(ids))})",
                                       (sujet, *ids))} if ids else set()
        if marquer:
            c.executemany("INSERT OR IGNORE INTO vus VALUES (?, ?, ?)", [(sujet, i, time.time()) for i in ids])
    return vus


def aujourdhui() -> str:
    return datetime.now(PARIS).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------------------------- appels
def appeler(ressource: str, params: dict, ttl: float = 3600, analytics: bool = False) -> dict:
    """GET sur l'API. `ttl` : durée de validité du cache en secondes (0 = jamais en cache)."""
    from . import oauth
    params = {k: v for k, v in params.items() if v is not None}
    empreinte = hashlib.sha1(json.dumps([analytics, ressource, sorted(params.items())], default=str).encode()).hexdigest()
    maintenant = time.time()
    if ttl:
        with _verrou, connexion() as c:
            ligne = c.execute("SELECT corps, expire FROM reponses WHERE cle = ?", (empreinte,)).fetchone()
        if ligne and ligne[1] > maintenant:
            return json.loads(ligne[0])
    entetes = {}
    if analytics:
        jeton = oauth.jeton_acces()
        if not jeton:
            raise ErreurYouTube("statistiques privées : connectez d'abord votre compte YouTube dans les Réglages")
        entetes["Authorization"] = f"Bearer {jeton}"
        url, cout = f"{api_analytics()}/{ressource}", 1
    else:
        if not cle():
            raise ErreurYouTube("aucune clé API YouTube : ajoutez-la dans les Réglages")
        params = {**params, "key": cle()}
        url, cout = f"{api()}/{ressource}", COUTS.get(ressource, 1)
        if quota()["utilise"] + cout > limite():
            raise ErreurYouTube(f"quota YouTube du jour atteint ({limite()} unités), il repart à 9 h")
    compteur.compter("youtube")
    try:
        r = requests.get(url, params=params, headers=entetes, timeout=20)
    except requests.RequestException as e:
        raise ErreurYouTube(f"YouTube ne répond pas ({type(e).__name__})") from e
    if not analytics and r.status_code not in (400, 401):
        _ajouter_quota(cout)                         # une clé refusée ne consomme pas de quota chez Google
    if r.status_code != 200:
        raison = ""
        try:
            erreur = r.json().get("error", {})
            raison = (erreur.get("errors") or [{}])[0].get("reason", "") or erreur.get("status", "")
        except ValueError:
            pass
        messages = {"quotaExceeded": "quota YouTube du jour épuisé chez Google, il repart à 9 h",
                    "keyInvalid": "Google refuse cette clé API", "API_KEY_INVALID": "Google refuse cette clé API",
                    "accessNotConfigured": "l'API YouTube Data v3 n'est pas activée pour ce projet Google",
                    "commentsDisabled": "les commentaires sont désactivés sur cette vidéo",
                    "forbidden": "accès refusé par YouTube"}
        if raison == "accessNotConfigured" and analytics:
            messages[raison] = "l'API YouTube Analytics n'est pas activée pour ce projet Google (à activer à côté de l'API Data)"
        raise ErreurYouTube(messages.get(raison, f"YouTube a répondu {r.status_code} {raison}".strip()))
    corps = r.json()
    if ttl:
        with _verrou, connexion() as c:
            c.execute("INSERT OR REPLACE INTO reponses VALUES (?, ?, ?)", (empreinte, json.dumps(corps), maintenant + ttl))
    return corps


def tester() -> dict:
    """Réglages : la clé marche-t-elle ? Un appel à une unité (la chaîne officielle YouTube), sans cache."""
    if not cle():
        return {"ok": False, "message": "Collez d'abord la clé API, puis enregistrez."}
    try:
        r = appeler("channels", {"part": "snippet", "forHandle": "@YouTube"}, ttl=0)
    except ErreurYouTube as e:
        return {"ok": False, "message": f"{e}.", "quota": quota()}
    q = quota()
    nom = ((r.get("items") or [{}])[0].get("snippet") or {}).get("title", "?")
    return {"ok": True, "quota": q,
            "message": f"La clé marche (réponse de la chaîne « {nom} »). Quota utilisé aujourd'hui par Jarvis : "
                       f"{q['utilise']} sur {q['limite']} unités, remise à zéro à 9 h."}
