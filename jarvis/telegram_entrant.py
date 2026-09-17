"""Le téléphone : Jarvis écoute son bot Telegram et exécute les messages de SON propriétaire.

Sécurité : seul l'identifiant de discussion saisi dans les Réglages (TELEGRAM_CHAT_ID) est obéi ; tout autre
expéditeur est ignoré sans réponse et signalé dans le HUD (événement telegram_refuse). Une action qui change
quelque chose sur le PC (fenêtres, rangement, frappe, presse-papiers, ouvrir une application, volume…) demandée
depuis le téléphone attend un bouton « Oui » dans Telegram ; sans réponse en 55 secondes, elle n'est pas faite.

Messages texte et vocaux : un vocal est téléchargé, décodé (PyAV) et transcrit par Whisper sur la machine, puis
traité comme un texte. La réponse revient en texte et en vocal : la voix de Jarvis (Kokoro) encodée en OGG Opus.

Commandes :
  /aide                    la liste
  /etat                    état de la machine (carte graphique, mémoire, disques)
  /capture                 capture d'écran envoyée en photo
  /image <description>     dessine une image sur la machine et l'envoie
  /notes                   les dernières notes
  /rappel <quand> | <texte>   programme un rappel (« dans 20 minutes | sortir le pain »)
  /dire <texte>            Jarvis le dit à voix haute à la maison
  /silence                 Jarvis se tait
  n'importe quel autre texte, ou un vocal : une question au cerveau, avec ses outils.

Écoute par getUpdates en appel long (25 s) : une connexion ouverte, affichée comme telle dans le HUD ; seuls les
messages reçus et envoyés comptent comme sorties Internet. Le décalage est gardé dans workspace/telegram.json :
un message n'est jamais exécuté deux fois, même après un redémarrage. Les messages sont traités un par un dans un
fil à part : l'écoute continue pendant qu'une question attend son bouton de confirmation."""
import io
import itertools
import json
import os
import queue
import threading
import time
from pathlib import Path

import requests

from . import compteur
from .config import CONFIG, RACINE, SECRETS

REGLAGES = CONFIG.setdefault("telegram", {})
# en essai (faux Telegram), un décalage à part : celui du vrai bot n'est jamais écrasé par de petits numéros
ETAT = RACINE / "workspace" / ("telegram_essai.json" if os.environ.get("JARVIS_TELEGRAM_API") else "telegram.json")
DELAI_BOUTON = 55                     # sous la limite d'une minute d'un outil

AIDE = ("Jarvis au téléphone. Commandes :\n/etat · état de la machine\n/capture · capture d'écran\n"
        "/image description · une image dessinée sur la machine\n/notes · les dernières notes\n"
        "/rappel quand | texte · un rappel\n/dire texte · je le dis à voix haute à la maison\n/silence · je me tais\n"
        "Ou écrivez, ou envoyez un vocal : je réponds en texte et en vocal. "
        "Une action sur le PC attend votre bouton « Oui ».")


def api() -> str:
    # JARVIS_TELEGRAM_API : un faux serveur Telegram pour les essais en direct (jamais écrit dans config.json)
    return (os.environ.get("JARVIS_TELEGRAM_API") or REGLAGES.get("api", "https://api.telegram.org")).rstrip("/")


def configure() -> bool:
    return bool(SECRETS.get("TELEGRAM_TOKEN")) and bool(SECRETS.get("TELEGRAM_CHAT_ID"))


def _bot() -> str:
    return f"{api()}/bot{SECRETS['TELEGRAM_TOKEN']}"


# --------------------------------------------------------------------------------------------- audio
def decoder_16k(donnees: bytes):
    """Un vocal Telegram (OGG Opus) ou tout fichier audio -> float32 mono 16 kHz pour Whisper."""
    import av
    import numpy as np
    morceaux = []
    with av.open(io.BytesIO(donnees)) as conteneur:
        reechantillonneur = av.AudioResampler(format="flt", layout="mono", rate=16000)
        for trame in conteneur.decode(audio=0):
            for t in reechantillonneur.resample(trame):
                morceaux.append(t.to_ndarray().reshape(-1))
        for t in reechantillonneur.resample(None):
            morceaux.append(t.to_ndarray().reshape(-1))
    return np.concatenate(morceaux).astype(np.float32) if morceaux else np.zeros(0, dtype=np.float32)


def ogg_opus(audio, frequence: int = 24000) -> bytes:
    """float32 mono -> OGG Opus, le format des messages vocaux Telegram (affichés avec leur forme d'onde)."""
    import av
    import numpy as np
    tampon = io.BytesIO()
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).reshape(1, -1)
    with av.open(tampon, "w", format="ogg") as conteneur:
        flux = conteneur.add_stream("libopus", rate=48000, layout="mono")
        flux.bit_rate = 48000
        trame = av.AudioFrame.from_ndarray(pcm, format="s16", layout="mono")
        trame.sample_rate = frequence
        for paquet in flux.encode(trame):
            conteneur.mux(paquet)
        for paquet in flux.encode(None):
            conteneur.mux(paquet)
    return tampon.getvalue()


def voix_ogg(texte: str, langue: str = "fr") -> bytes:
    """La réponse dite par la voix locale de Jarvis, phrase par phrase, en un seul vocal."""
    import numpy as np
    from . import voix
    morceaux, pause = [], np.zeros(int(voix.FREQ * 0.18), dtype=np.float32)
    for phrase in voix.decouper_phrases(texte[:1500]):
        audio, _ = voix.synthetiser(phrase, "local", langue)
        morceaux += [audio.astype(np.float32), pause]
    if not morceaux:
        return b""
    return ogg_opus(np.concatenate(morceaux), voix.FREQ)


def transcrire_vocal(donnees: bytes) -> tuple[str, str]:
    from . import oreilles
    audio = decoder_16k(donnees)
    if len(audio) < 16000 * 0.3:
        return "", "fr"
    return oreilles.transcrire_detail(audio)


class TelegramEntrant(threading.Thread):
    """`questionner(texte, langue) -> str` : la question au cerveau (le serveur branche _dialoguer, source telegram).
    `actions` : dict des commandes réelles, remplaçable pour les tests (dont transcrire et vocal)."""

    def __init__(self, questionner, sur_evenement=None, actions: dict | None = None):
        super().__init__(daemon=True, name="telegram-entrant")
        self.questionner = questionner
        self.sur_evenement = sur_evenement or (lambda e: None)
        self.actions = actions or actions_reelles()
        self.arret = threading.Event()
        self.offset = self._lire_offset()
        self.en_ecoute = False
        self.photos_attendues = 0          # une image demandée par Telegram : envoyée dès qu'elle est prête
        self.file: queue.Queue = queue.Queue()
        self.boutons: dict[str, dict] = {}  # jeton du bouton -> {evenement, choix, message_id, texte, apres, fin}
        self._numeros = itertools.count(1)
        self.questions_par_bouton: set[str] = set()
        threading.Thread(target=self._traiter_la_file, daemon=True, name="telegram-messages").start()

    # --- état persistant ---
    def _lire_offset(self) -> int:
        try:
            return int(json.loads(ETAT.read_text(encoding="utf-8")).get("offset", 0))
        except Exception:
            return 0

    def _ecrire_offset(self):
        ETAT.parent.mkdir(parents=True, exist_ok=True)
        ETAT.write_text(json.dumps({"offset": self.offset}), encoding="utf-8")

    def _emettre(self, type_, **champs):
        self.sur_evenement({"type": type_, "t": time.time(), **champs})

    # --- envoi ---
    def _poster(self, methode: str, **kwargs) -> dict:
        compteur.compter("telegram")
        r = requests.post(f"{_bot()}/{methode}", timeout=60, **kwargs)
        try:
            return r.json()
        except ValueError:
            return {}

    def envoyer(self, texte: str, boutons: list | None = None) -> int | None:
        corps = {"chat_id": SECRETS["TELEGRAM_CHAT_ID"], "text": texte[:4096]}
        if boutons:
            corps["reply_markup"] = {"inline_keyboard": boutons}
        return ((self._poster("sendMessage", json=corps) or {}).get("result") or {}).get("message_id")

    def envoyer_photo(self, chemin: str, legende: str = ""):
        with Path(chemin).open("rb") as f:
            self._poster("sendPhoto", data={"chat_id": SECRETS["TELEGRAM_CHAT_ID"], "caption": legende[:1024]},
                         files={"photo": (Path(chemin).name, f)})

    def envoyer_vocal(self, ogg: bytes):
        self._poster("sendVoice", data={"chat_id": SECRETS["TELEGRAM_CHAT_ID"]},
                     files={"voice": ("jarvis.ogg", ogg, "audio/ogg")})

    def repondre(self, texte: str, langue: str = "fr", vocal: bool = False):
        """Le texte d'abord (lisible tout de suite), puis la même réponse dite par Jarvis."""
        self.envoyer(texte)
        self._emettre("telegram_envoye", texte=texte)
        if vocal and REGLAGES.get("reponse_vocale", True):
            try:
                ogg = self.actions["vocal"](texte, langue)
                if ogg:
                    self.envoyer_vocal(ogg)
                    self._emettre("telegram_vocal_envoye", octets=len(ogg))
            except Exception as e:
                self._emettre("telegram_erreur", message=f"vocal : {type(e).__name__} : {e}")

    # --- boutons de confirmation ---
    def demander_bouton(self, question: str, delai: float | None = None, apres=None) -> bool | None:
        """Envoie la question avec « Oui » / « Non ». Sans `apres` : attend et rend True, False ou None (délai
        dépassé). Avec `apres(oui)` : rend la main tout de suite, `apres` est appelé au clic."""
        delai = delai or DELAI_BOUTON
        jeton = str(next(self._numeros))
        attente = {"evenement": threading.Event(), "choix": None, "texte": question, "apres": apres, "fin": time.time() + delai}
        self.boutons[jeton] = attente
        attente["message_id"] = self.envoyer(question, [[{"text": "✅ Oui", "callback_data": f"oui:{jeton}"},
                                                          {"text": "❌ Non", "callback_data": f"non:{jeton}"}]])
        self._emettre("telegram_confirmation", question=question)
        if apres is not None:
            threading.Thread(target=self._expirer, args=(jeton,), daemon=True).start()
            return None
        attente["evenement"].wait(delai)
        return self._clore(jeton)

    def _expirer(self, jeton: str):
        attente = self.boutons.get(jeton)
        if attente and not attente["evenement"].wait(max(0.0, attente["fin"] - time.time())):
            self._clore(jeton)

    def _clore(self, jeton: str) -> bool | None:
        attente = self.boutons.pop(jeton, None)
        if not attente:
            return None
        choix = attente["choix"]
        mention = {True: "→ ✅ confirmé", False: "→ ❌ refusé", None: "→ ⌛ sans réponse, rien n'est fait"}[choix]
        try:
            self._poster("editMessageText", json={"chat_id": SECRETS["TELEGRAM_CHAT_ID"], "message_id": attente.get("message_id"),
                                                  "text": f"{attente['texte']}\n{mention}"})
        except requests.RequestException:
            pass
        self._emettre("telegram_confirmation_reponse", question=attente["texte"], choix=choix)
        return choix

    def garde(self, nom: str, arguments: dict, description: str) -> str | None:
        """Branché dans outils.CONTEXTE pendant une question venue du téléphone."""
        choix = self.demander_bouton(f"Je vais {description} sur le PC. D'accord ?")
        if choix:
            return None
        return "Action annulée : vous n'avez pas confirmé." if choix is False else \
            "Action non faite : pas de confirmation dans la minute."

    def confirmer_par_bouton(self, question: str, delai: float):
        """confirmations.demander depuis le téléphone (ex. fermer un document non enregistré) : un bouton."""
        from . import confirmations

        def apres(oui):
            reponse = confirmations.confirmer() if oui else confirmations.refuser()
            if reponse:
                self.repondre(reponse)

        self.questions_par_bouton.add(question)
        self.demander_bouton(question, delai=delai, apres=apres)

    def _clic(self, rappel: dict):
        chat = str(((rappel.get("message") or {}).get("chat") or {}).get("id", ""))
        try:
            self._poster("answerCallbackQuery", json={"callback_query_id": rappel.get("id")})
        except requests.RequestException:
            pass
        if chat != str(SECRETS.get("TELEGRAM_CHAT_ID", "")).strip():
            self._emettre("telegram_refuse", chat=chat, expediteur=(rappel.get("from") or {}).get("username") or chat,
                          apercu="(clic sur un bouton)")
            return
        choix, _, jeton = str(rappel.get("data", "")).partition(":")
        attente = self.boutons.get(jeton)
        if not attente or attente["evenement"].is_set():
            return
        attente["choix"] = choix == "oui"
        attente["evenement"].set()
        if attente["apres"] is not None:
            self._clore(jeton)
            threading.Thread(target=attente["apres"], args=(attente["choix"],), daemon=True).start()

    # --- boucle ---
    def arreter(self):
        self.arret.set()
        self.file.put(None)

    def run(self):
        while not self.arret.is_set():
            if not (REGLAGES.get("commandes", True) and configure()):
                self.en_ecoute = False
                self.arret.wait(10)
                continue
            try:
                self.en_ecoute = True
                compteur.ouvrir_connexion("telegram")
                attente = int(REGLAGES.get("attente_s", 25))
                r = requests.get(f"{_bot()}/getUpdates",
                                 params={"offset": self.offset, "timeout": attente,
                                         "allowed_updates": json.dumps(["message", "callback_query"])},
                                 timeout=attente + 10)
                if r.status_code == 401:
                    self._emettre("telegram_erreur", message="jeton du bot refusé (401)")
                    self.arret.wait(60)
                    continue
                for maj in r.json().get("result", []):
                    self.offset = maj["update_id"] + 1
                    self._ecrire_offset()
                    if maj.get("callback_query"):
                        self._clic(maj["callback_query"])      # tout de suite : une question attend peut-être ce clic
                    else:
                        self.file.put(maj)
            except requests.RequestException:
                self.en_ecoute = False
                self.arret.wait(5)
            except Exception as e:
                self._emettre("telegram_erreur", message=f"{type(e).__name__} : {e}")
                self.arret.wait(5)
        compteur.fermer_connexion("telegram")

    def _traiter_la_file(self):
        while True:
            maj = self.file.get()
            if maj is None:
                return
            try:
                self.traiter_mise_a_jour(maj)
            except Exception as e:
                self._emettre("telegram_erreur", message=f"{type(e).__name__} : {e}")

    def traiter_mise_a_jour(self, maj: dict):
        message = maj.get("message") or {}
        chat = str((message.get("chat") or {}).get("id", ""))
        texte = (message.get("text") or "").strip()
        sonore = message.get("voice") or message.get("audio") or message.get("video_note")
        if not texte and not sonore:
            return
        if chat != str(SECRETS.get("TELEGRAM_CHAT_ID", "")).strip():
            expediteur = (message.get("from") or {}).get("username") or (message.get("from") or {}).get("first_name") or chat
            self._emettre("telegram_refuse", chat=chat, expediteur=expediteur, apercu=(texte or "(message vocal)")[:80])
            return
        compteur.compter("telegram_recu")
        langue = None
        if sonore:
            self._emettre("telegram_recu", texte="message vocal, transcription…", vocal=True)
            try:
                texte, langue = self.actions["transcrire"](self.telecharger(sonore["file_id"]))
            except Exception as e:
                self.envoyer(f"Je n'ai pas pu écouter ce vocal ({type(e).__name__}).")
                return
            if not texte.strip():
                self.envoyer("Je n'ai rien entendu dans ce vocal.")
                return
            self._emettre("telegram_transcrit", texte=texte, langue=langue)
        else:
            self._emettre("telegram_recu", texte=texte)
        try:
            reponse, vocal, langue = self.executer(texte, langue)
        except Exception as e:
            reponse, vocal = f"Échec : {type(e).__name__}.", False
        if reponse and reponse in self.questions_par_bouton:
            self.questions_par_bouton.discard(reponse)     # la question est déjà partie avec ses boutons
            return
        if reponse:
            if sonore:
                reponse = f"🎙 « {texte} »\n\n{reponse}"
            self.repondre(reponse, langue or "fr", vocal)

    def telecharger(self, file_id: str) -> bytes:
        compteur.compter("telegram")
        info = requests.get(f"{_bot()}/getFile", params={"file_id": file_id}, timeout=20).json()
        chemin = (info.get("result") or {}).get("file_path")
        if not chemin:
            raise RuntimeError("fichier introuvable chez Telegram")
        compteur.compter("telegram")
        r = requests.get(f"{api()}/file/bot{SECRETS['TELEGRAM_TOKEN']}/{chemin}", timeout=60)
        r.raise_for_status()
        return r.content

    def executer(self, texte: str, langue: str | None = None) -> tuple[str | None, bool, str | None]:
        """Rend (réponse, la dire aussi en vocal, langue)."""
        commande, _, argument = texte.partition(" ")
        commande = commande.lower().split("@")[0]
        argument = argument.strip()
        a = self.actions
        if commande in ("/start", "/aide", "/help"):
            return AIDE, False, None
        if commande == "/etat":
            return a["etat"](), True, "fr"
        if commande == "/capture":
            chemin = a["capture"]()
            self.envoyer_photo(chemin, "Capture d'écran")
            return None, False, None
        if commande == "/image":
            if not argument:
                return "Que faut-il dessiner ? Exemple : /image un phare sous l'orage", False, None
            self.photos_attendues += 1
            return a["image"](argument), False, None
        if commande == "/notes":
            return a["notes"](), True, "fr"
        if commande == "/rappel":
            quand, _, quoi = argument.partition("|")
            if not quoi.strip():
                return "Format : /rappel dans 20 minutes | sortir le pain", False, None
            return a["rappel"](quand.strip(), quoi.strip()), False, None
        if commande == "/dire":
            if not argument:
                return "Que dois-je dire ? Exemple : /dire le dîner est prêt", False, None
            a["dire"](argument)
            return "C'est dit à la maison.", False, None
        if commande == "/silence":
            a["silence"]()
            return "Je me tais.", False, None
        if commande.startswith("/"):
            return "Commande inconnue. /aide pour la liste.", False, None
        from . import langue as module_langue
        from . import outils
        outils.contexte("telegram", self.garde)
        try:
            reponse = self.questionner(texte, langue)
        finally:
            outils.contexte("", None)
        return reponse, True, langue or module_langue.detecter_texte(texte)

    def image_prete(self, chemin: str, legende: str):
        """Appelé par le serveur à chaque image générée : envoyée si Telegram l'attendait."""
        if self.photos_attendues > 0:
            self.photos_attendues -= 1
            self.envoyer_photo(chemin, legende)


def actions_reelles() -> dict:
    from .outils import etat_machine, generer_image, notes, rappel, systeme
    from .voix import VOIX

    def capture():
        systeme.capture()
        return str(sorted((RACINE / "workspace" / "captures").glob("capture_*.png"))[-1])

    return {"etat": etat_machine.executer, "capture": capture, "image": generer_image.executer, "notes": notes.lire_notes,
            "rappel": rappel.executer, "dire": lambda t: VOIX.dire(t), "silence": lambda: VOIX.taire("telegram"),
            "transcrire": transcrire_vocal, "vocal": voix_ogg}


# --------------------------------------------------------------------------------------------- assistant de clé
def verifier_jeton(jeton: str) -> dict:
    """Réglages : le jeton donné par @BotFather est-il bon ? Rend le nom du bot et son lien."""
    compteur.compter("telegram")
    try:
        r = requests.get(f"{api()}/bot{jeton}/getMe", timeout=15)
    except requests.RequestException as e:
        return {"ok": False, "message": f"Telegram ne répond pas ({type(e).__name__})."}
    if r.status_code in (401, 404):
        return {"ok": False, "message": "Telegram refuse ce jeton : recopiez-le en entier depuis @BotFather."}
    bot = (r.json() or {}).get("result") or {}
    nom = bot.get("username", "?")
    return {"ok": True, "bot": nom, "lien": f"https://t.me/{nom}",
            "message": f"Jeton valide : votre bot est @{nom}. Ouvrez t.me/{nom}, appuyez sur Démarrer, envoyez-lui "
                       f"« bonjour », puis cliquez sur « trouver mon identifiant »."}


def trouver_identifiant(jeton: str) -> dict:
    """Réglages : lit le dernier message privé reçu par le bot (celui que la personne vient d'envoyer) pour en
    tirer l'identifiant de discussion. Sert pendant la configuration, quand l'écoute n'est pas encore active."""
    compteur.compter("telegram")
    try:
        r = requests.get(f"{api()}/bot{jeton}/getUpdates", params={"timeout": 0, "allowed_updates": json.dumps(["message"])}, timeout=20)
    except requests.RequestException as e:
        return {"ok": False, "message": f"Telegram ne répond pas ({type(e).__name__})."}
    if r.status_code in (401, 404):
        return {"ok": False, "message": "Enregistrez d'abord un jeton valide."}
    if r.status_code == 409:
        return {"ok": False, "message": "Le bot est déjà écouté ailleurs (un autre programme ou un webhook) : arrêtez-le puis réessayez."}
    messages = [m.get("message") for m in (r.json() or {}).get("result", []) if m.get("message")]
    prives = [m for m in messages if (m.get("chat") or {}).get("type") == "private"]
    if not prives:
        return {"ok": False, "message": "Aucun message reçu par le bot : envoyez-lui « bonjour » depuis Telegram, puis réessayez."}
    chat = prives[-1]["chat"]
    nom = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username") or "?"
    return {"ok": True, "identifiant": str(chat["id"]), "nom": nom,
            "message": f"Trouvé : la discussion de {nom}. Enregistrez : seuls ses messages seront obéis."}
