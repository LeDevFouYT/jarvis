"""La voix du majordome (v3, consigne 3) : un troisième moteur de voix, `voix.moteur = "majordome"`.

Une voix de majordome britannique qui parle français, INVENTÉE à partir d'une description (Qwen3-TTS VoiceDesign,
voir voix_qwen/creer_voix.py : ni enregistrement ni nom de personne réelle), puis rejouée phrase par phrase par le
modèle Qwen3-TTS Base en clonage de cette référence synthétique. Tout est local, sur la carte graphique.

- Le modèle tourne dans un processus à part (voix_qwen/processus.py) avec le Python où `qwen-tts` est installé
  (`voix.majordome.python`) : Jarvis n'embarque pas torch. Il reste chargé tant que le moteur est choisi, et s'arrête
  quand on en change (la mémoire vidéo est rendue).
- Accéléré par graphes CUDA (voix_qwen/graphe.py) : 0,4 s de calcul par seconde de voix au lieu de 2,5 (1.7B) (mesuré le
  19/09 sur la RTX 5080), sans quoi il parlerait plus lentement qu'il ne calcule.
- Chaque phrase est RÉÉCOUTÉE par le Whisper déjà chargé par les oreilles (aucune mémoire de plus), comparée mot à mot,
  refaite si elle est fausse (voix_qwen/reecoute.py, la boucle des vidéos) ; rapport dans cache/voix/majordome/reecoute.jsonl
  et événement `reecoute` pour le HUD.
- Pas de place sur la carte (≈ 2,4 Go en pointe avec le modèle 0.6B), pas de Python Qwen, pas de référence : `Indisponible`, et voix.py repasse sur
  Kokoro avec un événement `voix_repli`, comme pour ElevenLabs.
"""
import base64
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

from .config import CONFIG, RACINE
from .voix_qwen import reecoute

ICI = Path(__file__).resolve().parent / "voix_qwen"
# 0.6B par défaut : 1,95 Go vus par la carte (2,35 en pointe sur une phrase longue ; table du texte laissée en mémoire
# système, voir voix_qwen/graphe.py) contre 5,0 pour le 1.7B, aussi juste (8/8 phrases du premier coup le 19/09) et un peu
# plus rapide ; le 1.7B ne tient pas à côté de qwen3:14b (il le pousse hors de la carte).
DEFAUTS = {"python": "", "modele": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "reference": str(ICI / "majordome" / "reference.wav"),
           "prises_max": reecoute.PRISES_MAX, "vram_mo": None, "chargement_max_s": 240}
VRAM_MO = {"0.6B": 2400, "1.7B": 5300}             # vu par la carte, pointe comprise ; `voix.majordome.vram_mo` pour forcer
JOURNAL = RACINE / "cache" / "voix" / "majordome" / "reecoute.jsonl"


def sur_evenement(e: dict):
    from . import voix                   # le même canal que la voix (diffusé sur /events par le serveur)
    voix.sur_evenement({"t": time.time(), **e})


def _faire_de_la_place(libre: int, besoin: int) -> int:
    """Demande au cerveau de rendre la carte, et attend qu'elle se vide vraiment.

    Ollama libère la mémoire quelques secondes après `keep_alive: 0` : on regarde jusqu'à dix secondes. Le verrou
    de la carte empêche le cerveau de revenir pendant qu'on charge la voix ; il revient tout seul ensuite.
    """
    from . import carte
    from .machine import vram_libre_mo
    try:
        from .cerveau import CERVEAU
        carte.occuper("voix du majordome")
        CERVEAU.decharger()
    except Exception:
        return libre
    for _ in range(20):
        time.sleep(0.5)
        maintenant = vram_libre_mo()
        if maintenant is None or maintenant >= besoin:
            return maintenant
        libre = maintenant
    return libre


class Indisponible(RuntimeError):
    pass


def reglage(nom: str):
    return CONFIG.get("voix", {}).get("majordome", {}).get(nom, DEFAUTS[nom])


def _python() -> str:
    """Le Python où qwen-tts est installé : réglage, sinon celui des outils externes de Jarvis."""
    for chemin in (reglage("python"), os.environ.get("JARVIS_QWEN_PYTHON", ""),
                   str(RACINE / "outils_externes" / "qwen_tts" / "Scripts" / "python.exe")):
        if chemin and Path(chemin).exists():
            return chemin
    return ""


def _poids_presents(modele: str) -> bool:
    if Path(modele).exists():
        return True
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return (cache / ("models--" + modele.replace("/", "--"))).exists()


def disponible() -> tuple[bool, str]:
    """(prêt à être lancé ?, raison sinon) — sans rien lancer."""
    if not _python():
        return False, "le Python de Qwen3-TTS est introuvable (voix.majordome.python)"
    ref = Path(reglage("reference"))
    if not ref.exists() or not ref.with_suffix(".txt").exists():
        return False, "la voix du majordome n'a pas encore été créée (voix_qwen/creer_voix.py)"
    if not _poids_presents(reglage("modele")):
        return False, f"le modèle {reglage('modele')} n'est pas téléchargé"
    return True, ""


class Majordome:
    def __init__(self):
        self.proc = None
        self.sr = None
        self.infos = {}
        self.verrou = threading.Lock()           # une phrase à la fois dans le processus
        self.hauteur_prec = 0.0
        self.dernier = {}
        self.echec = (0.0, "")                   # (quand, pourquoi) : un refus est retenu une minute

    @property
    def actif(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # --- le processus ---
    def _lire(self, delai: float) -> dict:
        fin = time.time() + delai
        while time.time() < fin:
            ligne = self.proc.stdout.readline()
            if not ligne:
                raise Indisponible("le processus de la voix du majordome s'est arrêté")
            if ligne.startswith("@@"):
                return json.loads(ligne[2:])
        raise Indisponible("la voix du majordome ne répond plus")

    def demarrer(self) -> dict:
        with self.verrou:
            if self.actif:
                return self.infos
            if time.time() - self.echec[0] < 60:             # pas de nvidia-smi ni de nouvel essai à chaque phrase
                raise Indisponible(self.echec[1])
            try:
                return self._lancer()
            except Indisponible as e:
                self.echec = (time.time(), str(e))
                raise
            finally:
                from . import carte
                carte.liberer("voix du majordome")   # la voix tient sa place ; le cerveau peut revenir à côté

    def _lancer(self) -> dict:
        ok, raison = disponible()
        if not ok:
            raise Indisponible(raison)
        from .machine import vram_libre_mo
        libre = vram_libre_mo()
        besoin = reglage("vram_mo") or next((v for k, v in VRAM_MO.items() if k in reglage("modele")), 5300)
        if libre is not None and libre < besoin:
            # La carte est pleine parce que le cerveau la tient. Les hologrammes et la vidéo, eux, lui demandent
            # la place ; la voix du majordome renonçait, et Jarvis repassait en voix locale sans qu'on comprenne
            # pourquoi (démo du 20/09 : 1884 Mo libres, il en fallait 2400). Elle demande la place à son tour.
            libre = _faire_de_la_place(libre, besoin)
            if libre is not None and libre < besoin:
                raise Indisponible(f"mémoire vidéo insuffisante : {libre} Mo libres, il en faut {besoin}")
        ref = Path(reglage("reference"))
        t = time.time()
        self.proc = subprocess.Popen(
            [_python(), str(ICI / "processus.py"), reglage("modele"), str(ref), str(ref.with_suffix(".txt"))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            pret = self._lire(reglage("chargement_max_s"))
        except Indisponible:
            self._tuer()
            raise
        if not pret.get("pret"):
            self._tuer()
            raise Indisponible(pret.get("erreur", "chargement impossible"))
        self.sr = pret["sr"]
        self.infos = {**pret, "demarrage_s": round(time.time() - t, 1)}
        return self.infos

    def _tuer(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except OSError:
                pass
        self.proc = None

    def arreter(self):
        with self.verrou:
            if self.actif:
                try:
                    self.proc.stdin.write(json.dumps({"fin": True}) + "\n")
                    self.proc.stdin.flush()
                    self.proc.wait(5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            self._tuer()

    def generer(self, texte: str, langue: str = "fr") -> np.ndarray:
        """Une prise brute, à `self.sr` Hz."""
        if not self.actif:
            self.demarrer()
        with self.verrou:
            self.proc.stdin.write(json.dumps({"texte": texte, "langue": langue}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            r = self._lire(60)
        if "erreur" in r:
            raise RuntimeError(r["erreur"])
        self.dernier = {k: r.get(k) for k in ("calcul_s", "pic_mo")}
        return np.frombuffer(base64.b64decode(r["audio"]), dtype=np.float32).copy()

    # --- la réécoute, avec le Whisper des oreilles ---
    @staticmethod
    def entendre(onde: np.ndarray, sr: int, langue: str = "fr") -> str:
        from . import oreilles
        oreilles.charger_whisper()
        n = int(len(onde) * 16000 / sr)
        a16 = np.interp(np.linspace(0, len(onde) - 1, n), np.arange(len(onde)), onde).astype(np.float32)
        segments, _ = oreilles._whisper.transcribe(a16, language=langue, beam_size=5, vad_filter=False,
                                                   condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()

    def synthetiser(self, texte: str, langue: str = "fr", freq: int = 24000) -> tuple[np.ndarray, dict]:
        t = time.time()
        if not self.actif:
            self.demarrer()
        sr = self.sr
        calcul = {"generation": 0.0, "ecoute": 0.0}

        def generer(phrase):
            t0 = time.time()
            onde = self.generer(phrase, langue)
            calcul["generation"] += time.time() - t0
            return onde

        def entendre(onde):
            t0 = time.time()
            texte_entendu = self.entendre(onde, sr, langue)
            calcul["ecoute"] += time.time() - t0
            return texte_entendu

        onde, rapport = reecoute.reecouter(texte, generer, entendre, sr, prises_max=int(reglage("prises_max")),
                                           hauteur_prec=self.hauteur_prec)
        self.hauteur_prec = rapport["hauteur_hz"] or self.hauteur_prec
        if sr != freq:
            n = int(len(onde) * freq / sr)
            onde = np.interp(np.linspace(0, len(onde) - 1, n), np.arange(len(onde)), onde).astype(np.float32)
        rapport.update(phrase=texte, langue=langue, total_s=round(time.time() - t, 3),
                       generation_s=round(calcul["generation"], 3), ecoute_s=round(calcul["ecoute"], 3),
                       duree_s=round(len(onde) / freq, 2))
        try:
            JOURNAL.parent.mkdir(parents=True, exist_ok=True)
            with JOURNAL.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), **rapport}, ensure_ascii=False) + "\n")
        except OSError:
            pass
        sur_evenement({"type": "reecoute", "prises": rapport["prises"], "score": rapport["score"],
                       "ecarts": rapport["ecarts"], "fautes_ecartees": rapport["fautes_ecartees"], "phrase": texte})
        return onde, rapport


MAJORDOME = Majordome()


def suivre_moteur(moteur: str):
    """Réglages changés : on charge le modèle en fond si le majordome est choisi, on rend la carte sinon."""
    if moteur == "majordome":
        MAJORDOME.echec = (0.0, "")              # choisi à la main : on retente tout de suite
        def charger():
            try:
                MAJORDOME.demarrer()
            except Exception as e:                            # noqa: BLE001
                sur_evenement({"type": "voix_repli", "raison": str(e)})
        threading.Thread(target=charger, daemon=True).start()
    elif MAJORDOME.actif:
        threading.Thread(target=MAJORDOME.arreter, daemon=True).start()
