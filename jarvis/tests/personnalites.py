"""Test du pouvoir 06, personnalités : python -m jarvis.tests.personnalites
Les trois personnalités répondent aux mêmes questions avec le vrai cerveau : les mêmes outils sont appelés, seul le
ton change. Le ton est jugé deux fois : par des marques simples (le coach tutoie, le majordome vouvoie) et par le
cerveau lui-même, qui doit reconnaître, sans savoir laquelle a parlé, chaque personnalité dans sa réponse.
La commande vocale « passe en mode coach » change de personnalité ; la config d'origine est remise à la fin."""
import json
import re
import sys

from ._commun import Verifs, faux_haut_parleur

faux_haut_parleur()

from .. import personnalites, serveur  # noqa: E402
from ..cerveau import CERVEAU  # noqa: E402
from ..config import RACINE  # noqa: E402

QUESTION_OUTIL = "Combien de mémoire vidéo est utilisée en ce moment ?"
QUESTION_TON = "Donne-moi un conseil pour mieux dormir."
TUTOIE = re.compile(r"\b(tu|te|toi|ton|ta|tes)\b|\bt'|\b\w+-toi\b", re.IGNORECASE)
VOUVOIE = re.compile(r"\b(vous|votre|vos)\b|\b\w+-vous\b|\b(?!chez\b|nez\b|assez\b)\w{3,}ez\b", re.IGNORECASE)
JUGE = ("On te donne une réponse d'assistant vocal. Dis quel ton elle a, en un seul mot parmi : majordome (courtois, vouvoie, "
        "sobre), sarcastique (ironique, pique moqueuse), coach (tutoie, énergique, encourageant). Réponds uniquement par le mot.")


def main() -> int:
    v = Verifs("Pouvoir 06 · personnalités")
    config_avant = (RACINE / "config.json").read_text(encoding="utf-8")
    serveur._brancher_evenements()
    CERVEAU.charger()
    resultats = {}
    try:
        for nom in ("majordome", "sarcastique", "coach"):
            personnalites.definir(nom)
            CERVEAU.oublier()
            resultats[nom] = [serveur._dialoguer(q, source="telegram") for q in (QUESTION_OUTIL, QUESTION_TON)]
            for q, r in zip((QUESTION_OUTIL, QUESTION_TON), resultats[nom]):
                v.info(f"{nom:<11} « {q} » -> outils {[o['outil'] for o in r['outils']]} : {r['reponse']}")
        outils_par = {n: [o["outil"] for o in rs[0]["outils"]] for n, rs in resultats.items()}
        v.ok(all("etat_machine" in o for o in outils_par.values()), "les trois personnalités appellent le même outil (etat_machine)", outils_par)
        v.ok(all(re.search(r"go|giga", rs[0]["reponse"], re.IGNORECASE) for rs in resultats.values()), "et donnent la mesure")
        coach = " ".join(r["reponse"] for r in resultats["coach"])
        majordome = " ".join(r["reponse"] for r in resultats["majordome"])
        v.ok(TUTOIE.search(coach) or re.search(r"\b(coupe|évite|essaie|pense|fais|mets|prends|garde)\b", coach, re.IGNORECASE),
             "le coach tutoie", coach)
        v.ok(VOUVOIE.search(majordome) and not TUTOIE.search(majordome), "le majordome vouvoie", majordome)
        v.ok(len({rs[1]["reponse"] for rs in resultats.values()}) == 3, "trois réponses différentes au même conseil")

        juges = {}
        for nom, rs in resultats.items():
            juges[nom] = CERVEAU.generer(JUGE, rs[1]["reponse"]).strip().lower().strip(".« »")
        v.info(f"le cerveau, à l'aveugle : {juges}")
        v.ok(sum(1 for n, j in juges.items() if n in j) >= 2, "à l'aveugle, le cerveau reconnaît au moins deux tons sur trois", juges)
        v.ok("sarcastique" in juges["sarcastique"], "le ton sarcastique est reconnu", resultats["sarcastique"][1]["reponse"])

        consignes = {n: serveur.module_cerveau.personnage(n) for n in personnalites.PERSONNALITES}
        regles = {c.split("Vos réponses sont dites")[1].split("Nous sommes le")[0] for c in consignes.values()}
        v.ok(len(regles) == 1, "consignes : règles et outils identiques, seuls le ton et son rappel diffèrent")

        # vu en direct le 16/09 : « j'ai la flemme de monter ma vidéo » -> « on la monte demain, pas de stress »
        personnalites.definir("coach")
        CERVEAU.oublier()
        flemme = serveur._dialoguer("J'ai la flemme de monter ma vidéo ce soir", source="telegram")["reponse"]
        v.ok(not re.search(r"\b(demain|plus tard|pas de stress|repose[- ]toi|une autre fois)\b", flemme, re.IGNORECASE)
             and re.search(r"\b(ouvre|lance|commence|monte|fais|prends|mets|attaque|juste)\b", flemme, re.IGNORECASE),
             "le coach face à la flemme : une petite action tout de suite, jamais « demain »", flemme)
        personnalites.definir("majordome")
        r = serveur._dialoguer("Jarvis, passe en mode coach", source="telegram")
        v.ok(r["commande"] == "personnalite" and personnalites.actuelle() == "coach", "« passe en mode coach » à la voix", r["reponse"])
        serveur._dialoguer("mode sarcastique", source="telegram")
        v.ok(personnalites.actuelle() == "sarcastique", "« mode sarcastique »")
        v.ok(json.loads((RACINE / "config.json").read_text(encoding="utf-8"))["personnage"]["personnalite"] == "sarcastique",
             "la personnalité est enregistrée dans config.json")
    finally:
        (RACINE / "config.json").write_text(config_avant, encoding="utf-8")
        personnalites.CONFIG["personnage"]["personnalite"] = json.loads(config_avant).get("personnage", {}).get("personnalite", "majordome")
        CERVEAU.oublier()
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
