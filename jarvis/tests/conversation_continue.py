"""Test du pouvoir 03, conversation continue : python -m jarvis.tests.conversation_continue
Les vraies oreilles (VAD, Whisper), un micro de test au rythme réel :
1. fenêtre ouverte (comme après une réponse) : une phrase SANS « Jarvis » est acceptée, la fenêtre se ferme sur la parole ;
2. fenêtre expirée : la même phrase est ignorée ;
3. sans fenêtre, une phrase qui commence par « Jarvis » passe toujours ;
4. réglage : durée lue dans la config, fenêtre désactivable."""
import sys
import time

from ._commun import Collecteur, SourceScenario, Verifs, attendre, faux_haut_parleur, phrase_wav

faux_haut_parleur()

from .. import oreilles  # noqa: E402
from ..config import CONFIG  # noqa: E402


def main() -> int:
    v = Verifs("Pouvoir 03 · conversation continue")
    sans_jarvis, _ = phrase_wav("continue_sans_jarvis", [("Et demain, il fera beau à Paris ?", "ff_siwis", "fr-fr")])
    avec_jarvis, _ = phrase_wav("continue_avec_jarvis", [("Jarvis,", "am_michael", "en-us"), ("quelle est la capitale du Japon ?", "ff_siwis", "fr-fr")])
    oreilles.prechauffer_whisper()

    micro, evts, recus = SourceScenario(), Collecteur(), []
    o = oreilles.Oreilles(sur_evenement=evts, sur_texte=lambda t, i: recus.append((t, i)), source=micro.generateur,
                          jarvis_parle=lambda: False, phrases_dites=lambda: [])
    o.start()
    v.ok(attendre(lambda: o.etat == "veille", 60), "oreilles prêtes")
    CONFIG["oreilles"]["conversation_continue"] = {"actif": True, "secondes": 8}

    # 1. dans la fenêtre
    micro.silence(0.5)
    o.ouvrir_fenetre()
    ouverte = evts.de_type("fenetre_ouverte")
    v.ok(ouverte and ouverte[-1]["duree"] == 8, "fenêtre ouverte pour 8 s (réglage)", ouverte[-1]["duree"] if ouverte else None)
    micro.silence(1.0)
    micro.jouer(sans_jarvis)
    v.ok(attendre(lambda: recus, 20), "dans la fenêtre : la phrase sans « Jarvis » est transmise au cerveau")
    if recus:
        texte, infos = recus[-1]
        v.ok(infos["mode"] == "fenetre", "mode de la phrase : fenêtre de conversation", infos["mode"])
        v.ok("demain" in texte.lower(), "transcription correcte", texte)
        v.ok(infos["fin_parole"] > 0, "l'instant de fin de parole accompagne le texte")
    fermees = evts.de_type("fenetre_fermee")
    v.ok(fermees and fermees[0]["raison"] == "parole", "la fenêtre se ferme dès que la personne parle", fermees[0]["raison"] if fermees else None)

    # 2. fenêtre expirée
    recus.clear()
    o.ouvrir_fenetre(1.5)
    micro.silence(2.5)
    micro.attendre_vide()
    v.ok(attendre(lambda: any(e["raison"] == "delai" for e in evts.de_type("fenetre_fermee")), 5), "la fenêtre se ferme seule après son délai")
    micro.jouer(sans_jarvis)
    micro.silence(1.5)
    micro.attendre_vide()
    time.sleep(3)
    v.ok(not recus, "après la fenêtre : la même phrase sans « Jarvis » est ignorée", recus)
    v.ok(evts.de_type("phrase_ignoree"), "et notée comme phrase ignorée")

    # 3. « Jarvis, … » passe toujours
    micro.jouer(avec_jarvis)
    v.ok(attendre(lambda: recus, 20), "hors fenêtre : « Jarvis, quelle est la capitale du Japon » passe", recus[-1][0] if recus else None)

    # 4. désactivée
    CONFIG["oreilles"]["conversation_continue"] = {"actif": False, "secondes": 8}
    avant = len(evts.de_type("fenetre_ouverte"))
    o.ouvrir_fenetre()
    v.ok(len(evts.de_type("fenetre_ouverte")) == avant, "réglage désactivé : aucune fenêtre ne s'ouvre")
    CONFIG["oreilles"]["conversation_continue"] = {"actif": True, "secondes": 8}
    o.arreter()
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
