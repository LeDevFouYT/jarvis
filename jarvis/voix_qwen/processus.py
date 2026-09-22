"""Le processus de la voix du majordome (Qwen3-TTS, Alibaba, Apache 2.0), lancé et piloté par `jarvis/majordome.py`.

Il tourne avec un Python à part, celui où `qwen-tts` est installé (torch cu128, transformers 4.57.3) : Jarvis n'a pas
torch. Il garde le modèle chargé et répond phrase par phrase.

    <python qwen> processus.py <modèle> <reference.wav> <reference.txt>

Protocole (lignes UTF-8) : une demande JSON par ligne sur l'entrée standard, {"texte", "langue"} ou {"fin": true} ;
une réponse par ligne sur la sortie standard, préfixée « @@ » (les bibliothèques y écrivent aussi) :
{"pret": true, "sr", "chargement_s", "vram_mo"} une fois, puis {"audio": base64 float32, "sr", "calcul_s"} ou {"erreur"}.
"""
import base64
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")                 # rien ne part sur internet : les poids sont déjà là
LANGUES = {"fr": "French", "en": "English", "es": "Spanish", "de": "German", "it": "Italian"}


def main() -> int:
    modele_nom, ref_wav, ref_txt = sys.argv[1:4]
    canal = sys.stdout
    sys.stdout = sys.stderr                                   # les impressions des bibliothèques ne salissent pas le canal
    sys.stdin.reconfigure(encoding="utf-8")

    def envoyer(d):
        canal.write("@@" + json.dumps(d) + "\n")
        canal.flush()

    t = time.time()
    try:
        import numpy as np
        import torch
        from qwen_tts import Qwen3TTSModel
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import graphe
        if not os.path.isdir(modele_nom):                    # un nom Hugging Face : son dossier dans le cache local
            from huggingface_hub import snapshot_download
            modele_nom = snapshot_download(modele_nom, local_files_only=True)
        modele = graphe.charger_leger(Qwen3TTSModel, modele_nom)
        graphe.accelerer(modele)
        with open(ref_txt, encoding="utf-8") as f:
            prompt = modele.create_voice_clone_prompt(ref_audio=ref_wav, ref_text=f.read().strip())
        graphe.alleger_memoire(modele)                        # la référence est lue : table du texte et encodeurs hors carte
        modele.generate_voice_clone(text="Bien.", language="French", voice_clone_prompt=prompt)   # grave le graphe
        wavs, sr = modele.generate_voice_clone(text="Bien, monsieur.", language="French", voice_clone_prompt=prompt)
        torch.cuda.empty_cache()                              # rend à la carte la mémoire de l'échauffement
    except Exception as e:                                    # noqa: BLE001
        envoyer({"erreur": f"chargement : {type(e).__name__} : {e}"})
        return 1
    envoyer({"pret": True, "sr": int(sr), "chargement_s": round(time.time() - t, 1),
             "vram_mo": round(torch.cuda.memory_reserved() / 2 ** 20),
             "vram_alloue_mo": round(torch.cuda.memory_allocated() / 2 ** 20)})

    for ligne in sys.stdin:
        try:
            d = json.loads(ligne)
        except ValueError:
            continue
        if d.get("fin"):
            break
        t = time.time()
        torch.cuda.reset_peak_memory_stats()
        try:
            wavs, sr = modele.generate_voice_clone(text=d["texte"], language=LANGUES.get(d.get("langue", "fr"), "French"),
                                                   voice_clone_prompt=prompt)
            onde = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
            envoyer({"audio": base64.b64encode(onde.tobytes()).decode("ascii"), "sr": int(sr),
                     "calcul_s": round(time.time() - t, 3), "pic_mo": round(torch.cuda.max_memory_reserved() / 2 ** 20)})
        except Exception as e:                                # noqa: BLE001
            envoyer({"erreur": f"{type(e).__name__} : {e}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
