"""Test du pouvoir v3-3 : la voix du majordome (Qwen3-TTS local, réécoutée par Whisper).

    python -m jarvis.tests.majordome

1. la voix est inventée par description (reference.json : modèle VoiceDesign, description, aucune imitation) ;
2. le comparateur de la réécoute : ce que Whisper écrit autrement n'est pas une faute (« 9h30 », « servie »), un mot
   changé, sauté, un nombre faux ou répété en est une ; la boucle refait une prise fautive et garde la juste ;
3. les Réglages proposent le moteur « majordome » et l'enregistrent ; sans modèle ni Python, repli sur Kokoro annoncé ;
4. le vrai moteur : chargé sur la carte, chaque phrase réécoutée et juste, niveau égalisé à -20 dB, rapport écrit ;
5. la latence du premier mot, mesurée comme Jarvis parle (Parleur, jusqu'au premier bloc joué), contre Kokoro ;
6. règle v3 : pendant qu'il parle, le HUD garde sa cadence (Edge sans fenêtre, WebGL) ; mémoire vidéo relevée."""
import asyncio
import json
import sys
import threading
import time

import numpy as np

from ._commun import Verifs

PHRASES = ["Bien, monsieur.", "Il est vingt heures, et votre réunion commence demain à neuf heures trente.",
           "J'ai rangé vos fichiers dans le dossier Documents, comme convenu.",
           "Je crains que la météo ne soit guère clémente ce week-end.",
           "Votre thé est servi, et la voiture vous attend devant la porte.", "Good evening, sir. Shall I prepare the car?"]


def voix_inventee(v: Verifs):
    from .. import majordome
    from pathlib import Path
    ref = Path(majordome.reglage("reference"))
    meta = ref.with_suffix(".json")
    v.ok(ref.exists() and meta.exists(), "la référence du majordome existe", str(ref))
    if not meta.exists():
        return
    m = json.loads(meta.read_text(encoding="utf-8"))
    v.ok("VoiceDesign" in m.get("modele", "") and len(m.get("description", "")) > 80 and m.get("imitation", "").startswith("aucune"),
         "inventée par description (VoiceDesign), aucune imitation", m.get("description", "")[:90] + "…")
    choisi = next((e for e in m.get("essais", []) if e["essai"] == m.get("choisi")), {})
    v.ok(choisi.get("score") == 0, "l'essai retenu a été réécouté juste par Whisper",
         f"essai {m.get('choisi')} sur {len(m.get('essais', []))}, {choisi.get('hauteur_hz')} Hz")


def comparateur(v: Verifs):
    from ..voix_qwen import reecoute as R
    justes = [("La réunion commence à neuf heures trente.", "La réunion commence à 9h30."),
              ("Votre thé est servi.", "Votre thé est servie."), ("Il est vingt heures.", "Il est 20h."),
              ("Cela coûte quatre-vingt-dix-sept euros.", "Cela coûte 97 euros."),
              ("La météo n'est guère clémente.", "la météo n'est guère clément")]
    faux = [("Bien, monsieur.", "Viens, monsieur."), ("La voiture vous attend.", "La voiture attend."),
            ("Il reste trois dossiers.", "Il reste 4 dossiers."), ("Il est vingt heures.", "Il est 20h 20h 20h.")]
    v.ok(all(not R.ecarts(a, b) for a, b in justes), "ce que Whisper écrit autrement n'est pas une faute",
         {b: R.ecarts(a, b) for a, b in justes if R.ecarts(a, b)} or "9h30, servie, 20h, 97, clément")
    v.ok(all(R.ecarts(a, b) for a, b in faux), "un mot changé, sauté, un nombre faux ou répété est une faute",
         {b: R.ecarts(a, b) for a, b in faux})
    # la boucle : la 1re prise saute un mot, la 2e est juste -> 2 prises, la juste gardée ; que des fausses -> la moins fausse
    sr = 24000
    ondes = [np.full(sr, 0.1 * (i + 1), np.float32) for i in range(3)]
    dites = iter(["La voiture attend.", "La voiture vous attend."])
    onde, r = R.reecouter("La voiture vous attend.", lambda p, it=iter(ondes): next(it), lambda o: next(dites), sr)
    v.ok(r["prises"] == 2 and r["score"] == 0 and r["fautes_ecartees"] == [[("delete", "vous", "")]],
         "une prise fautive est refaite, la juste est gardée", {k: r[k] for k in ("prises", "score", "fautes_ecartees")})
    v.ok(abs(R.rms_db(onde[int(sr * 0.05):-int(sr * 0.05)]) - R.NIVEAU_DB) < 0.5, "la prise gardée est ramenée à -20 dB")
    dites = iter(["Rien du tout.", "Viens, monsieur.", "Viens."])          # scores 3, 1, 2
    _, r = R.reecouter("Bien, monsieur.", lambda p, it=iter(ondes): next(it), lambda o: next(dites), sr)
    v.ok(r["prises"] == 3 and r["score"] == 1 and r["entendu"] == "Viens, monsieur.",
         "trois prises fausses : la moins fausse est gardée, et le rapport le dit", r["ecarts"])


def reglages_et_repli(v: Verifs):
    from .. import majordome, reglages, voix
    from ..config import CONFIG
    etat = reglages.lire()["voix"]
    v.ok("majordome" in etat and etat["majordome"]["disponible"], "les Réglages voient le moteur majordome, disponible",
         etat.get("majordome"))
    hud = (majordome.RACINE / "jarvis" / "hud" / "hud.js").read_text(encoding="utf-8")
    v.ok('["majordome", "Majordome britannique' in hud, "le HUD le propose dans le choix du moteur de voix")
    # repli : Python de Qwen introuvable -> Kokoro, annoncé
    evenements = []
    ancien, sauve = voix.sur_evenement, dict(CONFIG["voix"].get("majordome", {}))
    voix.sur_evenement = evenements.append
    CONFIG["voix"].setdefault("majordome", {})["python"] = "Z:/nulle_part/python.exe"
    en_marche = majordome.MAJORDOME.proc
    majordome.MAJORDOME.proc = None
    try:
        audio, infos = voix.synthetiser("Test de repli numéro %d." % int(time.time()), "majordome")
        v.ok(infos["moteur"] == "local" and len(audio) > 1000 and any(e["type"] == "voix_repli" for e in evenements),
             "sans Python Qwen : Kokoro prend le relais et le dit", infos.get("repli"))
    finally:
        voix.sur_evenement = ancien
        CONFIG["voix"]["majordome"] = sauve
        majordome.MAJORDOME.proc = en_marche
        majordome.MAJORDOME.echec = (0.0, "")


def moteur(v: Verifs) -> dict:
    from .. import majordome
    from ..machine import vram_libre_mo
    avant = vram_libre_mo()
    t = time.time()
    infos = majordome.MAJORDOME.demarrer()
    v.info(f"chargement : {infos['demarrage_s']} s ; modèle {majordome.reglage('modele')} ; {infos['vram_mo']} Mo réservés par le processus"
           f" (libre avant : {avant} Mo, après : {vram_libre_mo()} Mo)")
    v.ok(infos["sr"] == 24000 and time.time() - t < 120, "le modèle se charge sur la carte (24 kHz)")
    majordome.MAJORDOME.entendre(np.zeros(8000, np.float32), 16000)        # Whisper chargé hors mesure
    rapports = []
    for p in PHRASES:
        onde, r = majordome.MAJORDOME.synthetiser(p, "en" if p.startswith("Good") else "fr")
        rapports.append(r)
        v.info(f"{r['total_s']:.2f} s ({r['generation_s']:.2f} voix + {r['ecoute_s']:.2f} réécoute, {r['prises']} prise·s) "
               f"pour {r['duree_s']:.2f} s · entendu « {r['entendu']} »")
    v.ok(all(r["score"] == 0 for r in rapports), "chaque phrase est réécoutée par Whisper et juste",
         [r["ecarts"] for r in rapports if r["score"]] or f"{sum(r['prises'] for r in rapports)} prises pour {len(rapports)} phrases")
    rtf = sum(r["generation_s"] for r in rapports) / sum(r["duree_s"] for r in rapports)
    v.ok(rtf < 0.8, "il calcule plus vite qu'il ne parle", f"{rtf:.2f} s de calcul par seconde de voix")
    lignes = majordome.JOURNAL.read_text(encoding="utf-8").strip().splitlines()
    v.ok(json.loads(lignes[-1])["phrase"] == PHRASES[-1], "le rapport de réécoute est écrit", str(majordome.JOURNAL))
    return {"rtf": rtf, "vram_mo": infos["vram_mo"]}


def premier_mot(v: Verifs):
    """Comme en conversation : Parleur.dire, jusqu'au premier bloc réellement joué (événement premier_son)."""
    from .. import voix
    mesures = {}
    ancien, cache = voix.sur_evenement, voix.REGLAGES.get("cache", True)
    voix.REGLAGES["cache"] = False                         # rien ne vient du disque : on mesure le calcul
    for moteur_voix in ("local", "majordome"):
        for essai in range(3):
            texte = ["Bien, monsieur. Je m'en occupe tout de suite.", "Très bien. Je prépare la voiture.",
                     "Certainement, monsieur. Le rapport arrive."][essai]
            recu = threading.Event()
            voix.sur_evenement = lambda e: recu.set() if e.get("type") == "premier_son" else None
            t = time.time()
            voix.VOIX.dire(texte, moteur_voix)
            recu.wait(30)
            mesures.setdefault(moteur_voix, []).append(time.time() - t)
            voix.VOIX.attendre(30)
    voix.sur_evenement, voix.REGLAGES["cache"] = ancien, cache
    k, m = sorted(mesures["local"])[1], sorted(mesures["majordome"])[1]
    # la carte partagée ralentit la voix : mesuré le 20/09, 0,82 s à machine calme, 2,23 s en fin de batterie
    # complète (ComfyUI encore chargé, 1,6 Go libres). Le seuil suit donc ce qui reste réellement sur la carte.
    from ..machine import vram_libre_mo
    libre = vram_libre_mo() or 9999
    seuil = 1.5 if libre > 3000 else 2.5
    v.info(f"premier mot (médiane de 3, texte jamais dit) : Kokoro {k:.2f} s, majordome {m:.2f} s "
           f"(tous : {[round(x, 2) for x in mesures['majordome']]}) · {libre} Mo libres sur la carte")
    v.ok(m < seuil, f"latence du premier mot du majordome sous {seuil} s"
         + ("" if libre > 3000 else " (carte chargée)"), f"{m:.2f} s")
    return m


async def cadence(v: Verifs):
    from .. import majordome
    from .cadence import MARGE, Edge, SCENE, mesurer, serveur_fichiers
    s, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "", 4000)
        fini = threading.Event()

        def parler():
            while not fini.is_set():
                majordome.MAJORDOME.generer("Je vous prépare le rapport complet, monsieur, avec les chiffres de la semaine.")
        th = threading.Thread(target=parler, daemon=True)
        th.start()
        await asyncio.sleep(0.5)
        r = await mesurer(edge, "", 4000)
        fini.set()
        th.join(30)
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.05 and r["pire_ms"] < 18,
             "le HUD garde sa cadence pendant que le majordome calcule",
             f"{base['moyenne_ms']} -> {r['moyenne_ms']} ms/image, pire {r['pire_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-3 · la voix du majordome")
    voix_inventee(v)
    comparateur(v)
    reglages_et_repli(v)
    from .. import majordome
    ok, raison = majordome.disponible()
    if not ok:
        v.ok(False, "le moteur majordome est disponible", raison)
        return v.fin()
    try:
        moteur(v)
        premier_mot(v)
        asyncio.run(cadence(v))
    finally:
        majordome.MAJORDOME.arreter()
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
