"""La voix : deux moteurs et un interrupteur `voix.moteur` dans config.json.
  local       Kokoro ONNX sur CPU (rien en VRAM). Français : ff_siwis. Anglais : bm_george (voix.kokoro_voix_en),
              choisie phrase par phrase selon la langue de la question. Une phrase de 15 caractères coûte environ
              0,55 s de calcul, une de 68 caractères 1,4 s (mesuré le 16/09, processeur chargé par OBS) : d'où la
              première phrase coupée court (Decoupeur, premiere_courte). Essayé sans succès : le modèle int8
              (quatre fois plus lent sur ce processeur) et DirectML (ConvTranspose refusé par le pilote).
  elevenlabs  API ElevenLabs, clé ELEVENLABS_API_KEY dans .secrets, voix dans config.json, modèle multilingue.
              Clé absente ou API en panne : repli sur local sans planter, événement `voix_repli`.
  majordome   Qwen3-TTS en local sur la carte graphique, voix de majordome inventée par description, chaque phrase
              réécoutée par Whisper (jarvis/majordome.py). Indisponible (modèle, place sur la carte) : repli sur local.
Lecture par sounddevice, phrase par phrase pendant que le cerveau génère encore, niveau sonore diffusé
20 fois par seconde, interruption immédiate (`taire`), cache disque par moteur, voix et texte.
Événements : parole_debut, phrase (avec sa durée), premier_son (le premier bloc réellement joué d'une prise,
pour mesurer la réponse éclair), niveau, parole_fin, parole_interrompue."""
import collections
import hashlib
import queue
import re
import threading
import time

import numpy as np
import requests

from . import compteur
from .config import CONFIG, RACINE, SECRETS

REGLAGES = CONFIG["voix"]
FREQ = 24000                      # Kokoro et ElevenLabs (pcm_24000) parlent tous deux à 24 kHz
BLOC = FREQ // 20                 # 50 ms : une mesure de niveau par bloc, donc 20 par seconde
CACHE = RACINE / "cache" / "voix"

sur_evenement = lambda e: None    # branché par le serveur (diffusion sur /events)


def _emettre(type_, **champs):
    sur_evenement({"type": type_, "t": time.time(), **champs})


# =============================================================================================
# Moteurs
# =============================================================================================
_kokoro = None
_verrou = threading.Lock()


def charger() -> float:
    """Charge Kokoro (une fois). Retourne la durée."""
    global _kokoro
    with _verrou:
        if _kokoro is not None:
            return 0.0
        t = time.time()
        import espeakng_loader
        from kokoro_onnx import Kokoro
        from kokoro_onnx.config import EspeakConfig
        espeak = EspeakConfig(data_path=chemin_sans_accent(espeakng_loader.get_data_path()))
        _kokoro = Kokoro(str(RACINE / "modeles" / "kokoro" / "kokoro-v1.0.onnx"),
                         str(RACINE / "modeles" / "kokoro" / "voices-v1.0.bin"), espeak_config=espeak)
        return time.time() - t


def chemin_sans_accent(dossier: str) -> str:
    """espeak-ng (la prononciation de Kokoro) lit son chemin de données en ANSI : sous « C:\\Users\\Jérôme\\… », il ne
    trouvait rien et quittait tout le processus Jarvis (vu le 18/09, installation dans un dossier accentué). Le nom
    court Windows (8.3) ne suffit pas : phonemizer fait `Path.resolve()`, qui rend le nom long, accents compris. Les
    données (une vingtaine de Mo) sont donc copiées dans C:\\Users\\Public\\Jarvis, recopiées si elles changent."""
    if dossier.isascii():
        return dossier
    import os
    import shutil
    from pathlib import Path
    source = Path(dossier)
    copie = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Jarvis" / source.name
    temoin = "phontab"
    if not (copie / temoin).exists() or (copie / temoin).stat().st_size != (source / temoin).stat().st_size:
        shutil.rmtree(copie, ignore_errors=True)
        shutil.copytree(source, copie)
    return str(copie)


def pret() -> bool:
    return _kokoro is not None


def voix_kokoro(langue: str = "fr") -> tuple[str, str]:
    """(voix, code de langue espeak) pour une langue de réponse. Anglais : bm_george, un majordome britannique."""
    if langue == "en":
        v = REGLAGES.get("kokoro_voix_en", "bm_george")
        return v, ("en-gb" if v[:1] == "b" else "en-us")
    return REGLAGES.get("kokoro_voix", "ff_siwis"), "fr-fr"


def _local(texte: str, voix: str | None = None, langue: str = "fr-fr") -> np.ndarray:
    charger()
    audio, freq = _kokoro.create(texte, voice=voix or REGLAGES.get("kokoro_voix", "ff_siwis"),
                                 speed=float(REGLAGES.get("kokoro_vitesse", 1.0)), lang=langue)
    assert freq == FREQ, freq
    return audio.astype(np.float32)


def prechauffer() -> float:
    """Charge Kokoro et fait une première synthèse dans chaque langue : l'ONNX s'échauffe (953 ms au lieu de 631 ms
    pour la toute première phrase sinon). Appelé par le serveur au démarrage."""
    t = time.time()
    charger()
    for langue, texte in (("fr", "Bonjour."), ("en", "Hello.")):
        v, code = voix_kokoro(langue)
        try:
            _local(texte, v, code)
        except Exception:
            pass
    return time.time() - t


def elevenlabs_configure() -> bool:
    return bool(SECRETS.get("ELEVENLABS_API_KEY")) and bool(REGLAGES.get("elevenlabs_voix"))


def _elevenlabs(texte: str) -> np.ndarray:
    compteur.compter("elevenlabs")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{REGLAGES['elevenlabs_voix']}",
        params={"output_format": "pcm_24000"},
        headers={"xi-api-key": SECRETS["ELEVENLABS_API_KEY"], "Content-Type": "application/json"},
        json={"text": texte, "model_id": REGLAGES.get("elevenlabs_modele", "eleven_multilingual_v2"),
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=30)
    r.raise_for_status()
    return np.frombuffer(r.content, dtype=np.int16).astype(np.float32) / 32768.0


# =============================================================================================
# Cache disque : cache/voix/<moteur>/<sha1(voix|texte)>.npy
# =============================================================================================
def _chemin_cache(moteur: str, texte: str, langue: str = "fr"):
    voix = (REGLAGES.get("elevenlabs_voix") if moteur == "elevenlabs"
            else f"majordome|{langue}" if moteur == "majordome" else voix_kokoro(langue)[0])
    cle = hashlib.sha1(f"{voix}|{texte.strip()}".encode("utf-8")).hexdigest()
    return CACHE / moteur / f"{cle}.npy"


_REPLI_DIT = [None]


def synthetiser(texte: str, moteur: str | None = None, langue: str = "fr") -> tuple[np.ndarray, dict]:
    """Retourne (audio float32 24 kHz, infos : moteur réellement utilisé, voix, cache, durée, repli)."""
    demande = moteur or REGLAGES.get("moteur", "local")
    infos = {"moteur_demande": demande, "moteur": demande, "cache": False, "repli": None, "langue": langue}
    t = time.time()
    if demande == "majordome":
        from . import majordome
        infos["voix"] = "majordome"
        chemin = _chemin_cache("majordome", texte, langue)
        if REGLAGES.get("cache", True) and chemin.exists():
            infos.update(cache=True, duree=round(time.time() - t, 3))
            return np.load(chemin), infos
        if not majordome.MAJORDOME.actif and majordome.MAJORDOME.verrou.locked():
            infos["repli"] = "la voix du majordome se charge encore"          # pas d'attente de 30 s au démarrage
        else:
            try:
                audio, rapport = majordome.MAJORDOME.synthetiser(texte, langue, FREQ)
                if REGLAGES.get("cache", True) and rapport["score"] == 0:           # seule une prise juste est gardée
                    chemin.parent.mkdir(parents=True, exist_ok=True)
                    np.save(chemin, audio)
                infos.update(duree=round(time.time() - t, 3), reecoute=rapport)
                return audio, infos
            except majordome.Indisponible as e:
                infos["repli"] = str(e)
            except Exception as e:
                infos["repli"] = f"voix du majordome en échec ({type(e).__name__} : {e})"
        infos["moteur"] = "local"
        if (infos["repli"], int(time.time() // 60)) != _REPLI_DIT[0]:  # une note par raison et par minute, pas par phrase
            _REPLI_DIT[0] = (infos["repli"], int(time.time() // 60))
            _emettre("voix_repli", raison=infos["repli"])
    elif demande == "elevenlabs":
        if not elevenlabs_configure():
            infos["repli"] = "clé ElevenLabs ou identifiant de voix absent"
        else:
            infos["voix"] = REGLAGES.get("elevenlabs_voix")
            chemin = _chemin_cache("elevenlabs", texte, langue)
            if REGLAGES.get("cache", True) and chemin.exists():
                infos.update(cache=True, duree=round(time.time() - t, 3))
                return np.load(chemin), infos
            try:
                audio = _elevenlabs(texte)
                if REGLAGES.get("cache", True):
                    chemin.parent.mkdir(parents=True, exist_ok=True)
                    np.save(chemin, audio)
                infos["duree"] = round(time.time() - t, 3)
                return audio, infos
            except Exception as e:
                infos["repli"] = f"ElevenLabs en échec ({type(e).__name__})"
        infos["moteur"] = "local"
        _emettre("voix_repli", raison=infos["repli"])
    voix, code = voix_kokoro(langue)
    infos["voix"] = voix
    chemin = _chemin_cache("local", texte, langue)
    if REGLAGES.get("cache", True) and chemin.exists():
        infos.update(cache=True, duree=round(time.time() - t, 3))
        return np.load(chemin), infos
    audio = _local(texte, voix, code)
    if REGLAGES.get("cache", True):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        np.save(chemin, audio)
    infos["duree"] = round(time.time() - t, 3)
    return audio, infos


# =============================================================================================
# Découpage en phrases (et en propositions pour les phrases longues)
# =============================================================================================
_FIN_PHRASE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÝÉÈÊÀÂÎÔÛÇ«\"(\d])")
_LONGUEUR_MAX = 90
# la première phrase peut partir dès sa première virgule : « Il est vingt heures, » se dit pendant que la suite s'écrit
_PREMIERE_COUPE = re.compile(r"(?<=[,;:])\s+(?=\S)")


def decouper_phrases(texte: str) -> list[str]:
    morceaux = []
    for phrase in _FIN_PHRASE.split(texte.strip()):
        phrase = phrase.strip()
        if not phrase:
            continue
        if len(phrase) <= _LONGUEUR_MAX:
            morceaux.append(phrase)
            continue
        # Trop long pour tenir sous la seconde : couper aux virgules, points-virgules, deux-points.
        courant = ""
        for bout in re.split(r"(?<=[,;:])\s+", phrase):
            if courant and len(courant) + len(bout) > _LONGUEUR_MAX:
                morceaux.append(courant.strip())
                courant = bout
            else:
                courant = f"{courant} {bout}".strip()
        if courant:
            morceaux.append(courant.strip())
    return morceaux


class Decoupeur:
    """Reçoit le texte du cerveau morceau par morceau, rend les phrases complètes au fur et à mesure.
    `premiere_courte` : la toute première proposition part dès sa virgule si elle fait au moins deux mots
    (réponse éclair : Kokoro met 0,55 s pour 15 caractères, 1,4 s pour 68)."""

    def __init__(self, sur_phrase, premiere_courte: bool = False):
        self.sur_phrase = sur_phrase
        self.tampon = ""
        self.premiere_courte = premiere_courte
        self.emises = 0
        self.retenue = ""            # une bribe de quelques lettres (« sir. ») attend la phrase suivante pour ne pas sonner seule

    def _rendre(self, phrase: str):
        for p in decouper_phrases(phrase):
            if self.retenue:
                p, self.retenue = f"{self.retenue} {p}", ""
            if self.emises > 0 and len(p) < 8:
                self.retenue = p
                continue
            self.emises += 1
            self.sur_phrase(p)

    def ajouter(self, morceau: str):
        self.tampon += morceau
        while True:
            if self.premiere_courte and self.emises == 0:
                c = _PREMIERE_COUPE.search(self.tampon)
                fin = _FIN_PHRASE.search(self.tampon)
                if c and (not fin or c.start() < fin.start()):
                    debut = self.tampon[:c.start()].strip()
                    if len(debut.split()) >= 2 and len(debut) >= 8 and not re.search(r"\d,$", debut):
                        self.tampon = self.tampon[c.end():]
                        self._rendre(debut)
                        continue
            m = _FIN_PHRASE.search(self.tampon)
            if not m:
                # un retour à la ligne termine aussi une phrase
                if "\n" in self.tampon:
                    avant, _, apres = self.tampon.partition("\n")
                    self.tampon = apres
                    if avant.strip():
                        self._rendre(avant)
                    continue
                return
            phrase, self.tampon = self.tampon[:m.start()], self.tampon[m.end():]
            self._rendre(phrase)

    def terminer(self):
        reste, self.tampon = self.tampon.strip(), ""
        if reste:
            self._rendre(reste)
        if self.retenue:
            p, self.retenue = self.retenue, ""
            self.emises += 1
            self.sur_phrase(p)


# =============================================================================================
# Le parleur : file de phrases -> synthèse (thread) -> lecture (thread) avec niveau et interruption
# =============================================================================================
class Parleur:
    def __init__(self):
        self.generation = 0                     # incrémenté par taire() : tout ce qui est plus ancien est jeté
        self.phrases = queue.Queue()            # (generation, prise, texte, moteur, langue)
        self.audios = queue.Queue(maxsize=4)    # (generation, prise, texte, audio, infos)
        self.prise = 0                          # numéro de prise de parole (un dire() = une prise)
        self.en_lecture = threading.Event()
        self.muet = False                       # « Jarvis, silence » : plus rien n'est dit jusqu'au prochain réveil
        self.en_attente = 0                     # phrases pas encore jouées
        self.verrou = threading.Lock()
        self.arret_lecture = threading.Event()
        self.dites = collections.deque(maxlen=12)   # (instant, texte) : pour reconnaître l'écho de sa propre voix
        self.fin_derniere_parole = 0.0
        threading.Thread(target=self._synthese, daemon=True, name="voix-synthese").start()
        threading.Thread(target=self._lecture, daemon=True, name="voix-lecture").start()

    # --- API ---
    def dire(self, texte: str, moteur: str | None = None, nouvelle_prise: bool = True, langue: str = "fr") -> int:
        """Met les phrases du texte en file. Retourne le numéro de prise."""
        with self.verrou:
            if nouvelle_prise:
                self.prise += 1
            prise = self.prise
            if self.muet:
                return prise
            for phrase in decouper_phrases(texte):
                self.en_attente += 1
                self.phrases.put((self.generation, prise, phrase, moteur, langue))
        return prise

    def dire_phrase(self, phrase: str, prise: int | None = None, langue: str = "fr"):
        """Une phrase déjà découpée, rattachée à la prise en cours (streaming du cerveau)."""
        with self.verrou:
            if prise is None:
                prise = self.prise
            if self.muet:
                return
            self.en_attente += 1
            self.phrases.put((self.generation, prise, phrase, None, langue))

    def nouvelle_prise(self) -> int:
        with self.verrou:
            self.prise += 1
            return self.prise

    def taire(self, raison: str = "interruption"):
        """Se tait immédiatement : vide les files et coupe la lecture en cours."""
        with self.verrou:
            self.generation += 1
            self.en_attente = 0
        for f in (self.phrases, self.audios):
            try:
                while True:
                    f.get_nowait()
            except queue.Empty:
                pass
        if self.en_lecture.is_set():
            self.arret_lecture.set()
            _emettre("parole_interrompue", raison=raison)

    def parle(self) -> bool:
        return self.en_lecture.is_set() or self.en_attente > 0

    def attendre(self, delai: float = 120):
        fin = time.time() + delai
        while self.parle() and time.time() < fin:
            time.sleep(0.05)

    def phrases_recentes(self, secondes: float = 20) -> list[str]:
        limite = time.time() - secondes
        return [t for instant, t in self.dites if instant >= limite]

    # --- threads ---
    def _synthese(self):
        while True:
            generation, prise, texte, moteur, langue = self.phrases.get()
            if generation != self.generation:
                continue
            try:
                audio, infos = synthetiser(texte, moteur, langue)
            except Exception as e:
                _emettre("voix_erreur", message=f"{type(e).__name__} : {e}", texte=texte)
                with self.verrou:
                    self.en_attente = max(0, self.en_attente - 1)
                continue
            if generation != self.generation:
                continue
            self.audios.put((generation, prise, texte, audio, infos))

    def _lecture(self):
        import sounddevice as sd
        prise_en_cours = None
        prise_sonore = None                                  # la dernière prise dont le premier son a été signalé
        while True:
            try:
                generation, prise, texte, audio, infos = self.audios.get(timeout=0.3)
            except queue.Empty:
                if prise_en_cours is not None and self.en_attente == 0 and self.audios.empty():
                    self.fin_derniere_parole = time.time()
                    _emettre("parole_fin", prise=prise_en_cours)
                    prise_en_cours = None
                continue
            if generation != self.generation:
                continue
            if prise != prise_en_cours:
                if prise_en_cours is not None:
                    _emettre("parole_fin", prise=prise_en_cours)
                prise_en_cours = prise
                _emettre("parole_debut", prise=prise)
            # émis juste avant la lecture, avec sa durée : le HUD écrit la phrase au rythme où elle est dite
            _emettre("phrase", prise=prise, texte=texte, moteur=infos["moteur"], cache=infos["cache"],
                     duree=round(len(audio) / FREQ, 3), langue=infos.get("langue", "fr"), voix=infos.get("voix"))
            self.dites.append((time.time(), texte))
            self.en_lecture.set()
            self.arret_lecture.clear()
            try:
                for essai in (1, 2):
                    try:
                        with sd.OutputStream(samplerate=FREQ, channels=1, dtype="float32",
                                             device=REGLAGES.get("peripherique_sortie"), blocksize=BLOC) as flux:
                            for i in range(0, len(audio), BLOC):
                                if self.arret_lecture.is_set() or generation != self.generation:
                                    break
                                bloc = audio[i:i + BLOC]
                                if len(bloc) < BLOC:
                                    bloc = np.pad(bloc, (0, BLOC - len(bloc)))
                                if prise_sonore != prise:
                                    prise_sonore = prise
                                    _emettre("premier_son", prise=prise, texte=texte)
                                flux.write(bloc.reshape(-1, 1))
                                _emettre("niveau", prise=prise, valeur=round(float(np.sqrt(np.mean(bloc ** 2))) * 4, 3))
                        break
                    except sd.PortAudioError:
                        if essai == 2:
                            raise
                        # casque débranché ou changé : la liste des périphériques est relue, la phrase redite une fois
                        from .oreilles import rafraichir_peripheriques
                        rafraichir_peripheriques()
            except Exception as e:
                _emettre("voix_erreur", message=f"lecture : {type(e).__name__} : {e}")
            finally:
                self.en_lecture.clear()
                _emettre("niveau", prise=prise, valeur=0.0)
                with self.verrou:
                    self.en_attente = max(0, self.en_attente - 1)
            if self.arret_lecture.is_set():
                prise_en_cours = None


VOIX = Parleur()


def lister_sorties() -> list[dict]:
    import sounddevice as sd
    apis = sd.query_hostapis()
    return [{"index": i, "nom": p["name"], "api": apis[p["hostapi"]]["name"], "defaut": i == sd.default.device[1]}
            for i, p in enumerate(sd.query_devices()) if p["max_output_channels"] > 0]
