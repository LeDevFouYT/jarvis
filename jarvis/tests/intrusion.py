"""Jarvis n'appartient qu'à cette machine : python -m jarvis.tests.intrusion

Le serveur n'écoute que sur 127.0.0.1, et beaucoup s'arrêtent là en pensant être protégés. Ils ne le sont pas :
un site web peut faire pointer **son propre domaine** vers 127.0.0.1 (« DNS rebinding »). Son JavaScript parle
alors à Jarvis comme s'il était chez lui — sans CORS, sans préflight — et Jarvis obéit : ouvrir un programme,
déplacer des fichiers, regarder l'écran, prendre une photo par la webcam.

Vérifié le 22/09 sur la vraie machine : une requête portant « Host: site-mechant.example » a réellement fait
ranger le dossier Téléchargements (72 fichiers, remis en place ensuite). Depuis, le serveur n'accepte que les
requêtes qui s'adressent à lui par son vrai nom, et aucune page venue d'un autre domaine.

Ce test rejoue l'attaque, et vérifie aussi que l'usage normal n'est pas gêné.
"""
import json
import sys
import urllib.error
import urllib.request

from ._commun import Verifs

SERVEUR = "http://127.0.0.1:8765"
MECHANT = "site-mechant.example"


def appeler(chemin: str, methode="GET", corps=None, entetes=None, delai=30, tout=False):
    """Rend (code, texte). 0 si la connexion n'aboutit pas. `tout` : la réponse entière (sinon les 400 premiers)."""
    donnees = json.dumps(corps).encode() if corps is not None else None
    e = dict(entetes or {})
    if donnees is not None:
        e.setdefault("Content-Type", "application/json")
    requete = urllib.request.Request(SERVEUR + chemin, data=donnees, headers=e, method=methode)
    try:
        with urllib.request.urlopen(requete, timeout=delai) as r:
            return r.status, (r.read() if tout else r.read(400)).decode("utf-8", "replace")
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(400).decode("utf-8", "replace")
    except Exception:
        return 0, ""


def vivant() -> bool:
    return appeler("/etat")[0] == 200


def rebinding(v: Verifs):
    """Un domaine étranger qui pointe sur 127.0.0.1 : tout doit être refusé, y compris la simple lecture."""
    for nom, chemin, methode, corps in [
            ("lire l'état de la machine", "/etat", "GET", None),
            ("faire agir Jarvis (outils)", "/parler", "POST", {"texte": "Ouvre le bloc-notes"}),
            ("écrire dans les réglages", "/reglages", "POST", {"voix": {"moteur": "local"}}),
            ("écouter le flux d'événements", "/events", "GET", None)]:
        code, _ = appeler(chemin, methode, corps, {"Host": MECHANT})
        v.ok(code == 403, f"domaine étranger : {nom} → refusé", f"HTTP {code}")


def page_etrangere(v: Verifs):
    """Une page d'un autre site, même en s'adressant correctement à 127.0.0.1."""
    for nom, chemin, methode, corps in [
            ("lecture", "/etat", "GET", None),
            ("ordre avec outils", "/parler", "POST", {"texte": "Range mes téléchargements"})]:
        code, _ = appeler(chemin, methode, corps, {"Origin": "https://" + MECHANT})
        v.ok(code == 403, f"page d'un autre domaine : {nom} → refusé", f"HTTP {code}")


def usage_normal(v: Verifs):
    """Ce qui doit continuer de marcher : le HUD, les tests, les scripts locaux."""
    code, _ = appeler("/etat")
    v.ok(code == 200, "le HUD local lit toujours l'état", f"HTTP {code}")
    code, _ = appeler("/etat", entetes={"Origin": SERVEUR})
    v.ok(code == 200, "le HUD servi par Jarvis n'est pas pris pour un intrus", f"HTTP {code}")
    code, _ = appeler("/etat", entetes={"Host": "localhost:8765"})
    v.ok(code == 200, "« localhost » est accepté comme « 127.0.0.1 »", f"HTTP {code}")
    code, texte = appeler("/parler", "POST", {"texte": "Jarvis, quelle heure est-il ?"}, delai=90)
    v.ok(code == 200 and "erreur" not in texte[:40], "une demande locale passe toujours", texte[:70])


def secrets(v: Verifs):
    """Les clés ne doivent jamais sortir, même à une page locale."""
    code, texte = appeler("/reglages", tout=True)
    v.ok(code == 200, "les réglages répondent en local", f"HTTP {code}")
    if code == 200:
        d = json.loads(texte) if texte.startswith("{") else {}
        cles = d.get("cles", {})
        exposees = [n for n, x in cles.items() if isinstance(x, dict) and x.get("valeur")]
        v.ok(not exposees, "aucune valeur de clé n'est renvoyée par le serveur", exposees or f"{len(cles)} clés, toutes masquées")


def main() -> int:
    v = Verifs("Intrusion · Jarvis n'appartient qu'à cette machine")
    if not vivant():
        v.ok(False, "Jarvis répond", f"{SERVEUR} est éteint : lancez-le d'abord")
        return v.fin()
    rebinding(v)
    page_etrangere(v)
    usage_normal(v)
    secrets(v)
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
