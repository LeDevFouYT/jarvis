"""Crée une voix par DESCRIPTION (Qwen3-TTS VoiceDesign) : la voix du majordome, ou toute voix décrite par la personne
(vidéo 5, « change ta voix : une voix grave et posée », lancé par jarvis/voix_creees.py).

    <python qwen> creer_voix.py                                   la voix du majordome (dossier majordome/, 6 essais)
    <python qwen> creer_voix.py --dossier D --description "…" [--essais 3] [--texte "…"] [--hauteur 105]

Aucune imitation : ni enregistrement de quelqu'un, ni nom de personne réelle, seulement une description (Jarvis
refuse en amont « la voix de <quelqu'un> »). Le modèle VoiceDesign invente une voix qui y correspond ; plusieurs essais
sont faits, réécoutés par Whisper (mot à mot) et mesurés (hauteur, niveau). Le plus juste devient la référence que le
moteur rejoue ensuite en clonage (modèle Base, plus léger, voix stable d'une phrase à l'autre) : reference.wav,
reference.txt, et reference.json (description, modèle, graine, mesures de chaque essai). Tous les essais restent dans
candidats/ pour choisir à l'oreille.

Progression : une ligne « @@{json} » par étape sur la sortie standard (chargement, essai, choix), pour Jarvis.
"""
import argparse
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")                 # rien ne part sur internet : les poids sont déjà là
ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

MODELE = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
DESCRIPTION = ("A distinguished English butler in his fifties, speaking French fluently with a light, refined British "
               "accent. Deep, warm baritone voice, calm and measured pace, impeccable diction, courteous and composed, "
               "with a hint of dry wit. Clean studio recording, close microphone, no background noise, no music.")
TEXTE = ("Bonsoir, monsieur. Votre thé est servi, les rideaux sont tirés, et j'ai pris la liberté de préparer "
         "vos dossiers pour demain matin.")
ESSAIS = 6


def signaler(**d):
    # ASCII seulement : vu en démo le 29/10, lancé par Jarvis (sans PYTHONIOENCODING), la sortie partait en cp1252 et
    # Jarvis, qui lit en UTF-8, plantait sur le premier « é » de ce que Whisper avait entendu. Au test, l'écran des
    # tests forçait l'UTF-8 : le bug ne se voyait que dans le vrai Jarvis.
    print("@@" + json.dumps(d), flush=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("dossier_pos", nargs="?", default=None)     # ancien usage : creer_voix.py [dossier]
    p.add_argument("--dossier")
    p.add_argument("--description", default=DESCRIPTION)
    p.add_argument("--texte", default=TEXTE)
    p.add_argument("--essais", type=int, default=None)
    p.add_argument("--hauteur", type=float, default=None, help="hauteur visée en Hz pour départager (105 : baryton)")
    a = p.parse_args()
    majordome = a.description == DESCRIPTION
    dossier = a.dossier or a.dossier_pos or os.path.join(ICI, "majordome")
    essais_n = a.essais or ESSAIS            # six, comme le majordome : avec trois, la voix gardée variait davantage (29/10)
    cible = a.hauteur if a.hauteur is not None else (105 if majordome else None)
    os.makedirs(os.path.join(dossier, "candidats"), exist_ok=True)

    t_total = time.time()
    import reecoute
    reecoute.dll_cuda()
    import numpy as np
    import soundfile
    import torch
    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download
    from qwen_tts import Qwen3TTSModel

    signaler(etape="chargement")
    t = time.time()
    modele = Qwen3TTSModel.from_pretrained(snapshot_download(MODELE, local_files_only=True), device_map="cuda",
                                           dtype=torch.bfloat16)
    oreille = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
    chargement_s = round(time.time() - t, 1)
    signaler(etape="charge", chargement_s=chargement_s)
    essais = []
    for i in range(essais_n):
        graine = 1000 + i
        torch.manual_seed(graine)
        t = time.time()
        wavs, sr = modele.generate_voice_design(text=a.texte, instruct=a.description, language="French")
        onde = reecoute.rogner(np.asarray(wavs[0], dtype=np.float32).reshape(-1), sr)
        chemin = os.path.join(dossier, "candidats", f"essai_{i + 1}.wav")
        soundfile.write(chemin, onde, sr)
        segs, _ = oreille.transcribe(chemin, language="fr", beam_size=5, vad_filter=False)
        entendu = " ".join(s.text for s in segs).strip()
        e = reecoute.ecarts(a.texte, entendu)
        mesure = {"essai": i + 1, "graine": graine, "fichier": os.path.relpath(chemin, dossier), "entendu": entendu,
                  "ecarts": e, "score": reecoute.score(e), "hauteur_hz": round(reecoute.hauteur(onde, sr)),
                  "duree_s": round(len(onde) / sr, 2), "calcul_s": round(time.time() - t, 1)}
        essais.append(mesure)
        signaler(etape="essai", sur=essais_n, **mesure)
    # le plus juste d'abord ; à égalité, la hauteur visée (le baryton du majordome), sinon la hauteur médiane des
    # essais justes : ni la plus aiguë ni la plus grave, la plus « typique » de la description
    meilleur = min(m["score"] for m in essais)
    justes = [m for m in essais if m["score"] == meilleur]
    if cible is None:
        hauteurs = sorted(m["hauteur_hz"] for m in justes if m["hauteur_hz"])
        cible = hauteurs[len(hauteurs) // 2] if hauteurs else 0
    choisi = min(justes, key=lambda m: abs(m["hauteur_hz"] - cible) if m["hauteur_hz"] else 999)
    onde, sr = soundfile.read(os.path.join(dossier, choisi["fichier"]), dtype="float32")
    onde = reecoute.egaliser(onde)
    soundfile.write(os.path.join(dossier, "reference.wav"), onde, sr)
    with open(os.path.join(dossier, "reference.txt"), "w", encoding="utf-8") as f:
        f.write(a.texte + "\n")
    meta_chemin = os.path.join(dossier, "reference.json")
    meta = {}
    if os.path.exists(meta_chemin):                          # Jarvis a pu y écrire le nom et la description en français
        with open(meta_chemin, encoding="utf-8") as f:
            meta = json.load(f)
    meta.update({"description": a.description, "texte": a.texte, "modele": MODELE, "licence": "Apache-2.0",
                 "imitation": "aucune : voix inventée à partir de la description seule", "choisi": choisi["essai"],
                 "cree_le": time.strftime("%Y-%m-%d %H:%M"), "chargement_s": chargement_s,
                 "creation_s": round(time.time() - t_total, 1), "essais": essais})
    with open(meta_chemin, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    signaler(etape="fini", choisi=choisi["essai"], hauteur_hz=choisi["hauteur_hz"], score=choisi["score"],
             creation_s=meta["creation_s"], chargement_s=chargement_s)
    print(f"référence : essai {choisi['essai']} ({choisi['hauteur_hz']} Hz, {choisi['score']} écart(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
