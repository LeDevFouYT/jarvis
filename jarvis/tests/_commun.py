"""Outils partagés par les tests des pouvoirs (python -m jarvis.tests.pouvoirs).

- `faux_haut_parleur()` : à appeler AVANT d'importer la voix ou le serveur. Rien ne sort des haut-parleurs ; chaque
  bloc « joué » dort sa durée réelle et son instant est noté (SONS).
- `phrase_wav(nom, morceaux)` : une phrase de test dite par Kokoro, à 16 kHz, mise en cache dans modeles/tests_pouvoirs.
- `SourceScenario` : un micro de test ; on y joue des fichiers et du silence, au rythme réel (80 ms toutes les 80 ms).
- `Verifs` : les vérifications affichées ✓ / ✗ et le code de sortie."""
import json
import queue
import sys
import threading
import time
import types
import wave

import numpy as np

SONS: list[float] = []


class _SortieFactice:
    def __init__(self, samplerate=24000, **_):
        self.freq = samplerate

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, bloc):
        SONS.append(time.time())
        time.sleep(len(bloc) / self.freq)


def faux_haut_parleur():
    if "sounddevice" in sys.modules and getattr(sys.modules["sounddevice"], "_faux", False):
        return SONS
    faux = types.ModuleType("sounddevice")
    faux._faux = True
    faux.OutputStream = _SortieFactice
    faux.InputStream = _SortieFactice
    faux.query_devices = lambda *a, **k: []
    faux.query_hostapis = lambda *a, **k: []
    faux.default = types.SimpleNamespace(device=(None, None), samplerate=24000)
    faux.PortAudioError = RuntimeError
    sys.modules["sounddevice"] = faux
    return SONS


class Verifs:
    def __init__(self, titre: str):
        self.titre, self.echecs, self.total = titre, [], 0
        print(f"\n=== {titre} ===")

    def ok(self, condition, message: str, detail=""):
        self.total += 1
        print(f"  {'✓' if condition else '✗'} {message}" + (f"  [{detail}]" if detail != "" else ""), flush=True)
        if not condition:
            self.echecs.append(message)
        return bool(condition)

    def info(self, message: str):
        print(f"    · {message}", flush=True)

    def fin(self) -> int:
        reussis = self.total - len(self.echecs)
        print(f"--- {self.titre} : {reussis}/{self.total} vérifications réussies")
        return 0 if not self.echecs else 1


def phrase_wav(nom: str, morceaux: list[tuple[str, str, str]], silence_avant: float = 0.4, silence_apres: float = 0.2) -> tuple[str, float]:
    """`morceaux` : [(texte, voix Kokoro, code langue)]. Rend (chemin du WAV 16 kHz, durée de parole en secondes)."""
    from .. import voix
    from ..config import RACINE
    dossier = RACINE / "modeles" / "tests_pouvoirs"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin, meta = dossier / f"{nom}.wav", dossier / f"{nom}.json"
    signature = json.dumps(morceaux, ensure_ascii=False)
    if chemin.exists() and meta.exists() and json.loads(meta.read_text(encoding="utf-8")).get("signature") == signature:
        return str(chemin), json.loads(meta.read_text(encoding="utf-8"))["parole_s"]
    voix.charger()
    parties = []
    for texte, v, code in morceaux:
        a = voix._local(texte, v, code)
        n = int(len(a) * 16000 / voix.FREQ)
        parties.append((np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a) * 32767).astype(np.int16))
        parties.append(np.zeros(int(16000 * 0.12), dtype=np.int16))
    parole = np.concatenate(parties)
    audio = np.concatenate([np.zeros(int(16000 * silence_avant), dtype=np.int16), parole,
                            np.zeros(int(16000 * silence_apres), dtype=np.int16)])
    with wave.open(str(chemin), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(audio.tobytes())
    duree = len(parole) / 16000
    meta.write_text(json.dumps({"signature": signature, "parole_s": duree}, ensure_ascii=False), encoding="utf-8")
    return str(chemin), duree


class SourceScenario:
    """Un micro de test. `generateur` se donne aux Oreilles ; `jouer` et `silence` y déposent l'audio,
    livré au rythme réel. Entre deux dépôts, le micro rend du silence."""
    BLOC = 1280

    def __init__(self):
        self.file: queue.Queue = queue.Queue()

    def generateur(self, arret):
        prochain = time.time()
        while not arret.is_set():
            try:
                bloc = self.file.get_nowait()
            except queue.Empty:
                bloc = np.zeros(self.BLOC, dtype=np.int16)
            attente = prochain - time.time()
            if attente > 0:
                time.sleep(attente)
            prochain = max(prochain + self.BLOC / 16000, time.time() - 0.2)
            yield bloc

    def jouer(self, chemin: str, gain: float = 1.0):
        with wave.open(chemin, "rb") as w:
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if gain != 1.0:
            a = np.clip(a.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
        a = np.concatenate([a, np.zeros((-len(a)) % self.BLOC, dtype=np.int16)])
        for i in range(0, len(a), self.BLOC):
            self.file.put(a[i:i + self.BLOC])

    def silence(self, secondes: float):
        for _ in range(int(secondes * 16000 / self.BLOC)):
            self.file.put(np.zeros(self.BLOC, dtype=np.int16))

    def attendre_vide(self, delai: float = 60):
        fin = time.time() + delai
        while not self.file.empty() and time.time() < fin:
            time.sleep(0.05)


def attendre(condition, delai: float = 30, pas: float = 0.05) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        if condition():
            return True
        time.sleep(pas)
    return bool(condition())


class Collecteur:
    """Garde les événements émis (sur_evenement) avec leur type."""

    def __init__(self):
        self.evenements: list[dict] = []
        self.verrou = threading.Lock()

    def __call__(self, e: dict):
        with self.verrou:
            self.evenements.append(e)

    def types(self) -> list[str]:
        with self.verrou:
            return [e["type"] for e in self.evenements]

    def de_type(self, t: str) -> list[dict]:
        with self.verrou:
            return [e for e in self.evenements if e["type"] == t]
