"""Test du tournoi : python -m jarvis.tests.tournoi   (Jarvis arrêté ; cerveau, Whisper, Qwen3-TTS et la vision chargés.
`--complet` joue aussi les miniatures (ComfyUI) et la finale (sculptures, ~10 min))
Vidéo 5 : trois profils du même Jarvis s'affrontent.

1. Plusieurs voix dans un seul modèle : le majordome et Orage chargés ensemble, chaque phrase dans la bonne voix
   (Orage plus grave), sans rechargement entre les deux.
2. Les commandes : « lance le tournoi », « épreuve suivante », « plaidoiries », « j'élimine Pixel », « fin du tournoi ».
3. Un vrai tournoi, à la voix (haut-parleur factice, la synthèse est réelle) : présentations, « le dossier en
   bordel », plaidoiries, élimination, « devine ce que je fais » (la vraie capture de l'écran), et le micro sourd pendant
   qu'un candidat parle. Les répliques et les temps vont dans workspace/mesures/tournoi.json."""
import re
import sys
import time

import numpy as np

from ._commun import Verifs, faux_haut_parleur

faux_haut_parleur()

from .. import commandes, majordome, oreilles, profils, tournoi, voix, voix_creees  # noqa: E402
from ..cerveau import CERVEAU  # noqa: E402
from ..config import CONFIG  # noqa: E402
from ..voix_qwen import reecoute  # noqa: E402
from .prenom import ecrire_mesures  # noqa: E402


def copies(repliques: list[dict]) -> list[str]:
    """Les répliques qui reprennent six mots d'affilée d'une autre, ou qui disent « comme X l'a dit »."""
    def mots(t):
        return re.findall(r"\w+", t.lower())
    trouvees = []
    for i, a in enumerate(repliques):
        if re.search(r"\bcomme \w+ l'a (dit|précisé|fait)", a["texte"], re.IGNORECASE):
            trouvees.append(f"{a['candidat']} : « comme … l'a dit »")
        ma = mots(a["texte"])
        sixa = {" ".join(ma[k:k + 6]) for k in range(len(ma) - 5)}
        for b in repliques[:i]:
            mb = mots(b["texte"])
            if sixa & {" ".join(mb[k:k + 6]) for k in range(len(mb) - 5)}:
                trouvees.append(f"{a['candidat']} reprend {b['candidat']}")
    return trouvees


def main() -> int:
    v = Verifs("Le tournoi · trois candidats, un seul Jarvis")
    mesures = {}
    if not all(profils.trouver(n) for n in ("Nova", "Atlas", "Pixel")):
        v.ok(False, "les profils Nova, Atlas et Pixel existent (python -m jarvis.tests.profils les crée)")
        return v.fin()
    voix_avant = dict(CONFIG["voix"]), dict(CONFIG["voix"].get("majordome", {}))
    try:
        # ------------------------------------------------------------------ 1. plusieurs voix, un seul modèle
        orage = voix_creees.DOSSIER / "orage" / "reference.wav"
        CONFIG["voix"]["moteur"] = "majordome"
        CONFIG["voix"].setdefault("majordome", {})["reference"] = str(voix_creees.REF_MAJORDOME)
        majordome.MAJORDOME.arreter()
        majordome.MAJORDOME.echec = (0.0, "")
        majordome.MAJORDOME.regler_voix_en_plus([orage])
        oreilles.prechauffer_whisper()
        t = time.time()
        infos = majordome.MAJORDOME.demarrer()
        v.ok(infos.get("voix") == 2 and majordome.MAJORDOME.index_voix(orage) == 1,
             f"deux voix chargées dans un seul modèle en {round(time.time() - t, 1)} s", infos.get("voix_chargees"))
        # Sans cache : au premier passage du 29/10, ces phrases revenaient du cache disque d'un passage précédent. Et une
        # seule phrase par voix ne prouve rien par sa hauteur (le majordome a parlé une fois à 99 Hz) : on vérifie la voix
        # que le moteur dit avoir utilisée ; l'écart de hauteur sur dix phrases est mesuré par tests/voix_creees.py.
        CONFIG["voix"]["cache"] = False
        hauteurs, temps, utilisees = {}, {}, {}
        for nom, moteur in (("majordome", "majordome:majordome"), ("orage", "majordome:orage"), ("majordome2", "majordome:majordome")):
            t = time.time()
            audio, info = voix.synthetiser(f"Le tournoi commence dans {len(hauteurs) + 2} minutes, préparez-vous.", moteur)
            temps[nom] = round(time.time() - t, 2)
            hauteurs[nom] = round(reecoute.hauteur(audio, voix.FREQ))
            utilisees[nom] = majordome.MAJORDOME.dernier.get("voix")
        v.info(f"hauteurs {hauteurs} (une phrase chacune, pour information), temps {temps}")
        v.ok(utilisees == {"majordome": 0, "orage": 1, "majordome2": 0},
             "chaque phrase part dans la voix demandée (le moteur dit laquelle a parlé)", utilisees)
        v.ok(max(temps.values()) < 4 and majordome.MAJORDOME.actif, "passer d'une voix à l'autre ne recharge rien", temps)
        mesures["voix_multiples"] = {"hauteurs_hz": hauteurs, "temps_s": temps, "chargement_s": infos.get("demarrage_s")}

        # ------------------------------------------------------------------ 2. les commandes
        attendus = {"lance le tournoi": ("tournoi", "lancer"), "épreuve suivante": ("tournoi", "epreuve"),
                    "plaidoiries": ("tournoi", "plaidoiries"), "j'élimine Pixel": ("tournoi", "eliminer:pixel"),
                    "Jarvis, fin du tournoi": ("tournoi", "fin")}
        vus = {t_: commandes.analyser(t_) for t_ in attendus}
        v.ok(vus == attendus, "les commandes du tournoi", {k: vus[k] for k in attendus if vus[k] != attendus[k]} or "toutes justes")
        # ajouté après la démo du 07/11 : « Euh… je… » coupé à la victoire
        v.ok(tournoi.limiter("Euh… je… je crois que j'ai gagné. Merci ! Trois.", 2) == "Euh… je… je crois que j'ai gagné. Merci !",
             "les points de suspension ne coupent pas une phrase en deux", tournoi.limiter("Euh… je… je crois que j'ai gagné.", 1))

        # ajouté après la démo du 07/11 : après la miniature comme après la finale, les trois plaidoiries reparlaient de
        # « assets_jeu.rar est dans Archives » (seuls les faits du dossier leur étaient donnés). Cerveau factice : on
        # regarde les faits qu'il reçoit, et une plaidoirie qui reprend un fichier du dossier doit être refaite.
        class FauxCerveau:
            def __init__(self):
                self.demandes, self.reponses = [], ["Le fichier assets_jeu.rar est dans Archives/2026-09, c'est logique.",
                                                    "Ma miniature était la seule lisible sur un téléphone."]
            def generer(self, consigne, texte, **_):
                self.demandes.append(texte)
                return self.reponses[min(len(self.demandes) - 1, 1)]
        fc = FauxCerveau()
        F = tournoi.Tournoi.__new__(tournoi.Tournoi)
        F.cerveau, F.dire_brut, F.emettre_brut, F.titre, F.manche = fc, lambda t, m: None, lambda e: None, "monsieur", 1
        F.en_cours = None
        F.candidats = [{**profils.trouver("Pixel"), "en_lice": True, "derniere": "", "points": 0}]
        F.journal, F.destinations = [], {"assets_jeu.rar": "Archives/2026-09", "recette_crepes.md": "Documents/2026-04"}
        F.derniere = {"epreuve": "miniature", "titre": "La miniature de cette vidéo",
                      "candidats": {"Nova": {"idee": "Trois silhouettes tenant chacune un livre."},
                                    "Pixel": {"idee": "Trois écrans côte à côte, un assistant dans chacun."}}}
        F.plaidoiries()
        recu = fc.demandes[0]
        v.ok("La miniature de cette vidéo" in recu and "Trois silhouettes" in recu and "assets_jeu.rar ->" not in recu,
             "après la miniature, les plaidoiries reçoivent les faits de la miniature (pas ceux du dossier)", recu[-300:])
        v.ok(len(fc.demandes) == 2 and F.journal[-1]["texte"] == fc.reponses[1],
             "une plaidoirie qui reparle d'un fichier du dossier est refaite", F.journal[-1]["texte"] if F.journal else "")

        # ------------------------------------------------------------------ 3. un vrai tournoi
        CERVEAU.charger()
        evenements, dits = [], []
        def dire(texte, moteur):
            dits.append((texte, moteur))
            voix.VOIX.dire(texte, moteur=moteur)
        T = tournoi.Tournoi(CERVEAU, dire, evenements.append, "monsieur", ["Nova", "Atlas", "Pixel"])
        t = time.time()
        T.presenter()
        presentations = [j for j in T.journal if j["quoi"] == "présentation"]
        for j in presentations:
            v.info(f"{j['candidat']} : {j['texte']}")
        v.ok(len(presentations) == 3 and len({j["texte"] for j in presentations}) == 3,
             f"trois présentations, trois tons ({round(time.time() - t, 1)} s)")
        v.ok({m for _, m in dits} == {"majordome:orage", "majordome:majordome", "local"},
             "chacun parle dans sa voix : Orage, le majordome, Kokoro", sorted({m for _, m in dits}))
        dernier = evenements[-1]
        v.ok(dernier["type"] == "tournoi" and [c["prenom"] for c in dernier["candidats"]] == ["Nova", "Atlas", "Pixel"]
             and all(c["derniere"] for c in dernier["candidats"]), "le HUD reçoit les trois colonnes et leurs répliques")

        # le micro est sourd pendant qu'un candidat parle
        CONFIG["oreilles"]["sourd_pendant_parole"] = True
        o = oreilles.Oreilles(source=lambda arret: iter(()), jarvis_parle=lambda: True, phrases_dites=lambda: [])
        o.parle_veille, o.tampon_veille = True, [np.zeros(1280, dtype=np.int16)] * 5
        o.detecteur = type("D", (), {"predict": lambda self, b: {o.mot: 0.99}})()     # même un « Hey Jarvis » parfait
        o._veille(np.zeros(1280, dtype=np.int16))
        v.ok(o.etat != "ecoute" and not o.tampon_veille, "micro sourd pendant qu'un candidat parle (même un mot de réveil parfait)")
        CONFIG["oreilles"]["sourd_pendant_parole"] = False

        t = time.time()
        print("    · épreuve 1 :", T.epreuve_suivante(), flush=True)
        while T.en_cours:
            time.sleep(0.5)
        dossier = [j for j in T.journal if j["quoi"] == "dossier"]
        for j in dossier:
            v.info(f"{j['candidat']} : {j['texte']}")
        v.ok(len(dossier) == 3, f"épreuve « le dossier en bordel » : trois rangements et trois explications ({round(time.time() - t, 1)} s)")
        # ajoutés le 29/10 après le premier passage, avant de relancer : un candidat inventait un dossier « Inconnus » que
        # les autres répétaient, et ils se copiaient mot pour mot
        from ..outils import ranger
        reels = {f.lower() for f in ranger.FAMILLES} | {"autres"} | {p.name.lower() for p in ranger.DEMO.iterdir()}
        cites = [x.strip().lower() for j in dossier for x in re.findall(r"[«\"]\s*([^»\"]{2,40}?)\s*[»\"]", j["texte"])]
        v.ok(all(x in reels or x.split("/")[0] in reels for x in cites), "aucun dossier inventé : chaque nom cité existe vraiment", cites)
        v.ok(not copies(dossier), "aucun candidat ne reprend la phrase d'un autre", copies(dossier))
        # ajouté après la démo du 29/10 (« export_inconnu.xyz -> Archives », alors qu'il était dans Autres)
        import json as _json
        from ..tournoi import MESURES, destinations_fausses
        dest = [m for m in _json.loads(MESURES.read_text(encoding="utf-8"))["manches"] if m.get("epreuve") == "dossier"][-1]["destinations"]
        faux = {j["candidat"]: destinations_fausses(j["texte"], dest) for j in dossier}
        v.ok(not any(faux.values()), "chaque fichier cité est annoncé dans son vrai dossier", {k: x for k, x in faux.items() if x} or "")
        T.plaidoiries()
        plaidoiries = [j for j in T.journal if j["quoi"] == "plaidoirie"]
        for j in plaidoiries:
            v.info(f"plaidoirie de {j['candidat']} : {j['texte']}")
        v.ok(len(plaidoiries) == 3 and not copies(plaidoiries), "trois plaidoiries, chacune la sienne", copies(plaidoiries))
        # ajouté le 29/10 après le passage précédent (« log_tournai.txt est dans Logs/2026-07 » : rien de ça n'existait)
        from ..tournoi import fichiers_inventes
        inventes = {j["candidat"]: fichiers_inventes(j["texte"], dest) for j in plaidoiries}
        v.ok(not any(inventes.values()), "les plaidoiries n'inventent ni fichier ni dossier",
             {k: x for k, x in inventes.items() if x} or "")
        r = T.eliminer("Pixel")
        v.info(f"« j'élimine Pixel » -> {r} / {T.journal[-1]['texte']}")
        v.ok(not T.trouver("Pixel")["en_lice"] and len(T.en_lice()) == 2 and T.journal[-1]["quoi"] == "élimination",
             "Pixel est éliminé et dit au revoir dans son style")
        if "--complet" in sys.argv:
            print("    · épreuve 2 :", T.epreuve_suivante(), flush=True)
            while T.en_cours:
                time.sleep(1)
            v.ok(len([c for c in T.journal if c["quoi"] == "idée"]) == 2, "les miniatures : deux idées, deux images")
            v.ok(majordome.MAJORDOME.actif, "après les dessins, la voix est revenue (avant le cerveau)")
        else:
            T.manche = 1                                 # sans --complet, on saute les miniatures (ComfyUI)
        t = time.time()
        print("    · épreuve 3 :", T.epreuve_suivante(), flush=True)
        while T.en_cours:
            time.sleep(0.5)
        paris = [j for j in T.journal if j["quoi"] == "pari"]
        for j in paris:
            v.info(f"pari de {j['candidat']} : {j['texte']}")
        v.ok(len(paris) == 2, f"« devine ce que je fais » : les deux restants parient sur le même écran ({round(time.time() - t, 1)} s)")
        v.ok(not copies(paris), "deux paris différents, pas une copie", copies(paris))
        import json as _j
        yeux = [m for m in _j.loads(MESURES.read_text(encoding="utf-8"))["manches"] if m.get("epreuve") == "devine"][-1]["vision"]
        v.info(f"les yeux : {yeux['duree_s']} s (3 min 55 à la démo du 07/11, la voix encore chargée)")
        # ajouté après la démo du 07/11 : les plaidoiries d'après une autre épreuve reparlaient du dossier
        avant = len(T.journal)
        T.plaidoiries()
        apres_devine = [j for j in T.journal[avant:] if j["quoi"] == "plaidoirie"]
        for j in apres_devine:
            v.info(f"plaidoirie de {j['candidat']} : {j['texte']}")
        hors = {j["candidat"]: T.ancienne_epreuve(j["texte"]) for j in apres_devine}
        v.ok(len(apres_devine) == 2 and not any(hors.values()),
             "après « devine ce que je fais », les plaidoiries ne reparlent pas du dossier", {k: x for k, x in hors.items() if x} or "")
        if "--complet" in sys.argv:
            T.eliminer("Atlas") if T.trouver("Atlas")["en_lice"] and len(T.en_lice()) > 2 else None
            print("    · finale :", T.epreuve_suivante(), flush=True)
            while T.en_cours:
                time.sleep(2)
            dragons = [j for j in T.journal if j["quoi"] == "dragon"]
            for j in dragons:
                v.info(f"dragon de {j['candidat']} : {j['texte']}")
            fin = [m for m in _j.loads(MESURES.read_text(encoding="utf-8"))["manches"] if m.get("epreuve") == "finale"][-1]
            v.ok(not fin.get("erreur") and all(x["sculpture_s"] > 30 and not x["chrono"].get("cache") for x in fin["candidats"].values()),
                 "finale : chaque dragon est vraiment sculpté (aucun ne ressort du cache)",
                 {k: x["sculpture_s"] for k, x in fin["candidats"].items()})
            v.ok(not copies(dragons), "deux dragons différents, pas une copie", copies(dragons))
            v.ok(majordome.MAJORDOME.actif, "après les sculptures, la voix est revenue")
        voix.VOIX.attendre(180)
        mesures["journal"] = T.journal
        mesures["date"] = time.strftime("%Y-%m-%d %H:%M")
    finally:
        majordome.MAJORDOME.regler_voix_en_plus([])
        majordome.MAJORDOME.arreter()
        CONFIG["voix"].clear()
        CONFIG["voix"].update(voix_avant[0])
        CONFIG["oreilles"]["sourd_pendant_parole"] = False
    ecrire_mesures("tournoi_test", mesures)
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
