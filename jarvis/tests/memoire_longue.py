"""Test du pouvoir 02, mémoire longue : python -m jarvis.tests.memoire_longue
Dans un dossier temporaire (la vraie mémoire n'est jamais touchée) : souvenirs datés avec leur source, pas de doublon,
seuls les souvenirs pertinents accompagnent une question, « oublie que » retire le bon, les commandes vocales,
la proposition de fin de session par le vrai cerveau (stables gardés, passagers écartés), la constellation."""
import sys
import tempfile
from pathlib import Path

from ._commun import Verifs, faux_haut_parleur

faux_haut_parleur()

from .. import commandes, memoire  # noqa: E402
from ..cerveau import MODELE, OLLAMA, question_augmentee  # noqa: E402


def main() -> int:
    v = Verifs("Pouvoir 02 · mémoire longue")
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_memoire_"))
    memoire.FICHIER, memoire.VECTEURS, memoire.ANCIEN_RESUME = dossier / "souvenirs.json", dossier / "vecteurs.json", dossier / "resume.txt"
    memoire._vecteurs_cache = None

    for fait in ["Préfère le thé vert au café", "Son frère s'appelle Thomas", "Monte ses vidéos avec Filmora",
                 "Joue à des jeux de course le soir", "Est allergique aux arachides", "Apprend la guitare"]:
        memoire.ajouter(fait, "test", attendre_themes=True)
    v.info("mots-clés d'usage : " + " ; ".join(f"{s['fait']} -> {', '.join(s.get('themes', []))}" for s in memoire.lister()))
    souvenirs = memoire.lister()
    v.ok(len(souvenirs) == 6, "six souvenirs écrits dans souvenirs.json", len(souvenirs))
    v.ok(all(s["date"] and s["source"] == "test" and s["id"] for s in souvenirs), "chaque souvenir a sa date, sa source et son identifiant")
    memoire.ajouter("Préfère le thé vert au café", "répété")
    v.ok(len(memoire.lister()) == 6, "un souvenir répété ne fait pas de doublon", len(memoire.lister()))

    memoire.ajouter("Est végétarien", "test", attendre_themes=True)
    cas = [("Qu'est-ce que je pourrais boire ce matin ?", "thé"), ("Comment s'appelle mon frère déjà ?", "Thomas"),
           ("Quel logiciel j'utilise pour le montage ?", "Filmora"), ("Propose-moi une idée de dîner rapide pour ce soir", "végétarien"),
           ("Je peux manger ce snack aux cacahuètes ?", "arachides"), ("Combien font 17 fois 23 ?", None),
           ("Quelle heure est-il ?", None), ("Quel temps fera-t-il demain ?", None)]
    for question, attendu in cas:
        p = memoire.pertinents(question)
        faits = [s["fait"] for s in p]
        if attendu:
            v.ok(any(attendu in f for f in faits) and len(p) <= 3, f"« {question} » -> le souvenir utile, et au plus deux autres proches", faits)
        else:
            v.ok(not p, f"« {question} » -> aucun souvenir envoyé au cerveau", faits)
    methode = memoire.pertinents("Comment s'appelle mon frère ?")
    v.info(f"méthode : {methode[0]['methode'] if methode else '?'}, score {methode[0]['score'] if methode else '?'}")
    from ..cerveau import personnage
    augmentee = question_augmentee("Comment s'appelle mon frère déjà ?", "fr", memoire.pertinents("Comment s'appelle mon frère déjà ?"))
    v.ok("[Souvenirs" in augmentee and "Thomas" in augmentee and "Thomas" not in personnage(),
         "les souvenirs voyagent avec la question, jamais dans la consigne (qui reste en cache)")

    v.ok(commandes.analyser("Jarvis, retiens que ma sœur s'appelle Léa")[0] == "retenir", "« retiens que… » est une commande")
    v.ok(commandes.analyser("oublie que je joue à la guitare") == ("oublier_souvenir", "je joue à la guitare"), "« oublie que… » est une commande")
    v.ok(commandes.analyser("qu'est-ce que tu sais de moi ?")[0] == "souvenirs_liste", "« qu'est-ce que tu sais de moi » est une commande")
    v.ok(commandes.analyser("oublie tout")[0] == "oublier", "« oublie tout » reste l'effacement de la conversation")

    tournures = {"Est végétarien": "vous êtes végétarien", "Son frère s'appelle Thomas": "votre frère s'appelle Thomas",
                 "Monte ses vidéos avec Filmora": "vous montez vos vidéos avec Filmora",
                 "Préfère le thé vert au café": "vous préférez le thé vert au café", "S'appelle Camille": "vous vous appelez Camille",
                 "Kinésithérapeute de métier": "« Kinésithérapeute de métier »"}
    rates = {f: memoire.pour_la_personne(f) for f, attendu in tournures.items() if memoire.pour_la_personne(f) != attendu}
    v.ok(not rates, "à l'oral, un souvenir est tourné vers la personne (« vous êtes végétarien »), cité s'il n'est pas conjugable", rates)
    v.ok(memoire.pour_la_personne("Apprend la guitare", tu=True) == "tu apprends la guitare", "et tutoyé quand Jarvis tutoie")

    avant_oubli = len(memoire.lister())
    retires = memoire.oublier("que j'apprends la guitare")
    v.ok([s["fait"] for s in retires] == ["Apprend la guitare"], "« oublie que j'apprends la guitare » retire ce souvenir-là seulement",
         [s["fait"] for s in retires])
    v.ok(len(memoire.lister()) == avant_oubli - 1, "un souvenir de moins, les autres intacts")
    v.ok(memoire.oublier("mon numéro de sécurité sociale") == [], "rien n'est retiré quand rien ne correspond")

    # la fin de session, avec le vrai cerveau
    historique = [
        {"role": "user", "content": "Jarvis, quelle heure est-il ?"}, {"role": "assistant", "content": "Il est 21 h 12."},
        {"role": "user", "content": "Je prépare une vidéo sur mon assistant vocal, je la publie sur ma chaîne tous les dimanches."},
        {"role": "assistant", "content": "Excellent projet."},
        {"role": "user", "content": "Au fait, je suis kinésithérapeute de métier, pense à ça quand je parle de mon travail."},
        {"role": "assistant", "content": "C'est noté."},
        {"role": "user", "content": "Combien font 17 fois 23 ?"}, {"role": "assistant", "content": "391."},
        {"role": "user", "content": "Là je suis fatigué ce soir."}, {"role": "assistant", "content": "Reposez-vous."},
    ]
    resultat = memoire.proposer(historique, OLLAMA, MODELE)
    gardes = [s["fait"] for s in resultat["gardes"]]
    v.info(f"proposés : {resultat['proposes']}")
    v.ok(any("kiné" in f.lower() for f in gardes), "fin de session : le métier (kinésithérapeute) est gardé, stable", gardes)
    v.ok(not any("fatigu" in f.lower() or "heure" in f.lower() or "391" in f for f in gardes),
         "fin de session : la fatigue du soir, l'heure et le calcul sont écartés", resultat["ecartes"])

    c = memoire.constellation(allumes=[memoire.lister()[0]["id"]])
    v.ok(len(c["etoiles"]) == len(memoire.lister()) and all(len(e["position"]) == 3 for e in c["etoiles"]),
         "constellation : une étoile en 3D par souvenir", len(c["etoiles"]))
    v.ok(c["allumes"] and isinstance(c["liens"], list), "constellation : étoiles allumées et liens entre voisins", f"{len(c['liens'])} liens")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
