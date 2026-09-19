"""OAuth « application de bureau » pour les statistiques privées de SA chaîne (rétention, sources de trafic).

La personne crée dans Google Cloud un identifiant OAuth de type « application de bureau », télécharge son fichier
JSON et l'importe dans les Réglages. « Connecter mon compte » ouvre la page de consentement de Google dans le
navigateur ; Google renvoie un code sur une petite adresse locale (127.0.0.1, port libre, PKCE), Jarvis l'échange
contre un jeton d'accès et un jeton de renouvellement. Portées en lecture seule : youtube.readonly et
yt-analytics.readonly.

Le fichier client et les jetons sont dans .youtube_oauth.json à la racine : jamais servi par le HUD, jamais
versionné, jamais touché par une mise à jour. Sans OAuth, tout ce qui est public marche avec la seule clé."""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .. import compteur
from ..config import RACINE

FICHIER = RACINE / ".youtube_oauth.json"
PORTEES = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly"
_verrou = threading.Lock()
etat_connexion = {"en_cours": False, "message": ""}


def _lire() -> dict:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ecrire(donnees: dict):
    FICHIER.write_text(json.dumps(donnees, indent=2), encoding="utf-8")


def importer_client(contenu: str | bytes) -> dict:
    """Le fichier JSON téléchargé depuis Google Cloud (identifiant OAuth de type application de bureau)."""
    try:
        d = json.loads(contenu)
    except ValueError:
        return {"ok": False, "message": "Ce fichier n'est pas un JSON."}
    client = d.get("installed")
    if not client:
        genre = next(iter(d), "?")
        return {"ok": False, "message": f"Ce fichier est un identifiant « {genre} » : il faut un identifiant de type "
                                        "« application de bureau » (Desktop app)."}
    if not client.get("client_id") or not client.get("client_secret"):
        return {"ok": False, "message": "Le fichier ne contient pas client_id et client_secret."}
    _ecrire({"client": {k: client[k] for k in ("client_id", "client_secret", "auth_uri", "token_uri") if k in client}})
    return {"ok": True, "message": "Identifiant OAuth importé. Cliquez sur « connecter mon compte »."}


def etat() -> dict:
    d = _lire()
    return {"client": bool(d.get("client")), "connecte": bool((d.get("jetons") or {}).get("refresh_token")),
            "compte": d.get("compte", ""), "en_cours": etat_connexion["en_cours"], "message": etat_connexion["message"]}


def oublier():
    d = _lire()
    d.pop("jetons", None)
    d.pop("compte", None)
    d.pop("chaine_id", None)       # sinon l'ancienne chaîne restait « la mienne » après un changement de compte
    _ecrire(d)


def _uri_jeton(client: dict) -> str:
    return os.environ.get("JARVIS_GOOGLE_TOKEN_URI") or client.get("token_uri", "https://oauth2.googleapis.com/token")


def connecter(ouvrir=webbrowser.open, delai: float = 300) -> dict:
    """Lance la connexion dans un fil ; `etat()` dit où elle en est. `ouvrir(url)` ouvre la page de Google."""
    d = _lire()
    client = d.get("client")
    if not client:
        return {"ok": False, "message": "Importez d'abord le fichier OAuth (application de bureau)."}
    if etat_connexion["en_cours"]:
        return {"ok": True, "message": "Connexion déjà en cours : terminez-la dans le navigateur."}
    verificateur = secrets.token_urlsafe(64)
    defi = base64.urlsafe_b64encode(hashlib.sha256(verificateur.encode()).digest()).decode().rstrip("=")
    etat_attendu = secrets.token_urlsafe(16)
    recu: dict = {}

    class Retour(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            recu.update({k: v[0] for k, v in q.items()})
            ok = "code" in q and q.get("state", [""])[0] == etat_attendu
            corps = ("<meta charset=utf-8><body style='font:18px system-ui;background:#06131d;color:#dff6ff;padding:40px'>"
                     + ("Jarvis est connecté à votre compte YouTube. Vous pouvez fermer cet onglet." if ok
                        else "La connexion n'a pas abouti. Revenez dans Jarvis et réessayez.") + "</body>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

    serveur = HTTPServer(("127.0.0.1", 0), Retour)
    serveur.timeout = 1
    redirection = f"http://127.0.0.1:{serveur.server_address[1]}"
    url = client.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth") + "?" + urlencode({
        "client_id": client["client_id"], "redirect_uri": redirection, "response_type": "code", "scope": PORTEES,
        "access_type": "offline", "prompt": "consent", "code_challenge": defi, "code_challenge_method": "S256",
        "state": etat_attendu})

    def attendre():
        fin = time.time() + delai
        try:
            while time.time() < fin and "code" not in recu and "error" not in recu:
                serveur.handle_request()
            if "code" not in recu or recu.get("state") != etat_attendu:
                etat_connexion["message"] = "Connexion abandonnée ou refusée." if recu else "Connexion expirée : réessayez."
                return
            compteur.compter("youtube_oauth")
            r = requests.post(_uri_jeton(client), data={
                "client_id": client["client_id"], "client_secret": client["client_secret"], "code": recu["code"],
                "code_verifier": verificateur, "grant_type": "authorization_code", "redirect_uri": redirection}, timeout=20)
            if r.status_code != 200:
                etat_connexion["message"] = f"Google a refusé l'échange du code ({r.status_code})."
                return
            jetons = r.json()
            jetons["expire"] = time.time() + int(jetons.get("expires_in", 3600)) - 60
            d = _lire()
            d["jetons"] = jetons
            d["compte"] = _nom_de_la_chaine(jetons["access_token"])
            _ecrire(d)
            etat_connexion["message"] = f"Compte connecté : {d['compte'] or 'chaîne YouTube'}."
        except Exception as e:
            etat_connexion["message"] = f"Connexion en échec ({type(e).__name__})."
        finally:
            serveur.server_close()
            etat_connexion["en_cours"] = False

    etat_connexion.update(en_cours=True, message="Page de Google ouverte dans le navigateur : acceptez l'accès en lecture.")
    threading.Thread(target=attendre, daemon=True, name="youtube-oauth").start()
    ouvrir(url)
    return {"ok": True, "message": etat_connexion["message"], "url": url}


def _nom_de_la_chaine(jeton: str) -> str:
    from . import acces
    try:
        compteur.compter("youtube")
        r = requests.get(f"{acces.api()}/channels", params={"part": "snippet", "mine": "true"},
                         headers={"Authorization": f"Bearer {jeton}"}, timeout=20)
        return ((r.json().get("items") or [{}])[0].get("snippet") or {}).get("title", "")
    except Exception:
        return ""


def jeton_acces() -> str | None:
    """Un jeton d'accès valide, renouvelé au besoin ; None si le compte n'est pas connecté."""
    with _verrou:
        d = _lire()
        jetons, client = d.get("jetons") or {}, d.get("client") or {}
        if not jetons.get("refresh_token"):
            return None
        if jetons.get("access_token") and jetons.get("expire", 0) > time.time():
            return jetons["access_token"]
        compteur.compter("youtube_oauth")
        r = requests.post(_uri_jeton(client), data={"client_id": client.get("client_id"), "client_secret": client.get("client_secret"),
                                                     "refresh_token": jetons["refresh_token"], "grant_type": "refresh_token"}, timeout=20)
        if r.status_code != 200:
            if r.status_code in (400, 401) and "invalid_grant" in r.text:
                # accès retiré dans le compte Google : les Réglages ne l'affichent plus comme connecté
                oublier()
            return None
        nouveau = r.json()
        jetons.update(access_token=nouveau["access_token"], expire=time.time() + int(nouveau.get("expires_in", 3600)) - 60)
        d["jetons"] = jetons
        _ecrire(d)
        return jetons["access_token"]


def mon_id_de_chaine() -> str | None:
    """L'identifiant de la chaîne du compte connecté (pour savoir si une chaîne analysée est la sienne)."""
    jeton = jeton_acces()
    if not jeton:
        return None
    from . import acces
    d = _lire()
    if d.get("chaine_id"):
        return d["chaine_id"]
    compteur.compter("youtube")
    r = requests.get(f"{acces.api()}/channels", params={"part": "id", "mine": "true"}, headers={"Authorization": f"Bearer {jeton}"}, timeout=20)
    identifiant = (r.json().get("items") or [{}])[0].get("id")
    if identifiant:
        d["chaine_id"] = identifiant
        _ecrire(d)
    return identifiant
