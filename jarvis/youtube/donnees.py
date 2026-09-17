"""Les données publiques d'une chaîne : par l'API YouTube Data v3 si une clé est saisie, sinon par yt-dlp.

Même forme dans les deux cas :
  chaine(nom)                -> {id, titre, handle, abonnes, vues, nb_videos, uploads, source}
  videos_recentes(chaine, n) -> [{id, titre, publiee (ISO UTC), timestamp, duree_s, vues, likes, commentaires, approx}]
  commentaires(video, n)     -> [{id, auteur, texte, likes, timestamp}]

Coûts API (quota du jour) : une chaîne par @handle ou identifiant = 1 unité, par son nom = 100 (recherche, gardée
7 jours en cache) ; 30 vidéos = 2 unités ; 100 commentaires = 1 unité. Sans clé, yt-dlp lit les pages publiques :
aucun quota, mais 10 à 30 secondes, et le nombre de commentaires d'une vidéo est arrondi (« 1,7 k »), marqué approx.
Chaque lecture compte une sortie Internet ; les réponses sont gardées en cache (cache/youtube.sqlite)."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote_plus

from .. import compteur
from . import acces
from .acces import ErreurYouTube

_HANDLE = re.compile(r"^@?[A-Za-z0-9._-]{3,30}$")
_ID_CHAINE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def source() -> str:
    return "api" if acces.cle() else "yt-dlp"


def _duree_iso(texte: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", texte or "")
    if not m:
        return 0
    j, h, mi, s = (int(x or 0) for x in m.groups())
    return ((j * 24 + h) * 60 + mi) * 60 + s


def _en_cache(cle: str, ttl: float, fonction):
    """Le cache SQLite des réponses, aussi pour yt-dlp (les pages publiques ne changent pas à la minute)."""
    with acces._verrou, acces.connexion() as c:
        ligne = c.execute("SELECT corps, expire FROM reponses WHERE cle = ?", (cle,)).fetchone()
    if ligne and ligne[1] > time.time():
        return json.loads(ligne[0])
    valeur = fonction()
    with acces._verrou, acces.connexion() as c:
        c.execute("INSERT OR REPLACE INTO reponses VALUES (?, ?, ?)", (cle, json.dumps(valeur, ensure_ascii=False), time.time() + ttl))
    return valeur


def _nettoyer_nom(nom: str) -> str:
    nom = (nom or "").strip()
    m = re.search(r"youtube\.com/(@[A-Za-z0-9._-]+|channel/(UC[A-Za-z0-9_-]{22}))", nom)
    if m:
        return m.group(2) or m.group(1)
    return nom


# --------------------------------------------------------------------------------------------- chaîne
def chaine(nom: str) -> dict:
    nom = _nettoyer_nom(nom)
    if not nom.lstrip("@"):
        raise ErreurYouTube("quelle chaîne ? donnez son nom ou son @")
    return _chaine_api(nom) if source() == "api" else _chaine_ytdlp(nom)


def _chaine_api(nom: str) -> dict:
    parts = "snippet,statistics,contentDetails"
    if _ID_CHAINE.match(nom):
        r = acces.appeler("channels", {"part": parts, "id": nom}, ttl=6 * 3600)
    elif nom.startswith("@") or (_HANDLE.match(nom) and " " not in nom and not nom.isdigit() and nom.lower() == nom):
        r = acces.appeler("channels", {"part": parts, "forHandle": nom if nom.startswith("@") else "@" + nom}, ttl=6 * 3600)
        if not r.get("items") and not nom.startswith("@"):
            r = {}
    else:
        r = {}
    if not r.get("items"):
        trouve = acces.appeler("search", {"part": "snippet", "type": "channel", "q": nom.lstrip("@"), "maxResults": 1}, ttl=7 * 86400)
        items = trouve.get("items") or []
        if not items:
            raise ErreurYouTube(f"aucune chaîne trouvée pour « {nom} »")
        r = acces.appeler("channels", {"part": parts, "id": items[0]["id"]["channelId"]}, ttl=6 * 3600)
    if not r.get("items"):
        raise ErreurYouTube(f"aucune chaîne trouvée pour « {nom} »")
    c = r["items"][0]
    s, st = c.get("snippet", {}), c.get("statistics", {})
    return {"id": c["id"], "titre": s.get("title", ""), "handle": s.get("customUrl", ""),
            "abonnes": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
            "vues": int(st.get("viewCount", 0)), "nb_videos": int(st.get("videoCount", 0)),
            "uploads": c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"), "source": "api"}


class _Silence:
    """yt-dlp écrit ses erreurs même en mode quiet ; les nôtres sont rattrapées et dites à la personne."""
    def debug(self, message):
        pass

    info = warning = error = debug


def _ytdlp(url: str, process: bool = True, **options) -> dict:
    """`process=False` : les métadonnées sans choisir de format (deux fois plus rapide, pas de commentaires)."""
    import yt_dlp
    compteur.compter("youtube")
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True, "logger": _Silence(), **options}) as ydl:
        return ydl.extract_info(url, download=False, process=process) or {}


def _chaine_ytdlp(nom: str) -> dict:
    def lire():
        if _ID_CHAINE.match(nom):
            url = f"https://www.youtube.com/channel/{nom}"
        elif nom.startswith("@") or (_HANDLE.match(nom) and " " not in nom):
            url = f"https://www.youtube.com/@{nom.lstrip('@')}"
        else:
            url = None
        info = {}
        if url:
            try:
                info = _ytdlp(f"{url}/videos", extract_flat="in_playlist", playlistend=1)
            except Exception:
                info = {}
        if not info.get("channel_id"):
            recherche = _ytdlp(f"https://www.youtube.com/results?search_query={quote_plus(nom.lstrip('@'))}&sp=EgIQAg%253D%253D", extract_flat=True)
            entree = next((e for e in recherche.get("entries") or [] if e.get("channel_id")), None)
            if not entree:
                raise ErreurYouTube(f"aucune chaîne trouvée pour « {nom} »")
            info = _ytdlp(f"https://www.youtube.com/channel/{entree['channel_id']}/videos", extract_flat="in_playlist", playlistend=1)
        return {"id": info.get("channel_id"), "titre": info.get("channel") or info.get("uploader", ""),
                "handle": info.get("uploader_id", ""), "abonnes": info.get("channel_follower_count"), "vues": None,
                "nb_videos": None, "uploads": None, "source": "yt-dlp"}
    return _en_cache(f"ytdlp:chaine:{nom.lower()}", 6 * 3600, lire)


# --------------------------------------------------------------------------------------------- vidéos
def videos_recentes(ch: dict, n: int = 30) -> list[dict]:
    n = max(1, min(50, int(n)))
    return _videos_api(ch, n) if source() == "api" else _videos_ytdlp(ch, n)


def _videos_api(ch: dict, n: int) -> list[dict]:
    uploads = ch.get("uploads") or ("UU" + ch["id"][2:])
    liste = acces.appeler("playlistItems", {"part": "contentDetails", "playlistId": uploads, "maxResults": n}, ttl=3600)
    ids = [i["contentDetails"]["videoId"] for i in liste.get("items", [])][:n]
    if not ids:
        return []
    r = acces.appeler("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(ids)}, ttl=3600)
    videos = []
    for v in r.get("items", []):
        s, st = v.get("snippet", {}), v.get("statistics", {})
        publiee = s.get("publishedAt", "")
        ts = datetime.fromisoformat(publiee.replace("Z", "+00:00")).timestamp() if publiee else None
        videos.append({"id": v["id"], "titre": s.get("title", ""), "publiee": publiee, "timestamp": ts,
                       "duree_s": _duree_iso(v.get("contentDetails", {}).get("duration", "")),
                       "vues": int(st.get("viewCount", 0)), "likes": int(st["likeCount"]) if "likeCount" in st else None,
                       "commentaires": int(st["commentCount"]) if "commentCount" in st else None, "approx": False})
    return sorted(videos, key=lambda v: v["timestamp"] or 0, reverse=True)


def _videos_ytdlp(ch: dict, n: int) -> list[dict]:
    def lire():
        ids = []
        for onglet in ("videos", "shorts"):
            try:
                info = _ytdlp(f"https://www.youtube.com/channel/{ch['id']}/{onglet}", extract_flat="in_playlist", playlistend=n)
                ids += [e["id"] for e in info.get("entries") or [] if e.get("id")]
            except Exception:
                pass

        def une(vid):
            try:
                d = _ytdlp(f"https://www.youtube.com/watch?v={vid}", process=False)
            except Exception:
                return None
            ts = d.get("timestamp")
            return {"id": vid, "titre": d.get("title", ""), "timestamp": ts,
                    "publiee": datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z") if ts else "",
                    "duree_s": int(d.get("duration") or 0), "vues": int(d.get("view_count") or 0), "likes": d.get("like_count"),
                    "commentaires": d.get("comment_count"), "approx": True}
        with ThreadPoolExecutor(8) as ex:
            videos = [v for v in ex.map(une, list(dict.fromkeys(ids))) if v]
        return sorted(videos, key=lambda v: v["timestamp"] or 0, reverse=True)[:n]
    return _en_cache(f"ytdlp:videos:{ch['id']}:{n}", 3600, lire)


# --------------------------------------------------------------------------------------------- commentaires
def identifiant_video(lien: str) -> str | None:
    from ..outils.resumer_video import identifiant
    return identifiant(lien)


def titre_video(vid: str) -> str:
    try:
        if source() == "api":
            r = acces.appeler("videos", {"part": "snippet", "id": vid}, ttl=86400)
            return ((r.get("items") or [{}])[0].get("snippet") or {}).get("title", "")
        return _en_cache(f"ytdlp:titre:{vid}", 86400, lambda: _ytdlp(f"https://www.youtube.com/watch?v={vid}", process=False).get("title", ""))
    except Exception:
        return ""


def commentaires(vid: str, n: int = 200) -> list[dict]:
    n = max(1, min(1000, int(n)))
    if source() == "api":
        sortie, page = [], None
        while len(sortie) < n:
            r = acces.appeler("commentThreads", {"part": "snippet", "videoId": vid, "maxResults": 100, "order": "time",
                                                 "textFormat": "plainText", "pageToken": page}, ttl=1800)
            for fil in r.get("items", []):
                s = fil["snippet"]["topLevelComment"]["snippet"]
                publie = s.get("publishedAt", "")
                sortie.append({"id": fil["id"], "auteur": s.get("authorDisplayName", ""), "texte": s.get("textDisplay", ""),
                               "likes": int(s.get("likeCount", 0)),
                               "timestamp": datetime.fromisoformat(publie.replace("Z", "+00:00")).timestamp() if publie else None})
            page = r.get("nextPageToken")
            if not page:
                break
        return sortie[:n]

    def lire():
        d = _ytdlp(f"https://www.youtube.com/watch?v={vid}", getcomments=True, format="bestaudio/best",
                   extractor_args={"youtube": {"max_comments": [str(n), "all", "0", "0"], "comment_sort": ["new"]}})
        return [{"id": c.get("id"), "auteur": c.get("author", ""), "texte": c.get("text", ""), "likes": int(c.get("like_count") or 0),
                 "timestamp": c.get("timestamp")} for c in (d.get("comments") or []) if c.get("parent", "root") == "root"][:n]
    return _en_cache(f"ytdlp:commentaires:{vid}:{n}", 1800, lire)
