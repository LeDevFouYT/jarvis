"""Test du pouvoir 13, le téléphone : python -m jarvis.tests.telegram_entrant
Sur le faux Telegram local (tests/faux_telegram.py, même API) ; le jeton et l'identifiant de chat sont posés en
mémoire seulement, jamais écrits. On vérifie : /aide, /etat (texte + vocal), /capture, /dire, une question libre,
un VRAI message vocal (voix Kokoro encodée en OGG Opus, transcrite par Whisper), la réponse vocale décodable,
une action sur le PC bloquée jusqu'au bouton (non, puis oui, puis sans réponse), une confirmation de l'outil lui-même
par bouton, le refus d'un inconnu signalé, un message jamais exécuté deux fois, et l'assistant de clé."""
import json
import sys
import tempfile
import time
import types
from pathlib import Path

from ._commun import Collecteur, Verifs, attendre, faux_haut_parleur

faux_haut_parleur()

from .. import confirmations, outils  # noqa: E402
from .. import telegram_entrant as T  # noqa: E402
from ..config import CONFIG, SECRETS  # noqa: E402
from .faux_telegram import INCONNU, JETON, PROPRIETAIRE, FauxTelegram  # noqa: E402


def main() -> int:
    v = Verifs("Pouvoir 13 · le téléphone (Telegram entrant)")
    faux = FauxTelegram()
    anciens = {k: SECRETS.get(k) for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")}
    ancienne_config = dict(CONFIG.get("telegram", {}))
    ancien_outil = outils.OUTILS.get("ouvrir_application")
    SECRETS.update(TELEGRAM_TOKEN=JETON, TELEGRAM_CHAT_ID=PROPRIETAIRE)
    CONFIG["telegram"].update(api=faux.url, commandes=True, attente_s=1, reponse_vocale=True)
    T.ETAT = Path(tempfile.mkdtemp()) / "telegram.json"
    capture = Path(tempfile.mkdtemp()) / "capture.png"
    capture.write_bytes(b"\x89PNG faux")
    dit, questions, ouverts = [], [], []

    # un faux « ouvrir_application » : on vérifie qu'il n'est appelé qu'après le bouton « Oui »
    outils.OUTILS["ouvrir_application"] = types.SimpleNamespace(
        NOM="ouvrir_application", PARAMETRES={"nom": {}}, executer=lambda nom: ouverts.append(nom) or f"{nom} est ouvert.")

    def questionner(texte, langue=None):
        questions.append((texte, langue))
        if "calculatrice" in texte.lower():
            return outils.executer("ouvrir_application", {"nom": "calculatrice"})
        if "ferme le document" in texte.lower():
            return confirmations.demander("« Rapport » n'est pas enregistré. Je ferme quand même ?", action=lambda: "Rapport est fermé.")
        if "heure" in texte.lower():
            return "Il est 21 h 12."
        return "La capitale du Japon est Tokyo."

    actions = {"etat": lambda: "Carte graphique à 55 degrés, 12 Go de mémoire vidéo utilisés.", "capture": lambda: str(capture),
               "image": lambda d: f"Je dessine {d}.", "notes": lambda: "Acheter du pain.", "rappel": lambda q, t: f"Rappel {q} : {t}.",
               "dire": dit.append, "silence": lambda: None, "transcrire": T.transcrire_vocal, "vocal": T.voix_ogg}
    evts = Collecteur()
    tg = T.TelegramEntrant(questionner, evts, actions)
    confirmations.boutons_telegram = tg.confirmer_par_bouton
    try:
        tg.start()
        v.ok(attendre(lambda: faux.demandes > 0 and tg.en_ecoute, 5), "le bot écoute (appel long vers l'API)")
        faux.recevoir("/aide")
        v.ok(attendre(lambda: faux.envoyes, 5) and "/etat" in faux.envoyes[-1], "/aide : la liste des commandes revient")
        faux.recevoir("/etat")
        v.ok(attendre(lambda: len(faux.envoyes) >= 2, 5) and "55 degrés" in faux.envoyes[-1], "/etat : l'état de la machine en texte", faux.envoyes[-1])
        v.ok(attendre(lambda: faux.vocaux, 60) and faux.vocaux[-1][:4] == b"OggS", "… puis en vocal OGG", f"{len(faux.vocaux[-1]) if faux.vocaux else 0} octets")
        relu, _ = T.transcrire_vocal(faux.vocaux[-1]) if faux.vocaux else ("", "")
        v.ok("55" in relu and "degr" in relu.lower(), "le vocal de Jarvis se décode et dit bien la réponse", relu)
        faux.recevoir("/capture")
        v.ok(attendre(lambda: faux.photos, 5), "/capture : la capture revient en photo", faux.photos)
        faux.recevoir("/dire le dîner est prêt")
        v.ok(attendre(lambda: dit, 5) and dit[-1] == "le dîner est prêt", "/dire : Jarvis le dit à la maison")
        n = len(faux.envoyes)
        faux.recevoir("Quelle est la capitale du Japon ?")
        v.ok(attendre(lambda: len(faux.envoyes) > n, 20) and "Tokyo" in faux.envoyes[-1], "question libre : passée au cerveau, réponse renvoyée", faux.envoyes[-1])

        # un vrai vocal : la voix de Kokoro, en OGG Opus, comme un téléphone l'enverrait
        attendre(lambda: len(faux.vocaux) >= 2, 60)
        n_vocaux, n = len(faux.vocaux), len(faux.envoyes)
        faux.vocal(T.voix_ogg("Jarvis, quelle heure est-il ?"))
        v.ok(attendre(lambda: evts.de_type("telegram_transcrit"), 60), "vocal reçu : téléchargé et transcrit par Whisper",
             evts.de_type("telegram_transcrit")[-1]["texte"] if evts.de_type("telegram_transcrit") else "")
        v.ok(questions and "heure" in questions[-1][0].lower(), "la transcription est posée au cerveau comme une question", questions[-1] if questions else "")
        v.ok(attendre(lambda: len(faux.envoyes) > n, 20) and faux.envoyes[-1].startswith("🎙 «") and "21 h 12" in faux.envoyes[-1],
             "la réponse texte rappelle ce qui a été compris", faux.envoyes[-1] if faux.envoyes else "")
        v.ok(attendre(lambda: len(faux.vocaux) > n_vocaux, 60), "et revient aussi en vocal")

        # une action sur le PC : rien ne se fait avant le bouton
        T.DELAI_BOUTON = 6
        faux.recevoir("Ouvre la calculatrice")
        v.ok(attendre(lambda: faux.dernier_avec_boutons(), 10), "action sur le PC : Jarvis envoie la question avec les boutons Oui / Non",
             (faux.dernier_avec_boutons() or {}).get("texte"))
        time.sleep(1)
        v.ok(not ouverts, "rien n'est ouvert tant que personne n'a répondu")
        m = faux.dernier_avec_boutons()
        faux.cliquer(m["id"], m["boutons"][0][1]["callback_data"])          # ❌ Non
        v.ok(attendre(lambda: any("annulée" in e for e in faux.envoyes), 10) and not ouverts, "« Non » : l'action n'est pas faite", faux.envoyes[-1])
        v.ok(any("refusé" in t for t in faux.modifications), "le message à boutons est mis à jour (refusé)")
        attendre(lambda: not faux.dernier_avec_boutons(), 5)
        faux.recevoir("Ouvre la calculatrice")
        v.ok(attendre(lambda: faux.dernier_avec_boutons(), 10), "nouvelle demande, nouveaux boutons")
        m = faux.dernier_avec_boutons()
        faux.cliquer(m["id"], m["boutons"][0][0]["callback_data"])          # ✅ Oui
        v.ok(attendre(lambda: ouverts == ["calculatrice"], 10), "« Oui » : l'action est faite", ouverts)
        v.ok(attendre(lambda: any("calculatrice est ouvert" in e for e in faux.envoyes), 10), "et le résultat revient au téléphone")
        attendre(lambda: not faux.dernier_avec_boutons(), 5)
        faux.recevoir("Ouvre la calculatrice")
        v.ok(attendre(lambda: any("pas de confirmation" in e for e in faux.envoyes), 15) and ouverts == ["calculatrice"],
             "sans réponse : l'action expire et n'est pas faite", [e for e in faux.envoyes if "confirmation" in e][-1:])
        v.ok(any("sans réponse" in t for t in faux.modifications), "le message à boutons dit qu'il a expiré")

        # l'outil lui-même demande confirmation (document non enregistré) : un bouton, pas une question à taper
        attendre(lambda: not faux.dernier_avec_boutons(), 5)
        n = len(faux.envoyes)
        faux.recevoir("Ferme le document")
        v.ok(attendre(lambda: faux.dernier_avec_boutons() and "Rapport" in faux.dernier_avec_boutons()["texte"], 10),
             "confirmation de l'outil : envoyée avec ses boutons")
        time.sleep(1)
        v.ok(sum("Rapport" in e for e in faux.envoyes[n:]) == 1, "la question n'est pas envoyée deux fois")
        m = faux.dernier_avec_boutons()
        faux.cliquer(m["id"], m["boutons"][0][0]["callback_data"])
        v.ok(attendre(lambda: any("Rapport est fermé" in e for e in faux.envoyes), 10), "« Oui » : l'outil termine son action")

        n = len(faux.envoyes)
        faux.recevoir("/etat", chat=INCONNU)
        time.sleep(2.5)
        refus = evts.de_type("telegram_refuse")
        v.ok(len(faux.envoyes) == n and refus and refus[-1]["apercu"] == "/etat", "message d'un inconnu : aucune réponse, signalé au HUD avec son contenu")
        n_questions = len(questions)
        time.sleep(2.5)
        v.ok(len(questions) == n_questions and len(dit) == 1, "aucun message n'est exécuté deux fois")
        v.ok(json.loads(T.ETAT.read_text())["offset"] >= faux.a_livrer[-1]["update_id"] + 1, "le décalage est gardé pour le prochain démarrage")
    finally:
        tg.arreter()
        confirmations.boutons_telegram = None
        if ancien_outil is not None:
            outils.OUTILS["ouvrir_application"] = ancien_outil
        for k, val in anciens.items():
            if val is None:
                SECRETS.pop(k, None)
            else:
                SECRETS[k] = val

    # l'assistant de clé des Réglages (l'écoute est arrêtée, comme pendant une vraie configuration)
    v.ok(not T.verifier_jeton("999:FAUX")["ok"], "assistant : un mauvais jeton est refusé")
    j = T.verifier_jeton(JETON)
    v.ok(j["ok"] and j["bot"] == "jarvis_essai_bot", "assistant : le bon jeton donne le nom du bot et son lien", j.get("lien"))
    faux.a_livrer.clear()
    v.ok(not T.trouver_identifiant(JETON)["ok"], "assistant : sans message au bot, il demande d'écrire « bonjour »")
    faux.recevoir("bonjour")
    j = T.trouver_identifiant(JETON)
    v.ok(j["ok"] and j["identifiant"] == PROPRIETAIRE, "assistant : après « bonjour », l'identifiant de discussion est trouvé", j.get("message"))
    CONFIG["telegram"].clear()
    CONFIG["telegram"].update(ancienne_config)
    faux.arreter()
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
