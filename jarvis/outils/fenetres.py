"""Outil fenetres : les fenêtres des applications, par l'API Windows (user32, dwmapi, par ctypes, sans dépendance).
Placer une application à gauche ou à droite de son écran, en plein écran, sur l'autre écran, restaurer, réduire toutes
les autres, fermer (confirmation demandée si le titre montre du travail non enregistré), lister.
L'application se désigne par un nom courant (« chrome », « le bloc-notes », « discord ») : on cherche d'abord le nom
du programme, puis un mot du titre ; à égalité, la fenêtre la plus récemment au premier plan gagne."""
import ctypes
import re
import time
import unicodedata
from ctypes import wintypes

import psutil

from .. import confirmations

NOM = "fenetres"
DESCRIPTION = ("Gère les fenêtres ouvertes : placer une application sur la moitié gauche ou droite de l'écran, la mettre en "
               "plein écran, l'envoyer sur l'autre écran, la restaurer, réduire toutes les autres fenêtres pour se "
               "concentrer sur une seule, fermer une application (une confirmation est demandée si elle a du travail non "
               "enregistré), ou lister les fenêtres ouvertes.")
PARAMETRES = {
    "action": {"type": "string", "enum": ["gauche", "droite", "plein_ecran", "autre_ecran", "restaurer", "minimiser_autres",
                                          "fermer", "lister"],
               "description": "gauche / droite = moitié de l'écran ; minimiser_autres = réduire tout sauf cette application"},
    "application": {"type": "string", "description": "Nom de l'application ou mot du titre : chrome, bloc-notes, word, discord, spotify…"},
}
REQUIS = ["action"]

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE, SW_SHOWMINNOACTIVE = 3, 6, 9, 7
GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x00000080
WM_CLOSE = 0x0010
DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS = 14, 9
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
MONITOR_DEFAULTTONEAREST = 2

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

# Types déclarés : sur Windows 64 bits, un handle passé ou rendu comme un int 32 bits serait tronqué.
for _nom_fn, _args, _res in [
    ("EnumWindows", [EnumWindowsProc, wintypes.LPARAM], wintypes.BOOL),
    ("IsWindowVisible", [wintypes.HWND], wintypes.BOOL), ("IsWindow", [wintypes.HWND], wintypes.BOOL),
    ("IsIconic", [wintypes.HWND], wintypes.BOOL), ("IsZoomed", [wintypes.HWND], wintypes.BOOL),
    ("GetWindow", [wintypes.HWND, wintypes.UINT], wintypes.HWND),
    ("GetWindowLongW", [wintypes.HWND, ctypes.c_int], ctypes.c_long),
    ("GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int),
    ("GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
    ("GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
    ("ShowWindow", [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
    ("SetWindowPos", [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
    ("GetWindowRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
    ("SetForegroundWindow", [wintypes.HWND], wintypes.BOOL), ("GetForegroundWindow", [], wintypes.HWND),
    ("PostMessageW", [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
    ("MonitorFromWindow", [wintypes.HWND, wintypes.DWORD], wintypes.HMONITOR),
    ("GetMonitorInfoW", [wintypes.HMONITOR, ctypes.c_void_p], wintypes.BOOL),
    ("EnumDisplayMonitors", [wintypes.HDC, ctypes.c_void_p, MonitorEnumProc, wintypes.LPARAM], wintypes.BOOL),
    ("keybd_event", [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t], None),
]:
    _f = getattr(user32, _nom_fn)
    _f.argtypes, _f.restype = _args, _res
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.UINT]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT), ("showCmd", wintypes.UINT),
                ("ptMinPosition", wintypes.POINT), ("ptMaxPosition", wintypes.POINT), ("rcNormalPosition", wintypes.RECT)]


# noms courants -> morceaux de nom de programme
SYNONYMES = {
    "bloc-notes": ["notepad"], "bloc notes": ["notepad"], "notepad": ["notepad"], "navigateur": ["chrome", "msedge", "firefox", "brave", "opera"],
    "chrome": ["chrome"], "google chrome": ["chrome"], "edge": ["msedge"], "firefox": ["firefox"], "explorateur": ["explorer"],
    "explorateur de fichiers": ["explorer"], "fichiers": ["explorer"], "word": ["winword"], "excel": ["excel"], "powerpoint": ["powerpnt"],
    "vs code": ["code"], "visual studio code": ["code"], "code": ["code"], "discord": ["discord"], "spotify": ["spotify"],
    "obs": ["obs64", "obs"], "steam": ["steamwebhelper", "steam"], "telegram": ["telegram"], "filmora": ["filmora"],
    "vlc": ["vlc"], "terminal": ["windowsterminal", "cmd", "powershell"], "calculatrice": ["calculatorapp", "calc"],
    "paint": ["mspaint"], "teams": ["ms-teams", "teams"], "outlook": ["outlook", "olk"], "jarvis": ["jarvis"],
}
# titres qui trahissent du travail non enregistré
_NON_ENREGISTRE = re.compile(r"^\s*\*|\*\s*[-—]|●|•\s|\bmodifi[ée]\b|\bnon enregistr|\bunsaved\b|\bnot saved\b|\(modified\)|\bsans titre\b.*\*",
                             re.IGNORECASE)


def _normaliser(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


# =============================================================================================
# Inventaire des fenêtres
# =============================================================================================
def _titre(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, b, n + 1)
    return b.value


def _masquee(hwnd) -> bool:
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return bool(cloaked.value)


def lister_fenetres() -> list[dict]:
    """Les fenêtres d'application visibles, de la plus en avant à la plus en arrière."""
    fenetres = []

    def rappel(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4) or _masquee(hwnd):   # 4 = GW_OWNER
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        titre = _titre(hwnd)
        if not titre or titre in ("Program Manager", "Paramètres", "Settings"):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            programme = psutil.Process(pid.value).name().lower().removesuffix(".exe")
        except Exception:
            programme = ""
        fenetres.append({"hwnd": hwnd, "titre": titre, "programme": programme, "pid": pid.value,
                         "reduite": bool(user32.IsIconic(hwnd)), "agrandie": bool(user32.IsZoomed(hwnd))})
        return True

    user32.EnumWindows(EnumWindowsProc(rappel), 0)
    return fenetres


def trouver(application: str, fenetres: list[dict] | None = None) -> dict | None:
    fenetres = lister_fenetres() if fenetres is None else fenetres
    voulu = _normaliser(application)
    voulu = re.sub(r"^(le |la |les |l'|mon |ma |mes |l )", "", voulu).strip()
    if not voulu:
        return None
    programmes = SYNONYMES.get(voulu, [voulu.replace(" ", "")])
    for f in fenetres:                                   # 1. le programme
        if any(p in f["programme"] for p in programmes):
            return f
    for f in fenetres:                                   # 2. un mot du titre
        if voulu in _normaliser(f["titre"]):
            return f
    return None


# =============================================================================================
# Écrans et géométrie
# =============================================================================================
def ecrans() -> list[dict]:
    resultat = []

    def rappel(hmon, hdc, rect, _):
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        w = info.rcWork
        resultat.append({"hmon": hmon, "travail": (w.left, w.top, w.right, w.bottom), "principal": bool(info.dwFlags & 1)})
        return True

    user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(rappel), 0)
    return sorted(resultat, key=lambda e: e["travail"][:2])


def _ecran_de(hwnd) -> dict:
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    return next((e for e in ecrans() if e["hmon"] == hmon), ecrans()[0])


def _bordures(hwnd) -> tuple[int, int, int, int]:
    """Les bordures invisibles de Windows 10 : sans les compenser, deux fenêtres côte à côte laissent un espace."""
    fen = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(fen))
    cadre = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(cadre), ctypes.sizeof(cadre)) != 0:
        return 0, 0, 0, 0
    return cadre.left - fen.left, cadre.top - fen.top, fen.right - cadre.right, fen.bottom - cadre.bottom


def _placer(hwnd, x, y, largeur, hauteur):
    if user32.IsZoomed(hwnd) or user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.05)
    g, h, d, b = _bordures(hwnd)
    user32.SetWindowPos(hwnd, 0, x - g, y - h, largeur + g + d, hauteur + h + b, SWP_NOZORDER)


def rect(hwnd) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def premier_plan(hwnd):
    """SetForegroundWindow est refusé à un processus d'arrière-plan : une pression d'Alt fictive le débloque.
    Alt reste enfoncé pendant une touche neutre (F24) : un Alt seul, relâché, ouvre le menu de la fenêtre, qui avale
    ensuite la première touche tapée (mesuré : « Bonjour » arrivait « onjour » dans le Bloc-notes)."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x87, 0, 0, 0)
    user32.keybd_event(0x87, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 2, 0)


# =============================================================================================
# Les actions
# =============================================================================================
_SEPARATEUR_TITRE = re.compile(r"\s[-—–]\s")     # le Bloc-notes sépare par une espace insécable : « Sans titre - Bloc-notes »


def _nom(f: dict) -> str:
    return _SEPARATEUR_TITRE.split(f["titre"])[-1].strip() or f["programme"]


def _document(f: dict) -> str:
    """Le nom du document, sans l'astérisque de modification (qui serait lue à voix haute)."""
    morceaux = _SEPARATEUR_TITRE.split(f["titre"])
    return morceaux[0].strip().lstrip("*●• ").strip() if len(morceaux) > 1 else ""


def moitie(f: dict, cote: str) -> str:
    e = _ecran_de(f["hwnd"])
    gauche, haut, droite, bas = e["travail"]
    demi = (droite - gauche) // 2
    _placer(f["hwnd"], gauche if cote == "gauche" else gauche + demi, haut, demi, bas - haut)
    premier_plan(f["hwnd"])
    return f"{_nom(f)} est à {cote}."


def plein_ecran(f: dict) -> str:
    user32.ShowWindow(f["hwnd"], SW_MAXIMIZE)
    premier_plan(f["hwnd"])
    return f"{_nom(f)} est en plein écran."


def restaurer(f: dict) -> str:
    user32.ShowWindow(f["hwnd"], SW_RESTORE)
    premier_plan(f["hwnd"])
    return f"{_nom(f)} est restaurée."


def autre_ecran(f: dict) -> str:
    liste = ecrans()
    if len(liste) < 2:
        return "Un seul écran est branché : il n'y a pas d'autre écran où l'envoyer."
    actuel = _ecran_de(f["hwnd"])
    i = next(i for i, e in enumerate(liste) if e["hmon"] == actuel["hmon"])
    cible = liste[(i + 1) % len(liste)]
    agrandie = bool(user32.IsZoomed(f["hwnd"]))
    if agrandie:
        user32.ShowWindow(f["hwnd"], SW_RESTORE)
    g, h, d, b = rect(f["hwnd"])
    ag, ah, ad, ab = actuel["travail"]
    cg, ch, cd, cb = cible["travail"]
    # même place relative, même taille bornée au nouvel écran
    largeur, hauteur = min(d - g, cd - cg), min(b - h, cb - ch)
    x = cg + int((g - ag) / max(1, ad - ag) * (cd - cg))
    y = ch + int((h - ah) / max(1, ab - ah) * (cb - ch))
    user32.SetWindowPos(f["hwnd"], 0, min(x, cd - largeur), min(y, cb - hauteur), largeur, hauteur, SWP_NOZORDER)
    if agrandie:
        user32.ShowWindow(f["hwnd"], SW_MAXIMIZE)
    premier_plan(f["hwnd"])
    return f"{_nom(f)} est passée sur l'autre écran."


def minimiser_autres(f: dict, fenetres: list[dict], garder=lambda f: False) -> str:
    n = 0
    for autre in fenetres:
        if autre["hwnd"] == f["hwnd"] or autre["reduite"] or garder(autre):
            continue
        user32.ShowWindow(autre["hwnd"], SW_SHOWMINNOACTIVE)
        n += 1
    premier_plan(f["hwnd"])
    return f"J'ai réduit {n} fenêtre{'s' if n > 1 else ''} : il ne reste que {_nom(f)}."


def non_enregistre(f: dict) -> bool:
    return bool(_NON_ENREGISTRE.search(f["titre"]))


def _fermer_maintenant(f: dict) -> str:
    user32.PostMessageW(f["hwnd"], WM_CLOSE, 0, 0)
    for _ in range(20):
        time.sleep(0.1)
        if not user32.IsWindow(f["hwnd"]):
            return f"{_nom(f)} est fermée."
    return f"{_nom(f)} ne s'est pas fermée tout de suite : elle affiche peut-être sa propre question d'enregistrement."


def fermer(f: dict) -> str:
    if non_enregistre(f):
        return confirmations.demander(
            (f"« {_document(f)} », dans {_nom(f)}, n'est pas enregistré. Je ferme quand même ?" if _document(f)
             else f"{_nom(f)} a du travail non enregistré. Je la ferme quand même ?"),
            action=lambda: _fermer_maintenant(f),
            refus=f"Très bien, je laisse {_nom(f)} ouverte.")
    return _fermer_maintenant(f)


def executer(action: str, application: str = "") -> str:
    fenetres = lister_fenetres()
    if action == "lister":
        noms = []
        for f in fenetres[:12]:
            n = _nom(f)
            if n not in noms:
                noms.append(n)
        from . import panneaux
        panneaux.liste("Fenêtres ouvertes", [{"titre": f["titre"], "detail": f["programme"],
                                              "meta": "réduite" if f["reduite"] else ("plein écran" if f["agrandie"] else "")}
                                             for f in fenetres[:20]])
        return f"{len(fenetres)} fenêtres ouvertes, dont " + ", ".join(noms[:6]) + "."
    if not application:
        return "Quelle application, précisément ?"
    f = trouver(application, fenetres)
    if not f:
        return f"Je ne trouve aucune fenêtre ouverte pour « {application} »."
    if action in ("gauche", "droite"):
        return moitie(f, action)
    if action == "plein_ecran":
        return plein_ecran(f)
    if action == "autre_ecran":
        return autre_ecran(f)
    if action == "restaurer":
        return restaurer(f)
    if action == "minimiser_autres":
        # le HUD de Jarvis reste visible : il ne se cache pas lui-même
        return minimiser_autres(f, fenetres, garder=lambda autre: _normaliser(autre["titre"]).startswith("jarvis"))
    if action == "fermer":
        return fermer(f)
    return f"Action « {action} » inconnue. Je sais : gauche, droite, plein_ecran, autre_ecran, restaurer, minimiser_autres, fermer, lister."
