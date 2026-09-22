"""Le cerveau : Ollama, personnage Jarvis, boucle d'appel d'outils, historique de conversation.
La réponse est reçue en flux : chaque phrase complète est remise à `sur_phrase` dès qu'elle est finie,
pour que la voix commence à parler avant la fin de la génération.

Réponse éclair (mesuré le 16/09) : la consigne (personnage + règles + outils, environ 2 500 jetons) doit rester
identique d'un tour à l'autre, sinon Ollama la relit en entier (976 ms au lieu de 62 ms). D'où :
- la date seule dans la consigne, jamais l'heure ;
- les souvenirs pertinents et la langue de réponse ajoutés à la question, pas à la consigne ;
- `rechauffer()` au démarrage et après tout appel annexe, pour que le cache d'Ollama contienne déjà la consigne."""
import json
import re
import socket
import threading
import time
from datetime import datetime

import requests

from . import compteur, confirmations, memoire, outils, personnalites
from .config import CONFIG, SECRETS

MODE = CONFIG["cerveau"].get("mode", "local")            # local : Ollama sur ce PC ; cloud : URL distante compatible Ollama
CLOUD = CONFIG["cerveau"].get("cloud", {})
OLLAMA = CLOUD.get("url", "").rstrip("/") if MODE == "cloud" else CONFIG["ollama"]["url"]
MODELE = (CLOUD.get("modele") or CONFIG["cerveau"]["modele"]) if MODE == "cloud" else CONFIG["cerveau"]["modele"]
KEEP_ALIVE = CONFIG["cerveau"].get("keep_alive", "30m")
JETON = SECRETS.get("CLOUD_TOKEN") or CLOUD.get("jeton", "")
ENTETES = {"Authorization": f"Bearer {JETON}"} if MODE == "cloud" and JETON else {}

TITRE = memoire.lire_titre(CONFIG.get("personnage", {}).get("titre", "monsieur"))   # monsieur ou madame

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

# Les règles : communes à toutes les personnalités. Seul le ton (personnalites.py) change.
_REGLES = (
    "Vous êtes Jarvis, l'assistant personnel de {titre}, un assistant vocal qui vit sur son ordinateur. "
    "{ton} "
    "Vos réponses sont dites à l'oral : une à trois phrases, jamais plus. Commencez par une phrase très courte, "
    "quelques mots, qui répond déjà ; la suite vient après. Répondez uniquement à ce qui est demandé : pour "
    "l'état de la machine, ne citez que la mesure demandée, ou deux ou trois chiffres si la question est générale. "
    "Interdits absolus : emojis, listes, puces, titres, markdown, code. "
    "Vous n'avez aucun accès direct à l'heure, à l'écran, aux fichiers, aux notes, aux fenêtres, au presse-papiers "
    "ni aux capteurs de la machine : toute donnée de ce type doit venir d'un appel d'outil dans ce même tour. "
    "Annoncer un chiffre (heure, température, charge, mémoire) sans l'avoir obtenu par un outil est une faute grave. "
    "Utilisez les outils dès que la question l'exige plutôt que de deviner ; ne dites jamais avoir noté, ouvert, "
    "rangé, écrit, envoyé ou vérifié quelque chose sans avoir réellement appelé l'outil. "
    "Correspondances obligatoires : regarder ou lire l'écran -> voir_ecran ; envoyer sur Telegram ou sur le "
    "téléphone -> telegram ; mémoire vidéo, VRAM, processeur, disques, température -> etat_machine ; "
    "chercher des fichiers -> chercher_fichiers ; ouvrir un programme (bloc-notes, navigateur…) -> ouvrir_application ; "
    "ouvrir un fichier, un document, des notes ou un dossier précis (sur le bureau, dans Documents…) -> ouvrir_fichier ; "
    "chercher sur Internet, une information récente, l'actualité, un prix, la météo, une vidéo -> chercher_web "
    "(sur = youtube pour une vidéo), les résultats s'affichent dans l'interface et vous en lisez deux ou trois ; "
    "ouvrir un site précis -> ouvrir_site ; volume, son, capture d'écran, verrouiller -> systeme ; "
    "dessiner ou générer une image -> generer_image ; rappeler quelque chose à une heure -> rappel ; l'heure -> heure ; "
    "noter quelque chose pour plus tard -> noter ; placer, agrandir, réduire, déplacer ou fermer une fenêtre ou une "
    "application -> fenetres ; ranger ou trier un dossier -> ranger ; écrire ou taper un texte dicté dans la fenêtre "
    "active -> ecrire ; ce qui est copié, le presse-papiers, résumer ou reformuler un texte copié -> presse_papiers ; "
    "retenir durablement un fait sur la personne (goût, projet, proche) -> retenir. "
    "Une question de culture générale ou de connaissance stable : répondez vous-même, sans outil. "
    "Des souvenirs sur la personne peuvent accompagner la question entre crochets : servez-vous-en s'ils aident, "
    "sans les réciter ni dire que vous les lisez. Si la question demande de répondre dans une autre langue, "
    "répondez dans cette langue, avec le même ton. "
    "Si un outil renvoie une erreur ou demande une confirmation, dites-le simplement. "
    "Ne décrivez jamais vos outils ni votre fonctionnement interne, sauf si on vous le demande. "
    "Nous sommes le {date}. {rappel}"
)


def date_du_jour() -> str:
    d = datetime.now()
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


def personnage(nom: str | None = None) -> str:
    """La consigne complète : stable toute la journée tant que la personnalité ne change pas."""
    p = personnalites.PERSONNALITES[nom or personnalites.actuelle()]
    return _REGLES.format(titre=TITRE, ton=p["ton"].format(titre=TITRE), date=date_du_jour(), rappel=p["rappel"])


_TITRE_RE = re.compile(r"\s*,?\s*\b(monsieur|madame)\b\s*,?\s*", re.IGNORECASE)


def epurer_titre(phrase: str, deja: bool) -> tuple[str, bool]:
    """Garde le premier « monsieur / madame » de la réponse, retire les suivants."""
    if not _TITRE_RE.search(phrase):
        return phrase, deja
    if not deja:
        return phrase, True
    nouveau = _TITRE_RE.sub(" ", phrase).strip()
    nouveau = re.sub(r"\s+([.,!?])", r"\1", nouveau)
    nouveau = re.sub(r"\s{2,}", " ", nouveau)
    if nouveau:
        nouveau = nouveau[0].upper() + nouveau[1:]
    return nouveau, True


TITRE_ESPACEMENT = 4       # au plus un « monsieur » toutes les 4 réponses


def titre_une_fois(texte: str, deja: bool) -> tuple[str, bool]:
    """La réponse entière passée phrase par phrase dans epurer_titre ; renvoie (texte, le titre a-t-il été gardé)."""
    phrases, garde = [], False
    for p in re.split(r"(?<=[.!?…])\s+", texte):
        avant = deja
        p, deja = epurer_titre(p, deja)
        garde = garde or (not avant and deja)
        if p:
            phrases.append(p)
    return " ".join(phrases), garde


def question_augmentee(texte: str, langue: str = "fr", souvenirs: list[dict] | None = None) -> str:
    """La question telle que le cerveau la reçoit : souvenirs utiles et langue de réponse ajoutés après."""
    annexes = []
    bloc = memoire.annexe(souvenirs or [], langue)
    if bloc:
        annexes.append(bloc)
    if langue == "en":
        annexes.append("[The user spoke English: reply in English, same personality and tone. "
                       "Say « sir » or « madam » instead of monsieur or madame.]")
    return texte + ("\n\n" + "\n".join(annexes) if annexes else "")


# Une demande qui exige d'agir sur la machine (ouvrir, ranger, écrire…). Vu en direct le 17/09 : qwen3 répondait
# « Ouvrir_application, bloc-notes » ou « Oui, monsieur » en texte au lieu d'appeler l'outil, et l'historique ainsi
# empoisonné faisait échouer toutes les demandes suivantes.
_DEMANDE_ACTION = re.compile(
    # Audit du 19/09 : « écris-moi un poème », « quelle note as-tu eue ? », « le volume de la Terre »,
    # « rappelle-moi ce que tu as dit » passaient pour des actions sur le PC : la réponse était retenue et le modèle
    # poussé vers un outil (jusqu'à taper le poème dans la fenêtre active). Les mots ambigus exigent maintenant leur
    # contexte : écrire quelque part, noter quelque chose, régler le volume, se faire rappeler de faire quelque chose.
    r"\b(ouvr\w*|ferm(?:e|er|ez)\b(?!\s+(?:agricole|du|de la))|lance[rz]?|d[ée]marr\w*|mets|mettre|mettez|place[rz]?|"
    r"d[ée]place\w*|agrandi\w*|r[ée]dui[st]\w*|range[rz]?|tri[ez]?|tape[rz]?|dessine[rz]?|g[ée]n[èe]re[rz]?|envoie[rz]?|"
    r"cherche[rz]?|monte[rz]?|baisse[rz]?|coupe[rz]?(?!\s+d[eu]\s)|verrouill\w*|captur\w*|regarde[rz]?|r[ée]sume[rz]?|analyse[rz]?|"
    r"reformule[rz]?|briefing|miniatures?|"
    r"note[rz]?\s+(?:[çc]a|cela|que|qu'|le |la |les |mon |ma |mes |dans )|prends?\s+(?:en\s+)?note|noter\b|"
    r"rappelle[rz]?[- ](?:moi|nous)\s+(?!ce |ce qu|qui |comment |pourquoi |quand |quel|quoi |le nom |la |les |ton |ta |tes )\S+|"
    r"volume\s+(?:[àa]|au|de\s+\d)|"
    r"[ée]cri(?:s|re|vez)\b[^.?!]*\b(?:dans|sur|ici|l[àa]|fen[êe]tre|bloc|word|document|message|mail)\b|"
    # en anglais : ouvrir, fermer, lancer, écrire quelque part, noter, rappeler, dessiner, envoyer, chercher, son…
    r"open|close|launch|start|minimi[sz]e|maximi[sz]e|move|type|remind\s+me\s+to|draw|send|search|mute|lock|"
    r"screenshot|turn\s+(?:up|down|on|off)|take\s+a\s+(?:photo|picture)|look\s+at|write\b[^.?!]*\b(?:in|into)\b|"
    r"note\s+(?:that|this|down))\b", re.IGNORECASE)
RAPPEL_ACTION = ("[Consigne : cette demande exige une action sur l'ordinateur. Appelez maintenant l'outil qui convient, "
                 "sans écrire son nom dans votre texte. Si l'action est vraiment impossible, dites pourquoi en une phrase.]")


def _echo_d_outil(texte: str) -> bool:
    """Le modèle a écrit un nom d'outil en texte (« Ouvrir_application, bloc-notes ») au lieu de l'appeler."""
    debut = (texte or "").strip().lower()
    return bool(debut) and any(debut.startswith(nom) for nom in outils.OUTILS if "_" in nom)


class _Portillon:
    """Retient le tout début d'une réponse en flux (24 caractères ou la première ponctuation) : un nom d'outil écrit
    en texte n'est jamais dit. Coût mesuré : quelques jetons, une centaine de millisecondes."""

    def __init__(self, suite):
        self.suite, self.tampon, self.ouvert, self.echo = suite, "", False, False

    def __call__(self, morceau: str):
        if self.ouvert:
            return self.suite(morceau)
        if self.echo:
            return
        self.tampon += morceau
        if len(self.tampon) >= 24 or re.search(r"[.!?,;:]\s", self.tampon):
            self._decider()

    def _decider(self):
        if _echo_d_outil(self.tampon):
            self.echo = True
        else:
            self.ouvert = True
            if self.tampon:
                self.suite(self.tampon)

    def terminer(self):
        if not self.ouvert and not self.echo:
            self._decider()


class Cerveau:
    def __init__(self, max_tours: int = 12):
        self.historique: list[dict] = []
        self.tours = 0
        self.max_tours = max_tours
        self.verrou = threading.Lock()
        self.dernier_echange = 0.0
        self.tours_depuis_souvenirs = 0
        self.stop = threading.Event()          # une interruption : la génération en cours s'arrête tout de suite
        self.flux = None                       # la réponse Ollama en cours de lecture, pour la couper sans attendre
        self.tour_titre = -TITRE_ESPACEMENT    # le dernier tour où « monsieur / madame » a été dit
        self.source_courante = ""              # le canal de la réponse en cours : voix, texte, telegram
        self.derniere_mesure = {}

    def interrompre(self, par: str = "voix"):
        """La personne a repris la parole : la réponse en cours s'arrête, la nouvelle question passera juste après.
        Une réponse pour le téléphone (Telegram) n'est pas coupée par un « Hey Jarvis » ou un Espace à la maison :
        avant l'audit du 19/09 elle s'arrêtait et le téléphone ne recevait jamais rien.
        Le flux est coupé net : attendre le jeton suivant coûtait plus d'une seconde quand la carte graphique est
        occupée par autre chose (vu le 17/09, un jeu ouvert : 1054 ms)."""
        if self.source_courante == "telegram" and par != "telegram":
            return
        self.stop.set()
        flux = self.flux
        try:
            flux.raw._connection.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass                                # pas de flux en cours, ou déjà fermé : le drapeau suffit

    # --- chargement en VRAM ----------------------------------------------
    def _options(self) -> dict:
        return {"num_ctx": CONFIG["cerveau"].get("num_ctx", 8192), "temperature": CONFIG["cerveau"].get("temperature", 0.3)}

    def charger(self) -> float:
        """Charge le modèle en VRAM et remplit le cache d'Ollama avec la consigne. Retourne la durée. Rien en mode cloud.
        Rien non plus si un travail lourd tient la carte (image, hologramme, vidéo) : il la rendra, le cerveau reviendra."""
        from . import carte
        if MODE == "cloud":
            return 0.0
        if carte.occupee():                    # un rendu tient la carte : il la rendra, on reviendra après
            return 0.0
        t = time.time()
        # Même num_ctx que les vrais appels, sinon Ollama recharge le modèle au premier message.
        requests.post(f"{OLLAMA}/api/chat", json={"model": MODELE, "messages": [], "keep_alive": KEEP_ALIVE,
                                                  "options": {"num_ctx": CONFIG["cerveau"].get("num_ctx", 8192)}},
                      timeout=300)
        self.rechauffer()
        return time.time() - t

    def rechauffer(self) -> float:
        """Un appel d'un seul jeton avec la vraie consigne et les vrais outils : Ollama garde ce préfixe en cache,
        la prochaine question ne paie plus que ses propres jetons. À rappeler après un appel annexe au modèle.
        Sauté si un travail lourd tient la carte : c'est ce réchauffage qui ramenait le cerveau pendant un rendu."""
        from . import carte
        if MODE == "cloud" or carte.occupee():
            return 0.0
        t = time.time()
        try:
            with self.verrou:
                messages = [{"role": "system", "content": personnage()}] + self._recents() + [{"role": "user", "content": "Bonjour."}]
            requests.post(f"{OLLAMA}/api/chat", json={
                "model": MODELE, "messages": messages, "tools": outils.SCHEMAS, "stream": False,
                "think": CONFIG["cerveau"].get("think", False), "keep_alive": KEEP_ALIVE,
                "options": {**self._options(), "num_predict": 1}}, timeout=120)
        except Exception:
            pass
        return time.time() - t

    def decharger(self) -> None:
        if MODE == "cloud":
            return
        requests.post(f"{OLLAMA}/api/chat", json={"model": MODELE, "messages": [],
                                                  "keep_alive": 0}, timeout=60)

    @staticmethod
    def solde_cloud() -> dict | None:
        """Crédit restant sur la passerelle (mode cloud), None en local ; {"erreur": …} si elle ne répond pas."""
        if MODE != "cloud":
            return None
        try:
            base = OLLAMA[:-len("/ollama")] if OLLAMA.endswith("/ollama") else OLLAMA
            r = requests.get(f"{base}/solde", headers=ENTETES, timeout=5)
            return r.json() if r.status_code == 200 else {"erreur": r.status_code}
        except Exception:
            return {"erreur": "injoignable"}

    @staticmethod
    def modeles_charges() -> list[str]:
        if MODE == "cloud":
            return [f"{MODELE} (distant)"]
        try:
            r = requests.get(f"{OLLAMA}/api/ps", timeout=5).json()
            return [m["name"] for m in r.get("models", [])]
        except Exception:
            return []

    # --- conversation -----------------------------------------------------
    def _appel(self, messages: list[dict], sur_morceau=None) -> dict:
        """Un appel Ollama en flux. Renvoie le message assistant complet (contenu + appels d'outils)."""
        corps = {
            "model": MODELE,
            "messages": messages,
            "tools": outils.SCHEMAS,
            "stream": True,
            "think": CONFIG["cerveau"].get("think", False),
            "keep_alive": KEEP_ALIVE,
            "options": self._options(),
        }
        contenu, appels = "", []
        if MODE == "cloud":
            compteur.compter("cerveau_cloud")
        with requests.post(f"{OLLAMA}/api/chat", json=corps, headers=ENTETES, stream=True, timeout=300) as r:
            if MODE == "cloud" and r.status_code >= 400:
                # la passerelle explique pourquoi (hors ligne, crédit, plafond) : Jarvis le dit au lieu de planter
                explications = {401: "Aucun jeton Jarvis Cloud n'est configuré. Ajoutez-le dans les Réglages.",
                                403: "Votre jeton Jarvis Cloud n'est pas reconnu. Vérifiez-le dans les Réglages.",
                                402: "Votre crédit Jarvis Cloud est épuisé. Rechargez-le sur la boutique pour continuer.",
                                429: "Vous avez atteint le plafond de calcul du jour sur le cerveau distant. À demain.",
                                503: "Le cerveau distant est hors ligne pour le moment : la machine qui l'héberge est éteinte. "
                                     "Je reste là pour tout ce qui ne demande pas de réfléchir.",
                                504: "Le cerveau distant met trop de temps à répondre. Réessayez dans un instant."}
                texte = explications.get(r.status_code, f"Le cerveau distant a répondu une erreur {r.status_code}.")
                if sur_morceau:
                    sur_morceau(texte)
                return {"role": "assistant", "content": texte}
            r.raise_for_status()
            self.flux = r
            try:
                if self.stop.is_set():
                    return {"role": "assistant", "content": ""}
                for ligne in r.iter_lines():
                    if self.stop.is_set():
                        break
                    if not ligne:
                        continue
                    j = json.loads(ligne)
                    m = j.get("message") or {}
                    if m.get("content"):
                        contenu += m["content"]
                        if sur_morceau:
                            sur_morceau(m["content"])
                    if m.get("tool_calls"):
                        appels.extend(m["tool_calls"])
                    if j.get("done"):
                        self.derniere_mesure = {k: j.get(k) for k in ("prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")}
                        break
            except (requests.RequestException, OSError, ValueError, AttributeError):
                if not self.stop.is_set():
                    raise                       # une vraie panne ; sinon c'est interrompre() qui a coupé le flux
            finally:
                self.flux = None
        message = {"role": "assistant", "content": contenu}
        if appels:
            message["tool_calls"] = appels
        return message

    def repondre(self, texte: str, journal=None, sur_phrase=None, sur_jeton=None, langue: str = "fr",
                 souvenirs: list[dict] | None = None, source: str = "") -> str:
        """Question -> réponse orale complète.
        `journal(nom, resultat)` reçoit chaque appel d'outil ; `sur_phrase(phrase)` chaque phrase dès qu'elle est finie ;
        `sur_jeton(morceau)` chaque morceau de texte tel qu'il sort du modèle (pour l'affichage) ;
        `langue` la langue de la question (fr ou en) ; `souvenirs` les souvenirs pertinents (memoire.pertinents)."""
        with self.verrou:
            try:
                return self._repondre(texte, journal, sur_phrase, sur_jeton, langue, souvenirs, source)
            finally:
                self.source_courante = ""

    def _repondre(self, texte, journal, sur_phrase, sur_jeton, langue, souvenirs, source) -> str:
        from .voix import Decoupeur
        self.source_courante = source
        self.stop.clear()
        systeme = {"role": "system", "content": personnage()}
        debut = len(self.historique)
        self.historique.append({"role": "user", "content": question_augmentee(texte, langue, souvenirs)})
        # L'historique garde les appels d'outils et leurs résultats : sans eux, le modèle ne voit que des
        # réponses « sorties de nulle part » et se met à imiter ce style en inventant les chiffres.
        messages = [systeme] + self._recents()
        # « monsieur » une fois de temps en temps, pas à chaque réponse (vu le 17/09 : « il m'appelle monsieur à
        # chaque phrase ») : s'il a été dit dans l'une des TITRE_ESPACEMENT dernières réponses, il est retiré.
        recent = self.tours - self.tour_titre < TITRE_ESPACEMENT
        titre_dit = {"deja": recent, "initial": recent}

        def sur_phrase_epuree(p):
            p, titre_dit["deja"] = epurer_titre(p, titre_dit["deja"])
            if p:
                sur_phrase(p)

        decoupeur = Decoupeur(sur_phrase_epuree, premiere_courte=True) if sur_phrase else None
        reponse_totale = []

        def sur_morceau(m):
            if sur_jeton:
                sur_jeton(m)
            if decoupeur:
                decoupeur.ajouter(m)

        action = bool(_DEMANDE_ACTION.search(texte))
        for tour in range(5):
            parle = sur_morceau if (sur_jeton or decoupeur) else None
            # la première réponse à une demande d'action n'est dite qu'une fois sûre : outil appelé, ou vraie réponse
            retenue = tour == 0 and action
            portillon = _Portillon(parle) if parle and not retenue else None
            message = self._appel(messages, None if retenue else portillon)
            if portillon:
                portillon.terminer()
            contenu = (message.get("content") or "").strip()
            appels = message.get("tool_calls") or []
            if tour == 0 and not appels and not self.stop.is_set() and (action or _echo_d_outil(contenu)):
                relance = self._appel(messages + [{"role": "assistant", "content": contenu},
                                                  {"role": "user", "content": RAPPEL_ACTION}], None)
                if relance.get("tool_calls"):
                    message, appels = relance, relance["tool_calls"]        # la fausse réponse n'entre pas dans l'historique
                    contenu = (relance.get("content") or "").strip()
                else:
                    if _echo_d_outil(contenu) or not contenu:
                        contenu = (relance.get("content") or "").strip()
                    message = {"role": "assistant", "content": contenu}
                if parle and contenu and (retenue or portillon.echo) and not self.stop.is_set():
                    parle(contenu)
            elif retenue and parle and contenu and not self.stop.is_set():
                parle(contenu)
            if _echo_d_outil(contenu):
                contenu = ""
            message["content"] = contenu
            if contenu:
                reponse_totale.append(contenu)
            if not appels or self.stop.is_set():
                break
            messages.append(message)
            self.historique.append(message)
            direct = None
            for appel in appels:
                fonction = appel["function"]
                arguments = fonction.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                questions_avant, refus_avant = confirmations.demandes, outils.refus_compte
                resultat = outils.executer(fonction["name"], arguments)
                if journal:
                    journal(fonction["name"], resultat)
                message_outil = {"role": "tool", "content": resultat, "tool_name": fonction["name"]}
                messages.append(message_outil)
                self.historique.append(message_outil)
                # une question de confirmation se dit mot pour mot : reformulée, le « oui / non » perd son objet
                if outils.est_direct(fonction["name"]) or confirmations.demandes != questions_avant \
                        or outils.refus_compte != refus_avant:
                    direct = resultat
            if direct is not None:
                # Outil à réponse directe (image en cours) : son texte est la réponse, sans rappeler le
                # modèle, pour ne pas recharger le cerveau pendant que ComfyUI occupe la VRAM.
                reponse_totale.append(direct)
                if decoupeur:
                    decoupeur.ajouter(direct)
                if sur_jeton:
                    sur_jeton(direct)
                break
        else:
            texte_boucle = "Je tourne en rond. Reformulez, je vous prie." if langue != "en" else "I'm going in circles. Could you rephrase?"
            reponse_totale.append(texte_boucle)
            if decoupeur:
                decoupeur.ajouter(texte_boucle)

        if self.stop.is_set():
            # Coupé par la personne (elle a repris la parole) : le bout de réponse n'est ni rendu ni gardé. Vu en
            # direct le 17/09 : « Oui, monsieur. », début d'une réponse coupée, entrait dans l'historique ; le modèle
            # l'imitait ensuite (« tu m'entends ? » -> « Oui, monsieur. ») et n'appelait plus l'outil demandé.
            if any(m.get("role") == "tool" for m in self.historique[debut:]):
                self.historique.append({"role": "assistant", "content": "(réponse interrompue : la personne a repris la parole)"})
            else:
                del self.historique[debut:]
            self.dernier_echange = time.time()
            return ""
        if decoupeur:
            decoupeur.terminer()
        reponse = " ".join(r for r in reponse_totale if r).strip() or ("…" if langue == "en" else f"Je n'ai rien à répondre, {TITRE}.")
        reponse, titre_garde = titre_une_fois(reponse, titre_dit["initial"])
        if titre_garde:
            self.tour_titre = self.tours
        self.historique.append({"role": "assistant", "content": reponse})
        self.tours += 1
        self.tours_depuis_souvenirs += 1
        self.dernier_echange = time.time()
        return reponse

    def ajouter_echange(self, question: str, reponse: str):
        """Un échange traité sans le modèle (commande, réflexe) entre quand même dans l'historique."""
        with self.verrou:
            self.historique.append({"role": "user", "content": question})
            self.historique.append({"role": "assistant", "content": reponse})
            self.dernier_echange = time.time()

    def generer(self, consigne: str, texte: str, delai: float = 60, format: dict | None = None) -> str:
        """Un appel simple, sans outils ni historique (résumé, reformulation). Le cache est réchauffé après.
        `format` : un schéma JSON (sortie structurée d'Ollama). Même num_ctx que le dialogue : sinon Ollama recharge."""
        corps = {"model": MODELE, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
                 "messages": [{"role": "system", "content": consigne}, {"role": "user", "content": texte}],
                 "options": {"num_ctx": CONFIG["cerveau"].get("num_ctx", 8192), "temperature": 0.3}}
        if format:
            corps["format"] = format
            corps["options"]["num_predict"] = 2000      # un JSON qui boucle ne remplit pas tout le contexte
        r = requests.post(f"{OLLAMA}/api/chat", json=corps, headers=ENTETES, timeout=delai)
        r.raise_for_status()
        resultat = r.json()["message"]["content"].strip()
        threading.Thread(target=self.rechauffer, daemon=True).start()
        return resultat

    def fin_de_session(self, historique: list[dict] | None = None) -> dict:
        """Le cerveau relit la session et propose des souvenirs ; seuls les stables sont gardés.
        `historique` : une copie prise avant un « oublie tout » (sinon l'historique courant, s'il a du neuf)."""
        if historique is None:
            if self.tours_depuis_souvenirs == 0:
                return {"gardes": [], "ecartes": []}
            with self.verrou:
                historique = list(self.historique)
        resultat = memoire.proposer(historique, OLLAMA, MODELE, ENTETES)
        self.tours_depuis_souvenirs = 0
        threading.Thread(target=self.rechauffer, daemon=True).start()
        return resultat

    def _recents(self) -> list[dict]:
        """Les `max_tours` derniers tours complets (question, appels d'outils, résultats, réponse)."""
        indices = [i for i, m in enumerate(self.historique) if m["role"] == "user"]
        exces = len(indices) - self.max_tours
        if exces <= 0:
            return self.historique
        # la fenêtre avance par paquets de quatre tours : le début de l'historique reste identique d'un tour à
        # l'autre, Ollama garde son cache au lieu de tout relire à chaque question
        return self.historique[indices[min(len(indices) - 1, ((exces + 3) // 4) * 4)]:]

    def oublier(self) -> None:
        self.historique.clear()
        self.tours_depuis_souvenirs = 0


CERVEAU = Cerveau()
