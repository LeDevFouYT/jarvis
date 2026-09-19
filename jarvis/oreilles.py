"""Les oreilles, en deux étages.

1. Mot de réveil : openWakeWord (modèle « hey_jarvis » fourni avec la bibliothèque) sur le micro en
   permanence, sur CPU, environ 2 ms par tranche de 80 ms. Rien en VRAM.
2. Après détection : enregistrement jusqu'à un court silence (VAD Silero fourni par faster-whisper, en flux, sur CPU),
   puis transcription faster-whisper sur GPU, langue reconnue (français ou anglais), filtre d'hallucinations.

Sans mot de réveil, une phrase est acceptée dans trois cas :
- mode phrase : elle commence par « Jarvis » (« Jarvis, quelle heure est-il ») ;
- conversation continue : elle commence pendant la fenêtre ouverte après une réponse (`ouvrir_fenetre`, 8 s) ;
- interruption : elle est dite pendant que Jarvis parle (au moins `interruption.duree_min_s` de voix nette).
  L'écho de sa propre voix dans des haut-parleurs est reconnu à la transcription (mots de ses dernières phrases)
  et ignoré ; au deuxième écho d'affilée, l'interruption se coupe pour la session. Casque recommandé.

Réponse éclair : la transcription démarre dès `anticipation_s` de silence, pendant qu'on attend la fin de phrase
(`silence_phrase_s`) ; si la voix reprend, elle est jetée. L'instant de fin de parole accompagne le texte.

Les DLL cuBLAS/cuDNN viennent des paquets pip nvidia-* et doivent être préchargées par chemin complet
avant l'import de faster_whisper, sinon CTranslate2 ne les trouve pas sous Windows."""
import ctypes
import inspect
import os
import queue
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

import numpy as np

from .config import CONFIG, RACINE

# --- DLL NVIDIA -------------------------------------------------------------------------------
_NVIDIA = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
for dossier, dll in (("cublas", "cublasLt64_12"), ("cublas", "cublas64_12"), ("cudnn", "cudnn64_9")):
    chemin = _NVIDIA / dossier / "bin"
    if chemin.exists():
        os.add_dll_directory(str(chemin))
        os.environ["PATH"] = str(chemin) + os.pathsep + os.environ["PATH"]
        try:
            ctypes.CDLL(str(chemin / f"{dll}.dll"))
        except OSError:
            pass

from faster_whisper import WhisperModel  # noqa: E402
from faster_whisper.audio import decode_audio  # noqa: E402
from faster_whisper.vad import get_vad_model  # noqa: E402

FREQ = 16000
PAUSE_MAX_S = 60                  # le micro du navigateur ne garde pas celui du PC en pause plus longtemps
BLOC = 1280  # 80 ms : la tranche qu'attend openWakeWord
REGLAGES = CONFIG["oreilles"]


def reglage(nom: str, defaut):
    """Lu à chaque usage : les Réglages du HUD changent ces valeurs à chaud."""
    return type(defaut)(REGLAGES.get(nom, defaut)) if not isinstance(defaut, (dict, list)) else REGLAGES.get(nom, defaut)


# =============================================================================================
# Étage 2a : transcription (faster-whisper sur GPU)
# =============================================================================================
_whisper = None
_verrou_whisper = threading.Lock()


def charger_whisper() -> float:
    """Charge Whisper une seule fois. Retourne la durée. Repli CPU int8 si le GPU refuse."""
    global _whisper
    with _verrou_whisper:
        if _whisper is not None:
            return 0.0
        t = time.time()
        dossier = str(RACINE / "modeles" / "whisper")
        try:
            _whisper = WhisperModel(REGLAGES["modele"], device=REGLAGES.get("appareil", "cuda"),
                                    compute_type=REGLAGES.get("calcul", "float16"), download_root=dossier)
        except Exception:
            _whisper = WhisperModel(REGLAGES["modele"], device="cpu", compute_type="int8", download_root=dossier)
        return time.time() - t


def prechauffer_whisper() -> float:
    """Chargement puis une transcription de rien : les noyaux CUDA sont prêts pour la première vraie phrase."""
    t = time.time()
    charger_whisper()
    bruit = (np.random.default_rng(0).standard_normal(FREQ) * 0.003).astype(np.float32)
    try:
        list(_whisper.transcribe(bruit, language="fr", beam_size=1, vad_filter=False)[0])
    except Exception:
        pass
    return time.time() - t


def whisper_pret() -> bool:
    return _whisper is not None


# Phrases que Whisper invente sur du silence ou du souffle. Comparées après normalisation
# (minuscules, sans accents ni ponctuation) : égalité ou inclusion, jamais un critère de longueur.
HALLUCINATIONS = [
    "sous-titres réalisés par la communauté d'amara.org",
    "sous-titres réalisés par",
    "sous-titres par",
    "sous-titrage société radio-canada",
    "sous-titrage st' 501",
    "sous-titrage",
    "sous-titres",
    "merci d'avoir regardé cette vidéo",
    "merci d'avoir regardé",
    "merci de votre attention",
    "merci de vous être abonné",
    "merci d'avoir écouté",
    "n'oubliez pas de vous abonner",
    "abonnez-vous",
    "à la prochaine",
    "à bientôt pour une nouvelle vidéo",
    "musique",
    "rires",
    "applaudissements",
    "thank you for watching",
    "thanks for watching",
    "subtitles by",
    "you",
    "bye",
    "merci",
]


def _normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFD", texte.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_HALLUCINATIONS_NORMALISEES = [_normaliser(h) for h in HALLUCINATIONS]


def est_hallucination(texte: str) -> bool:
    n = _normaliser(texte)
    if not n:
        return True
    return any(n == h or (len(h) > 8 and h in n) for h in _HALLUCINATIONS_NORMALISEES)


def transcrire_detail(audio) -> tuple[str, str]:
    """`audio` : chemin de fichier (wav, webm, ogg, mp3) ou tableau float32 à 16 kHz.
    Rend (texte, langue) ; texte vide si rien d'utile. Langues autorisées : `oreilles.langues` (fr, en)."""
    charger_whisper()
    langues = reglage("langues", ["fr", "en"])
    beam = reglage("beam", 1)
    commun = dict(beam_size=beam, vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                  condition_on_previous_text=False)
    if len(langues) == 1:
        segments, info = _whisper.transcribe(audio, language=langues[0], initial_prompt="Jarvis.", **commun)
        langue = langues[0]
    else:
        segments, info = _whisper.transcribe(audio, language=None, initial_prompt="Jarvis.", **commun)
        langue = info.language
        # une phrase courte mal reconnue (néerlandais, allemand…) ou un anglais incertain : on repasse en français
        if langue not in langues or (langue != langues[0] and info.language_probability < 0.7):
            segments, info = _whisper.transcribe(audio, language=langues[0], initial_prompt="Jarvis.", **commun)
            langue = langues[0]
    texte = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.8).strip()
    if info.duration < 0.3 or est_hallucination(texte):
        return "", langue
    return texte, langue


def transcrire(audio) -> str:
    return transcrire_detail(audio)[0]


# =============================================================================================
# Étage 2b : détection d'activité vocale en flux (Silero, session ONNX de faster-whisper)
# =============================================================================================
class DetecteurParole:
    """Silero VAD appelé tranche par tranche de 512 échantillons, en gardant son état entre les appels."""
    TRANCHE = 512
    CONTEXTE = 64

    def __init__(self):
        self.session = get_vad_model().session
        self.reinitialiser()

    def reinitialiser(self):
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = np.zeros((1, 1, 128), dtype=np.float32)
        self.contexte = np.zeros(self.CONTEXTE, dtype=np.float32)
        self.reste = np.zeros(0, dtype=np.float32)

    def probabilite(self, bloc: np.ndarray) -> float:
        """Probabilité de parole la plus haute dans ce bloc (float32, 16 kHz)."""
        audio = np.concatenate([self.reste, bloc])
        n = len(audio) // self.TRANCHE
        self.reste = audio[n * self.TRANCHE:]
        meilleure = 0.0
        for i in range(n):
            x = audio[i * self.TRANCHE:(i + 1) * self.TRANCHE]
            entree = np.concatenate([self.contexte, x])[None, :].astype(np.float32)
            sortie, self.h, self.c = self.session.run(None, {"input": entree, "h": self.h, "c": self.c})
            self.contexte = x[-self.CONTEXTE:]
            meilleure = max(meilleure, float(np.asarray(sortie).reshape(-1)[0]))
        return meilleure


# =============================================================================================
# Sources audio : le micro (sounddevice) ou un fichier (pour tester sans parler)
# =============================================================================================
def lister_peripheriques() -> list[dict]:
    import sounddevice as sd
    apis = sd.query_hostapis()
    resultat = []
    for i, p in enumerate(sd.query_devices()):
        if p["max_input_channels"] > 0:
            resultat.append({"index": i, "nom": p["name"], "api": apis[p["hostapi"]]["name"],
                             "defaut": i == sd.default.device[0]})
    return resultat


def choisir_peripherique():
    """config oreilles.peripherique : null = micro par défaut, entier = index, texte = morceau du nom."""
    import sounddevice as sd
    voulu = REGLAGES.get("peripherique")
    if voulu is None or voulu == "":
        return sd.default.device[0]
    if isinstance(voulu, int):
        return voulu
    for p in lister_peripheriques():
        if voulu.lower() in p["nom"].lower():
            return p["index"]
    raise ValueError(f"Aucun micro dont le nom contient « {voulu} ». Lancer : python -m jarvis peripheriques")


_verrou_audio = threading.Lock()
MICRO_MUET_S = 3.0                # plus aucun son du micro pendant ce temps : il a disparu (casque débranché)


def rafraichir_peripheriques():
    """PortAudio fige la liste des périphériques au démarrage : un casque Bluetooth branché ou changé en route
    n'existait pas pour Jarvis (audit du 19/09). On la relit ; les flux ouverts se referment et se rouvrent seuls."""
    import sounddevice as sd
    with _verrou_audio:
        try:
            sd._terminate()
        except Exception:
            pass
        sd._initialize()


def source_micro(arret: threading.Event, peripherique=None, choisir=None):
    """Générateur de blocs int16 de 80 ms à 16 kHz mono. Si le micro se tait complètement (débranché, casque
    Bluetooth coupé ou changé), la liste des périphériques est relue et le micro rouvert (`choisir` le redésigne)."""
    import sounddevice as sd
    while not arret.is_set():
        file = queue.Queue()

        def rappel(indata, frames, temps, statut, file=file):
            file.put(indata[:, 0].copy())

        try:
            flux = sd.InputStream(samplerate=FREQ, channels=1, dtype="int16", blocksize=BLOC,
                                  device=peripherique, callback=rappel)
        except Exception:
            arret.wait(3)                        # aucun micro pour l'instant : on réessaie, sans tuer l'écoute
            rafraichir_peripheriques()
            try:
                peripherique = choisir() if choisir else None
            except Exception:
                peripherique = None
            continue
        with flux:
            dernier_son = time.time()
            while not arret.is_set():
                try:
                    bloc = file.get(timeout=0.5)
                except queue.Empty:
                    if not flux.active or time.time() - dernier_son > MICRO_MUET_S:
                        break                    # le périphérique a disparu : on le rouvre
                    continue
                dernier_son = time.time()
                yield bloc
        if arret.is_set():
            return
        rafraichir_peripheriques()
        try:
            peripherique = choisir() if choisir else None
        except Exception:
            peripherique = None


def source_fichier(chemin: str, silence_final_s: float = 3.0):
    """Rejoue un fichier audio comme si c'était le micro, puis du silence pour fermer l'écoute."""
    def generateur(arret: threading.Event):
        audio = decode_audio(chemin, sampling_rate=FREQ)
        entier = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        reste = (-len(entier)) % BLOC
        entier = np.concatenate([entier, np.zeros(reste, dtype=np.int16),
                                 np.zeros(int(silence_final_s * FREQ), dtype=np.int16)])
        for i in range(0, len(entier), BLOC):
            if arret.is_set():
                return
            yield entier[i:i + BLOC]
    return generateur


# =============================================================================================
# La boucle : veille -> mot de réveil -> écoute -> transcription -> veille
# =============================================================================================
_REVEIL_PHRASE = re.compile(
    r"^(?:ok |okay |hey |eh |he |dis |dis-moi |dites |allo |salut |bonjour |bonsoir |bon |alors |et )*"
    r"(?:jarvis|jarviss|jarvice|jarvi|jarvys|javis|djarvis|charvis|jarvise|jarwis)\b[\s,.!?:;-]*", re.IGNORECASE)


def detacher_reveil(texte: str) -> str | None:
    """« Jarvis, quelle heure est-il » -> « quelle heure est-il » ; None si la phrase ne commence pas par Jarvis."""
    n = unicodedata.normalize("NFD", texte.strip())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    m = _REVEIL_PHRASE.match(n)
    if not m:
        return None
    return texte.strip()[m.end():].strip() if len(texte.strip()) >= m.end() else ""


_REVEIL_COUPE = re.compile(r"^\s*(?:arvis|rvis)\b[\s,.!?:;-]*", re.IGNORECASE)   # « …rvis, » coupé ; pas « avis » ni « vis »


def retirer_reveil(texte: str) -> str:
    """Après un réveil : « Hey Jarvis, ouvre le bloc-notes » -> « ouvre le bloc-notes » ; un « …rvis, » coupé en tête
    aussi. Le texte sans mot de réveil reste tel quel. Première lettre remise en capitale."""
    reste = detacher_reveil(texte)
    if reste is None:
        reste = _REVEIL_COUPE.sub("", texte.strip(), count=1)
    reste = reste.strip()
    return reste[:1].upper() + reste[1:] if reste else ""


def est_echo(texte: str, phrases_dites: list[str], seuil: float = 0.6) -> bool:
    """Le texte entendu reprend-il les mots de ce que Jarvis vient de dire ? (écho des haut-parleurs)"""
    mots = [m for m in _normaliser(texte).split() if len(m) > 2]
    if len(mots) < 2:
        return False
    dits = set(" ".join(_normaliser(p) for p in phrases_dites).split())
    return sum(1 for m in mots if m in dits) / len(mots) >= seuil


class Oreilles(threading.Thread):
    """`sur_evenement(dict)` reçoit chaque étape ; `sur_texte(texte, infos)` reçoit la transcription finale
    (infos : langue, mode, fin_parole = instant où la personne s'est tue). `sur_texte(texte)` seul est accepté.
    `source` : générateur de blocs (par défaut le micro de config.json)."""

    def __init__(self, sur_evenement=None, sur_texte=None, source=None, jarvis_parle=None, phrases_dites=None):
        super().__init__(daemon=True, name="oreilles")
        self.sur_evenement = sur_evenement or (lambda e: None)
        self.sur_texte = sur_texte
        self._texte_avec_infos = bool(sur_texte) and len(inspect.signature(sur_texte).parameters) >= 2
        self.source = source
        self.jarvis_parle = jarvis_parle
        self.phrases_dites = phrases_dites
        self.arret = threading.Event()
        self.en_pause = threading.Event()
        self.etat = "demarrage"
        self.mot = REGLAGES.get("mot", "hey_jarvis")
        self.tampon_veille: list = []
        self.parle_veille = False
        self.silence_veille = 0.0
        self.compteur_niveau = 0
        self.erreur = None
        self.detecteur = None
        self.vad = None
        # conversation continue et interruption
        self.fenetre_jusqua = 0.0
        self.phrase_libre = None            # None, « fenetre » ou « interruption » : phrase acceptée sans « Jarvis »
        self.voix_nette = 0.0               # secondes de voix nette pendant que Jarvis parle
        self.echos_de_suite = 0
        self.interruption_coupee = False
        # réponse éclair
        self.t_derniere_voix = 0.0
        self.anticipation = None
        self._reprise_auto: threading.Timer | None = None

    # --- cycle de vie ---
    def arreter(self):
        self.arret.set()

    def suspendre(self):
        """Le micro du navigateur prend la main (Espace maintenu) : le micro du PC n'écoute plus, rien d'entamé ne sera livré."""
        self.en_pause.set()
        # filet de sécurité : si la reprise n'arrive jamais (onglet fermé Espace enfoncé, navigateur planté), le micro
        # du PC se rouvre seul au bout d'une minute au lieu de rester sourd jusqu'au redémarrage
        if self._reprise_auto:
            self._reprise_auto.cancel()
        self._reprise_auto = threading.Timer(PAUSE_MAX_S, self.reprendre)
        self._reprise_auto.daemon = True
        self._reprise_auto.start()
        self.parle_veille, self.tampon_veille, self.phrase_libre, self.anticipation = False, [], None, None
        if self.etat == "ecoute":
            self.tampon, self.a_parle, self.etat = [], False, "veille"

    def reprendre(self):
        if self._reprise_auto:
            self._reprise_auto.cancel()
            self._reprise_auto = None
        self.parle_veille, self.tampon_veille = False, []
        if self.detecteur:
            self.detecteur.reset()
        self.en_pause.clear()

    def _emettre(self, type_, **champs):
        self.sur_evenement({"type": type_, "t": time.time(), **champs})

    def run(self):
        try:
            from openwakeword.model import Model
            self.detecteur = Model(wakeword_models=[self.mot], inference_framework="onnx")
            self.vad = DetecteurParole()
            threading.Thread(target=charger_whisper, daemon=True).start()  # préchauffe pendant la veille
            source = self.source or (lambda arret: source_micro(arret, choisir_peripherique(), choisir=choisir_peripherique))
            self.etat = "veille"
            self._emettre("pret", mot=self.mot, seuil=reglage("seuil", 0.5))
            for bloc in source(self.arret):
                if self.en_pause.is_set():
                    continue
                try:
                    if self.etat == "veille":
                        self._veille(bloc)
                    elif self.etat == "ecoute":
                        self._ecoute(bloc)
                except Exception as e:
                    # Une phrase ratée (Whisper sans mémoire vidéo pendant un dessin, par exemple) ne rend plus Jarvis
                    # sourd jusqu'au prochain lancement (audit du 19/09) : on l'annonce, on oublie cette phrase, on
                    # se remet en veille et on continue d'écouter.
                    self._emettre("erreur", message=f"écoute : {type(e).__name__} : {e}")
                    self.tampon, self.a_parle, self.anticipation = [], False, None
                    self.parle_veille, self.tampon_veille = False, []
                    self.etat = "veille"
                    try:
                        self.detecteur.reset()
                    except Exception:
                        pass
                    time.sleep(0.5)
        except Exception as e:
            self.erreur = f"{type(e).__name__} : {e}"
            self.etat = "erreur"
            self._emettre("erreur", message=self.erreur)

    def _jarvis_parle(self) -> bool:
        if self.jarvis_parle:
            return self.jarvis_parle()
        try:
            from .voix import VOIX
            return VOIX.parle()
        except Exception:
            return False

    def _phrases_dites(self) -> list[str]:
        if self.phrases_dites:
            return self.phrases_dites()
        try:
            from .voix import VOIX
            return VOIX.phrases_recentes(25)
        except Exception:
            return []

    def _niveau(self, bloc):
        """Niveau du micro pour le HUD, environ 6 fois par seconde."""
        self.compteur_niveau += 1
        if self.compteur_niveau % 2 == 0:
            rms = float(np.sqrt(np.mean((bloc.astype(np.float32) / 32768.0) ** 2)))
            self._emettre("micro_niveau", valeur=round(min(1.0, rms * 8), 3))

    def _livrer(self, texte: str, langue: str, mode: str):
        infos = {"langue": langue, "mode": mode, "fin_parole": self.t_derniere_voix or time.time()}
        if not self.sur_texte:
            return
        if self._texte_avec_infos:
            self.sur_texte(texte, infos)
        else:
            self.sur_texte(texte)

    # --- conversation continue ---
    def ouvrir_fenetre(self, secondes: float | None = None):
        """Après une réponse : la prochaine phrase, si elle commence dans les `secondes`, n'a pas besoin de « Jarvis »."""
        cc = REGLAGES.get("conversation_continue", {})
        secondes = float(cc.get("secondes", 8)) if secondes is None else secondes
        if not cc.get("actif", True) or secondes <= 0 or self.etat not in ("veille", "transcription"):
            return
        self.fenetre_jusqua = time.time() + secondes
        self._emettre("fenetre_ouverte", duree=secondes, jusqua=self.fenetre_jusqua)

    def fermer_fenetre(self, raison: str = "fermee"):
        if self.fenetre_jusqua:
            self.fenetre_jusqua = 0.0
            self._emettre("fenetre_fermee", raison=raison)

    # --- transcription anticipée ---
    def _anticiper(self, blocs: list):
        if self.anticipation is not None:
            return
        instantane = list(blocs)
        tache = {"n": len(instantane), "fini": threading.Event(), "resultat": ("", "fr")}

        def travail():
            try:
                tache["resultat"] = transcrire_detail(np.concatenate(instantane).astype(np.float32) / 32768.0)
            except Exception:
                tache["resultat"] = None
            finally:
                tache["fini"].set()

        self.anticipation = tache
        threading.Thread(target=travail, daemon=True, name="transcription-anticipee").start()

    def _transcription(self, blocs: list) -> tuple[str, str]:
        """Le résultat anticipé s'il vaut encore (aucune voix depuis), sinon une transcription maintenant."""
        tache, self.anticipation = self.anticipation, None
        if tache is not None and tache["fini"].wait(10) and tache["resultat"] is not None:
            self._emettre("transcription_anticipee", utilisee=True)
            return tache["resultat"]
        return transcrire_detail(np.concatenate(blocs).astype(np.float32) / 32768.0)

    # --- étage 1 : le mot de réveil, la phrase qui commence par « Jarvis », la fenêtre, l'interruption ---
    def _veille(self, bloc):
        maintenant = time.time()
        jarvis_parle = self._jarvis_parle()
        score = float(self.detecteur.predict(bloc)[self.mot])
        seuil = reglage("seuil_parole", 0.85) if jarvis_parle else reglage("seuil", 0.5)
        if score >= seuil:
            self._reveiller(score)
            return
        if self.fenetre_jusqua and maintenant > self.fenetre_jusqua and not self.parle_veille:
            self.fermer_fenetre("delai")
        inter = REGLAGES.get("interruption", {})
        interruption_active = inter.get("actif", True) and not self.interruption_coupee
        if not (reglage("mode_phrase", True) or self.fenetre_jusqua or (jarvis_parle and interruption_active)):
            return
        f = bloc.astype(np.float32) / 32768.0
        p = self.vad.probabilite(f)
        if p >= 0.5:
            if not self.parle_veille:
                self.parle_veille = True
                self.tampon_veille = self.tampon_veille[-6:]      # un peu d'avant-parole
                self.voix_nette = 0.0
                if self.fenetre_jusqua and maintenant <= self.fenetre_jusqua and not jarvis_parle:
                    self.phrase_libre = "fenetre"
                    self.fermer_fenetre("parole")
            self.silence_veille = 0.0
            self.anticipation = None                              # la voix reprend : l'anticipation ne vaut plus
            self.tampon_veille.append(bloc)
            self.t_derniere_voix = maintenant
            self._niveau(bloc)
            if jarvis_parle and interruption_active and self.phrase_libre is None:
                rms = float(np.sqrt(np.mean(f ** 2)))
                nette = p >= float(inter.get("seuil_vad", 0.85)) and rms >= float(inter.get("seuil_niveau", 0.012))
                self.voix_nette = self.voix_nette + BLOC / FREQ if nette else max(0.0, self.voix_nette - BLOC / FREQ)
                if self.voix_nette >= float(inter.get("duree_min_s", 0.35)):
                    self.phrase_libre = "interruption"
                    self._emettre("interruption", voix_s=round(self.voix_nette, 2))
        elif self.parle_veille:
            self.tampon_veille.append(bloc)
            self.silence_veille += BLOC / FREQ
            duree = len(self.tampon_veille) * BLOC / FREQ
            if self.silence_veille >= reglage("anticipation_s", 0.25) and not self._jarvis_parle():
                self._anticiper(self.tampon_veille)
            if self.silence_veille >= reglage("silence_phrase_s", 0.6) or duree >= reglage("max_s", 15.0):
                self._fin_de_phrase_en_veille(duree)
        else:
            self.tampon_veille.append(bloc)
            self.tampon_veille = self.tampon_veille[-6:]

    def _reveiller(self, score):
        # « Jarvis, ouvre le bloc-notes » d'une traite : le mot de réveil est détecté ~0,5 s après « Jarvis », quand
        # « ouvre » est déjà passé. Vu le 17/09 : Jarvis n'avait reçu que « le bloc note ». On garde donc la parole en
        # cours (jusqu'à 1,6 s) : Whisper entend « Jarvis, ouvre le bloc-notes » et le mot de réveil est retiré après.
        garde = self.tampon_veille[-20:] if self.parle_veille and not isinstance(score, str) else []
        self.detecteur.reset()
        self.vad.reinitialiser()
        self.fermer_fenetre("reveil")
        self.tampon = list(garde)
        self.silence = 0.0
        self.a_parle = False
        self.parle_veille = False
        self.tampon_veille = []
        self.phrase_libre = None
        self.anticipation = None
        self.etat = "ecoute"
        self._emettre("mot_detecte", score=round(score, 3) if isinstance(score, float) else score)

    def _fin_de_phrase_en_veille(self, duree):
        """Une phrase vient de finir sans mot de réveil détecté : commence-t-elle par « Jarvis », est-elle dans la
        fenêtre de conversation, ou interrompt-elle Jarvis ?"""
        blocs, libre = self.tampon_veille, self.phrase_libre
        self.parle_veille = False
        self.tampon_veille = []
        self.phrase_libre = None
        if duree < (0.3 if libre else 0.6) or (self._jarvis_parle() and duree < 1.0 and not libre):
            self.anticipation = None
            return
        self.etat = "transcription"
        try:
            texte, langue = self._transcription(blocs)
            if not texte:
                if libre:
                    self._emettre("rien_entendu", raison="transcription vide ou hallucination")
                return
            reste = detacher_reveil(texte)
            if libre == "interruption" and est_echo(texte, self._phrases_dites()):
                self.echos_de_suite += 1
                self._emettre("interruption_ignoree", texte=texte, raison="écho de sa propre voix")
                if self.echos_de_suite >= 2:
                    self.interruption_coupee = True
                    self._emettre("interruption_coupee", raison="écho répété : casque recommandé")
                return
            if libre:
                self.echos_de_suite = 0
                question = reste if reste else texte
                self._emettre("transcription", texte=question, duree=0.0, mode=libre, langue=langue)
                self._livrer(question, langue, libre)
                return
            if reste is None:
                self._emettre("phrase_ignoree", texte=texte)
                return
            if len(reste.split()) >= 2:
                self._emettre("mot_detecte", score="phrase")
                self._emettre("transcription", texte=reste, duree=0.0, mode="phrase", langue=langue)
                self._livrer(reste, langue, "phrase")
            else:
                self._reveiller("phrase")       # « Jarvis ? » seul : on attend la question
                return
        finally:
            if self.etat == "transcription":
                self.detecteur.reset()
                self.etat = "veille"

    # --- étage 2 : l'écoute jusqu'au silence ---
    def _ecoute(self, bloc):
        self.tampon.append(bloc)
        self._niveau(bloc)
        p = self.vad.probabilite(bloc.astype(np.float32) / 32768.0)
        if p >= 0.5:
            if not self.a_parle:
                self.a_parle = True
                self._emettre("ecoute")
            self.silence = 0.0
            self.anticipation = None
            self.t_derniere_voix = time.time()
        else:
            self.silence += BLOC / FREQ
            if self.a_parle and self.silence >= reglage("anticipation_s", 0.25):
                self._anticiper(self.tampon)
        duree = len(self.tampon) * BLOC / FREQ
        if (self.a_parle and self.silence >= reglage("silence_s", 0.7)) or duree >= reglage("max_s", 15.0) \
                or (not self.a_parle and duree >= reglage("attente_parole_s", 4.0)):
            self._terminer(duree)

    def _terminer(self, duree):
        self.etat = "transcription"
        try:
            if not self.a_parle:
                self.anticipation = None
                self._emettre("rien_entendu", raison="pas de parole après le mot de réveil")
                return
            self._emettre("transcription_en_cours", duree_audio=round(duree, 1))
            t = time.time()
            texte, langue = self._transcription(self.tampon)
            if not texte:
                self._emettre("rien_entendu", raison="transcription vide ou hallucination")
                return
            texte = retirer_reveil(texte)
            if not texte:
                # « Hey Jarvis » seul, puis une pause : on attend la vraie question au lieu de dire « rien entendu »
                self.tampon, self.a_parle, self.silence = [], False, 0.0
                self.etat = "ecoute"
                self._emettre("mot_detecte", score="attente")
                return
            self._emettre("transcription", texte=texte, duree=round(time.time() - t, 2), langue=langue)
            self._livrer(texte, langue, "reveil")
        finally:
            if self.etat == "transcription":
                self.tampon = []
                self.detecteur.reset()
                self.etat = "veille"
