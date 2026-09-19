"""Outil systeme : volume, coupure du son, capture d'écran dans workspace/captures/, verrouillage de session.
Rien de destructif : pas d'extinction, pas de redémarrage."""
import ctypes
import time
from datetime import datetime

from ..config import RACINE

NOM = "systeme"
DESCRIPTION = ("Actions système : régler le volume (0 à 100, ou plus, ou moins), couper ou remettre le son, "
               "prendre une capture d'écran enregistrée sur le disque, verrouiller la session Windows.")
PARAMETRES = {
    "action": {"type": "string", "enum": ["volume", "muet", "son", "capture", "verrouiller"],
               "description": "volume = régler ; muet = couper ; son = remettre ; capture = capture d'écran ; verrouiller = verrouiller la session"},
    "valeur": {"type": "string", "description": "Pour volume : un nombre de 0 à 100, ou « plus », ou « moins »"},
}
REQUIS = ["action"]

CAPTURES = RACINE / "workspace" / "captures"
sur_evenement = lambda e: None   # branché par le registre


def _volume_interface():
    from comtypes import CLSCTX_ALL, CoInitialize
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    CoInitialize()
    haut_parleurs = AudioUtilities.GetSpeakers()
    if hasattr(haut_parleurs, "EndpointVolume"):
        return haut_parleurs.EndpointVolume
    interface = haut_parleurs.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))


def volume(valeur: str | None) -> str:
    v = _volume_interface()
    actuel = round(v.GetMasterVolumeLevelScalar() * 100)
    if valeur is None or str(valeur).strip() == "":
        return f"Le volume est à {actuel} %."
    texte = str(valeur).lower().strip().rstrip("%").strip()
    if texte in ("plus", "fort", "monter", "augmenter", "up"):
        cible = min(100, actuel + 10)
    elif texte in ("moins", "baisser", "diminuer", "down"):
        cible = max(0, actuel - 10)
    else:
        cible = max(0, min(100, int(float(texte.replace(",", ".")))))
    v.SetMasterVolumeLevelScalar(cible / 100, None)
    if cible > 0 and v.GetMute():
        v.SetMute(0, None)
    return f"Volume réglé à {cible} %."


def muet(couper: bool) -> str:
    v = _volume_interface()
    v.SetMute(1 if couper else 0, None)
    return "Son coupé." if couper else "Son rétabli."


def capture() -> str:
    from PIL import ImageGrab
    CAPTURES.mkdir(parents=True, exist_ok=True)
    chemin = CAPTURES / f"capture_{datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab(all_screens=True).save(chemin)
    from . import source_courante
    sur_evenement({"type": "capture", "t": time.time(), "chemin": str(chemin),
                   "url": f"/workspace/captures/{chemin.name}", "demande": source_courante()})
    return f"Capture enregistrée : {chemin.name} dans workspace/captures."


def verrouiller() -> str:
    if not ctypes.windll.user32.LockWorkStation():
        return "Windows a refusé de verrouiller la session."
    return "Session verrouillée."


def executer(action: str, valeur: str | None = None) -> str:
    a = (action or "").lower().strip()
    if a == "volume":
        return volume(valeur)
    if a in ("muet", "couper"):
        return muet(True)
    if a in ("son", "remettre"):
        return muet(False)
    if a == "capture":
        return capture()
    if a in ("verrouiller", "verrouillage"):
        return verrouiller()
    return f"Action « {action} » inconnue, monsieur. Je sais : volume, muet, son, capture, verrouiller."
