"""Le serveur : sert le HUD et expose l'API. Chaque route existe sous /x et sous /api/x.
La réponse du cerveau est parlée par le serveur (sounddevice), phrase par phrase ; le HUD suit par /events
(WebSocket, ou SSE pour les clients simples).

Le dialogue (`_dialoguer`) : commandes rapides (mémoire, personnalité, confirmation, annulation…), réflexes (l'heure,
la date, sans modèle), puis le cerveau avec les souvenirs pertinents et la langue de la question. Chaque prise de
parole garde l'instant où la personne s'est tue : au premier son, l'événement `latence` donne la réponse éclair.
À la fin d'une réponse dite à la voix, les oreilles ouvrent la fenêtre de conversation continue."""
import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import queue
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

# Windows lit parfois .js comme text/plain dans le registre : les modules ES seraient refusés
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import cerveau as module_cerveau
from . import (commandes, compteur, confirmations, memoire, oreilles, outils, personnalites, reglages, sentinelle,
               telegram_entrant, voix)
from . import langue as module_langue
from .cerveau import CERVEAU, MODE, MODELE
from .config import CONFIG, RACINE
from .outils import etat_machine, ranger, rappel, telegram

HUD = Path(__file__).parent / "hud" / "index.html"
WORKSPACE = RACINE / "workspace"
DEMARRAGE = {"cerveau": False, "whisper": False, "voix": False, "micro": False, "erreurs": []}
OREILLES: oreilles.Oreilles | None = None
SENTINELLE: sentinelle.Sentinelle | None = None
TELEGRAM: telegram_entrant.TelegramEntrant | None = None
EXTINCTION = threading.Event()

# Amorces dites pendant qu'un outil travaille, si Jarvis n'a encore rien dit (viennent du cache).
AMORCES = ["Voyons voir.", "Un instant.", "Je vérifie.", "Tout de suite."]
AMORCES_EN = ["Let me see.", "One moment.", "Checking."]
OUTILS_AVEC_AMORCE = {"etat_machine", "chercher_fichiers", "chercher_web", "systeme", "telegram", "rappel",
                      "ouvrir_application", "ouvrir_site", "fenetres", "ranger", "presse_papiers"}
_amorce_index = [0]

# prise de parole -> {t0 (fin de la phrase de la personne), source, langue, mode, t_phrase, mesuree}
PRISES: dict[int, dict] = {}
DERNIERE_LATENCE: dict = {}
JOURNAL_DIALOGUE = logging.getLogger("dialogue")   # workspace/journal.log : chaque question, sa réponse, ses outils
class _LangueEnCours(threading.local):
    """La langue de la question en cours, propre à chaque fil. Audit du 19/09 : un dictionnaire global, modifié avant
    le verrou du cerveau, se mélangeait entre une question vocale et une question Telegram (amorces dites à la
    maison pendant la question du téléphone, capture partie sur le mauvais canal)."""
    langue = "fr"


_langue_en_cours = _LangueEnCours()


# --- diffusion des événements ------------------------------------------------------------
class Emetteur:
    def __init__(self):
        self.abonnes: list[queue.Queue] = []
        self.verrou = threading.Lock()

    def emettre(self, evenement: dict):
        with self.verrou:
            for q in list(self.abonnes):
                q.put(evenement)

    def abonner(self) -> queue.Queue:
        q = queue.Queue()
        with self.verrou:
            self.abonnes.append(q)
        return q

    def desabonner(self, q):
        with self.verrou:
            if q in self.abonnes:
                self.abonnes.remove(q)

    def flux(self):
        """Version SSE, pour curl et les tests."""
        q = self.abonner()
        try:
            yield "data: " + json.dumps({"type": "connecte", "t": time.time()}) + "\n\n"
            while True:
                try:
                    yield "data: " + json.dumps(q.get(timeout=15)) + "\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            self.desabonner(q)


EMETTEUR = Emetteur()


def _brancher_evenements():
    """Les briques diffusent sur /events ; le serveur réagit à quelques-uns."""
    compteur.sur_evenement = EMETTEUR.emettre
    memoire.sur_evenement = EMETTEUR.emettre
    confirmations.sur_evenement = EMETTEUR.emettre

    def sur_voix(e):
        EMETTEUR.emettre(e)
        infos = PRISES.get(e.get("prise"))
        if not infos:
            return
        if e["type"] == "premier_son" and not infos.get("mesuree"):
            infos["mesuree"] = True
            total = (e["t"] - infos["t0"]) * 1000
            t_debut = infos.get("t_debut", infos["t_texte"])
            detail = {"oreille_ms": round((t_debut - infos["t0"]) * 1000), "memoire_ms": round((infos["t_texte"] - t_debut) * 1000)}
            if infos.get("t_phrase"):
                detail["cerveau_ms"] = round((infos["t_phrase"] - infos["t_texte"]) * 1000)
                detail["voix_ms"] = round((e["t"] - infos["t_phrase"]) * 1000)
            DERNIERE_LATENCE.clear()
            DERNIERE_LATENCE.update(total_ms=round(total), source=infos["source"], mode=infos.get("mode"), **detail,
                                    premiere_phrase=e.get("texte"), quand=time.time())
            EMETTEUR.emettre({"type": "latence", "t": time.time(), "prise": e["prise"], **DERNIERE_LATENCE})
        elif e["type"] == "parole_fin" and infos.get("source") == "voix" and OREILLES:
            OREILLES.ouvrir_fenetre()                 # conversation continue : on écoute sans mot de réveil

    voix.sur_evenement = sur_voix

    def sur_outil(e):
        EMETTEUR.emettre(e)
        if e["type"] == "outil_appel" and e["outil"] in OUTILS_AVEC_AMORCE and not voix.VOIX.parle() \
                and e.get("source") != "telegram":
            langue = _langue_en_cours.langue
            liste = AMORCES_EN if langue == "en" else AMORCES
            voix.VOIX.dire_phrase(liste[_amorce_index[0] % len(liste)], langue=langue)
            _amorce_index[0] += 1

    outils.sur_evenement = sur_outil

    def sur_evenement_module(e):
        EMETTEUR.emettre(e)
        # chaque résultat part là où la demande a été faite (champ « demande » posé par l'outil) : le téléphone
        # ou la maison, jamais les deux au hasard (audit du 19/09)
        au_telephone = e.get("demande") == "telegram" and TELEGRAM
        if e["type"] == "image":
            if au_telephone:
                TELEGRAM.envoyer_photo(e["chemin"], e.get("prompt", ""))
            else:
                voix.VOIX.dire(f"L'image est prête, {module_cerveau.TITRE}, en {e['duree']:.0f} secondes. Elle est à l'écran.")
        elif e["type"] == "capture" and au_telephone:
            TELEGRAM.envoyer_photo(e["chemin"], "Capture d'écran")
        elif e["type"] == "image_erreur":
            if au_telephone:
                TELEGRAM.repondre(f"Le dessin a échoué : {e['message'].split(' : ', 1)[-1]}")
            else:
                voix.VOIX.dire(f"Le dessin a échoué, {module_cerveau.TITRE}.")
        elif e["type"] == "vision_erreur" and au_telephone:
            TELEGRAM.repondre(f"Je n'ai pas pu regarder l'écran : {e['message'].split(' : ', 1)[-1]}")
        elif e["type"] == "vision":
            # La description du modèle de vision est dite telle quelle et entre dans l'historique du cerveau.
            if au_telephone:
                TELEGRAM.repondre(e["texte"], vocal=True)
            else:
                voix.VOIX.dire(e["texte"])
            CERVEAU.historique.append({"role": "assistant", "content": f"(Sur {e['ecran']}) {e['texte']}"})
        elif e["type"] == "video_resume":
            moments = " ; ".join(f"{int(m['t']) // 60}:{int(m['t']) % 60:02d} {m['titre']}" for m in e["moments"])
            CERVEAU.historique.append({"role": "assistant", "content": f"(Résumé de la vidéo « {e['titre']} ») {e['resume']} Moments : {moments}"})
            if e.get("source") == "telegram" and TELEGRAM:
                lignes = "\n".join(f"{int(m['t']) // 60}:{int(m['t']) % 60:02d} · {m['titre']}" for m in e["moments"])
                TELEGRAM.repondre(f"« {e['titre']} »\n\n{e['resume']}\n\nMoments clés :\n{lignes}\n\nhttps://youtu.be/{e['id']}")
            else:
                voix.VOIX.dire(f"Voici le résumé de « {e['titre']} ». {e['resume']} Les moments clés sont sur la frise.")
        elif e["type"] == "video_erreur":
            texte = f"Je n'ai pas pu résumer cette vidéo : {e['message'].split(' : ', 1)[-1]}."
            if e.get("source") == "telegram" and TELEGRAM:
                TELEGRAM.repondre(texte)
            else:
                voix.VOIX.dire(texte)
        elif e["type"] == "miniatures":
            if e.get("source") == "telegram" and TELEGRAM:
                for n, chemin in enumerate(e["chemins"], 1):
                    TELEGRAM.envoyer_photo(chemin, f"Miniature {n} · {e['titre']}")
            else:
                voix.VOIX.dire(f"Les trois miniatures « {e['titre']} » sont prêtes, en {e['duree']:.0f} secondes. Elles sont à l'écran.")
        elif e["type"] == "miniatures_erreur":
            texte = f"Les miniatures ont échoué : {e['message'].split(' : ', 1)[-1]}."
            if e.get("source") == "telegram" and TELEGRAM:
                TELEGRAM.repondre(texte)
            else:
                voix.VOIX.dire(texte)
        elif e["type"] == "vision_erreur":
            voix.VOIX.dire(f"Je n'ai pas réussi à voir l'écran, {module_cerveau.TITRE}.")

    for module in outils.MODULES:
        if hasattr(module, "sur_evenement"):
            module.sur_evenement = sur_evenement_module

    def sur_rappel(r):
        texte = f"Rappel, {module_cerveau.TITRE} : {r['texte']}"
        if r.get("en_retard"):
            prevu = datetime.fromtimestamp(r["quand"])
            texte = f"Rappel en retard, prévu à {prevu.hour} h {prevu.minute:02d} pendant que j'étais éteint : {r['texte']}"
        EMETTEUR.emettre({"type": "rappel", "t": time.time(), "texte": r["texte"]})
        voix.VOIX.taire("rappel")
        voix.VOIX.dire(texte)
        if CONFIG.get("rappels", {}).get("telegram", True) and telegram.configure():
            threading.Thread(target=telegram.envoyer, args=(texte,), daemon=True).start()

    rappel.sur_rappel = sur_rappel


def _prechauffer():
    """Charge les briques en parallèle au démarrage et fait une première inférence de chacune (réponse éclair :
    la première question ne paie ni les noyaux CUDA de Whisper, ni l'échauffement de Kokoro, ni la lecture de la consigne)."""
    def brique(nom, fonction):
        try:
            fonction()
            DEMARRAGE[nom] = True
        except Exception as e:
            DEMARRAGE["erreurs"].append(f"{nom} : {e}")
            EMETTEUR.emettre({"type": "erreur", "t": time.time(), "message": f"{nom} : {e}"})

    def memoire_prete():
        # un appel annexe au modèle (mots-clés, souvenirs de session) vide son cache : on le réchauffe juste après
        memoire.apres_appel_cerveau = lambda: threading.Thread(target=CERVEAU.rechauffer, daemon=True).start()
        if MODE == "local":
            memoire.importer_ancien_resume(module_cerveau.OLLAMA, MODELE)
            memoire.thematiser_manquants()
        memoire.pertinents("bonjour")                 # calcule les vecteurs manquants et charge le modèle de plongements

    for nom, fonction in (("cerveau", CERVEAU.charger), ("whisper", oreilles.prechauffer_whisper),
                          ("voix", voix.prechauffer), ("memoire", memoire_prete)):
        threading.Thread(target=brique, args=(nom, fonction), daemon=True).start()
    outils.demarrer_taches_de_fond()
    threading.Thread(target=_gardien_de_session, daemon=True, name="gardien-session").start()


def _gardien_de_session():
    """Dix minutes sans échange après une vraie conversation : fin de session, le cerveau propose ses souvenirs."""
    while not EXTINCTION.is_set():
        time.sleep(30)
        inactivite = float(CONFIG.get("memoire", {}).get("session_inactivite_min", 10)) * 60
        if CERVEAU.tours_depuis_souvenirs >= 2 and time.time() - CERVEAU.dernier_echange > inactivite \
                and not CERVEAU.verrou.locked():
            try:
                CERVEAU.fin_de_session()
            except Exception:
                pass


def _demarrer_oreilles():
    """Le micro en permanence : mot de réveil -> transcription -> cerveau -> voix."""
    global OREILLES
    if not CONFIG["oreilles"].get("actif", True):
        return

    def sur_evenement(e):
        if e["type"] == "pret":
            DEMARRAGE["micro"] = True
        elif e["type"] == "erreur":
            DEMARRAGE["erreurs"].append("micro : " + e["message"])
        elif e["type"] == "mot_detecte":
            voix.VOIX.taire("mot de réveil")   # Jarvis se tait et écoute
            CERVEAU.interrompre()
            if voix.VOIX.muet:
                voix.VOIX.muet = False         # « silence » ne dure que jusqu'au prochain réveil
                EMETTEUR.emettre({"type": "silence", "t": time.time(), "actif": False})
        elif e["type"] == "interruption":
            CERVEAU.interrompre()              # la génération en cours s'arrête,
            voix.VOIX.taire("interruption")    # la voix se coupe tout de suite
        EMETTEUR.emettre(e)

    def sur_texte(texte, infos):
        if _doublon_vocal(texte):
            return

        # dans un fil à part : les oreilles continuent d'écouter pendant que Jarvis répond (interruption possible)
        def traiter():
            resultat = _dialoguer(texte, langue=infos.get("langue"), fin_parole=infos.get("fin_parole"),
                                  source="voix", mode=infos.get("mode"))
            EMETTEUR.emettre({"type": "reponse", "t": time.time(), **resultat})
        threading.Thread(target=traiter, daemon=True, name="dialogue").start()

    OREILLES = oreilles.Oreilles(sur_evenement=sur_evenement, sur_texte=sur_texte)
    OREILLES.start()


_DERNIERES_PHRASES: list[tuple[float, str]] = []
_verrou_doublons = threading.Lock()


def _doublon_vocal(texte: str, fenetre_s: float = 6.0) -> bool:
    """Vu le 17/09 : Espace maintenu dans le HUD ET micro du PC ouvert, chaque phrase était traitée deux fois (« Tu peux
    ouvrir le bloc-notes ? » et « Tu peux ouvrir le bloc note ? ») : deux réponses, deux Bloc-notes. Une phrase presque
    identique à une autre reçue il y a moins de 6 s, par l'un ou l'autre micro, est ignorée."""
    import difflib
    cle = re.sub(r"\W+", " ", texte.lower()).strip()
    maintenant = time.time()
    with _verrou_doublons:
        _DERNIERES_PHRASES[:] = [(t, c) for t, c in _DERNIERES_PHRASES if maintenant - t < fenetre_s]
        if cle and any(difflib.SequenceMatcher(None, cle, c).ratio() >= 0.8 for _, c in _DERNIERES_PHRASES):
            EMETTEUR.emettre({"type": "phrase_ignoree", "t": maintenant, "texte": texte, "raison": "doublon (deux micros)"})
            return True
        _DERNIERES_PHRASES.append((maintenant, cle))
    return False


def _sentinelle_parler(texte: str) -> bool:
    """La sentinelle ne coupe jamais la parole : ni pendant que Jarvis parle, ni pendant une question."""
    if voix.VOIX.parle() or voix.VOIX.muet or CERVEAU.verrou.locked():
        return False
    if OREILLES and (OREILLES.etat in ("ecoute", "transcription") or OREILLES.fenetre_jusqua > time.time()
                     or OREILLES.parle_veille):
        return False
    voix.VOIX.dire(texte)
    return True


@contextlib.asynccontextmanager
async def cycle_de_vie(app):
    global SENTINELLE, TELEGRAM
    _brancher_evenements()
    _prechauffer()
    _demarrer_oreilles()
    SENTINELLE = sentinelle.Sentinelle(_sentinelle_parler, EMETTEUR.emettre)
    SENTINELLE.start()
    TELEGRAM = telegram_entrant.TelegramEntrant(_questionner_depuis_telegram, EMETTEUR.emettre)
    confirmations.boutons_telegram = TELEGRAM.confirmer_par_bouton
    TELEGRAM.start()
    # La carte graphique de cette machine sert aussi les clients cloud (config maison.actif) : l'agent va
    # chercher le travail sur la passerelle, aucun port ouvert ici.
    from . import maison, service_cloud
    maison.sur_evenement = EMETTEUR.emettre
    if service_cloud.service_externe_actif():
        # le service autonome (python -m jarvis cloud, lancé avec Windows) tourne déjà : on l'affiche, on ne le double pas
        service_cloud.etat.update(actif=True, passerelle=True, externe=True, tunnel=bool(service_cloud.DOMAINE),
                                  adresse=f"https://{service_cloud.DOMAINE}" if service_cloud.DOMAINE else "")
    elif CONFIG.get("service_cloud", {}).get("actif"):
        service_cloud.demarrer(EMETTEUR.emettre)      # passerelle + agent + tunnel, tout chez l'auteur
    elif maison.demarrer():
        DEMARRAGE["maison"] = True                    # agent seul, passerelle ailleurs
    yield
    service_cloud.arreter()
    for fil in (OREILLES, SENTINELLE, TELEGRAM):
        if fil:
            fil.arreter()
    voix.VOIX.taire("arrêt")


app = FastAPI(title="Jarvis", lifespan=cycle_de_vie)
WORKSPACE.mkdir(exist_ok=True)
app.mount("/workspace", StaticFiles(directory=str(WORKSPACE)), name="workspace")


# le HUD : scripts en modules ES et three.js copié dans hud/vendor (aucun chargement Internet)
class _HudSansCache(StaticFiles):
    """Toujours revalidé : après une mise à jour automatique, le navigateur ne garde pas l'ancien HUD en cache."""
    async def get_response(self, path, scope):
        reponse = await super().get_response(path, scope)
        reponse.headers["Cache-Control"] = "no-cache"
        return reponse


app.mount("/hud", _HudSansCache(directory=str(HUD.parent)), name="hud")


class Demande(BaseModel):
    texte: str


class Phrase(BaseModel):
    texte: str
    moteur: str | None = None


@app.get("/")
def page():
    return FileResponse(HUD, headers={"Cache-Control": "no-cache"})


@app.get("/etat")
@app.get("/api/etat")
def etat():
    from .outils import chercher_fichiers
    return {"modele": MODELE, "cerveau": {"mode": MODE, "modele": MODELE, "distant": MODE == "cloud"},
            "charges": CERVEAU.modeles_charges(), "pret": DEMARRAGE,
            "micro": OREILLES.etat if OREILLES else "inactif", "parle": voix.VOIX.parle(), "silence": voix.VOIX.muet,
            "voix": {"moteur": CONFIG["voix"]["moteur"], "elevenlabs": voix.elevenlabs_configure()},
            "titre": module_cerveau.TITRE, "souvenirs": memoire.nombre(), "solde": CERVEAU.solde_cloud(),
            "personnalite": personnalites.actuelle(), "latence": DERNIERE_LATENCE or None,
            "conversation_continue": CONFIG["oreilles"].get("conversation_continue", {}),
            "interruption": {**CONFIG["oreilles"].get("interruption", {}),
                             "coupee": bool(OREILLES and OREILLES.interruption_coupee)},
            "sentinelle": {"actif": CONFIG.get("sentinelle", {}).get("actif", True)},
            "telegram": {"configure": telegram_entrant.configure(), "ecoute": bool(TELEGRAM and TELEGRAM.en_ecoute)},
            "cagnotte_url": CONFIG.get("cagnotte", {}).get("url", ""),
            "maison": __import__("jarvis.maison", fromlist=["etat"]).etat,
            "service_cloud": {**__import__("jarvis.service_cloud", fromlist=["etat"]).etat,
                              "bilan": __import__("jarvis.service_cloud", fromlist=["solde_admin"]).solde_admin()},
            "sorties_internet": compteur.etat(),
            "index_fichiers": chercher_fichiers.etat(), "rappels": rappel.liste(),
            "machine": etat_machine.mesures()}


@app.get("/events")
@app.get("/api/events")
def evenements_sse():
    return StreamingResponse(EMETTEUR.flux(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.websocket("/events")
async def evenements_ws(websocket: WebSocket):
    await websocket.accept()
    q = EMETTEUR.abonner()
    boucle = asyncio.get_running_loop()
    try:
        await websocket.send_text(json.dumps({"type": "connecte", "t": time.time()}))
        while True:
            try:
                e = await boucle.run_in_executor(None, q.get, True, 10)
            except queue.Empty:
                e = {"type": "ping", "t": time.time()}
            await websocket.send_text(json.dumps(e))
    except (WebSocketDisconnect, RuntimeError, ConnectionError):
        pass
    finally:
        EMETTEUR.desabonner(q)


class Evenement(BaseModel):
    type: str
    champs: dict = {}


@app.post("/evenement")
@app.post("/api/evenement")
def evenement(e: Evenement):
    """Injecte un événement (pour déclencher les états du HUD depuis le serveur, en test ou en démo)."""
    EMETTEUR.emettre({"type": e.type, "t": time.time(), **e.champs})
    return {"ok": True}


def _extinction():
    """« Jarvis, éteins-toi » : au revoir, puis arrêt propre du serveur (le lanceur se termine)."""
    EXTINCTION.set()
    EMETTEUR.emettre({"type": "extinction", "t": time.time()})
    voix.VOIX.taire("extinction")
    voix.VOIX.muet = False
    voix.VOIX.dire(f"Au revoir, {module_cerveau.TITRE}. Extinction des systèmes.")

    def finir():
        if OREILLES:
            OREILLES.arreter()
        try:
            CERVEAU.fin_de_session()      # les souvenirs de la session, avant de partir
        except Exception:
            pass
        voix.VOIX.attendre(20)
        try:
            CERVEAU.decharger()
        except Exception:
            pass
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=finir, daemon=True).start()


# =============================================================================================
# Le dialogue
# =============================================================================================
def _tutoie() -> bool:
    return personnalites.actuelle() == "coach"


def _dire_reponse(question: str, reponse: str, t0: float, source: str, langue: str = "fr", mode: str | None = None,
                  commande: str | None = None, historique: bool = True) -> dict:
    """Une réponse faite sans le cerveau (commande, réflexe) : dite, mesurée, affichée, gardée dans l'historique."""
    prise = None
    if reponse and source != "telegram":
        voix.VOIX.taire("réponse")
        prise = voix.VOIX.nouvelle_prise()
        PRISES[prise] = {"t0": t0, "t_texte": time.time(), "t_phrase": time.time(), "source": source, "langue": langue, "mode": mode}
        EMETTEUR.emettre({"type": "reflexion", "t": time.time(), "prise": prise, "question": question})
        for p in voix.decouper_phrases(reponse):
            voix.VOIX.dire_phrase(p, prise, langue=langue)
        EMETTEUR.emettre({"type": "reponse_complete", "t": time.time(), "prise": prise, "texte": reponse, "chrono": {}})
    if historique and reponse:
        CERVEAU.ajouter_echange(question, reponse)
    return {"question": question, "reponse": reponse, "outils": [], "chrono": {}, "commande": commande, "prise": prise}


_REFLEXE_HEURE = re.compile(r"^(?:jarvis[,.]?\s*)?(?:quelle heure (?:est[- ]il|il est)|il est quelle heure|t'?as l'?heure|"
                            r"tu as l'?heure|vous avez l'?heure|l'?heure s'il (?:te|vous) pla[iî]t|donne[- ]moi l'?heure|"
                            r"what time is it|what's the time|what is the time)\s*(?:s'il (?:te|vous) pla[iî]t|please)?\s*[?!.]*$",
                            re.IGNORECASE)
_REFLEXE_DATE = re.compile(r"^(?:jarvis[,.]?\s*)?(?:quel jour (?:sommes[- ]nous|on est|est[- ]on|nous sommes)|on est quel jour|"
                           r"quelle est la date(?: d'aujourd'hui)?|on est le combien|what day is it|what's the date|"
                           r"what is the date(?: today)?)\s*[?!.]*$", re.IGNORECASE)


def _reflexe(texte: str, langue: str) -> str | None:
    """L'heure et la date sans passer par le modèle : réponse en un clin d'œil, dans le ton de la personnalité."""
    maintenant = datetime.now()
    nom = personnalites.actuelle()
    if _REFLEXE_HEURE.match(texte.strip()):
        if langue == "en":
            base = maintenant.strftime("It's %I:%M %p.").replace(" 0", " ").lstrip("0")
            return {"sarcastique": base + " Time flies when you're having fun.", "coach": base + " Let's make it count!"}.get(nom, base)
        base = f"Il est {maintenant.hour} h {maintenant.minute:02d}."
        return {"sarcastique": base + " Le temps file, surtout quand on me le demande.",
                "coach": base + " Chaque minute compte, on avance !"}.get(nom, base)
    if _REFLEXE_DATE.match(texte.strip()):
        if langue == "en":
            return maintenant.strftime("Today is %A, %B %d, %Y.").replace(" 0", " ")
        return f"Nous sommes le {module_cerveau.date_du_jour()}."
    return None


def _a_la_troisieme_personne(fait: str) -> str:
    """« je préfère le thé » -> « Préfère le thé » ; « mon frère » -> « son frère ». Simple, sans modèle."""
    f = " " + fait.strip().rstrip(".") + " "
    for de, vers in ((" je suis ", " est "), (" j'ai ", " a "), (" je m'appelle ", " s'appelle "), (" je vais ", " va "),
                     (" je fais ", " fait "), (" je peux ", " peut "), (" je veux ", " veut "), (" je dois ", " doit "),
                     (" j'", " "), (" je ", " "), (" mon ", " son "), (" ma ", " sa "), (" mes ", " ses "), (" moi ", " lui "),
                     (" me ", " se "), (" m'", " s'")):
        f = re.sub(re.escape(de), vers, f, flags=re.IGNORECASE)
    f = re.sub(r"\s+", " ", f).strip()
    return f[:1].upper() + f[1:]


def _commande(commande: str, argument, texte: str, t0: float, source: str, langue: str, mode) -> dict:
    tu = _tutoie()
    titre = module_cerveau.TITRE
    if commande == "extinction":
        _extinction()
        return {"question": texte, "reponse": f"Au revoir, {titre}. Extinction des systèmes.", "outils": [], "chrono": {},
                "commande": commande}
    if commande == "oublier":
        # les souvenirs de la session d'abord (sur une copie), puis la conversation s'efface
        if CERVEAU.tours_depuis_souvenirs:
            threading.Thread(target=CERVEAU.fin_de_session, args=(list(CERVEAU.historique),), daemon=True).start()
        CERVEAU.oublier()
        voix.VOIX.taire("oublier")
        return _dire_reponse(texte, "C'est oublié." if tu else f"C'est oublié, {titre}.", t0, source, langue, mode, commande, historique=False)
    if commande == "silence":
        voix.VOIX.taire("silence")
        voix.VOIX.muet = True
        EMETTEUR.emettre({"type": "silence", "t": time.time(), "actif": True})
        return {"question": texte, "reponse": "", "outils": [], "chrono": {}, "commande": commande}
    if commande in ("titre_madame", "titre_monsieur"):
        titre = "madame" if commande == "titre_madame" else "monsieur"
        module_cerveau.TITRE = titre
        memoire.ecrire_titre(titre)
        EMETTEUR.emettre({"type": "titre", "t": time.time(), "titre": titre})
        threading.Thread(target=CERVEAU.rechauffer, daemon=True).start()
        return _dire_reponse(texte, f"Bien, {titre}. Je m'en souviendrai.", t0, source, langue, mode, commande)
    if commande == "souvenirs_liste":
        souvenirs = sorted(memoire.lister(), key=lambda s: (-s.get("utilise", 0), -s.get("cree", 0)))
        EMETTEUR.emettre({"type": "panneau", "t": time.time(), "genre": "constellation", "titre": "Ce que je sais de vous",
                          **memoire.constellation()})
        if not souvenirs:
            reponse = "Je ne sais encore rien de toi." if tu else "Je ne sais encore rien de vous. Dites-moi « retiens que… »."
        else:
            exemples = " ; ".join(memoire.pour_la_personne(s["fait"], tu) for s in souvenirs[:3])
            n = len(souvenirs)
            reponse = (f"Je sais {n} chose{'s' if n > 1 else ''} sur {'toi' if tu else 'vous'}. "
                       + (f"Par exemple : {exemples}." if n > 1 else f"{exemples[:1].upper()}{exemples[1:]}.")
                       + (" Tout est dans la constellation." if n > 3 else ""))
        return _dire_reponse(texte, reponse, t0, source, langue, mode, commande)
    if commande == "retenir":
        s = memoire.ajouter(_a_la_troisieme_personne(argument), f"dit le {datetime.now():%d/%m/%Y}")
        reponse = (f"C'est noté : {memoire.pour_la_personne(s['fait'], tu)}." if s else "Je n'ai rien compris à retenir.")
        return _dire_reponse(texte, reponse, t0, source, langue, mode, commande)
    if commande == "oublier_souvenir":
        retires = memoire.oublier(argument)
        if retires:
            reponse = "C'est oublié : " + " ; ".join(memoire.pour_la_personne(s["fait"], tu) for s in retires) + "."
        else:
            reponse = "Je n'ai aucun souvenir qui corresponde."
        return _dire_reponse(texte, reponse, t0, source, langue, mode, commande)
    if commande == "personnalite":
        personnalites.definir(argument)
        EMETTEUR.emettre({"type": "personnalite", "t": time.time(), "nom": argument})
        threading.Thread(target=CERVEAU.rechauffer, daemon=True).start()
        return _dire_reponse(texte, personnalites.PERSONNALITES[argument]["accuse"].format(titre=titre), t0, source, langue, mode, commande)
    if commande == "sentinelle":
        actif = argument == "on"
        sentinelle.definir_actif(actif)
        EMETTEUR.emettre({"type": "sentinelle_etat", "t": time.time(), "actif": actif})
        return _dire_reponse(texte, "Sentinelle activée, je surveille." if actif else "Sentinelle désactivée.", t0, source, langue, mode, commande)
    if commande == "annuler":
        return _dire_reponse(texte, ranger.annuler()["message"], t0, source, langue, mode, commande)
    if commande == "confirmer":
        return _dire_reponse(texte, confirmations.confirmer(), t0, source, langue, mode, commande)
    if commande == "refuser":
        return _dire_reponse(texte, confirmations.refuser(), t0, source, langue, mode, commande)
    return {"question": texte, "reponse": "", "outils": [], "chrono": {}, "commande": commande}


def _dialoguer(texte: str, langue: str | None = None, fin_parole: float | None = None, source: str = "texte",
               mode: str | None = None) -> dict:
    """Question -> commande, réflexe, ou cerveau (souvenirs, outils, flux) -> voix phrase par phrase.
    `source` : voix (micro), texte (HUD), telegram (réponse écrite, rien n'est dit à la maison)."""
    t_debut = time.time()
    t0 = fin_parole or t_debut
    langue = langue or module_langue.detecter_texte(texte)
    commande, argument = commandes.analyser(texte, confirmations.en_attente())
    if commande:
        EMETTEUR.emettre({"type": "commande", "t": time.time(), "commande": commande, "question": texte})
        return _commande(commande, argument, texte, t0, source, langue, mode)
    reflexe = _reflexe(texte, langue)
    if reflexe:
        EMETTEUR.emettre({"type": "reflexe", "t": time.time(), "question": texte, "reponse": reflexe})
        return _dire_reponse(texte, reflexe, t0, source, langue, mode)

    parler = source != "telegram"
    souvenirs = memoire.pertinents(texte) if CONFIG.get("memoire", {}).get("actif", True) else []
    if souvenirs:
        EMETTEUR.emettre({"type": "souvenirs_utilises", "t": time.time(), "ids": [s["id"] for s in souvenirs],
                          "faits": [s["fait"] for s in souvenirs]})
    appels, chrono = [], {}
    if parler:
        voix.VOIX.taire("nouvelle question")
    prise = voix.VOIX.nouvelle_prise()
    infos = {"t0": t0, "t_debut": t_debut, "t_texte": time.time(), "source": source, "langue": langue, "mode": mode}
    PRISES[prise] = infos
    for ancienne in [p for p in PRISES if p < prise - 50]:
        PRISES.pop(ancienne, None)
    _langue_en_cours.langue = langue

    def sur_phrase(p):
        infos.setdefault("t_phrase", time.time())
        if parler and not CERVEAU.stop.is_set():
            voix.VOIX.dire_phrase(p, prise, langue=langue)

    def sur_jeton(m):
        EMETTEUR.emettre({"type": "jeton", "t": time.time(), "prise": prise, "texte": m})

    t = time.time()
    EMETTEUR.emettre({"type": "reflexion", "t": time.time(), "prise": prise, "question": texte, "langue": langue})
    try:
        reponse = CERVEAU.repondre(texte, journal=lambda nom, res: appels.append({"outil": nom, "resultat": res[:300]}),
                                   sur_phrase=sur_phrase, sur_jeton=sur_jeton, langue=langue, souvenirs=souvenirs,
                                   source=source)
    except Exception as e:
        # Ollama arrêté, erreur 500 faute de mémoire vidéo… Avant l'audit du 19/09 l'exception tuait le fil : rien
        # n'était dit et le HUD restait bloqué sur « réflexion ». Jarvis dit maintenant ce qui se passe.
        JOURNAL_DIALOGUE.exception("cerveau")
        injoignable = isinstance(e, requests.ConnectionError)
        reponse = (f"Mon cerveau ne répond pas, {module_cerveau.TITRE} : Ollama n'a pas l'air lancé. Relancez-moi, ou lancez Ollama."
                   if injoignable else f"Mon cerveau a eu un problème ({type(e).__name__}). Reposez-moi la question dans un instant.")
        EMETTEUR.emettre({"type": "erreur", "t": time.time(), "message": f"cerveau : {type(e).__name__} : {e}"})
        if parler:
            voix.VOIX.dire_phrase(reponse, prise, langue=langue)
    finally:
        _langue_en_cours.langue = "fr"
    chrono["cerveau"] = round(time.time() - t, 2)
    chrono["premiere_phrase"] = round(infos["t_phrase"] - t, 2) if infos.get("t_phrase") else None
    verification = _verifier_chiffres(appels, reponse)
    JOURNAL_DIALOGUE.info("%s [%s/%s] « %s » -> « %s » ; outils : %s ; %.1f s", source, mode or "-", langue, texte, reponse,
                          ", ".join(f"{a['outil']}" for a in appels) or "aucun", chrono["cerveau"])
    chrono["prompt"] = CERVEAU.derniere_mesure
    EMETTEUR.emettre({"type": "reponse_complete", "t": time.time(), "prise": prise, "texte": reponse, "chrono": chrono, "source": source})
    return {"question": texte, "reponse": reponse, "outils": appels, "chrono": chrono, "prise": prise, "langue": langue,
            "souvenirs": [s["fait"] for s in souvenirs], "verification": verification}


DERNIERE_VERIFICATION: dict = {}


def _verifier_chiffres(appels: list[dict], reponse: str) -> dict | None:
    """Après un outil à faits (YouTube, briefing) : chaque chiffre de la réponse est cherché dans le JSON de faits,
    les écarts s'affichent dans un panneau."""
    noms = [a["outil"] for a in appels if a["outil"] in outils.OUTILS_A_FAITS]
    if not noms or not reponse:
        return None
    from .youtube import verification
    faits = outils.OUTILS_A_FAITS[noms[-1]].faits()
    if not faits:
        return None
    resultat = verification.verifier(reponse, faits)
    verification.panneau(resultat, faits)
    DERNIERE_VERIFICATION.clear()
    DERNIERE_VERIFICATION.update(outil=noms[-1], reponse=reponse, faits=faits, quand=time.time(), **resultat)
    EMETTEUR.emettre({"type": "verification_chiffres", "t": time.time(), "outil": noms[-1], "total": resultat["total"],
                      "trouves": resultat["trouves"], "ecarts": [e["cite"] for e in resultat["ecarts"]],
                      "alertes": [a["cite"] for a in resultat["alertes"]]})

    def juger():
        # après la réponse (la voix n'attend pas) : chaque phrase confrontée aux faits par le cerveau
        try:
            resultat["phrases_jugees"] = verification.juger_phrases(reponse, faits)
        except Exception as e:
            resultat["phrases_jugees"] = []
            EMETTEUR.emettre({"type": "erreur", "t": time.time(), "message": f"jugement des phrases : {type(e).__name__}"})
        verification.panneau(resultat, faits)
        if DERNIERE_VERIFICATION.get("reponse") == reponse:
            DERNIERE_VERIFICATION["phrases_jugees"] = resultat["phrases_jugees"]
        inexactes = [j["phrase"] for j in resultat["phrases_jugees"] if j["verdict"] == "inexacte"]
        EMETTEUR.emettre({"type": "verification_phrases", "t": time.time(), "phrases": len(resultat["phrases_jugees"]),
                          "inexactes": inexactes})

    if CONFIG.get("youtube", {}).get("juger_phrases", True):
        threading.Thread(target=juger, daemon=True, name="jugement-phrases").start()
    return resultat


@app.get("/verification")
def derniere_verification():
    """La dernière vérification : la réponse, le JSON de faits et chaque chiffre avec le fait qui le porte."""
    return DERNIERE_VERIFICATION or {"message": "aucune réponse à faits vérifiée pour l'instant"}


def _questionner_depuis_telegram(texte: str, langue: str | None = None) -> str:
    EMETTEUR.emettre({"type": "transcription", "t": time.time(), "texte": texte, "mode": "telegram"})
    return _dialoguer(texte, langue=langue, source="telegram")["reponse"]


@app.post("/parler")
@app.post("/api/parler")
def parler(demande: Demande):
    texte = demande.texte.strip()
    if not texte:
        return JSONResponse({"erreur": "texte vide"}, status_code=400)
    return _dialoguer(texte, source="texte")


@app.post("/dire")
@app.post("/api/dire")
def dire(phrase: Phrase):
    """Fait dire un texte tel quel (sans passer par le cerveau)."""
    voix.VOIX.taire("dire")
    prise = voix.VOIX.dire(phrase.texte, phrase.moteur)
    return {"prise": prise}


@app.post("/taire")
@app.post("/api/taire")
def taire():
    CERVEAU.interrompre()
    voix.VOIX.taire("demande")
    return {"ok": True}


@app.post("/oreilles/pause")
def oreilles_pause():
    """Le HUD enregistre avec le micro du navigateur : le micro du PC se tait pendant ce temps."""
    if OREILLES:
        OREILLES.suspendre()
    return {"ok": True}


@app.post("/oreilles/reprise")
def oreilles_reprise():
    if OREILLES:
        OREILLES.reprendre()
    return {"ok": True}


@app.post("/ecouter")
@app.post("/api/ecouter")
async def ecouter(audio: UploadFile):
    """Audio poussé par le HUD (appui sur Espace) : transcription puis dialogue."""
    fin_parole = time.time()
    donnees = await audio.read()
    suffixe = ".webm" if "webm" in (audio.content_type or "") else ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffixe, delete=False) as f:
        f.write(donnees)
        chemin = f.name
    t = time.time()
    try:
        texte, langue = await asyncio.get_running_loop().run_in_executor(None, oreilles.transcrire_detail, chemin)
    finally:
        Path(chemin).unlink(missing_ok=True)
    duree = round(time.time() - t, 2)
    if not texte:
        EMETTEUR.emettre({"type": "rien_entendu", "t": time.time(), "raison": "transcription vide"})
        return {"transcription": "", "reponse": "", "chrono": {"oreille": duree}}
    if _doublon_vocal(texte):
        return {"transcription": texte, "reponse": "", "chrono": {"oreille": duree}, "doublon": True}
    EMETTEUR.emettre({"type": "transcription", "t": time.time(), "texte": texte, "duree": duree, "langue": langue})
    resultat = await asyncio.get_running_loop().run_in_executor(
        None, lambda: _dialoguer(texte, langue=langue, fin_parole=fin_parole, source="voix", mode="navigateur"))
    resultat["transcription"] = texte
    resultat["chrono"]["oreille"] = duree
    return resultat


# --- mémoire longue ----------------------------------------------------------------------------------------------
@app.get("/souvenirs")
def souvenirs_lire():
    return {"souvenirs": memoire.lister(), "constellation": memoire.constellation()}


@app.post("/souvenirs/constellation")
def souvenirs_constellation():
    """Ouvre le panneau constellation dans le HUD."""
    EMETTEUR.emettre({"type": "panneau", "t": time.time(), "genre": "constellation", "titre": "Ce que je sais de vous",
                      **memoire.constellation()})
    return {"ok": True}


@app.post("/souvenirs/oublier/{identifiant}")
def souvenirs_oublier(identifiant: str):
    avant = memoire.lister()
    restants = [s for s in avant if s["id"] != identifiant]
    if len(restants) == len(avant):
        return JSONResponse({"erreur": "souvenir inconnu"}, status_code=404)
    with memoire._verrou:
        memoire._ecrire_fichier(restants)
    EMETTEUR.emettre({"type": "souvenirs_oublies", "t": time.time(), "ids": [identifiant]})
    return {"ok": True}


# --- réglages depuis l'application : clés, voix, personnalité, conversation, sentinelle, Telegram ---------------
@app.get("/reglages")
def reglages_lire():
    return reglages.lire()


@app.post("/reglages")
def reglages_ecrire(donnees: dict):
    avant = personnalites.actuelle()
    etat_reglages = reglages.ecrire(donnees)
    if personnalites.actuelle() != avant:
        threading.Thread(target=CERVEAU.rechauffer, daemon=True).start()
    if OREILLES and CONFIG["oreilles"].get("interruption", {}).get("actif", True):
        OREILLES.interruption_coupee = False           # réactivée à la main : on lui redonne sa chance
    EMETTEUR.emettre({"type": "reglages", "t": time.time(), "voix": etat_reglages["voix"]["moteur"],
                      "telegram": etat_reglages["telegram"]["configure"], "personnalite": personnalites.actuelle()})
    return etat_reglages


@app.post("/reglages/tester/{quoi}")
def reglages_tester(quoi: str):
    return reglages.tester(quoi)


@app.get("/reglages/youtube")
def reglages_youtube():
    from .youtube import acces, oauth
    return {"quota": acces.quota(), "oauth": oauth.etat(), "source": "api" if acces.cle() else "yt-dlp"}


@app.post("/reglages/youtube/oauth_client")
async def reglages_youtube_client(fichier: UploadFile):
    from .youtube import oauth
    return oauth.importer_client(await fichier.read())


@app.post("/reglages/youtube/connecter")
def reglages_youtube_connecter():
    from .youtube import oauth
    return oauth.connecter()


@app.post("/reglages/youtube/deconnecter")
def reglages_youtube_deconnecter():
    from .youtube import oauth
    oauth.oublier()
    return {"ok": True, "message": "Compte YouTube déconnecté : statistiques publiques seulement."}


class JetonTelegram(BaseModel):
    jeton: str = ""


@app.post("/reglages/telegram/verifier_jeton")
def reglages_telegram_jeton(demande: JetonTelegram):
    """Assistant : le jeton tapé (ou celui déjà enregistré) est vérifié auprès de Telegram, jamais renvoyé."""
    from .config import SECRETS
    jeton = demande.jeton.strip() or SECRETS.get("TELEGRAM_TOKEN", "")
    if not jeton:
        return {"ok": False, "message": "Collez d'abord le jeton donné par @BotFather."}
    return telegram_entrant.verifier_jeton(jeton)


@app.post("/reglages/telegram/trouver_identifiant")
def reglages_telegram_identifiant(demande: JetonTelegram):
    from .config import SECRETS
    jeton = demande.jeton.strip() or SECRETS.get("TELEGRAM_TOKEN", "")
    if not jeton:
        return {"ok": False, "message": "Collez d'abord le jeton donné par @BotFather."}
    return telegram_entrant.trouver_identifiant(jeton)


@app.get("/reglages/voix_elevenlabs")
def reglages_voix():
    try:
        return {"voix": reglages.voix_elevenlabs()}
    except Exception as e:
        return {"voix": [], "erreur": type(e).__name__}


@app.post("/oublier")
@app.post("/api/oublier")
def oublier():
    if CERVEAU.tours_depuis_souvenirs:
        threading.Thread(target=CERVEAU.fin_de_session, args=(list(CERVEAU.historique),), daemon=True).start()
    CERVEAU.oublier()
    return {"ok": True}


def lancer():
    import webbrowser
    import uvicorn
    import socket
    import urllib.request
    hote, port = CONFIG["serveur"]["hote"], CONFIG["serveur"]["port"]
    with socket.socket() as s:
        occupe = s.connect_ex((hote, port)) == 0
    if occupe:
        # Jarvis lancé deux fois (double-clic sur le raccourci alors qu'il tourne) : au lieu d'une erreur de port en
        # anglais, on ouvre l'interface de celui qui tourne déjà. Un autre programme sur le port : on le dit.
        try:
            with urllib.request.urlopen(f"http://{hote}:{port}/etat", timeout=3) as r:
                deja = "modele" in json.loads(r.read())
        except Exception:
            deja = False
        if deja:
            print("[Jarvis] Jarvis tourne déjà : j'ouvre son interface.", flush=True)
            webbrowser.open(f"http://{hote}:{port}/?plein=1")
            return
        raise SystemExit(f"[Jarvis] Le port {port} est pris par un autre programme. Fermez-le, ou changez "
                         f"« serveur.port » dans config.json, puis relancez Jarvis.")
    if CONFIG["serveur"].get("ouvrir_navigateur", True):
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{hote}:{port}/?plein=1")).start()
    uvicorn.run(app, host=hote, port=port, log_level="warning")
