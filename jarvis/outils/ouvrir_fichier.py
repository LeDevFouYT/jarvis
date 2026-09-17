"""Outil ouvrir_fichier : ouvre un fichier ou un dossier par son nom, tel qu'on le dit à voix haute.

Vu en direct le 17/09 : « ouvre le document texte "je suis beau" sur le bureau » (Whisper a entendu « je suis bon »),
« ouvre mes notes sur mon bureau », « ouvre note.md ». Jarvis ne savait ouvrir que des applications, a cherché sur
tout le disque, et a même ouvert le site web « note.md ».

Recherche : le bureau (le sien et le bureau public), Documents, Téléchargements, Images, Vidéos, Musique, sur deux
niveaux ; ou seulement le dossier nommé (« sur le bureau »). Chaque nom est comparé mot à mot à ce qui a été dit, avec
une tolérance aux mots mal entendus (« bon » ~ « beau »), et un bonus quand le type dit (« texte », « pdf », « photo »)
correspond à l'extension. Un gagnant net est ouvert par Windows avec son programme habituel puis amené au premier plan ;
plusieurs candidats proches : Jarvis les nomme et demande lequel."""
import difflib
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

NOM = "ouvrir_fichier"
DESCRIPTION = ("Ouvre un fichier ou un dossier précis par son nom (document texte, notes, PDF, photo, vidéo, dossier…) sur le bureau, "
               "dans Documents, Téléchargements, Images, Vidéos ou Musique, avec son programme habituel. À utiliser pour « ouvre le "
               "fichier… », « ouvre mes notes », « ouvre le document … sur le bureau », « ouvre photo.jpg ». Donne les mots du nom "
               "tels que la personne les a dits, et le type s'il est dit (texte, pdf, image, vidéo, dossier).")
PARAMETRES = {
    "nom": {"type": "string", "description": "Les mots du nom du fichier, tels qu'ils ont été dits (ex. « je suis beau », « notes »)"},
    "type": {"type": "string", "description": "Le type s'il est dit : texte, pdf, image, vidéo, audio, tableur, présentation, dossier"},
    "dossier": {"type": "string", "enum": ["", "bureau", "documents", "telechargements", "images", "videos", "musique"],
                "description": "Le dossier s'il est dit (« sur le bureau » -> bureau), sinon vide"},
}
REQUIS = ["nom"]

direct_dernier = False
_VIDES = set("le la les l un une des de du d mon ma mes ton ta tes son sa ses sur dans au aux a et fichier fichiers document "
             "documents doc truc machin appele appelee nomme nommee qui qu il y ouvre ouvrir moi stp svp plait te vous".split())
TYPES = {
    "texte": {".txt", ".md", ".rtf", ".log", ".ini", ".json", ".csv"}, "note": {".txt", ".md"}, "notes": {".txt", ".md"},
    "pdf": {".pdf"}, "word": {".doc", ".docx", ".odt"}, "tableur": {".xls", ".xlsx", ".ods", ".csv"}, "excel": {".xls", ".xlsx"},
    "presentation": {".ppt", ".pptx", ".odp"}, "powerpoint": {".ppt", ".pptx"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}, "photo": {".png", ".jpg", ".jpeg", ".webp", ".heic"},
    "capture": {".png", ".jpg"}, "video": {".mp4", ".mkv", ".mov", ".avi", ".webm"}, "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a"},
    "musique": {".mp3", ".wav", ".ogg", ".flac", ".m4a"}, "zip": {".zip", ".rar", ".7z"}, "archive": {".zip", ".rar", ".7z"},
    "txt": {".txt"}, "md": {".md"}, "jpg": {".jpg", ".jpeg"}, "png": {".png"}, "mp4": {".mp4"}, "docx": {".docx"}, "mp3": {".mp3"},
}
EXTENSIONS_CONNUES = set().union(*TYPES.values()) | {".exe", ".lnk", ".url", ".bat", ".py", ".html", ".docx"}


def normaliser(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _mots(t: str) -> list[str]:
    return [m for m in normaliser(t).split() if m not in _VIDES]


def dossiers(dossier: str = "") -> list[Path]:
    from .ranger import _DOSSIERS_CONNUS, _dossier_connu
    noms = [dossier] if dossier else ["bureau", "documents", "telechargements", "images", "videos", "musique"]
    trouves = []
    for n in noms:
        p = _dossier_connu(_DOSSIERS_CONNUS[normaliser(n).replace(" ", "")]) if normaliser(n).replace(" ", "") in _DOSSIERS_CONNUS else None
        if p and p.exists():
            trouves.append(p)
        if n == "bureau":
            public = Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop"
            if public.exists():
                trouves.append(public)
    return list(dict.fromkeys(trouves))


def candidats(racines: list[Path], profondeur: int = 2) -> list[Path]:
    sortie = []

    def parcourir(d: Path, niveau: int):
        try:
            for p in d.iterdir():
                if p.name.startswith((".", "~$")) or p.name.lower() == "desktop.ini":
                    continue
                sortie.append(p)
                if p.is_dir() and niveau < profondeur:
                    parcourir(p, niveau + 1)
        except OSError:
            pass
    for r in racines:
        parcourir(r, 1)
    return sortie


def score(dit: str, type_: str, chemin: Path) -> float:
    """0 à 1 : combien les mots dits se retrouvent dans le nom (mots proches acceptés), plus le bonus de type."""
    voulus = _mots(dit)
    extension = chemin.suffix.lower()
    # une extension dite (« note.md ») compte comme un type, et « note » doit ressembler au nom
    ext_dite = next((e for e in EXTENSIONS_CONNUES if normaliser(dit).endswith(" " + e[1:]) or normaliser(dit) == e[1:]), None)
    if ext_dite:
        voulus = [m for m in voulus if m != ext_dite[1:]]
    nom = _mots(chemin.stem if chemin.is_file() else chemin.name) or [normaliser(chemin.stem)]
    if not voulus:
        return 0.0
    total = 0.0
    for m in voulus:
        meilleur = max(difflib.SequenceMatcher(None, m, n).ratio() for n in nom)
        if m in nom:
            meilleur = 1.0
        elif any(n.startswith(m) or m.startswith(n) for n in nom if min(len(n), len(m)) >= 3):
            meilleur = max(meilleur, 0.85)
        elif len(m) <= 3:
            meilleur = 0.0                    # un mot court ne compte que s'il est exact (« edf » n'est pas « saved »)
        total += meilleur if meilleur >= 0.65 else 0.0
    s = total / len(voulus)
    # le nom ne doit pas contenir beaucoup d'autres mots que ceux dits
    s *= 1.0 - 0.08 * max(0, len(nom) - len(voulus))
    familles = [TYPES[t] for t in _mots(type_ + " " + dit) if t in TYPES]
    if ext_dite:
        familles.append({ext_dite})
    if familles:
        s += 0.15 if any(extension in f for f in familles) else -0.2
    if normaliser(type_) == "dossier":
        s += 0.15 if chemin.is_dir() else -0.2
    return round(s, 3)


def choisir(dit: str, type_: str = "", dossier: str = "", racines: list[Path] | None = None) -> tuple[list[tuple[float, Path]], list[Path]]:
    racines = racines if racines is not None else dossiers(dossier)
    uniques = list({p.resolve(): p for p in candidats(racines)}.values())
    notes = sorted(((score(dit, type_, p), p) for p in uniques), key=lambda x: -x[0])
    retenus = [x for x in notes if x[0] >= 0.55][:5]
    if not retenus:
        # « ouvre mes notes sur le bureau » : aucun nom ne ressemble, mais un seul fichier du type dit à cet endroit
        familles = [TYPES[t] for t in _mots(type_ + " " + dit) if t in TYPES]
        if familles:
            du_type = [p for p in uniques if p.is_file() and any(p.suffix.lower() in f for f in familles)
                       and len(p.relative_to(next(r for r in racines if p.is_relative_to(r))).parts) == 1]
            if 1 <= len(du_type) <= 3:
                retenus = [(0.55 if len(du_type) == 1 else 0.5, p) for p in du_type]
    return retenus, racines


def amener_devant(avant: set, programme: str | None = None, delai: float = 6.0):
    """La fenêtre qui vient de s'ouvrir passe devant : lancé par un serveur en arrière-plan, Windows la laisse
    sinon derrière le navigateur plein écran (« il n'ouvre pas le bloc-notes » alors qu'il l'a ouvert)."""
    from . import fenetres as F

    def travail():
        fin = time.time() + delai
        while time.time() < fin:
            nouvelles = [f for f in F.lister_fenetres() if f["hwnd"] not in avant and (not programme or programme in f["programme"])]
            if nouvelles:
                time.sleep(0.2)
                F.premier_plan(nouvelles[0]["hwnd"])
                return
            time.sleep(0.15)
    threading.Thread(target=travail, daemon=True, name="premier-plan").start()


def ouvrir(chemin: Path, ouvreur=os.startfile):
    from . import fenetres as F
    avant = {f["hwnd"] for f in F.lister_fenetres()}
    ouvreur(str(chemin))
    amener_devant(avant)


def executer(nom: str, type: str = "", dossier: str = "", racines: list[Path] | None = None, ouvreur=os.startfile) -> str:
    global direct_dernier
    direct_dernier = False
    from ..cerveau import TITRE
    dit = nom.strip()
    retenus, lieux = choisir(dit, type or "", dossier or "", racines)
    ou = "sur le bureau" if dossier == "bureau" else "sur le bureau, dans Documents, Téléchargements, Images, Vidéos ou Musique" if not dossier else f"dans {dossier}"
    if not retenus:
        direct_dernier = True
        return f"Je ne trouve aucun fichier qui ressemble à « {dit} » {ou}, {TITRE}."
    meilleur_score, meilleur = retenus[0]
    second = retenus[1][0] if len(retenus) > 1 else 0.0
    if meilleur_score - second >= 0.12 or meilleur_score >= 0.95 > second:
        ouvrir(meilleur, ouvreur)
        direct_dernier = True
        return f"J'ouvre « {meilleur.name} », {TITRE}."
    noms = [p.name for _, p in retenus[:3]]
    direct_dernier = True
    return f"J'hésite entre « {' », « '.join(noms[:-1])} » et « {noms[-1]} ». Lequel dois-je ouvrir, {TITRE} ?"
