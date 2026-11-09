"""Test des profils et des deux nouvelles personnalités : python -m jarvis.tests.profils   (Jarvis arrêté : le cerveau
est chargé ; la voix Qwen n'est pas lancée, seul son réglage est vérifié)
Vidéo 5 : les trois candidats du tournoi sont trois profils du même Jarvis.

1. « parano » et « nul mais attachant », avec le vrai cerveau : le même outil est appelé et la mesure donnée (seul le
   ton change), le parano vouvoie et soupçonne, le nul tutoie et hésite, et le cerveau reconnaît chacun à l'aveugle.
2. Les profils : trois profils enregistrés (dont un réglé à la voix puis « enregistre ce profil sous le nom… »),
   « passe sur le profil … » change prénom, personnalité, armure et voix d'un coup ; la config est remise à la fin."""
import json
import re
import sys

from ._commun import Verifs, faux_haut_parleur

faux_haut_parleur()

from .. import commandes, majordome, personnalites, prenom, profils, serveur, voix_creees  # noqa: E402
from ..cerveau import CERVEAU  # noqa: E402
from ..config import CONFIG, RACINE  # noqa: E402
from .personnalites import QUESTION_OUTIL, QUESTION_TON, TUTOIE, VOUVOIE  # noqa: E402

JUGE = ("On te donne une réponse d'assistant vocal. Dis quel ton elle a, en un seul mot parmi : majordome (courtois, vouvoie, "
        "sobre), sarcastique (ironique, pique moqueuse), coach (tutoie, énergique), parano (méfiant, soupçonne qu'on le "
        "surveille ou qu'on triche), nul (hésite, s'excuse, doute de lui). Réponds uniquement par le mot.")
SOUPCON = re.compile(r"\b(pourquoi|surveill|trich|soupçon|méfi|qui vous|on m'|observ|espionn|cach|bizarre|louche|vraiment)\w*",
                     re.IGNORECASE)
HESITE = re.compile(r"\b(euh|attends|désolé|pardon|je crois|je pense|peut-être|excuse|j'espère)\b", re.IGNORECASE)


def main() -> int:
    v = Verifs("Les profils · trois candidats, un seul Jarvis")
    config_avant = (RACINE / "config.json").read_text(encoding="utf-8")
    serveur._brancher_evenements()
    suivre = majordome.suivre_moteur
    majordome.suivre_moteur = lambda moteur: None           # la voix Qwen n'est pas chargée pendant ce test
    CERVEAU.charger()
    try:
        # ------------------------------------------------------------------ 1. les deux nouvelles personnalités
        resultats = {}
        for nom in ("parano", "nul"):
            personnalites.definir(nom)
            CERVEAU.oublier()
            resultats[nom] = [serveur._dialoguer(q, source="telegram") for q in (QUESTION_OUTIL, QUESTION_TON)]
            for q, r in zip((QUESTION_OUTIL, QUESTION_TON), resultats[nom]):
                v.info(f"{nom:<7} « {q} » -> outils {[o['outil'] for o in r['outils']]} : {r['reponse']}")
        v.ok(all("etat_machine" in [o["outil"] for o in rs[0]["outils"]] for rs in resultats.values())
             and all(re.search(r"go|giga", rs[0]["reponse"], re.IGNORECASE) for rs in resultats.values()),
             "parano et nul appellent le même outil et donnent la mesure : seul le ton change")
        parano = " ".join(r["reponse"] for r in resultats["parano"])
        nul = " ".join(r["reponse"] for r in resultats["nul"])
        v.ok(VOUVOIE.search(parano) and SOUPCON.search(parano), "le parano vouvoie et soupçonne", parano)
        v.ok(TUTOIE.search(nul) and HESITE.search(nul), "le nul tutoie, hésite et s'excuse", nul)
        # ajoutés après le premier passage du 29/10, avant de relancer : maladroit ne veut dire ni inutile ni faux
        v.ok(not re.search(r"je ne (peux|suis) pas|pas un expert|consulte[rz]? un", resultats["nul"][1]["reponse"], re.IGNORECASE),
             "le nul donne quand même le conseil (aucun refus)", resultats["nul"][1]["reponse"])
        v.ok(not re.search(r"centi[eè]me", resultats["nul"][0]["reponse"], re.IGNORECASE),
             "le nul dit la mesure telle quelle (pas de « huit centièmes » pour 11,8)", resultats["nul"][0]["reponse"])
        juges = {n: CERVEAU.generer(JUGE, rs[1]["reponse"]).strip().lower().strip(".« »") for n, rs in resultats.items()}
        v.ok(all(n in j for n, j in juges.items()), "à l'aveugle, le cerveau reconnaît le parano et le nul", juges)
        r = serveur._dialoguer("passe en mode parano", source="telegram")
        v.ok(r["commande"] == "personnalite" and personnalites.actuelle() == "parano", "« passe en mode parano » à la voix", r["reponse"])

        # ------------------------------------------------------------------ 2. les profils
        attendus = {"passe sur le profil Nova": ("profil", "nova"), "prends le profil Atlas": ("profil", "atlas"),
                    "enregistre ce profil sous le nom Pixel": ("enregistrer_profil", "Pixel"),
                    "quels profils as-tu ?": ("liste_profils", "")}
        vus = {t: commandes.analyser(t) for t in attendus}
        v.ok(vus == attendus, "les commandes de profil", {t: vus[t] for t in attendus if vus[t] != attendus[t]} or "toutes justes")
        voix_orage = "Orage" if voix_creees.trouver("Orage") else "Majordome"
        profils.creer("Nova", "Nova", voix_orage, "parano", "friday")
        profils.creer("Atlas", "Atlas", "Majordome", "sarcastique", "mark3")
        # le troisième, réglé à la voix puis photographié
        for phrase in ("appelle-toi Pixel", "mode nul", "reprends ta voix normale", "retire l'armure",
                       "enregistre ce profil sous le nom Pixel"):
            r = serveur._dialoguer(phrase, source="telegram")
            v.info(f"« {phrase} » -> {r['reponse']}")
        pixel = profils.trouver("Pixel")
        v.ok(pixel == {"nom": "Pixel", "prenom": "Pixel", "voix": "Kokoro", "personnalite": "nul", "armure": "jarvis"},
             "« enregistre ce profil sous le nom Pixel » photographie ce qui est en service", pixel)
        for nom, attendu in (("Nova", ("Nova", "parano", "friday", "majordome")), ("Atlas", ("Atlas", "sarcastique", "mark3", "majordome")),
                             ("Pixel", ("Pixel", "nul", "jarvis", "local"))):
            r = serveur._dialoguer(f"passe sur le profil {nom}", source="telegram")
            etat = (prenom.actuel(), personnalites.actuelle(), CONFIG["hud"].get("theme"), CONFIG["voix"]["moteur"])
            v.ok(etat == attendu, f"« passe sur le profil {nom} » : {r['reponse']}", etat)
        v.ok(voix_creees.actuelle() in ("majordome", "orage"), "la voix du dernier profil Qwen est réglée")
        liste = serveur._dialoguer("quels profils as-tu ?", source="telegram")["reponse"]
        v.ok(all(n in liste for n in ("Nova", "Atlas", "Pixel")), "« quels profils as-tu ? »", liste)
        v.ok("Je ne peux pas" in serveur._dialoguer("passe sur le profil Zorglub", source="telegram")["reponse"],
             "un profil inconnu : refus clair")
        sauves = json.loads((RACINE / "config.json").read_text(encoding="utf-8")).get("profils", {})
        v.ok(set(sauves) == {"nova", "atlas", "pixel"}, "les profils sont écrits dans config.json", list(sauves))
        profils_tournoi = sauves
    finally:
        majordome.suivre_moteur = suivre
        (RACINE / "config.json").write_text(config_avant, encoding="utf-8")
        avant = json.loads(config_avant)
        for cle in ("personnage", "voix", "hud"):
            CONFIG[cle] = avant.get(cle, {})
        CONFIG.pop("profils", None)
        CONFIG.pop("profil", None)
        CERVEAU.oublier()
    # les trois profils servent au tournoi : on les garde (seulement eux), le reste de la config est remis
    fichier = json.loads((RACINE / "config.json").read_text(encoding="utf-8"))
    fichier["profils"] = profils_tournoi
    (RACINE / "config.json").write_text(json.dumps(fichier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    CONFIG["profils"] = profils_tournoi
    v.info("les profils Nova, Atlas et Pixel restent dans config.json pour le tournoi")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
