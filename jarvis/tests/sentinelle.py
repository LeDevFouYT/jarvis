"""Test du pouvoir 12, sentinelle : python -m jarvis.tests.sentinelle
Mesures et horloge simulées : la carte chauffe, un disque se remplit, un rappel approche. Jarvis parle de lui-même,
une fois par sujet, pas avant dix minutes pour le même sujet, jamais s'il est occupé (l'annonce attend). Puis un
passage réel sur la machine, et la désactivation."""
import sys
import time

from ._commun import Collecteur, Verifs

from .. import sentinelle  # noqa: E402
from ..config import CONFIG  # noqa: E402


def main() -> int:
    v = Verifs("Pouvoir 12 · sentinelle")
    horloge = {"t": 1_000_000.0}
    mesures = {"temperature_gpu": 62, "disques": [{"nom": "C", "libre_go": 180.0, "total_go": 465.0}], "rappels": []}
    dits, occupe = [], {"oui": False}

    def parler(texte):
        if occupe["oui"]:
            return False
        dits.append(texte)
        return True

    evts = Collecteur()
    s = sentinelle.Sentinelle(parler, evts, mesures=lambda: mesures, horloge=lambda: horloge["t"])
    CONFIG["sentinelle"] = {"actif": True, "temperature_max": 85, "disque_min_go": 10, "disque_min_pourcent": 2,
                            "disque_taille_min_go": 16, "rappel_avance_min": 5, "repos_min": 10}

    v.ok(s.tour() == [], "tout va bien : Jarvis ne dit rien")
    mesures["temperature_gpu"] = 91
    v.ok(len(s.tour()) == 1 and "91 degrés" in dits[-1], "la carte chauffe : Jarvis le dit de lui-même", dits[-1] if dits else None)
    horloge["t"] += 120
    v.ok(s.tour() == [], "deux minutes après : il ne répète pas")
    horloge["t"] += 9 * 60
    v.ok(len(s.tour()) == 1, "onze minutes après la première annonce : il le redit")

    mesures["disques"][0]["libre_go"] = 6.0
    faites = s.tour()
    v.ok(len(faites) == 1 and "disque C" in faites[0], "le disque C est presque plein : annoncé (sujet différent, pas bloqué)", faites)

    mesures["rappels"] = [{"id": "r1", "quand": horloge["t"] + 4 * 60, "texte": "sortir le pain du four"}]
    occupe["oui"] = True
    v.ok(s.tour() == [], "un rappel approche mais Jarvis est occupé : l'annonce attend")
    occupe["oui"] = False
    faites = s.tour()
    v.ok(any("Dans 4 minutes" in f and "pain" in f for f in faites), "dès qu'il est libre : « Dans 4 minutes : sortir le pain du four »", faites)
    v.ok(len(evts.de_type("sentinelle")) == len(dits), "chaque annonce est aussi envoyée au HUD")

    s.ajouter_source("commentaires", lambda: [("commentaire:42", "Un nouveau commentaire sur votre dernière vidéo.")])
    v.ok(any("commentaire" in f for f in s.tour()), "une source future (commentaires) se branche sans toucher au reste")

    reel = sentinelle.Sentinelle(lambda t: True)
    m = sentinelle.mesures_reelles()
    v.ok(m["disques"] and "temperature_gpu" in m, "mesures réelles de la machine", f"{len(m['disques'])} disques, {m['temperature_gpu']} °C")
    v.info(f"alertes réelles maintenant : {reel.alertes()}")

    appels = []
    s2 = sentinelle.Sentinelle(lambda t: appels.append(t) or True, mesures=lambda: {"temperature_gpu": 99, "disques": [], "rappels": []})
    CONFIG["sentinelle"]["actif"] = False
    CONFIG["sentinelle"]["intervalle_s"] = 0.1
    s2.start()
    time.sleep(0.5)
    v.ok(not appels, "désactivée : aucune annonce")
    CONFIG["sentinelle"]["actif"] = True
    time.sleep(0.5)
    v.ok(appels, "réactivée : elle reprend")
    s2.arreter()
    CONFIG["sentinelle"].pop("intervalle_s", None)
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
