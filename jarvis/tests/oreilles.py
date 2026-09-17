"""Tests manuels des oreilles.

  python -m jarvis ecouter            en direct sur le micro : dire « Jarvis » trois fois puis une phrase
  python -m jarvis ecouter FICHIER    même chose en rejouant un fichier audio (test sans parler)
  python -m jarvis.tests.oreilles     aller-retour : Piper dit une phrase, Whisper la transcrit"""
import sys
import tempfile
import time
from pathlib import Path

import requests

from .. import oreilles, voix
from ..config import CONFIG

URL = f"http://{CONFIG['serveur']['hote']}:{CONFIG['serveur']['port']}"
PHRASE = "Jarvis, quelle est la température du processeur graphique ce soir ?"


def afficher_peripheriques():
    print("Micros disponibles (index à mettre dans config.json, oreilles.peripherique ; ou un morceau du nom) :")
    for p in oreilles.lister_peripheriques():
        print(f"  {'>' if p['defaut'] else ' '} {p['index']:3d}  {p['nom']}  [{p['api']}]")


def fabriquer_fixture() -> str:
    """« Hey Jarvis » (voix anglaise de Kokoro : la voix française le prononce mal) puis une question en français,
    à 16 kHz mono. Sert à tester les oreilles sans parler."""
    import wave

    import numpy as np

    from ..config import RACINE
    fixture = RACINE / "modeles" / "test_oreilles.wav"
    if fixture.exists():
        return str(fixture)
    voix.charger()

    def dire(texte, voix_, langue):
        audio = voix._local(texte, voix_, langue)
        n = int(len(audio) * oreilles.FREQ / voix.FREQ)
        return (np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio) * 32767).astype(np.int16)

    silence = lambda s: np.zeros(int(oreilles.FREQ * s), dtype=np.int16)
    audio = np.concatenate([silence(0.5), dire("Hey Jarvis", "am_michael", "en-us"), silence(0.6),
                            dire("Quelle heure est-il, s'il vous plaît ?", "ff_siwis", "fr-fr"), silence(2.0)])
    with wave.open(str(fixture), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(oreilles.FREQ)
        w.writeframes(audio.tobytes())
    print(f"Fixture écrite : {fixture} ({len(audio) / oreilles.FREQ:.1f} s)")
    return str(fixture)


def en_direct(args):
    afficher_peripheriques()
    fichier = args[0] if args else None
    if fichier == "fixture":
        fichier = fabriquer_fixture()
    source = oreilles.source_fichier(fichier) if fichier else None
    if fichier:
        print(f"\nSource : le fichier {fichier}")
    else:
        print(f"\nSource : micro {oreilles.choisir_peripherique()}")
    r = CONFIG["oreilles"]
    print(f"Mot de réveil « {r['mot']} », seuil {r['seuil']}, fin après {r['silence_s']} s de silence, "
          f"Whisper {r['modele']} sur {r['appareil']}\n")
    serveur_present = False
    try:
        requests.get(f"{URL}/etat", timeout=2)
        serveur_present = True
        print("Serveur joignable : les transcriptions seront envoyées à /parler.\n")
    except requests.RequestException:
        print("Serveur absent : les transcriptions seront seulement affichées.\n")

    debut = time.time()
    fini = {"compte": 0}

    def horodate():
        return f"[{time.time() - debut:6.1f} s]"

    def sur_evenement(e):
        t = e["type"]
        if t == "pret":
            print(f"{horodate()} en veille, dites « Jarvis »…")
        elif t == "mot_detecte":
            print(f"{horodate()} MOT DE RÉVEIL détecté (score {e['score']})")
        elif t == "ecoute":
            print(f"{horodate()}   parole détectée, j'écoute…")
        elif t == "transcription_en_cours":
            print(f"{horodate()}   silence, transcription de {e['duree_audio']} s d'audio…")
        elif t == "transcription":
            print(f"{horodate()}   TRANSCRIPTION ({e['duree']} s) : « {e['texte']} »")
            fini["compte"] += 1
        elif t == "rien_entendu":
            print(f"{horodate()}   rien entendu ({e['raison']})")
            fini["compte"] += 1
        elif t == "phrase_ignoree":
            print(f"{horodate()}   entendu sans « Jarvis » devant, ignoré : « {e['texte']} »")
        elif t == "erreur":
            print(f"{horodate()} ERREUR : {e['message']}")

    def sur_texte(texte):
        if not serveur_present:
            return
        t = time.time()
        r = requests.post(f"{URL}/parler", json={"texte": texte}, timeout=300).json()
        print(f"{horodate()}   JARVIS ({time.time() - t:.1f} s) : {r['reponse']}")

    o = oreilles.Oreilles(sur_evenement=sur_evenement, sur_texte=sur_texte, source=source)
    o.start()
    try:
        while o.is_alive():          # avec un fichier, le fil s'arrête tout seul à la fin de l'audio
            time.sleep(0.2)
        if fichier:
            time.sleep(0.5)
        if o.erreur:
            sys.exit(1)
    except KeyboardInterrupt:
        o.arreter()
        print("\nArrêt.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fichier = sys.argv[1]
        attendu = None
    else:
        import wave
        import numpy as np
        audio, _ = voix.synthetiser(PHRASE)
        fichier = str(Path(tempfile.gettempdir()) / "jarvis_oreille.wav")
        with wave.open(fichier, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(voix.FREQ)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        attendu = PHRASE
    print(f"Chargement de Whisper : {oreilles.charger_whisper():.1f} s")
    for essai in (1, 2):
        t = time.time()
        texte = oreilles.transcrire(fichier)
        print(f"Essai {essai} : « {texte} »  ({time.time() - t:.2f} s)")
    if attendu:
        print(f"Attendu : « {attendu} »")
    for h in ("Sous-titres réalisés par la communauté d'Amara.org", "Merci d'avoir regardé !", "...", "Il pleut ce soir."):
        print(f"hallucination ? {oreilles.est_hallucination(h)!s:5}  « {h} »")
