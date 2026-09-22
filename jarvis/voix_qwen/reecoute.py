"""La réécoute des voix locales : générer, RÉÉCOUTER avec Whisper, garder la bonne prise. La même boucle que celle des
vidéos (yt-studio, voix_reecoute.py) : un moteur local est aléatoire (il saute un mot, en répète trois, en change un),
donc chaque phrase est transcrite et comparée mot à mot au texte voulu ; une prise fautive est refaite ; parmi les
prises justes on garde celle dont la hauteur colle à la phrase précédente ; la prise gardée est ramenée à -20 dB et
raccordée par des fondus de 20 ms.

Deux différences pour la conversation : on s'arrête à la première prise juste (`prises_mini` = 1, la vidéo en veut 2),
et le comparateur ne compte plus comme fautes ce que Whisper écrit autrement sans que la voix se trompe : « 9h30 »
pour « neuf heures trente », « servie » pour « servi » (19/09 : 5 fausses fautes sur 12 phrases justes).

Rien que numpy : ce module sert aussi bien dans Jarvis (sans torch) que dans le Python de Qwen3-TTS (creer_voix.py).
"""
import difflib
import os
import re
import unicodedata

import numpy as np

NIVEAU_DB = -20.0
FONDU_S = 0.02
PRISES_MAX = 3

# ce que Whisper écrit en chiffres : « vingt heures » -> « 20h », « trois virgule cinq » -> « 3,5 ». On compare les
# VALEURS : « trois » entendu « 4 » ou « vingt heures » entendu « 20h 20h 20h » restent des fautes.
_VALEURS = {"zero": 0, "un": 1, "une": 1, "premier": 1, "premiere": 1, "deux": 2, "deuxieme": 2, "trois": 3,
            "troisieme": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
            "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "vingts": 20,
            "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
_SEPARATEURS = {"heure", "heures", "h", "minute", "minutes", "virgule", "euro", "euros", "pourcent"}


def _nombres_dits(mots: list[str]) -> list[int] | None:
    """« neuf heures trente » -> [9, 30] ; None si un mot n'est ni un nombre ni un séparateur."""
    sortie, total, courant, vu = [], 0, 0, False
    for m in mots + ["h"]:                                     # un séparateur final pousse le dernier nombre
        if m == "et":
            continue
        if m in _VALEURS:
            v = _VALEURS[m]
            courant += 76 if v == 20 and courant % 100 == 4 else v      # quatre-vingt
            vu = True
        elif m in ("cent", "cents"):
            courant, vu = max(courant, 1) * 100, True
        elif m == "mille":
            total, courant, vu = total + max(courant, 1) * 1000, 0, True
        elif m in _SEPARATEURS:
            if vu:
                sortie.append(total + courant)
            total, courant, vu = 0, 0, False
        else:
            return None
    return sortie


def dll_cuda():
    """Dans le Python de Qwen3-TTS : ctranslate2 (Whisper) cherche cuBLAS et cuDNN, que torch livre dans torch/lib."""
    try:
        import torch
        lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        if os.path.isdir(lib):
            os.environ["PATH"] = lib + os.pathsep + os.environ.get("PATH", "")
            os.add_dll_directory(lib)
    except Exception:                                          # noqa: BLE001
        pass


def mots_de(texte: str) -> list[str]:
    t = unicodedata.normalize("NFD", texte.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("'", " ").replace("’", " ").replace("-", " ")
    return re.findall(r"[a-z0-9]+", t)


def _plier(mot: str) -> str:
    """Les finales muettes du français : servi/servie/servis, clément/clémente se disent pareil."""
    for fin in ("es", "s", "x", "e"):
        if mot.endswith(fin) and len(mot) - len(fin) >= 3:
            return mot[: -len(fin)]
    return mot


def ecarts(attendu: str, entendu: str) -> list[tuple[str, str, str]]:
    a, b = mots_de(attendu), mots_de(entendu)
    sm = difflib.SequenceMatcher(a=[_plier(m) for m in a], b=[_plier(m) for m in b], autojunk=False)
    sortie = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        va, vb = a[i1:i2], b[j1:j2]
        if va and any(c.isdigit() for m in vb for c in m):
            dits = _nombres_dits(va)
            ecrits = [int(x) for x in re.findall(r"\d+", " ".join(vb))]
            if dits and dits == ecrits and all(re.fullmatch(r"[0-9]+(?:[a-z]{1,3}[0-9]*)?|[a-z]{1,3}", m) for m in vb):
                continue                                       # « neuf heures trente » entendu « 9h30 »
        sortie.append((op, " ".join(va), " ".join(vb)))
    return sortie


def score(liste) -> int:
    return sum(max(len(x.split()), len(y.split())) for _, x, y in liste)


def rms_db(onde) -> float:
    return 20.0 * float(np.log10(np.sqrt(np.mean(np.square(onde, dtype=np.float64))) + 1e-9))


def hauteur(onde, sr) -> float:
    """Hauteur médiane de la voix (Hz), autocorrélation sur des fenêtres de 40 ms."""
    fen = int(sr * 0.04)
    lo, hi = int(sr / 400), int(sr / 60)
    f0 = []
    for d in range(0, max(0, len(onde) - fen), fen // 2):
        x = onde[d:d + fen].astype(np.float64)
        if np.sqrt(np.mean(x * x)) < 0.01:
            continue
        x = x - x.mean()
        ac = np.correlate(x, x, "full")[fen - 1:]
        if ac[0] <= 0 or len(ac[lo:hi]) == 0:
            continue
        k = int(np.argmax(ac[lo:hi])) + lo
        if ac[k] / ac[0] > 0.5:
            f0.append(sr / k)
    return float(np.median(f0)) if f0 else 0.0


def rogner(onde, sr, seuil=0.004, garde=0.06):
    """Retire le silence de tête et de queue (le modèle en laisse parfois une seconde)."""
    idx = np.where(np.abs(onde) > seuil)[0]
    if len(idx) == 0:
        return onde
    return onde[max(0, idx[0] - int(sr * garde)): min(len(onde), idx[-1] + int(sr * garde))]


def egaliser(onde, sr=24000):
    """-20 dB pour chaque phrase, et des fondus de 20 ms aux deux bouts."""
    gain = 10 ** ((NIVEAU_DB - rms_db(onde)) / 20.0)
    onde = np.clip(onde * min(gain, 8.0), -0.98, 0.98).astype(np.float32)
    fondu = int(sr * FONDU_S)
    if len(onde) > 2 * fondu:
        rampe = np.linspace(0.0, 1.0, fondu, dtype=np.float32)
        onde[:fondu] *= rampe
        onde[-fondu:] *= rampe[::-1]
    return onde


def reecouter(phrase: str, generer, entendre, sr: int, prises_max: int = PRISES_MAX, prises_mini: int = 1,
              hauteur_prec: float = 0.0):
    """`generer(phrase) -> np.ndarray` à `sr`, `entendre(onde) -> str`. Rend (onde prête à jouer, rapport)."""
    prises = []
    for _ in range(prises_max):
        onde = rogner(np.asarray(generer(phrase), dtype=np.float32), sr)
        entendu = entendre(onde)
        e = ecarts(phrase, entendu)
        prises.append({"score": score(e), "ecarts": e, "entendu": entendu, "onde": onde})
        justes = [p for p in prises if p["score"] == 0]
        if len(justes) >= prises_mini:
            break
    meilleur = min(p["score"] for p in prises)
    candidates = [p for p in prises if p["score"] == meilleur]
    if len(candidates) > 1 and hauteur_prec:
        candidates.sort(key=lambda p: abs(hauteur(p["onde"], sr) - hauteur_prec))
    choisie = candidates[0]
    onde = egaliser(choisie["onde"], sr)
    return onde, {"prises": len(prises), "score": choisie["score"], "ecarts": choisie["ecarts"],
                  "entendu": choisie["entendu"], "hauteur_hz": round(hauteur(onde, sr)),
                  "refaite": len(prises) > 1, "fautes_ecartees": [p["ecarts"] for p in prises if p["score"]]}
