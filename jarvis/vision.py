"""La vision : capture d'un écran (principal ou secondaire) décrite par le modèle de vision d'Ollama.
Un seul gros modèle en VRAM : le cycle décharger le cerveau / charger la vision / la décharger / recharger
le cerveau est orchestré par l'outil voir_ecran."""
import base64
import ctypes
import io
import time

import requests
from PIL import ImageGrab

from .config import CONFIG, SECRETS

# En mode cloud, la vision passe aussi par la passerelle (même URL, même jeton que le cerveau).
_CLOUD = CONFIG["cerveau"].get("mode", "local") == "cloud"
_C = CONFIG["cerveau"].get("cloud", {})
OLLAMA = _C.get("url", "").rstrip("/") if _CLOUD else CONFIG["ollama"]["url"]
_JETON = SECRETS.get("CLOUD_TOKEN") or _C.get("jeton", "")
ENTETES = {"Authorization": f"Bearer {_JETON}"} if _CLOUD and _JETON else {}
MODELE = CONFIG["vision"]["modele"]
LARGEUR_MAX = CONFIG["vision"].get("largeur_max", 1280)

CONSIGNE = ("Vous décrivez une capture d'écran pour un assistant vocal français. "
            "Répondez en français, en deux ou trois phrases, sans liste ni markdown. "
            "Dites ce que la personne est en train de faire (application, contenu, action visible). "
            "Si on vous demande de lire un texte, citez-le fidèlement.")


def ecrans() -> list[dict]:
    """Les moniteurs, via l'API Windows : rectangle en coordonnées de l'écran virtuel et drapeau principal."""
    resultat = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(RECT), ctypes.c_double)

    def rappel(hmon, hdc, lprect, data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcMonitor
        resultat.append({"bbox": (r.left, r.top, r.right, r.bottom), "principal": bool(info.dwFlags & 1)})
        return 1

    ctypes.windll.user32.SetProcessDPIAware()
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, PROC(rappel), 0)
    resultat.sort(key=lambda e: (not e["principal"], e["bbox"][0]))
    return resultat


def capturer(ecran: str = "principal") -> tuple[str, str]:
    """Retourne (JPEG base64, libellé de l'écran capturé)."""
    liste = ecrans()
    e = (ecran or "principal").lower()
    if e.startswith("second") or e in ("2", "deux", "droite"):
        choix = next((m for m in liste if not m["principal"]), None)
        libelle = "l'écran secondaire"
        if choix is None:
            choix = liste[0] if liste else None
            libelle = "l'écran principal (pas d'écran secondaire)"
    elif e in ("tous", "tout", "all"):
        choix, libelle = None, "tous les écrans"
    else:
        choix = next((m for m in liste if m["principal"]), liste[0] if liste else None)
        libelle = "l'écran principal"
    if choix is None:
        image = ImageGrab.grab(all_screens=True)
    else:
        image = ImageGrab.grab(bbox=choix["bbox"], all_screens=True)
    image = image.convert("RGB")
    if image.width > LARGEUR_MAX:
        image = image.resize((LARGEUR_MAX, int(image.height * LARGEUR_MAX / image.width)))
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", quality=80)
    return base64.b64encode(tampon.getvalue()).decode(), libelle


CONSIGNE_WEBCAM = ("Vous décrivez une photo prise à l'instant par la webcam de l'ordinateur, pour un assistant vocal français. "
                   "Répondez en français, en deux ou trois phrases, sans liste ni markdown, en vous adressant à la personne "
                   "(vouvoiement). Décrivez ce qui est visible : la personne, son expression, ce qu'elle tient ou montre, "
                   "le décor. Ne devinez ni l'identité, ni l'âge précis, ni l'origine de quelqu'un. "
                   "Si on vous pose une question précise, répondez-y d'abord.")


def decrire_image(question: str, image_b64: str, consigne: str | None = None) -> str:
    corps = {
        "model": MODELE,
        "messages": [{"role": "system", "content": consigne or CONSIGNE},
                     {"role": "user", "content": question, "images": [image_b64]}],
        "stream": False,
        "keep_alive": CONFIG["vision"].get("keep_alive", 0),
        "options": {"num_ctx": 4096, "temperature": 0.3},
    }
    r = requests.post(f"{OLLAMA}/api/chat", json=corps, headers=ENTETES, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def modele_present() -> bool:
    try:
        noms = [m["name"] for m in requests.get(f"{OLLAMA}/api/tags", headers=ENTETES, timeout=5).json().get("models", [])]
        return any(n == MODELE or n.split(":")[0] == MODELE.split(":")[0] for n in noms)
    except Exception:
        return False
