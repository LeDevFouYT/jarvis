"""Outil ecrire : tape un texte dicté dans la fenêtre active, comme au clavier (SendInput, caractères Unicode :
accents, apostrophes typographiques et emojis passent sans dépendre de la disposition du clavier).
Le presse-papiers n'est pas touché. Refus si la fenêtre active est le HUD de Jarvis lui-même."""
import ctypes
import time
from ctypes import wintypes

NOM = "ecrire"
DESCRIPTION = ("Tape un texte dicté dans la fenêtre active (Word, un mail, le bloc-notes, un champ de discussion), exactement "
               "comme au clavier. À utiliser quand la personne dit « écris », « tape », « dicte » ou « écris dans ma fenêtre ». "
               "Le texte doit être écrit tel quel, ponctuation comprise.")
PARAMETRES = {
    "texte": {"type": "string", "description": "Le texte exact à taper"},
    "entree": {"type": "boolean", "description": "Appuyer sur Entrée à la fin (envoyer un message), faux par défaut"},
}
REQUIS = ["texte"]

user32 = ctypes.WinDLL("user32", use_last_error=True)
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x0002, 0x0004
VK_RETURN = 0x0D


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):     # le plus grand membre de l'union : fixe la taille de INPUT
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", _MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


def _touches(texte: str, entree: bool) -> list[INPUT]:
    evenements = []
    for car in texte.replace("\r\n", "\n"):
        if car == "\n":
            for drapeau in (0, KEYEVENTF_KEYUP):
                evenements.append(INPUT(type=INPUT_KEYBOARD, u=_UNION(ki=KEYBDINPUT(wVk=VK_RETURN, dwFlags=drapeau))))
            continue
        code = car.encode("utf-16-le")
        for i in range(0, len(code), 2):                  # un emoji = deux unités UTF-16
            unite = int.from_bytes(code[i:i + 2], "little")
            for drapeau in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                evenements.append(INPUT(type=INPUT_KEYBOARD, u=_UNION(ki=KEYBDINPUT(wScan=unite, dwFlags=drapeau))))
    if entree:
        for drapeau in (0, KEYEVENTF_KEYUP):
            evenements.append(INPUT(type=INPUT_KEYBOARD, u=_UNION(ki=KEYBDINPUT(wVk=VK_RETURN, dwFlags=drapeau))))
    return evenements


def titre_actif() -> str:
    b = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(user32.GetForegroundWindow(), b, 512)
    return b.value


def taper(texte: str, entree: bool = False, pause_s: float = 0.25) -> int:
    """Envoie le texte à la fenêtre active par paquets. Rend le nombre d'événements acceptés par Windows."""
    time.sleep(pause_s)                                   # les touches de la personne sont relâchées
    evenements = _touches(texte, entree)
    envoyes = 0
    for i in range(0, len(evenements), 64):
        paquet = evenements[i:i + 64]
        tableau = (INPUT * len(paquet))(*paquet)
        envoyes += user32.SendInput(len(paquet), tableau, ctypes.sizeof(INPUT))
        time.sleep(0.004)
    return envoyes


def executer(texte: str, entree: bool = False) -> str:
    if not texte:
        return "Il n'y a rien à écrire."
    titre = titre_actif()
    if titre.lower().startswith("jarvis"):
        return "La fenêtre active est Jarvis lui-même : cliquez d'abord dans l'application où écrire, puis redites le texte."
    attendus = len(_touches(texte, entree))
    envoyes = taper(texte, entree)
    if envoyes < attendus:
        return f"Windows a bloqué une partie de la frappe ({envoyes} sur {attendus}) : la fenêtre active est peut-être protégée."
    fin = " et j'ai appuyé sur Entrée" if entree else ""
    return f"C'est écrit dans « {titre or 'la fenêtre active'} »{fin} : {len(texte)} caractères."
