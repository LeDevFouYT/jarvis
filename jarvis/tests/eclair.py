"""Test du pouvoir 05, réponse éclair : python -m jarvis.tests.eclair [etiquette] [tours]

Le vrai pipeline (oreilles en mode phrase -> Whisper -> cerveau -> voix Kokoro), sans micro ni haut-parleur :
le micro est un fichier WAV rejoué en temps réel, le haut-parleur un faux qui note l'instant du premier son.
Pour chaque question : fin de la phrase dite -> texte transcrit -> premier jeton du cerveau -> premier son.
« Premier son » compte tout ce que Jarvis fait entendre ; « premier mot utile » exclut les amorces
(« Un instant. ») pour ne pas tricher sur la vraie réponse.
Résultats dans workspace/mesures/eclair_<etiquette>.json. Arrêter le Jarvis lancé avant (même carte, même micro)."""
import json
import statistics
import sys
import threading
import time
import types
import wave
from pathlib import Path

import numpy as np

# --- le faux haut-parleur, installé avant tout import de la voix ------------------------------------------------
SONS: list[float] = []


class _SortieFactice:
    def __init__(self, samplerate=24000, **_):
        self.freq = samplerate
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def write(self, bloc):
        SONS.append(time.time())
        time.sleep(len(bloc) / self.freq)           # la durée réelle de lecture


_faux = types.ModuleType("sounddevice")
_faux.OutputStream = _SortieFactice
_faux.InputStream = _SortieFactice
_faux.query_devices = lambda *a, **k: []
_faux.query_hostapis = lambda *a, **k: []
_faux.default = types.SimpleNamespace(device=(None, None), samplerate=24000)
_faux.PortAudioError = RuntimeError
sys.modules["sounddevice"] = _faux

from .. import oreilles, serveur, voix  # noqa: E402
from ..config import RACINE  # noqa: E402

DOSSIER = RACINE / "modeles" / "tests_eclair"
QUESTIONS = [
    ("heure", "Quelle heure est-il ?"),
    ("presentation", "Présente-toi en une phrase."),
    ("calcul", "Combien font dix-sept fois vingt-trois ?"),
    ("diner", "Donne-moi une idée de dîner rapide."),
    ("machine", "Dans quel état est la machine ?"),
]


def fabriquer(nom: str, question: str) -> tuple[str, float]:
    """« Jarvis, » (voix anglaise : la française le prononce mal) puis la question, à 16 kHz. Rend (chemin, fin de parole)."""
    DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin, meta = DOSSIER / f"{nom}.wav", DOSSIER / f"{nom}.json"
    if chemin.exists() and meta.exists():
        return str(chemin), json.loads(meta.read_text())["fin_parole_s"]
    voix.charger()

    def dire(texte, v, langue):
        a = voix._local(texte, v, langue)
        n = int(len(a) * oreilles.FREQ / voix.FREQ)
        return (np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a) * 32767).astype(np.int16)

    silence = lambda s: np.zeros(int(oreilles.FREQ * s), dtype=np.int16)
    parole = np.concatenate([dire("Jarvis,", "am_michael", "en-us"), silence(0.15), dire(question, "ff_siwis", "fr-fr")])
    # la fin de parole : dernier échantillon au-dessus du bruit
    fort = np.nonzero(np.abs(parole) > 300)[0]
    fin = 0.5 + (fort[-1] + 1) / oreilles.FREQ
    audio = np.concatenate([silence(0.5), parole, silence(4.0)])
    with wave.open(str(chemin), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(oreilles.FREQ); w.writeframes(audio.tobytes())
    meta.write_text(json.dumps({"question": question, "fin_parole_s": round(fin, 3)}))
    return str(chemin), fin


def source_temps_reel(chemin: str, debut: dict):
    """Le fichier rejoué à la vitesse du micro (une tranche de 80 ms toutes les 80 ms)."""
    def generateur(arret):
        from faster_whisper.audio import decode_audio
        a = (np.clip(decode_audio(chemin, sampling_rate=oreilles.FREQ), -1, 1) * 32767).astype(np.int16)
        a = np.concatenate([a, np.zeros((-len(a)) % oreilles.BLOC, dtype=np.int16)])
        debut["t"] = time.time()
        for i in range(0, len(a), oreilles.BLOC):
            if arret.is_set():
                return
            attente = debut["t"] + i / oreilles.FREQ - time.time()
            if attente > 0:
                time.sleep(attente)
            yield a[i:i + oreilles.BLOC]
        while not arret.is_set():                   # puis le silence d'une pièce calme
            time.sleep(oreilles.BLOC / oreilles.FREQ)
            yield np.zeros(oreilles.BLOC, dtype=np.int16)
    return generateur


def mesurer(nom: str, chemin: str, fin_parole: float, file) -> dict:
    while not file.empty():
        file.get_nowait()
    SONS.clear()
    debut, fini = {}, threading.Event()
    resultat = {}

    def sur_texte(texte, infos=None):
        resultat["texte"] = texte
        try:
            infos = infos or {}
            resultat["reponse"] = serveur._dialoguer(texte, langue=infos.get("langue"), fin_parole=infos.get("fin_parole"),
                                                     source="voix", mode=infos.get("mode"))["reponse"]
        finally:
            fini.set()

    o = oreilles.Oreilles(sur_evenement=lambda e: serveur.EMETTEUR.emettre(e), sur_texte=sur_texte,
                          source=source_temps_reel(chemin, debut))
    o.start()
    if not fini.wait(90):
        o.arreter()
        return {"question": nom, "erreur": "pas de réponse en 90 s"}
    voix.VOIX.attendre(60)
    o.arreter()
    t_fin = debut["t"] + fin_parole
    evts = []
    while not file.empty():
        evts.append(file.get_nowait())
    premier = lambda typ, filtre=lambda e: True: next((e["t"] for e in evts if e["type"] == typ and filtre(e)), None)
    amorces = set(getattr(serveur, "AMORCES", []))
    t_transcrit = premier("transcription")
    t_jeton = premier("jeton")
    t_phrase = premier("phrase")
    t_utile = premier("phrase", lambda e: e["texte"] not in amorces)
    t_son = SONS[0] if SONS else None
    # le premier son utile : le premier bloc joué après l'annonce de la première phrase non amorce
    t_son_utile = next((s for s in SONS if t_utile and s >= t_utile), None)
    ms = lambda t: round((t - t_fin) * 1000) if t else None
    return {"question": nom, "texte": resultat.get("texte"), "reponse": (resultat.get("reponse") or "")[:120],
            "transcription_ms": ms(t_transcrit), "premier_jeton_ms": ms(t_jeton), "premiere_phrase_ms": ms(t_phrase),
            "premier_son_ms": ms(t_son), "premier_mot_utile_ms": ms(t_son_utile),
            "premiere_phrase": next((e["texte"] for e in evts if e["type"] == "phrase"), None),
            "latence_hud": next((e for e in evts if e["type"] == "latence"), None)}


def main():
    etiquette = sys.argv[1] if len(sys.argv) > 1 else "mesure"
    tours = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    fichiers = {nom: fabriquer(nom, q) for nom, q in QUESTIONS}
    serveur._brancher_evenements()
    file = serveur.EMETTEUR.abonner()
    # comme le serveur au démarrage : les briques chargées, sans aucune inférence d'essai
    t = time.time()
    serveur._prechauffer()
    for _ in range(600):
        if all(serveur.DEMARRAGE.get(b) for b in ("cerveau", "whisper", "voix")):
            break
        time.sleep(0.1)
    print(f"briques chargées en {time.time() - t:.1f} s")
    serveur.CERVEAU.oublier()
    mesures = []
    # la toute première question après le démarrage, puis les suivantes
    for tour in range(tours):
        for nom, _ in QUESTIONS:
            chemin, fin = fichiers[nom]
            m = mesurer(nom, chemin, fin, file)
            m["tour"] = tour
            m["premiere_apres_demarrage"] = not mesures
            mesures.append(m)
            print(f"  {nom:<13} tour {tour}  transcrit {m.get('transcription_ms')} ms  jeton {m.get('premier_jeton_ms')} ms  "
                  f"son {m.get('premier_son_ms')} ms  utile {m.get('premier_mot_utile_ms')} ms  « {m.get('premiere_phrase')} »")
    chaudes = [m for m in mesures if not m["premiere_apres_demarrage"] and m.get("premier_son_ms") is not None]
    med = lambda cle: round(statistics.median([m[cle] for m in chaudes if m.get(cle) is not None])) if chaudes else None
    bilan = {"etiquette": etiquette, "date": time.strftime("%Y-%m-%d %H:%M"), "questions": len(QUESTIONS), "tours": tours,
             "premiere_apres_demarrage": {k: mesures[0].get(k) for k in ("transcription_ms", "premier_jeton_ms", "premier_son_ms", "premier_mot_utile_ms")},
             "mediane": {k: med(k) for k in ("transcription_ms", "premier_jeton_ms", "premiere_phrase_ms", "premier_son_ms", "premier_mot_utile_ms")},
             "pire_premier_son_ms": max((m["premier_son_ms"] for m in chaudes), default=None),
             "mesures": mesures}
    sortie = RACINE / "workspace" / "mesures" / f"eclair_{etiquette}.json"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: bilan[k] for k in ("premiere_apres_demarrage", "mediane", "pire_premier_son_ms")}, ensure_ascii=False, indent=2))
    print(f"écrit : {sortie}")


if __name__ == "__main__":
    main()
