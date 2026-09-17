"""Test du pouvoir 04, interruption : python -m jarvis.tests.interruption
1. oreilles : pendant que Jarvis parle, une vraie phrase coupe la parole avant même sa fin (événement interruption),
   puis est transmise sans « Jarvis » ;
2. écho : si ce que le micro entend reprend les mots que Jarvis vient de dire (haut-parleurs), c'est ignoré ; au
   deuxième écho d'affilée, l'interruption se coupe pour la session ;
3. voix et cerveau : taire() coupe la lecture en moins de 200 ms, interrompre() arrête une génération en cours."""
import sys
import threading
import time

from ._commun import Collecteur, SourceScenario, Verifs, attendre, faux_haut_parleur, phrase_wav

faux_haut_parleur()

from .. import oreilles, voix  # noqa: E402
from ..cerveau import CERVEAU  # noqa: E402
from ..config import CONFIG  # noqa: E402

DIT_PAR_JARVIS = "Il est vingt heures trente-quatre, et la carte graphique est à cinquante-deux degrés, tout va bien."


def main() -> int:
    v = Verifs("Pouvoir 04 · interruption")
    coupure, _ = phrase_wav("interruption_personne", [("Attends, arrête, je voulais plutôt savoir la météo de demain.", "ff_siwis", "fr-fr")])
    echo, _ = phrase_wav("interruption_echo", [(DIT_PAR_JARVIS, "ff_siwis", "fr-fr")])
    oreilles.prechauffer_whisper()
    CONFIG["oreilles"]["interruption"] = {"actif": True, "seuil_vad": 0.85, "seuil_niveau": 0.012, "duree_min_s": 0.35}

    parle = {"oui": True}
    micro, evts, recus = SourceScenario(), Collecteur(), []
    o = oreilles.Oreilles(sur_evenement=evts, sur_texte=lambda t, i: recus.append((t, i)), source=micro.generateur,
                          jarvis_parle=lambda: parle["oui"], phrases_dites=lambda: [DIT_PAR_JARVIS])
    o.start()
    v.ok(attendre(lambda: o.etat == "veille", 60), "oreilles prêtes")

    # 1. une vraie interruption
    micro.silence(0.5)
    micro.attendre_vide()
    debut = time.time()
    micro.jouer(coupure)
    v.ok(attendre(lambda: evts.de_type("interruption"), 6), "Jarvis parle, la personne parle : interruption détectée")
    if evts.de_type("interruption"):
        delai = evts.de_type("interruption")[0]["t"] - debut - 0.4       # 0,4 s de silence en tête du fichier
        v.ok(delai < 1.0, "détectée en moins d'une seconde de parole, avant la fin de la phrase", f"{delai * 1000:.0f} ms")
    parle["oui"] = False                                               # le serveur a coupé la voix
    v.ok(attendre(lambda: recus, 20), "la nouvelle phrase est transmise au cerveau sans « Jarvis »")
    if recus:
        v.ok(recus[-1][1]["mode"] == "interruption", "mode : interruption", recus[-1][1]["mode"])
        v.ok("météo" in recus[-1][0].lower() or "meteo" in recus[-1][0].lower(), "transcription correcte", recus[-1][0])

    # 2. l'écho des haut-parleurs
    recus.clear()
    for tour in (1, 2):
        parle["oui"] = True
        micro.silence(0.6)
        micro.jouer(echo)
        micro.silence(1.2)
        v.ok(attendre(lambda: len(evts.de_type("interruption_ignoree")) >= tour, 25), f"écho n°{tour} : reconnu et ignoré")
    parle["oui"] = False
    v.ok(not recus, "l'écho n'est jamais envoyé au cerveau", recus)
    v.ok(attendre(lambda: evts.de_type("interruption_coupee"), 5) and o.interruption_coupee,
         "deux échos d'affilée : l'interruption se coupe (casque recommandé)")
    o.arreter()

    # 3. la voix se tait vite, le cerveau s'arrête
    evts_voix = Collecteur()
    voix.sur_evenement = evts_voix
    voix.charger()
    voix.VOIX.dire("Voici une phrase assez longue pour avoir le temps de m'interrompre au milieu. Et une deuxième phrase derrière.")
    v.ok(attendre(lambda: voix.VOIX.en_lecture.is_set(), 15), "Jarvis parle")
    time.sleep(0.4)
    t = time.time()
    voix.VOIX.taire("interruption")
    v.ok(attendre(lambda: not voix.VOIX.parle(), 2, 0.01), "taire() : plus rien ne joue", f"{(time.time() - t) * 1000:.0f} ms")
    v.ok((time.time() - t) < 0.25 and evts_voix.de_type("parole_interrompue"), "coupé en moins de 250 ms, événement parole_interrompue")

    CERVEAU.charger()
    question = "Explique en trois phrases complètes pourquoi le ciel est bleu."
    t = time.time()
    complete = CERVEAU.repondre(question)
    duree_complete = time.time() - t
    CERVEAU.oublier()

    jetons, fini = [], {}

    def premier_jeton(m):
        jetons.append(time.time())
        if len(jetons) == 3:
            fini["coupe"] = time.time()
            CERVEAU.interrompre()                 # la personne reprend la parole dès les premiers mots

    def longue():
        fini["reponse"] = CERVEAU.repondre(question, sur_jeton=premier_jeton)
        fini["t"] = time.time()

    fil = threading.Thread(target=longue)
    fil.start()
    fil.join(30)
    arret_ms = (fini["t"] - fini["coupe"]) * 1000 if "coupe" in fini and "t" in fini else None
    v.ok(arret_ms is not None and arret_ms < 300, "interrompre() : la génération s'arrête aussitôt",
         f"{arret_ms:.0f} ms après la coupure" if arret_ms is not None else "pas de coupure")
    v.ok(len(fini.get("reponse", "")) < len(complete) / 2, "la réponse coupée est bien plus courte que la réponse complète",
         f"{len(fini.get('reponse', ''))} contre {len(complete)} caractères ({duree_complete:.1f} s en entier)")
    CERVEAU.oublier()
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
