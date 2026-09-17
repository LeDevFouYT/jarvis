"""Outil ranger : trie les fichiers d'un dossier nommé par type puis par mois (Images/2026-09/photo.jpg).
Règles de sûreté :
- uniquement des déplacements, jamais de suppression ni d'écrasement (un doublon de nom devient « nom (2).ext ») ;
- seuls les fichiers posés à la racine du dossier bougent, les sous-dossiers existants ne sont pas touchés ;
- chaque rangement écrit un journal (workspace/rangements/) ; « annule » remet tout en place et retire les dossiers
  créés s'ils sont vides ;
- refus des dossiers système, des racines de disque, du profil utilisateur lui-même, des dossiers de programmes,
  des projets (présence de .git) et du dossier de Jarvis.
`creer_demo()` remplit workspace/demo_rangement/ de faux fichiers datés pour la démo filmée
(python -m jarvis demo_rangement)."""
import ctypes
import json
import os
import re
import random
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from ..config import RACINE

NOM = "ranger"
DESCRIPTION = ("Range un dossier que la personne nomme (téléchargements, bureau, documents, images, un chemin, ou le dossier "
               "de démonstration) : les fichiers sont classés par type puis par mois, uniquement déplacés, jamais supprimés. "
               "Un rangement peut être annulé ensuite par la commande « annule ».")
PARAMETRES = {"dossier": {"type": "string", "description": "Nom ou chemin du dossier : téléchargements, bureau, documents, images, "
                                                          "vidéos, musique, démo, ou un chemin complet"}}
REQUIS = ["dossier"]

JOURNAUX = RACINE / "workspace" / "rangements"
DEMO = RACINE / "workspace" / "demo_rangement"
MAX_FICHIERS = 3000

FAMILLES = {
    "Images": {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "heic", "svg", "ico", "psd", "raw", "cr2", "nef"},
    "Vidéos": {"mp4", "mkv", "mov", "avi", "webm", "wmv", "flv", "m4v", "mts"},
    "Musique": {"mp3", "wav", "flac", "ogg", "m4a", "aac", "wma", "opus"},
    "Documents": {"pdf", "doc", "docx", "odt", "txt", "md", "rtf", "xls", "xlsx", "ods", "csv", "ppt", "pptx", "odp", "epub"},
    "Archives": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"},
    "Programmes": {"exe", "msi", "bat", "cmd", "ps1", "appx", "msix", "apk", "jar"},
    "Code": {"py", "js", "ts", "html", "css", "json", "xml", "yaml", "yml", "c", "cpp", "h", "cs", "java", "go", "rs", "php", "sql", "ipynb"},
    "3D": {"stl", "obj", "fbx", "glb", "gltf", "blend", "3mf"},
    "Polices": {"ttf", "otf", "woff", "woff2"},
    "Raccourcis": {"lnk", "url"},
}


def famille(chemin: Path) -> str:
    ext = chemin.suffix.lower().lstrip(".")
    return next((f for f, exts in FAMILLES.items() if ext in exts), "Autres")


# =============================================================================================
# Trouver le dossier, refuser les dossiers dangereux
# =============================================================================================
_DOSSIERS_CONNUS = {  # FOLDERID de l'API Windows : suit un dossier Téléchargements déplacé sur un autre disque
    "telechargements": "{374DE290-123F-4565-9164-39C4925E467B}", "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "bureau": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}", "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", "images": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "photos": "{33E28130-4E1E-4676-835A-98395C3BC3BB}", "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "musique": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
}


def _dossier_connu(guid: str) -> Path | None:
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
    u = uuid.UUID(guid)
    g = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
    chemin = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(chemin)) != 0:
        return None
    resultat = Path(chemin.value)
    ctypes.windll.ole32.CoTaskMemFree(chemin)
    return resultat


def resoudre(nom: str) -> Path | None:
    import unicodedata
    n = unicodedata.normalize("NFD", nom.lower().strip())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    for prefixe in ("le dossier ", "dossier ", "mes ", "mon ", "ma ", "le ", "la ", "les ", "de ", "du ", "d'"):
        if n.startswith(prefixe):
            n = n[len(prefixe):]
    # « démo », « dossier de démonstration », « demo_rangement »… : le cerveau reformule le nom (vu en direct le 16/09)
    if re.fullmatch(r"(la |le )?demo(nstration)?([ _-]?(de )?rangement)?", n):
        return DEMO
    if n in _DOSSIERS_CONNUS:
        return _dossier_connu(_DOSSIERS_CONNUS[n])
    p = Path(os.path.expandvars(os.path.expanduser(nom.strip().strip('"'))))
    if p.is_absolute() and p.is_dir():
        return p
    # un sous-dossier du profil ou du workspace qui porte ce nom
    for base in (Path.home(), Path.home() / "Documents", Path.home() / "Desktop", RACINE / "workspace"):
        candidat = base / nom.strip()
        if candidat.is_dir():
            return candidat
    return None


def refus(dossier: Path) -> str | None:
    """Une raison de refuser, ou None si le dossier peut être rangé."""
    d = dossier.resolve()
    systeme = [Path(os.environ.get(v, "")) for v in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
                                                        "APPDATA", "LOCALAPPDATA", "ProgramW6432")] + [Path.home() / "AppData"]
    if d.anchor and Path(d.anchor) == d:
        return "c'est la racine d'un disque"
    if d == Path.home().resolve() or d == Path.home().parent.resolve():
        return "c'est le dossier du profil utilisateur lui-même"
    for s in systeme:
        if str(s) not in ("", ".") and (d == s.resolve() or s.resolve() in d.parents):
            return f"c'est un dossier système ({s})"
    parties = {p.lower() for p in d.parts}
    if parties & {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information"}:
        return "c'est un dossier système"
    if RACINE.resolve() == d or RACINE.resolve() in d.parents and d != DEMO.resolve() and DEMO.resolve() not in d.parents:
        return "c'est le dossier de Jarvis"
    if (d / ".git").exists():
        return "c'est un projet de programmation (dossier .git), son organisation compte"
    return None


# =============================================================================================
# Ranger et annuler
# =============================================================================================
def _destination_libre(cible: Path) -> Path:
    if not cible.exists():
        return cible
    for i in range(2, 1000):
        autre = cible.with_name(f"{cible.stem} ({i}){cible.suffix}")
        if not autre.exists():
            return autre
    raise FileExistsError(cible)


def plan(dossier: Path) -> list[tuple[Path, Path]]:
    mouvements = []
    for f in sorted(dossier.iterdir()):
        if not f.is_file() or f.name.startswith(".") or f.name.lower() in ("desktop.ini", "thumbs.db"):
            continue
        attributs = getattr(f.stat(), "st_file_attributes", 0)
        if attributs & 0x6:                                  # caché ou système
            continue
        mois = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m")
        mouvements.append((f, dossier / famille(f) / mois / f.name))
    return mouvements


def ranger(dossier: Path) -> dict:
    raison = refus(dossier)
    if raison:
        return {"ok": False, "message": f"Je refuse de ranger {dossier} : {raison}."}
    mouvements = plan(dossier)
    if not mouvements:
        return {"ok": True, "message": f"Rien à ranger dans {dossier.name} : aucun fichier à sa racine.", "deplaces": 0}
    if len(mouvements) > MAX_FICHIERS:
        return {"ok": False, "message": f"{len(mouvements)} fichiers dans {dossier.name} : c'est trop pour un rangement d'un coup."}
    journal = {"dossier": str(dossier), "date": datetime.now().isoformat(timespec="seconds"), "mouvements": [],
               "dossiers_crees": [], "annule": False}
    JOURNAUX.mkdir(parents=True, exist_ok=True)
    fichier_journal = JOURNAUX / f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}.json"
    compte: dict[str, int] = {}
    for source, cible in mouvements:
        for parent in (cible.parent.parent, cible.parent):
            if not parent.exists():
                parent.mkdir()
                journal["dossiers_crees"].append(str(parent))
        cible = _destination_libre(cible)
        shutil.move(str(source), str(cible))
        journal["mouvements"].append({"de": str(source), "vers": str(cible)})
        compte[famille(source)] = compte.get(famille(source), 0) + 1
        fichier_journal.write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8")  # à chaque pas : jamais perdu
    resume = ", ".join(f"{n} {fam.lower()}" for fam, n in sorted(compte.items(), key=lambda x: -x[1]))
    return {"ok": True, "deplaces": len(mouvements), "familles": compte, "journal": str(fichier_journal),
            "message": f"{dossier.name} est rangé : {len(mouvements)} fichiers classés par type et par mois ({resume}). "
                       f"Dites « annule » pour tout remettre."}


def dernier_journal() -> Path | None:
    if not JOURNAUX.exists():
        return None
    for f in sorted(JOURNAUX.glob("*.json"), reverse=True):
        try:
            if not json.loads(f.read_text(encoding="utf-8")).get("annule"):
                return f
        except Exception:
            continue
    return None


def annuler() -> dict:
    fichier = dernier_journal()
    if not fichier:
        return {"ok": False, "message": "Il n'y a aucun rangement à annuler."}
    journal = json.loads(fichier.read_text(encoding="utf-8"))
    remis, manquants = 0, 0
    for m in reversed(journal["mouvements"]):
        de, vers = Path(m["de"]), Path(m["vers"])
        if vers.exists() and not de.exists():
            shutil.move(str(vers), str(de))
            remis += 1
        else:
            manquants += 1
    for d in sorted(journal["dossiers_crees"], key=len, reverse=True):
        try:
            Path(d).rmdir()                                   # seulement s'il est vide
        except OSError:
            pass
    journal["annule"] = datetime.now().isoformat(timespec="seconds")
    fichier.write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8")
    message = f"Rangement annulé : {remis} fichiers remis à leur place dans {Path(journal['dossier']).name}."
    if manquants:
        message += f" {manquants} fichiers avaient bougé depuis, je n'y ai pas touché."
    return {"ok": True, "remis": remis, "manquants": manquants, "message": message}


def executer(dossier: str) -> str:
    chemin = resoudre(dossier)
    if chemin is None:
        return f"Je ne trouve pas de dossier « {dossier} »."
    if chemin == DEMO and not DEMO.exists():
        creer_demo()
    r = ranger(chemin)
    if r.get("familles"):
        from . import panneaux
        panneaux.graphique(f"Rangement : {chemin.name}", [
            {"nom": fam, "valeur": n, "max": r["deplaces"], "unite": "fichiers"} for fam, n in sorted(r["familles"].items(), key=lambda x: -x[1])])
    return r["message"]


# =============================================================================================
# Le dossier de démonstration
# =============================================================================================
_DEMO_NOMS = [
    "IMG_20260712_183401.jpg", "IMG_20260712_183455.jpg", "IMG_20260803_101122.jpg", "capture_ecran_2026-06-02.png",
    "fond_ecran_espace.png", "logo_chaine_v3.png", "miniature_jarvis_finale.png", "photo_identite.jpg",
    "vlog_vacances_montage.mp4", "rush_tournage_01.mov", "rush_tournage_02.mov", "clip_drone_plage.mp4",
    "podcast_episode_12.mp3", "musique_intro.wav", "bruit_de_fond_pluie.flac",
    "facture_electricite_juin.pdf", "facture_internet_juillet.pdf", "contrat_location.pdf", "cv_2026.docx",
    "notes_reunion.txt", "budget_vacances.xlsx", "liste_courses.txt", "presentation_projet.pptx", "recette_crepes.md",
    "pilotes_carte_graphique.zip", "sauvegarde_photos_2025.7z", "assets_jeu.rar",
    "installateur_obs.exe", "setup_discord.exe", "script_sauvegarde.bat",
    "calculatrice.py", "page_test.html", "config_serveur.json",
    "support_casque.stl", "figurine_dragon.obj",
    "police_titres.ttf", "raccourci_jeu.lnk", "document_sans_extension", "export_inconnu.xyz",
]


def creer_demo(graine: int = 7) -> Path:
    """Remplit (ou remet à neuf) workspace/demo_rangement/ : une quarantaine de faux fichiers, datés sur huit mois."""
    if DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO.mkdir(parents=True)
    hasard = random.Random(graine)
    maintenant = datetime.now()
    for nom in _DEMO_NOMS:
        chemin = DEMO / nom
        chemin.write_bytes(f"Faux fichier de démonstration pour Jarvis : {nom}\n".encode("utf-8") + bytes(hasard.randrange(200, 4000)))
        quand = (maintenant - timedelta(days=hasard.randrange(0, 240), hours=hasard.randrange(0, 24))).timestamp()
        os.utime(chemin, (quand, quand))
    return DEMO
