"""Un faux YouTube (API Data v3, YouTube Analytics, jeton OAuth) avec une chaîne aux chiffres connus d'avance.

La chaîne « Atelier Test » (@ateliertest) a 30 vidéos publiées un jour sur deux à 18 h (heure de Paris), sauf les
vidéos 5, 12 et 20 publiées le samedi à 10 h ; la vidéo 30 date d'hier. Vues : 1 000 + 100 × n pour toutes, sauf trois
exceptions (vidéos 5, 12 et 20 : 9 000, 12 000 et 15 000 vues). Médiane attendue : 2 750. Durée : 600 s, sauf les vidéos 3, 6… (120 s).
Les titres des exceptions contiennent un chiffre et un point d'interrogation.

La vidéo « vid00000001 » porte 12 commentaires : 5 demandent un tutoriel d'installation, 3 une vidéo sur Linux,
4 ne demandent rien. Analytics : une courbe de rétention qui chute de 12 points à 10 % de la vidéo."""
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CHAINE = "UCateliertest0000000000"[:24].ljust(24, "0")
EXCEPTIONS = {5: 9000, 12: 12000, 20: 15000}
COMMENTAIRES = (["Tu peux faire un tuto pour l'installer sur Windows ?", "Un tutoriel d'installation stp", "Comment on l'installe ?",
                 "Fais une vidéo tuto installation svp", "J'aimerais un tutoriel pour l'installation pas à pas"]
                + ["Tu pourrais faire une vidéo sur Linux ?", "Une vidéo sur Linux ce serait top", "Est-ce que ça marche sous Linux ?"]
                + ["Super vidéo", "Merci beaucoup", "Trop fort", "Génial le montage"])


def videos() -> list[dict]:
    hier = datetime.now(timezone.utc).replace(hour=16, minute=0, second=0, microsecond=0) - timedelta(days=1)
    base = hier - timedelta(days=58)                                 # 18 h à Paris en été (16 h UTC), la 30e hier
    sortie = []
    for n in range(1, 31):
        quand = base + timedelta(days=2 * (n - 1))
        titre = f"Épisode {n} de l'atelier"
        if n in EXCEPTIONS:
            quand = (quand - timedelta(days=quand.weekday() - 5)).replace(hour=8)   # le samedi de la semaine, 10 h à Paris
            titre = f"J'ai testé 3 outils : lequel gagne ? (partie {n})"
        sortie.append({"id": f"vid{n:08d}", "titre": titre, "publiee": quand.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "vues": EXCEPTIONS.get(n, 1000 + 100 * n), "duree": "PT2M" if n % 3 == 0 else "PT10M"})
    return sortie


class FauxYouTube:
    def __init__(self):
        self.appels: list[str] = []
        self.analytics: list[str] = []
        faux = self

        class Gestion(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, d, code=200):
                corps = json.dumps(d).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def do_POST(self):
                longueur = int(self.headers.get("Content-Length", 0))
                corps = parse_qs(self.rfile.read(longueur).decode())
                if self.path.startswith("/token"):
                    if corps.get("grant_type", [""])[0] in ("authorization_code", "refresh_token"):
                        return self._json({"access_token": "acces-essai", "refresh_token": "renouvellement-essai", "expires_in": 3600})
                self._json({"error": "invalid_grant"}, 400)

            def do_GET(self):
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                ressource = url.path.rstrip("/").split("/")[-1]
                if url.path.startswith("/analytics"):
                    faux.analytics.append(ressource)
                    if self.headers.get("Authorization") != "Bearer acces-essai":
                        return self._json({"error": {"code": 401, "status": "UNAUTHENTICATED"}}, 401)
                    if q.get("dimensions") == "elapsedVideoTimeRatio":
                        lignes = [[round(i / 20, 2), round(1.0 - (0.12 if i >= 2 else 0) - 0.02 * i, 3)] for i in range(21)]
                        return self._json({"rows": lignes})
                    return self._json({"rows": [["YT_SEARCH", 600], ["RELATED_VIDEO", 300], ["EXT_URL", 100]]})
                if self.headers.get("Authorization") == "Bearer acces-essai" and q.get("mine") == "true":
                    return self._json({"items": [{"id": CHAINE, "snippet": {"title": "Atelier Test"}}]})
                if q.get("key") != "CLE-ESSAI":
                    return self._json({"error": {"code": 400, "errors": [{"reason": "keyInvalid"}]}}, 400)
                faux.appels.append(ressource)
                vids = videos()
                if ressource == "search":
                    return self._json({"items": [{"id": {"channelId": CHAINE}}]})
                if ressource == "channels":
                    if q.get("forHandle") not in (None, "@ateliertest", "@YouTube") and q.get("id") != CHAINE:
                        return self._json({"items": []})
                    titre = "YouTube" if q.get("forHandle") == "@YouTube" else "Atelier Test"
                    return self._json({"items": [{"id": CHAINE, "snippet": {"title": titre, "customUrl": "@ateliertest"},
                                                  "statistics": {"subscriberCount": "4200", "viewCount": "98000", "videoCount": "30"},
                                                  "contentDetails": {"relatedPlaylists": {"uploads": "UU" + CHAINE[2:]}}}]})
                if ressource == "playlistItems":
                    return self._json({"items": [{"contentDetails": {"videoId": v["id"]}} for v in reversed(vids)][: int(q.get("maxResults", 5))]})
                if ressource == "videos":
                    ids = q.get("id", "").split(",")
                    return self._json({"items": [{"id": v["id"], "snippet": {"title": v["titre"], "publishedAt": v["publiee"]},
                                                  "contentDetails": {"duration": v["duree"]},
                                                  "statistics": {"viewCount": str(v["vues"]), "likeCount": "50", "commentCount": "12"}}
                                                 for v in vids if v["id"] in ids]})
                if ressource == "commentThreads":
                    return self._json({"items": [{"id": f"c{i}", "snippet": {"topLevelComment": {"snippet": {
                        "authorDisplayName": f"Spectateur {i}", "textDisplay": t, "likeCount": i, "publishedAt": "2026-09-15T10:00:00Z"}}}}
                        for i, t in enumerate(COMMENTAIRES)]})
                self._json({"error": {"code": 404}}, 404)

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestion)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.serveur.server_address[1]}"

    def arreter(self):
        self.serveur.shutdown()
