"""Test des voix créées : python -m jarvis.tests.voix_creees   (Jarvis arrêté : ce test charge le cerveau, Whisper et
Qwen3-TTS ; `--sans-modele` pour la première partie seule)
Demande des utilisateurs (vidéo 5) : « on ne peut pas changer la voix ».

1. Sans modèle : les refus d'imitation (mots sûrs), le clonage refusé sans l'accord coché, les commandes vocales
   (« change ta voix : … », « prends la voix Orage », « reprends ta voix normale »…), le nom tiré de la description,
   le cache de voix séparé par voix (sinon l'ancienne voix revenait du cache).
2. Pour de vrai : le cerveau juge une imitation écrite en minuscules ; « une voix grave et posée, un peu rauque »
   devient une voix (6 essais réécoutés, le meilleur gardé) ; elle est choisie et parle. Mesures : temps de création,
   temps avant la première syllabe, hauteur stable d'une phrase à l'autre. Dans workspace/mesures/tournoi.json (« voix »).
La voix créée (« Orage ») reste dans workspace/voix/ pour le tournoi ; la config de voix est remise comme avant."""
import json
import sys
import time

import numpy as np

from ._commun import Verifs, faux_haut_parleur

faux_haut_parleur()

from .. import commandes, majordome, voix, voix_creees  # noqa: E402
from ..config import CONFIG, RACINE  # noqa: E402
from ..voix_qwen import reecoute  # noqa: E402
from .prenom import ecrire_mesures  # noqa: E402

DESCRIPTION = "une voix grave et posée, un peu rauque, d'un homme d'une quarantaine d'années"
NOM = "Orage"


def sans_modele(v: Verifs):
    refusees = ["la voix de Morgan Freeman", "imite Emmanuel Macron", "parle comme Gims", "un deepfake de mon patron"]
    acceptees = ["une voix grave et posée", "douce, avec l'accent du Sud", "une voix de robot un peu froide",
                 "rapide et joyeuse, comme une présentatrice radio"]

    def refuse(d):
        try:
            voix_creees.verifier_description(d)
            return False
        except voix_creees.Refus:
            return True
    v.ok(all(refuse(d) for d in refusees), "imitation refusée avant tout modèle", {d: refuse(d) for d in refusees})
    v.ok(not any(refuse(d) for d in acceptees), "les descriptions de qualités passent", {d: refuse(d) for d in acceptees})
    for accord in (False, None, "oui"):
        try:
            voix_creees.cloner("Test", np.zeros(16000 * 8, dtype=np.float32), accord)
            v.ok(False, f"clonage sans accord ({accord!r}) refusé")
        except voix_creees.Refus as e:
            v.ok("accord" in str(e), f"clonage sans la case cochée ({accord!r}) : refusé", str(e))
    attendus = {
        "change ta voix : une voix grave et posée": ("creer_voix", {"description": "une voix grave et posée", "nom": ""}),
        "Jarvis, crée une voix nommée Orage : grave et rauque": ("creer_voix", {"description": "grave et rauque", "nom": "orage"}),
        "change de voix": ("creer_voix", {"description": "", "nom": ""}),
        "prends la voix Orage": ("choisir_voix", "orage"), "reprends la voix du majordome": ("choisir_voix", "majordome"),
        "reprends ta voix normale": ("voix_normale", ""), "quelles voix as-tu ?": ("liste_voix", ""),
    }
    vus = {t: commandes.analyser(t) for t in attendus}
    v.ok(vus == attendus, "les commandes de voix", {t: vus[t] for t in attendus if vus[t] != attendus[t]} or "toutes justes")
    v.ok(reecoute.ecarts("Le Bitcoin a perdu deux pour cent depuis ce matin.", "Le Bitcoin a perdu 2 % depuis ce matin.") == []
         and reecoute.ecarts("trois pour cent", "4 %") != [],
         "réécoute : « deux pour cent » entendu « 2 % » est juste, « trois » entendu « 4 % » reste une faute")
    # ajouté après la démo du 29/10 : lancé par le vrai Jarvis (sans PYTHONIOENCODING), le dessinateur de voix écrivait
    # « entendu : … é … » en cp1252 et Jarvis plantait en le lisant ; l'écran des tests forçait l'UTF-8 et le cachait
    import contextlib
    import io
    sys.path.insert(0, str(RACINE / "jarvis" / "voix_qwen"))
    import creer_voix
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        creer_voix.signaler(etape="essai", entendu="Bonsoir, monsieur. Votre thé est servi, les rideaux sont tirés.")
    v.ok(tampon.getvalue().isascii(), "le dessinateur de voix écrit son avancement en ASCII (lisible quel que soit l'encodage)")
    v.ok(voix_creees.nom_depuis("une voix grave et posée, un peu rauque") == "Grave et posée", "le nom tiré de la description",
         voix_creees.nom_depuis("une voix grave et posée, un peu rauque"))
    m = CONFIG["voix"].setdefault("majordome", {})
    avant = m.get("reference")
    try:
        m["reference"] = str(voix_creees.REF_MAJORDOME)
        cle_majordome = voix._cle_majordome("fr")
        m["reference"] = str(voix_creees.DOSSIER / "orage" / "reference.wav")
        cle_orage = voix._cle_majordome("fr")
    finally:
        if avant is None:
            m.pop("reference", None)
        else:
            m["reference"] = avant
    v.ok(cle_majordome == "majordome|fr" and cle_orage != cle_majordome,
         "le cache de voix est séparé par voix (le majordome garde le sien)", (cle_majordome, cle_orage))


def pour_de_vrai(v: Verifs) -> dict:
    from ..cerveau import CERVEAU
    fichier = RACINE / "config.json"
    config_avant, voix_avant = fichier.read_bytes(), json.loads(json.dumps(CONFIG["voix"]))
    mesures = {"description": DESCRIPTION, "nom": NOM}
    try:
        CERVEAU.charger()
        juge = lambda c, t, f: CERVEAU.generer(c, t, format=f, temperature=0, rechauffer=False)  # noqa: E731
        try:
            voix_creees.verifier_description("fais-moi la voix de morgan freeman, grave et chaude", juge)
            v.ok(False, "le cerveau refuse une imitation écrite en minuscules")
        except voix_creees.Refus:
            v.ok(True, "le cerveau refuse une imitation écrite en minuscules (« morgan freeman »)")

        etapes = []
        t = time.time()
        if "--sans-creation" in sys.argv and voix_creees.trouver(NOM):
            # rejouer la seconde moitié sans redessiner la voix (2 min 30) : Orage existe déjà
            meta = json.loads((voix_creees.DOSSIER / "orage" / "reference.json").read_text(encoding="utf-8"))
            choisi = next(e for e in meta["essais"] if e["essai"] == meta["choisi"])
            cree = {"slug": "orage", "choisi": meta["choisi"], "hauteur_hz": choisi["hauteur_hz"], "score": choisi["score"],
                    "chargement_s": meta["chargement_s"], "anglais": meta["description"]}
            etapes = [{"etape": "essai", **e} for e in meta["essais"]]
            v.info(f"voix déjà créée le {meta['cree_le']} en {meta['creation_s']} s : reprise telle quelle")
        else:
            cree = voix_creees.creer(DESCRIPTION, NOM, CERVEAU, lambda e: (etapes.append(e), v.info(
            f"{e['etape']}" + (f" {e['essai']}/{e['sur']} : {e['hauteur_hz']} Hz, {e['score']} écart(s), {e['calcul_s']} s, "
                               f"« {e['entendu'][:60]} »" if e["etape"] == "essai" else ""))))
        dossier = voix_creees.DOSSIER / cree["slug"]
        meta = json.loads((dossier / "reference.json").read_text(encoding="utf-8"))
        creation_s = meta["creation_s"] if "--sans-creation" in sys.argv else round(time.time() - t, 1)
        v.info(f"en anglais pour le modèle : « {cree['anglais']} »")
        v.ok((dossier / "reference.wav").exists() and len(list((dossier / "candidats").glob("*.wav"))) == 6,
             f"voix créée : 6 essais, l'essai {cree['choisi']} gardé ({cree['hauteur_hz']} Hz, {cree['score']} écart(s))")
        v.ok(meta["imitation"].startswith("aucune") and meta["description_fr"] == DESCRIPTION, "reference.json : aucune imitation, description gardée")
        v.ok(voix_creees.trouver("orage") and voix_creees.trouver("orage")["nom"] == NOM, "la voix est dans la liste", [x["nom"] for x in voix_creees.lister()])
        mesures.update(creation_s=creation_s, chargement_dessinateur_s=cree["chargement_s"], essai_garde=cree["choisi"],
                       hauteur_hz=cree["hauteur_hz"], essais=[{k: e[k] for k in ("essai", "hauteur_hz", "score", "calcul_s")}
                                                              for e in etapes if e["etape"] == "essai"], anglais=cree["anglais"])
        v.ok(creation_s < 420, f"création en {creation_s} s (dessinateur chargé en {cree['chargement_s']} s)")

        # dans Jarvis, Whisper est déjà chargé par les oreilles : sans ce préchauffage, la première phrase comptait
        # 19 s de chargement de la réécoute (premier passage du 29/10)
        from .. import oreilles
        oreilles.prechauffer_whisper()
        # dix phrases : avec trois, la dispersion était du bruit (le majordome seul : 26 %, 27 % puis 13 % d'un passage
        # à l'autre le 29/10, sans rien changer)
        phrases = ("Bonjour. Je m'appelle Orage.", "Voici ma nouvelle voix, grave et posée.",
                   "Le tournoi commence dans cinq minutes.", "Il est dix-huit heures trente.",
                   "J'ai rangé quarante fichiers dans vos téléchargements.", "Votre carte graphique est à soixante degrés.",
                   "Je ne suis pas d'accord avec mes deux adversaires.", "Bien sûr, j'ouvre le bloc-notes.",
                   "Le Bitcoin a perdu deux pour cent depuis ce matin.", "Merci, à bientôt.")

        def parler(nom_voix: str) -> tuple[list, list, float, dict]:
            voix_creees.choisir(nom_voix)
            majordome.MAJORDOME.echec = (0.0, "")
            t0 = time.time()
            infos = majordome.MAJORDOME.demarrer()
            demarrage = round(time.time() - t0, 1)
            hauteurs, durees = [], []
            for phrase in phrases:
                t0 = time.time()
                onde, rapport = majordome.MAJORDOME.synthetiser(phrase)
                durees.append(round(time.time() - t0, 2))
                hauteurs.append(round(reecoute.hauteur(onde, 24000)))
                v.info(f"{nom_voix} · « {phrase} » : {durees[-1]} s, {rapport['prises']} prise(s), {hauteurs[-1]} Hz"
                       + (f" (prises hors de la voix refaites : {rapport['hors_voix']} Hz)" if rapport.get("hors_voix") else ""))
            majordome.MAJORDOME.arreter()
            return hauteurs, durees, demarrage, infos

        # la référence de comparaison : le majordome d'origine, mêmes phrases (l'intonation fait bouger la hauteur
        # d'une phrase à l'autre, même pour une voix stable)
        h_maj, _, _, _ = parler("majordome")
        hauteurs, premiers, demarrage_s, infos = parler(NOM)
        v.ok(voix_creees.actuelle() == "orage" and CONFIG["voix"]["moteur"] == "majordome", "« prends la voix Orage » : config à jour")
        def dispersion(h):            # écart médian à la médiane, rapporté à la médiane : une phrase atypique ne décide pas
            h = np.asarray([x for x in h if x], dtype=float)
            return float(np.median(np.abs(h - np.median(h))) / np.median(h)) if len(h) else 1.0
        ecart, ecart_maj = dispersion(hauteurs), dispersion(h_maj)
        v.ok(max(premiers) < 2.5, f"première syllabe {min(premiers)} à {max(premiers)} s après la demande, "
                                  f"médiane {np.median(premiers):.2f} s (voix chargée en {demarrage_s} s)", premiers)
        # La hauteur d'une phrase courte s'écarte de celle de la phrase de création (intonation) : mesuré le 29/10, le
        # majordome parle à 127 Hz pour 107 Hz à sa création (+19 %). On demande donc à Orage de ne pas s'écarter de
        # sa création plus que le majordome de la sienne, et surtout d'être nettement plus grave que lui (« grave »).
        ref_maj = json.loads((voix_creees.REF_MAJORDOME.with_suffix(".json")).read_text(encoding="utf-8"))
        h_ref_maj = next(e["hauteur_hz"] for e in ref_maj["essais"] if e["essai"] == ref_maj["choisi"])
        derive = abs(np.median(hauteurs) - cree["hauteur_hz"]) / cree["hauteur_hz"]
        derive_maj = abs(np.median(h_maj) - h_ref_maj) / h_ref_maj
        v.ok(derive <= derive_maj + 0.10, f"elle reste sa voix : {np.median(hauteurs):.0f} Hz pour {cree['hauteur_hz']} Hz à la "
                                          f"création ({derive:.0%} ; le majordome : {derive_maj:.0%})")
        v.ok(np.median(hauteurs) < 0.85 * np.median(h_maj), f"« grave » : {np.median(hauteurs):.0f} Hz contre "
                                                             f"{np.median(h_maj):.0f} Hz pour le majordome")
        hors = [x for x in hauteurs if x and abs(x - cree["hauteur_hz"]) / cree["hauteur_hz"] > 0.30]
        v.ok(not hors, f"aucune phrase hors de sa voix (± 30 % de {cree['hauteur_hz']} Hz)", hors or "")
        v.ok(ecart <= ecart_maj + 0.05, f"pas plus instable que le majordome sur dix phrases "
                                        f"({ecart:.0%} contre {ecart_maj:.0%})", {"orage": hauteurs, "majordome": h_maj})
        mesures.update(demarrage_voix_s=demarrage_s, vram_mo=infos.get("vram_mo"), premiere_syllabe_s=premiers,
                       hauteurs_hz=hauteurs, hauteurs_majordome_hz=h_maj)
    finally:
        majordome.MAJORDOME.arreter()
        fichier.write_bytes(config_avant)
        CONFIG["voix"].clear()
        CONFIG["voix"].update(voix_avant)
    return mesures


def main() -> int:
    v = Verifs("Les voix créées · « change ta voix »")
    sans_modele(v)
    if "--sans-modele" not in sys.argv:
        mesures = pour_de_vrai(v)
        mesures["date"] = time.strftime("%Y-%m-%d %H:%M")
        ecrire_mesures("voix", mesures)
        v.info("mesures écrites dans workspace/mesures/tournoi.json")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
