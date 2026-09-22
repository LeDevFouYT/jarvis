"""Crée la voix du majordome par DESCRIPTION (Qwen3-TTS VoiceDesign), une seule fois.

    <python qwen> creer_voix.py [dossier]        (par défaut : le dossier majordome/ à côté de ce fichier)

Aucune imitation : ni enregistrement de quelqu'un, ni nom de personne réelle, seulement la description ci-dessous.
Le modèle VoiceDesign invente une voix qui y correspond ; plusieurs essais sont faits, réécoutés par Whisper (mot à mot)
et mesurés (hauteur, niveau). Le plus juste devient la référence que le moteur rejoue ensuite en clonage (modèle Base,
plus léger, voix stable d'une phrase à l'autre) : reference.wav, reference.txt, et reference.json (description,
modèle, graine, mesures de chaque essai). Tous les essais restent dans candidats/ pour choisir à l'oreille.
"""
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

MODELE = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
DESCRIPTION = ("A distinguished English butler in his fifties, speaking French fluently with a light, refined British "
               "accent. Deep, warm baritone voice, calm and measured pace, impeccable diction, courteous and composed, "
               "with a hint of dry wit. Clean studio recording, close microphone, no background noise, no music.")
TEXTE = ("Bonsoir, monsieur. Votre thé est servi, les rideaux sont tirés, et j'ai pris la liberté de préparer "
         "vos dossiers pour demain matin.")
ESSAIS = 6


def main() -> int:
    dossier = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ICI, "majordome")
    os.makedirs(os.path.join(dossier, "candidats"), exist_ok=True)
    import reecoute
    reecoute.dll_cuda()
    import numpy as np
    import soundfile
    import torch
    from faster_whisper import WhisperModel
    from qwen_tts import Qwen3TTSModel

    modele = Qwen3TTSModel.from_pretrained(MODELE, device_map="cuda", dtype=torch.bfloat16)
    oreille = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
    essais = []
    for i in range(ESSAIS):
        graine = 1000 + i
        torch.manual_seed(graine)
        t = time.time()
        wavs, sr = modele.generate_voice_design(text=TEXTE, instruct=DESCRIPTION, language="French")
        onde = reecoute.rogner(np.asarray(wavs[0], dtype=np.float32).reshape(-1), sr)
        chemin = os.path.join(dossier, "candidats", f"essai_{i + 1}.wav")
        soundfile.write(chemin, onde, sr)
        segs, _ = oreille.transcribe(chemin, language="fr", beam_size=5, vad_filter=False)
        entendu = " ".join(s.text for s in segs).strip()
        e = reecoute.ecarts(TEXTE, entendu)
        mesure = {"essai": i + 1, "graine": graine, "fichier": os.path.relpath(chemin, dossier), "entendu": entendu,
                  "ecarts": e, "score": reecoute.score(e), "hauteur_hz": round(reecoute.hauteur(onde, sr)),
                  "duree_s": round(len(onde) / sr, 2), "calcul_s": round(time.time() - t, 1)}
        essais.append(mesure)
        print(json.dumps(mesure, ensure_ascii=False), flush=True)
    # le plus juste d'abord ; à égalité, la voix la plus grave (un baryton), sans descendre dans le grognement
    justes = sorted(essais, key=lambda m: (m["score"], abs(m["hauteur_hz"] - 105) if m["hauteur_hz"] else 999))
    choisi = justes[0]
    onde, sr = soundfile.read(os.path.join(dossier, choisi["fichier"]), dtype="float32")
    onde = reecoute.egaliser(onde)
    soundfile.write(os.path.join(dossier, "reference.wav"), onde, sr)
    with open(os.path.join(dossier, "reference.txt"), "w", encoding="utf-8") as f:
        f.write(TEXTE + "\n")
    with open(os.path.join(dossier, "reference.json"), "w", encoding="utf-8") as f:
        json.dump({"description": DESCRIPTION, "texte": TEXTE, "modele": MODELE, "licence": "Apache-2.0",
                   "imitation": "aucune : voix inventée à partir de la description seule", "choisi": choisi["essai"],
                   "cree_le": time.strftime("%Y-%m-%d %H:%M"), "essais": essais}, f, ensure_ascii=False, indent=1)
    print(f"référence : essai {choisi['essai']} ({choisi['hauteur_hz']} Hz, {choisi['score']} écart(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
