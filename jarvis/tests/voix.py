"""Test manuel de la voix : python -m jarvis dire "Bonjour monsieur, tout est en ordre."
Les deux moteurs l'un après l'autre (local = Kokoro, puis ElevenLabs), lus dans les haut-parleurs,
avec la durée de synthèse, le cache et le repli éventuel. Un second passage montre le cache."""
import sys
import time

from .. import voix
from ..config import CONFIG

PHRASE = "Bonjour monsieur, tout est en ordre."


def dire(args):
    texte = " ".join(a for a in args if not a.startswith("--")) or PHRASE
    moteurs = ["local", "elevenlabs"]
    if "--local" in args:
        moteurs = ["local"]
    if "--elevenlabs" in args:
        moteurs = ["elevenlabs"]
    evenements = []
    voix.sur_evenement = lambda e: evenements.append(e) if e["type"] != "niveau" else None
    print(f"Moteur configuré : {CONFIG['voix']['moteur']} | ElevenLabs configuré : {voix.elevenlabs_configure()}")
    print(f"Kokoro chargé en {voix.charger():.2f} s\n")
    for moteur in moteurs:
        for passage in (1, 2):
            evenements.clear()
            t = time.time()
            audio, infos = voix.synthetiser(texte, moteur)
            print(f"[{moteur}] passage {passage} : synthèse {infos['duree']} s, cache {infos['cache']}, "
                  f"moteur utilisé {infos['moteur']}"
                  + (f", REPLI : {infos['repli']}" if infos["repli"] else "")
                  + f", {len(audio) / voix.FREQ:.1f} s d'audio")
            niveaux = []
            voix.sur_evenement = lambda e, n=niveaux: n.append(e["valeur"]) if e["type"] == "niveau" else None
            voix.VOIX.dire(texte, moteur)
            voix.VOIX.attendre()
            print(f"          lecture terminée en {time.time() - t:.2f} s, {len(niveaux)} mesures de niveau "
                  f"(max {max(niveaux) if niveaux else 0:.2f})")
        print()
    # interruption : on lance une phrase longue et on la coupe après 0,8 s
    voix.sur_evenement = lambda e: print(f"          événement : {e['type']}") if e["type"] in ("parole_interrompue",) else None
    voix.VOIX.dire("Je vais maintenant réciter une très longue phrase, monsieur, pour prouver que je sais me taire "
                   "quand on m'interrompt, ce qui est une qualité rare chez un majordome.", "local")
    time.sleep(2.5)
    voix.VOIX.taire("test")
    voix.VOIX.attendre()
    print("Interruption : OK si la phrase s'est arrêtée net.")
