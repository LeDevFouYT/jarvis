"""Outil chercher_fichiers : par nom ou extension, filtre par période, sur F: et les dossiers utilisateur.
Pas de parcours du disque à chaque appel : un index léger (chemin, nom, extension, date, taille) est construit
au démarrage du serveur en tâche de fond, puis rafraîchi toutes les `fichiers.rafraichir_minutes`."""
import os
import pickle
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from ..config import CONFIG, RACINE

NOM = "chercher_fichiers"
DESCRIPTION = ("Cherche des fichiers sur l'ordinateur (disque F et dossiers de monsieur) par morceau de nom "
               "et/ou par type (extension comme mp4, ou famille : vidéo, image, audio, document, code), "
               "avec un filtre de date : aujourd'hui, hier, cette semaine, ce mois. Au plus 10 résultats, "
               "les plus récents d'abord.")
PARAMETRES = {
    "nom": {"type": "string", "description": "Morceau du nom de fichier (facultatif)"},
    "type": {"type": "string", "description": "Extension (mp4, png…) ou famille : vidéo, image, audio, document, code"},
    "periode": {"type": "string", "enum": ["aujourd'hui", "hier", "cette semaine", "ce mois", "toutes"],
                "description": "Fichiers modifiés pendant cette période"},
}
REQUIS = []

REGLAGES = CONFIG.get("fichiers", {})
FAMILLES = {
    "video": {"mp4", "mkv", "mov", "avi", "webm", "m4v", "wmv"},
    "image": {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff", "psd"},
    "audio": {"mp3", "wav", "flac", "ogg", "m4a", "aac", "opus"},
    "document": {"pdf", "docx", "doc", "txt", "md", "xlsx", "xls", "pptx", "odt", "csv"},
    "code": {"py", "js", "ts", "html", "css", "json", "bat", "ps1", "sh", "gd", "lua", "cs"},
}
_CACHE = RACINE / "cache" / "index_fichiers.pkl"
_MAX = 10

_index: list[tuple] = []          # (chemin, nom_normalise, extension, mtime, taille)
_pret = threading.Event()
_verrou = threading.Lock()
_derniere_construction = 0.0
_duree_construction = 0.0


def _normaliser(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _racines() -> list[Path]:
    return [Path(os.path.expanduser(r)) for r in REGLAGES.get("racines", ["F:/"]) if Path(os.path.expanduser(r)).exists()]


def construire() -> int:
    """Parcourt les racines en évitant les dossiers exclus et cachés. Retourne le nombre de fichiers."""
    global _index, _derniere_construction, _duree_construction
    exclus = set(REGLAGES.get("exclure", []))
    t = time.time()
    nouveau = []
    pile = _racines()
    vus = set()
    while pile:
        dossier = pile.pop()
        try:
            with os.scandir(dossier) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name in exclus or e.name.startswith("."):
                                continue
                            cle = os.path.normcase(e.path)
                            if cle not in vus:
                                vus.add(cle)
                                pile.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            st = e.stat(follow_symlinks=False)
                            ext = e.name.rsplit(".", 1)[-1].lower() if "." in e.name else ""
                            nouveau.append((e.path, _normaliser(e.name), ext, st.st_mtime, st.st_size))
                    except OSError:
                        continue
        except OSError:
            continue
    with _verrou:
        _index = nouveau
        _derniere_construction = time.time()
        _duree_construction = round(_derniere_construction - t, 1)
    _pret.set()
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE.open("wb") as f:
            pickle.dump((nouveau, _derniere_construction), f)
    except OSError:
        pass
    return len(nouveau)


def _boucle():
    global _index, _derniere_construction
    if _CACHE.exists():
        try:
            with _CACHE.open("rb") as f:
                ancien, quand = pickle.load(f)
            with _verrou:
                _index, _derniere_construction = ancien, quand
            _pret.set()
        except Exception:
            pass
    while True:
        age = time.time() - _derniere_construction
        attente = REGLAGES.get("rafraichir_minutes", 10) * 60 - age
        if attente > 0:
            time.sleep(attente)
        construire()


_fil = None


def demarrer_index():
    global _fil
    if _fil is None:
        _fil = threading.Thread(target=_boucle, daemon=True, name="index-fichiers")
        _fil.start()


def etat() -> dict:
    return {"fichiers": len(_index), "pret": _pret.is_set(), "derniere": _derniere_construction,
            "duree_construction_s": _duree_construction}


def _extensions(type_: str | None) -> set | None:
    if not type_:
        return None
    t = _normaliser(type_).strip(". ")
    for famille, exts in FAMILLES.items():
        if t.startswith(famille) or t in ("videos", "images", "audios", "documents", "codes") and t.rstrip("s") == famille:
            return exts
    if t in ("photo", "photos"):
        return FAMILLES["image"]
    if t in ("film", "films"):
        return FAMILLES["video"]
    return {t}


def _depuis(periode: str | None) -> tuple[float, float]:
    maintenant = datetime.now()
    minuit = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    p = _normaliser(periode or "toutes")
    if "aujourd" in p:
        return minuit.timestamp(), float("inf")
    if "hier" in p:
        return (minuit - timedelta(days=1)).timestamp(), minuit.timestamp()
    if "semaine" in p:
        return (minuit - timedelta(days=7)).timestamp(), float("inf")
    if "mois" in p:
        return (minuit - timedelta(days=30)).timestamp(), float("inf")
    return 0.0, float("inf")


def chercher(nom: str | None = None, type: str | None = None, periode: str | None = None) -> list[tuple]:
    demarrer_index()
    _pret.wait(20)
    exts = _extensions(type)
    debut, fin = _depuis(periode)
    motif = _normaliser(nom).strip() if nom else ""
    with _verrou:
        candidats = [e for e in _index
                     if (not exts or e[2] in exts) and debut <= e[3] < fin and (not motif or motif in e[1])]
    candidats.sort(key=lambda e: e[3], reverse=True)
    return candidats[:_MAX]


def executer(nom: str | None = None, type: str | None = None, periode: str | None = None) -> str:
    if not _pret.is_set():
        return "L'index des fichiers se construit encore, monsieur. Réessayez dans une minute."
    resultats = chercher(nom, type, periode)
    from . import panneaux
    panneaux.liste("Fichiers" + (f" : {nom}" if nom else ""), [
        {"titre": Path(c).name, "detail": str(Path(c).parent),
         "meta": f"{datetime.fromtimestamp(t):%d/%m %H:%M} · {s / 1024 ** 2:.1f} Mo"} for c, _, _, t, s in resultats],
        vide="Aucun fichier trouvé.")
    quoi = " ".join(x for x in [f"« {nom} »" if nom else "", f"de type {type}" if type else "",
                                 periode if periode and periode != "toutes" else ""] if x)
    if not resultats:
        return f"Aucun fichier {quoi}, monsieur." if quoi else "Aucun fichier trouvé, monsieur."
    lignes = []
    for chemin, _, _, mtime, taille in resultats:
        p = Path(chemin)
        quand = datetime.fromtimestamp(mtime)
        date = f"{quand.hour} h {quand.minute:02d}" if quand.date() == datetime.now().date() else f"le {quand.day}/{quand.month:02d}"
        lignes.append(f"{p.name} dans {p.parent} ({date}, {taille / 1024 ** 2:.1f} Mo)")
    return f"{len(resultats)} fichier{'s' if len(resultats) > 1 else ''} {quoi} : " + " ; ".join(lignes) + "."
