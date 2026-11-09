"""La couche par système (vidéo 5, demande des utilisateurs : « une version Linux »).

Tout ce qui dépend de Windows passe par ici : ouvrir un fichier ou une adresse, les dossiers connus (Téléchargements,
Bureau…), la mémoire vive, le volume, le verrouillage, lancer un programme sans fenêtre. Sous Linux, l'équivalent
(xdg-open, xdg-user-dir, /proc/meminfo, pactl, loginctl) ; un pouvoir qui n'a pas d'équivalent le dit clairement au
lieu de planter (`Absent`). macOS : `open` pour ouvrir, le reste n'est pas porté.

`SYSTEME` est lu à chaque appel par `systeme()` : le test le force à « linux » pour rejouer les chemins Linux sur ce PC.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SYSTEME = None                       # None : le vrai système ; « linux » / « windows » / « mac » pour les tests

# Ce qui ne marche pas (encore) sous Linux, et pourquoi : affiché dans le README et dit par Jarvis
ABSENTS_LINUX = {
    "superposition": "la fenêtre posée par-dessus le bureau utilise les API de Windows",
    "fenetres": "le placement des fenêtres utilise les API de Windows (X11/Wayland pas encore portés)",
    "ecrire": "la frappe au clavier utilise SendInput de Windows",
    "presse_papiers": "le presse-papiers est lu par les API de Windows",
    "service_cloud": "le service Jarvis Cloud (passerelle + ngrok) n'est livré que pour Windows",
    "installateur": "l'installateur .exe est pour Windows ; sous Linux : installation par le terminal (README)",
}


class Absent(RuntimeError):
    """Un pouvoir qui n'existe pas sur ce système : le message est dit tel quel."""


def systeme() -> str:
    if SYSTEME:
        return SYSTEME
    return "windows" if sys.platform == "win32" else "mac" if sys.platform == "darwin" else "linux"


def est_windows() -> bool:
    return systeme() == "windows"


def verifier(pouvoir: str):
    """Lève Absent si ce pouvoir n'existe pas sur ce système."""
    if systeme() == "linux" and pouvoir in ABSENTS_LINUX:
        raise Absent(f"Pas encore sous Linux : {ABSENTS_LINUX[pouvoir]}.")


SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)       # 0 hors de Windows : Popen l'accepte partout


class BibliothequeAbsente:
    """Ce qu'on obtient à la place d'une DLL Windows sous Linux : le module qui la déclare se charge quand même (ses
    `argtypes` et `restype` sont avalés), et un appel réel lève Absent. Sans ça, `ctypes.WinDLL` au niveau du module
    faisait planter l'import des outils, donc Jarvis entier, au lancement sous Linux (trouvé par tests/linux.py)."""

    def __init__(self, nom: str):
        object.__setattr__(self, "_nom", nom)

    def __getattr__(self, attribut):
        return self

    def __setattr__(self, attribut, valeur):
        pass

    def __call__(self, *a, **k):
        raise Absent(f"Pas encore sous Linux : cette fonction utilise {self._nom}.dll de Windows.")


def dll(nom: str, **options):
    """ctypes.WinDLL sous Windows, une BibliothequeAbsente ailleurs (le vrai système, pas la simulation des tests)."""
    import ctypes
    return ctypes.WinDLL(nom, **options) if sys.platform == "win32" else BibliothequeAbsente(nom)


def _fonction_rappel():
    import ctypes
    return getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)


FONCTION_RAPPEL = _fonction_rappel()     # ctypes.WINFUNCTYPE sous Windows ; CFUNCTYPE ailleurs, pour que le module se charge


def lancer(arguments: list[str], **options) -> subprocess.Popen:
    """Popen sans fenêtre de console sous Windows (creationflags n'existe que là-bas)."""
    if est_windows():
        options.setdefault("creationflags", SANS_FENETRE)
    return subprocess.Popen(arguments, **options)


def ouvrir(cible: str) -> None:
    """Ouvre un fichier, un dossier ou une adresse avec le programme par défaut."""
    s = systeme()
    if s == "windows":
        os.startfile(cible)                                   # noqa: S606 (fichier choisi par la personne)
    elif s == "mac":
        lancer(["open", cible])
    else:
        if not shutil.which("xdg-open") and SYSTEME is None:
            raise Absent("xdg-open est introuvable (paquet xdg-utils)")
        lancer(["xdg-open", cible], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_XDG = {"telechargements": "DOWNLOAD", "downloads": "DOWNLOAD", "bureau": "DESKTOP", "desktop": "DESKTOP",
        "documents": "DOCUMENTS", "images": "PICTURES", "photos": "PICTURES", "videos": "VIDEOS", "musique": "MUSIC"}
_ANGLAIS = {"DOWNLOAD": "Downloads", "DESKTOP": "Desktop", "DOCUMENTS": "Documents", "PICTURES": "Pictures",
            "VIDEOS": "Videos", "MUSIC": "Music"}


def dossier_connu(nom: str) -> Path | None:
    """« telechargements », « bureau »… : le vrai dossier, même déplacé (FOLDERID sous Windows, xdg-user-dir sous Linux)."""
    if est_windows():
        from .outils.ranger import _DOSSIERS_CONNUS, _dossier_connu
        return _dossier_connu(_DOSSIERS_CONNUS[nom]) if nom in _DOSSIERS_CONNUS else None
    cle = _XDG.get(nom)
    if not cle:
        return None
    try:
        sortie = subprocess.run(["xdg-user-dir", cle], capture_output=True, text=True, timeout=5).stdout.strip()
        if sortie and sortie != str(Path.home()):
            return Path(sortie)
    except (OSError, subprocess.SubprocessError):
        pass
    fichier = Path.home() / ".config" / "user-dirs.dirs"          # ce que lit xdg-user-dir, si l'outil manque
    if fichier.exists():
        m = re.search(rf'XDG_{cle}_DIR="([^"]+)"', fichier.read_text(encoding="utf-8", errors="replace"))
        if m:
            return Path(m.group(1).replace("$HOME", str(Path.home())))
    return Path.home() / _ANGLAIS[cle]


def ram_go(meminfo: str | None = None) -> float:
    """La mémoire vive totale, en Go. `meminfo` : le contenu de /proc/meminfo (pour le test)."""
    if est_windows() and meminfo is None:
        import ctypes

        class M(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = M()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round(m.ullTotalPhys / 1024 ** 3, 1)
    try:
        texte = meminfo if meminfo is not None else Path("/proc/meminfo").read_text()
        kio = int(re.search(r"MemTotal:\s+(\d+)\s+kB", texte).group(1))
        return round(kio / 1024 ** 2, 1)
    except (OSError, AttributeError, ValueError):
        return 0.0


def volume_linux(valeur: str | None, executer=None) -> str:
    """Le volume par PulseAudio / PipeWire (pactl). `executer(arguments) -> sortie` : remplacé dans le test."""
    executer = executer or (lambda a: subprocess.run(a, capture_output=True, text=True, timeout=5).stdout)
    if not shutil.which("pactl") and executer is None:
        raise Absent("pactl est introuvable (PulseAudio ou PipeWire)")
    sortie = executer(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    m = re.search(r"(\d+)%", sortie or "")
    actuel = int(m.group(1)) if m else 50
    if valeur is None or str(valeur).strip() == "":
        return f"Le volume est à {actuel} %."
    texte = str(valeur).lower().strip().rstrip("%").strip()
    if texte in ("plus", "fort", "monter", "augmenter", "up"):
        cible = min(100, actuel + 10)
    elif texte in ("moins", "baisser", "diminuer", "down"):
        cible = max(0, actuel - 10)
    else:
        cible = max(0, min(100, int(float(texte.replace(",", ".")))))
    executer(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{cible}%"])
    if cible > 0:
        executer(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
    return f"Volume réglé à {cible} %."


def muet_linux(couper: bool, executer=None) -> str:
    executer = executer or (lambda a: subprocess.run(a, capture_output=True, text=True, timeout=5).stdout)
    executer(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if couper else "0"])
    return "Son coupé." if couper else "Son rétabli."


def verrouiller_linux(executer=None) -> str:
    executer = executer or (lambda a: subprocess.run(a, capture_output=True, text=True, timeout=5).returncode)
    for commande in (["loginctl", "lock-session"], ["xdg-screensaver", "lock"]):
        try:
            if executer(commande) in (0, "", None):
                return "Session verrouillée."
        except (OSError, subprocess.SubprocessError):
            continue
    return "Je n'ai pas réussi à verrouiller la session (loginctl et xdg-screensaver ont refusé)."
