"""Test des pouvoirs 14 à 16, il voit et il crée : python -m jarvis.tests.voir_et_creer [webcam|video|miniatures]
Jarvis arrêté (ce test charge son propre Whisper et le cerveau alterne avec la vision et ComfyUI).

14 webcam : la liste des périphériques vidéo, une image (image d'essai si aucune webcam ne diffuse) décrite par le
   vrai modèle de vision avec l'alternance de mémoire vidéo ; rien n'est écrit sur le disque, sauf sur demande.
15 résumé de vidéo : une vraie vidéo YouTube (lien public), audio téléchargé puis effacé, Whisper, résumé et 5 à 8
   moments dont chaque instant existe dans la transcription et tient dans la durée ; le second appel sort du cache.
16 miniatures : trois images 1280×720 dessinées par ComfyUI avec le titre incrusté, dans workspace/miniatures/."""
import json
import os
import sys
import time
from pathlib import Path

from ._commun import Collecteur, Verifs, attendre, faux_haut_parleur

faux_haut_parleur()

from ..config import RACINE  # noqa: E402

VIDEO = "https://www.youtube.com/watch?v=0kfSp8CDZRw"     # « J'ai construit un vrai Jarvis », 14 min 43, publique
IMAGE_ESSAI = RACINE / "workspace" / "images" / "test_cloud.png"


def webcam(v: Verifs):
    from .. import vision
    from ..outils import webcam as W
    noms = W.peripheriques()
    v.info(f"périphériques vidéo : {noms or 'aucun'}")
    v.ok(isinstance(noms, list), "la liste des périphériques vidéo se lit (DirectShow)")
    vraie = False
    for nom in noms:
        try:
            W.capturer(nom)
            vraie = True
            break
        except Exception as e:
            v.info(f"{nom} ne diffuse pas ({type(e).__name__})")
    if not vraie:
        W.vision.modele_present = lambda: True
        message = W.executer()
        v.ok(message.startswith("Je ne peux pas regarder") and ("OBS" in message or "webcam" in message),
             "sans webcam qui diffuse : Jarvis dit quoi faire, sans rien inventer", message)
        os.environ["JARVIS_WEBCAM_IMAGE"] = str(IMAGE_ESSAI)
        v.info(f"aucune webcam ne diffuse : image d'essai {IMAGE_ESSAI.name}")
    jpeg, libelle = W.capturer()
    v.ok(jpeg[:2] == b"\xff\xd8" and len(jpeg) > 5000, "une image JPEG est prise", f"{libelle}, {len(jpeg) // 1024} Ko")
    avant = set(W.DOSSIER.glob("*")) if W.DOSSIER.exists() else set()
    evts = Collecteur()
    W.sur_evenement = evts
    t = time.time()
    reponse = W.executer("Que voyez-vous ?")
    v.ok("webcam" in reponse.lower(), "réponse immédiate : « je regarde »", reponse)
    v.ok(attendre(lambda: evts.de_type("vision_fin"), 240), "la description arrive, le cerveau est rechargé",
         f"{round(time.time() - t, 1)} s")
    vues = evts.de_type("vision")
    texte = vues[-1]["texte"] if vues else ""
    v.info(f"description : {texte}")
    v.ok(len(texte) > 30 and (vraie or any(m in texte.lower() for m in ("phare", "mer", "rocher", "océan", "côte"))),
         "la description correspond à l'image")
    chrono = evts.de_type("vision_fin")[-1]["chrono"] if evts.de_type("vision_fin") else {}
    v.info(f"chrono : {chrono}")
    v.ok(vues and vues[-1]["image"].startswith("data:image/jpeg") and not vues[-1]["enregistree"], "l'image part au HUD en mémoire seulement")
    apres = set(W.DOSSIER.glob("*")) if W.DOSSIER.exists() else set()
    v.ok(apres == avant, "aucune image écrite sur le disque sans demande")
    evts.evenements.clear()
    W.executer("Que voyez-vous ?", enregistrer=True)
    attendre(lambda: evts.de_type("vision_fin"), 240)
    nouvelles = (set(W.DOSSIER.glob("*")) if W.DOSSIER.exists() else set()) - avant
    v.ok(len(nouvelles) == 1 and evts.de_type("vision") and evts.de_type("vision")[-1]["enregistree"], "« garde la photo » : une image dans workspace/webcam",
         [p.name for p in nouvelles])
    for p in nouvelles:
        p.unlink()
    os.environ.pop("JARVIS_WEBCAM_IMAGE", None)


def video(v: Verifs):
    from ..outils import resumer_video as R
    cas = {"https://www.youtube.com/watch?v=0kfSp8CDZRw&t=42s": "0kfSp8CDZRw", "https://youtu.be/0kfSp8CDZRw": "0kfSp8CDZRw",
           "https://www.youtube.com/shorts/abcdefghijk": "abcdefghijk", "0kfSp8CDZRw": "0kfSp8CDZRw", "https://example.com": None}
    v.ok(all(R.identifiant(lien) == attendu for lien, attendu in cas.items()), "les liens YouTube sont reconnus (watch, youtu.be, shorts, id)")
    cales = R.caler_moments([{"t": "0:03", "titre": "a"}, {"t": "0:05", "titre": "doublon"}, {"t": "99:00", "titre": "inventé"},
                             {"t": "1:10", "titre": "b"}, {"t": "2:03", "titre": "c"}], [(0.0, "x"), (60.0, "y"), (120.0, "z")], 150)
    v.ok([c["t"] for c in cales] == [0.0, 60.0, 120.0] and [c["titre"] for c in cales] == ["a", "b", "c"],
         "instants recalés sur la transcription, doublons écartés, bornés à la durée", cales)
    cache = R.CACHE / f"{R.identifiant(VIDEO)}.json"
    cache.unlink(missing_ok=True)
    etapes = []
    t = time.time()
    d = R.analyser(VIDEO, etapes.append)
    total = round(time.time() - t, 1)
    v.info(f"« {d['titre']} », {d['duree']:.0f} s, {len(d['segments'])} phrases, étapes {etapes}, chrono {d['chrono']}, total {total} s")
    v.info(f"résumé : {d['resume']}")
    for m in d["moments"]:
        v.info(f"  {R._mmss(m['t'])} {m['titre']}")
    v.ok(not d["depuis_cache"] and len(d["resume"]) > 150, "un résumé de plusieurs phrases")
    v.ok(5 <= len(d["moments"]) <= 8, "5 à 8 moments clés", len(d["moments"]))
    debuts = {t for t, _ in R._transcription_horodatee(d["segments"])}
    v.ok(all(m["t"] in debuts and 0 <= m["t"] <= d["duree"] for m in d["moments"]), "chaque instant existe dans la transcription et tient dans la durée")
    v.ok(d["moments"] == sorted(d["moments"], key=lambda m: m["t"]) and d["moments"][-1]["t"] > d["duree"] * 0.5,
         "moments dans l'ordre, répartis sur la vidéo")
    v.ok(not list(R.CACHE.glob("*.audio.*")), "l'audio téléchargé est effacé")
    t = time.time()
    d2 = R.analyser("https://youtu.be/0kfSp8CDZRw")
    v.ok(d2["depuis_cache"] and d2["resume"] == d["resume"] and time.time() - t < 1, "second appel : servi par le cache",
         f"{round((time.time() - t) * 1000)} ms")
    json.loads(cache.read_text(encoding="utf-8"))


def miniatures(v: Verifs):
    from PIL import Image
    from ..outils import generer_image as G
    from ..outils import miniatures as M
    if not G.comfyui_present():
        v.info("ComfyUI n'est pas lancé : lancement…")
    etapes = []
    t = time.time()
    r = M.creer("un assistant vocal local façon Iron Man, gratuit, qui tourne sur une carte graphique", progression=etapes.append)
    v.info(f"titre « {r['titre']} », étapes {etapes}, chrono {r['chrono']}, total {round(time.time() - t, 1)} s")
    for p in r["prompts"]:
        v.info(f"  prompt : {p[:110]}…")
    v.ok(2 <= len(r["titre"].split()) <= 6, "un titre court de 2 à 5 mots", r["titre"])
    v.ok(len(r["prompts"]) == 3 and len(set(r["prompts"])) == 3, "trois idées d'image différentes")
    tailles = [Image.open(c).size for c in r["chemins"]]
    v.ok(len(r["chemins"]) == 3 and all(s == (1280, 720) for s in tailles), "trois miniatures 1280×720", tailles)
    v.ok(all(Path(c).parent == M.DOSSIER for c in r["chemins"]), "rangées dans workspace/miniatures", [Path(c).name for c in r["chemins"]])
    v.ok(all(u.startswith("/workspace/miniatures/") for u in r["urls"]), "servies au HUD pour le panneau")
    v.ok(r["chrono"].get("dessin", 999) <= 150, "les trois images dessinées en moins de 2 min 30 (1024×576, 8 pas, agrandies)",
         f"{r['chrono'].get('dessin')} s")
    impose = M.idees("une vidéo sur le montage", "Monter plus vite")
    v.ok(impose["titre"] == "Monter plus vite", "un titre donné par la personne est gardé tel quel")


def main() -> int:
    v = Verifs("Pouvoirs 14 à 16 · il voit et il crée")
    choix = sys.argv[1:] or ["webcam", "video", "miniatures"]
    for nom, fonction in (("webcam", webcam), ("video", video), ("miniatures", miniatures)):
        if nom in choix:
            try:
                fonction(v)
            except Exception as e:
                v.ok(False, f"{nom} : exception {type(e).__name__} : {e}")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
