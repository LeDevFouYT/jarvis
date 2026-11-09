"""Test du prénom : python -m jarvis.tests.prenom   (Jarvis arrêté : ce test charge Whisper et Kokoro)
Demande des utilisateurs (vidéo 5) : « on ne peut pas changer le prénom, sinon ça bug ».

1. Sans modèle : variantes du prénom, prénoms refusés, la phrase qui commence par le prénom (et pas « on va »,
   « novembre »…), les commandes sous un autre prénom (« Nova, éteins-toi »), « appelle-toi Nova », la consigne du
   cerveau, l'écriture dans config.json (remise comme avant à la fin).
2. Au micro de test, prénom « Nova » : 20 phrases qui commencent par le prénom -> combien le réveillent ;
   ~5 minutes de conversation sans le prénom (dont des pièges : « on va », « novembre », « nouveau ») -> combien de
   faux réveils. L'audio est livré plus vite que le temps réel (Whisper décide, pas la montre).
Mesures dans workspace/mesures/tournoi.json, clé « prenom »."""
import json
import queue
import sys
import time

import numpy as np

from ._commun import Collecteur, SourceScenario, Verifs, attendre, faux_haut_parleur, phrase_wav

faux_haut_parleur()

from .. import cerveau, commandes, oreilles, prenom  # noqa: E402
from ..config import CONFIG, RACINE  # noqa: E402

NOM = "Nova"
MESURES = RACINE / "workspace" / "mesures" / "tournoi.json"

# (début, question) : le prénom en tête, dit comme on le dit vraiment
APPELS = [
    ("Nova,", "quelle heure est-il ?"), ("Nova,", "ouvre le bloc-notes."), ("Hey Nova,", "dans quel état est la machine ?"),
    ("Nova,", "mets un peu de musique."), ("Dis Nova,", "quel temps fait-il à Lyon ?"), ("Nova,", "range mes téléchargements."),
    ("Nova,", "rappelle-moi d'appeler ma mère à dix-huit heures."), ("Ok Nova,", "baisse le volume."),
    ("Nova,", "montre-moi la Terre."), ("Nova,", "combien vaut le Bitcoin ?"), ("Bonjour Nova,", "tu vas bien ?"),
    ("Nova,", "fais-moi une image d'un chat astronaute."), ("Nova,", "qu'est-ce que tu sais de moi ?"),
    ("Nova,", "note que je dois acheter du pain."), ("Nova,", "passe en mode coach."), ("Nova,", "regarde mon écran."),
    ("Nova,", "écris bonjour à tout le monde."), ("Nova,", "quelle est la date aujourd'hui ?"),
    ("Nova,", "cherche une recette de crêpes."), ("Nova,", "éteins-toi."),
]
# ~5 minutes de conversation ordinaire sans le prénom ; les pièges sont en tête de phrase, là où il se réveillerait
CONVERSATION = [
    "On va manger vers vingt heures, ça te va ?", "Novembre arrive vite cette année.", "Nouveau projet, nouvelle énergie.",
    "Non, va plutôt chercher le pain.", "Nos vacances commencent samedi.", "La Nouvelle-Écosse, c'est au Canada je crois.",
    "Il faut que je rappelle le garagiste demain matin.", "Tu as vu le match hier soir ? C'était serré jusqu'au bout.",
    "La réunion est déplacée à quinze heures, pense à prévenir Thomas.", "J'ai oublié mes clés dans la voiture, encore.",
    "On pourrait repeindre le salon en vert clair, qu'est-ce que tu en penses ?", "Le chat a encore renversé son bol d'eau.",
    "Elle m'a dit qu'elle passerait vers dix-sept heures avec les enfants.", "Je regarde une série coréenne en ce moment.",
    "Ça fait trois jours qu'il pleut sans arrêt.", "Ma sœur déménage à Bordeaux le mois prochain.",
    "Il reste des pâtes d'hier, on les finit ce soir.", "Le colis devait arriver lundi, toujours rien.",
    "J'ai couru cinq kilomètres ce matin, je suis content.", "Ton ordinateur fait un bruit bizarre depuis hier.",
    "On va au cinéma dimanche ou on reste à la maison ?", "Nouvelle mise à jour de Windows, encore un redémarrage.",
    "No problem, je m'en occupe tout à l'heure.", "Novak a gagné le tournoi, incroyable.", "Noé arrive à quelle heure ?",
    "Le boulanger était fermé, j'ai pris des biscottes.", "Il faudrait réserver le restaurant pour l'anniversaire.",
    "Les impôts, c'est avant la fin du mois, n'oublie pas.", "J'ai trouvé une super vidéo sur les volcans.",
    "Le voisin tond sa pelouse à huit heures du matin, sérieusement.", "On n'a plus de lait, ni de café d'ailleurs.",
    "Je crois que la batterie du téléphone est fichue.", "Tu te souviens du nom de ce restaurant italien ?",
    "Mon frère vient manger samedi, il apporte le dessert.", "Le train avait vingt minutes de retard ce matin.",
    "Il fait vraiment froid dans le bureau aujourd'hui.", "J'ai fini le livre, la fin est complètement folle.",
    "On devrait ranger le garage ce week-end.", "La chaudière fait encore des siennes.",
    "Elle a eu son permis du premier coup, je suis fier d'elle.", "Le dentiste a rappelé pour décaler le rendez-vous.",
    "Va voir si le courrier est arrivé, s'il te plaît.", "Novembre, décembre, et après c'est déjà Noël.",
    "Nouveau record de chaleur annoncé pour la semaine prochaine.", "On va finir par être en retard, dépêche-toi.",
    "Les enfants dorment, parle moins fort.", "J'ai réparé le robinet de la cuisine tout seul.",
    "Le match recommence dans dix minutes.", "Tu peux me passer le sel ?", "Bonne nuit, à demain.",
    "Hé, tu as vu l'heure ? On va rater le bus.", "Eh bien, ça c'est une surprise, je ne m'y attendais pas.",
    "Nouvelle-Calédonie ou Réunion, je n'arrive pas à choisir pour les vacances.", "Novice ou pas, il s'en est bien sorti.",
    "Henri passe ce soir récupérer la perceuse.", "Énorme, ce gâteau, il en reste pour demain.",
    "On a reçu une lettre de la banque, il faudrait l'ouvrir.", "Il a neigé en montagne, les pistes ouvrent samedi.",
    "Je n'ai pas compris la fin du film, tu me l'expliques ?", "La machine à laver a fini, tu peux étendre le linge ?",
    "Ce soir c'est pizza, et pas de discussion.", "Mon téléphone ne charge plus, il faut changer le câble.",
    "Tu crois qu'il va faire beau pour le pique-nique ?", "Le chien du voisin aboie depuis une heure.",
    "J'ai rendez-vous chez le coiffeur jeudi à dix heures.", "Elle a appelé pendant que tu étais sous la douche.",
    "On n'a toujours pas rendu les livres à la médiathèque.", "Le chauffage est trop fort, j'ouvre la fenêtre.",
    "Novembre dernier, on était déjà allés là-bas, tu te rappelles ?", "Nos amis arrivent demain vers midi.",
    "Il faut arroser les plantes, elles font la tête.", "Je vais faire un tour, je reviens dans une heure.",
    "La facture d'électricité a encore augmenté.", "Ce jeu vidéo est beaucoup trop dur, j'abandonne.",
    "Tu as pensé à prendre les billets pour le concert ?", "J'ai rêvé que je volais au-dessus de la mer.",
    "Les fraises du marché étaient délicieuses.", "On devrait inviter les voisins un de ces jours.",
    "Hé ho, il y a quelqu'un ?", "Ah non, pas encore une réunion.", "Bon, je crois qu'on a fait le tour.",
    "Allez, au lit, demain on se lève tôt.",
]


class SourceRapide(SourceScenario):
    """Le micro de test, mais sans attendre la montre tant qu'il reste de l'audio : la transcription bloque la boucle
    des oreilles, donc rien ne se perd. File vide : silence au rythme réel."""

    def generateur(self, arret):
        while not arret.is_set():
            try:
                yield self.file.get_nowait()
            except queue.Empty:
                time.sleep(self.BLOC / 16000)
                yield np.zeros(self.BLOC, dtype=np.int16)


def ecrire_mesures(cle: str, valeur):
    MESURES.parent.mkdir(parents=True, exist_ok=True)
    tout = json.loads(MESURES.read_text(encoding="utf-8")) if MESURES.exists() else {}
    tout[cle] = valeur
    MESURES.write_text(json.dumps(tout, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sans_modele(v: Verifs):
    v.ok(prenom.est_jarvis() and "jarvis" in prenom.variantes(), "par défaut : Jarvis, ses graphies habituelles", prenom.actuel())
    var = prenom.variantes(NOM)
    v.ok("nova" in var and "novah" in var and not set(var) & prenom.MOTS_COURANTS,
         "« Nova » : graphies générées, aucune ne tombe sur un mot courant", var)
    v.ok(all(not prenom.valider(x)[0] for x in ("Le", "Oui", "A", "Un prénom beaucoup trop long pour moi", "R2-D2")),
         "prénoms refusés : mot courant, une lettre, trop long, chiffres", {x: prenom.valider(x)[1] for x in ("Le", "Oui", "R2-D2")})
    v.ok(prenom.valider("nova") == (True, "Nova") and prenom.valider("Jean-Luc")[0], "« nova » devient « Nova »")
    v.ok(prenom.sigle("Nova") == "N.O.V.A." and prenom.sigle("Jarvis") == "J.A.R.V.I.S.", "le sigle du HUD", prenom.sigle("Nova"))

    CONFIG["personnage"]["prenom"] = NOM
    cas = {"Nova, quelle heure est-il ?": "quelle heure est-il ?", "Hey Nova ouvre le bloc-notes": "ouvre le bloc-notes",
           "Novah, range mes téléchargements": "range mes téléchargements", "Dis Nova, tu vas bien ?": "tu vas bien ?",
           "Enova, dans quel état est la machine ?": "dans quel état est la machine ?", "Énorme, ce gâteau": None,
           "On va manger": None, "Novembre arrive": None, "Nouveau projet": None, "Non, va chercher le pain": None,
           "Jarvis, quelle heure est-il ?": None}
    v.ok(all(prenom.detacher(t) == r for t, r in cas.items()), "sous « Nova » : la phrase qui commence par lui, et rien d'autre",
         {t: prenom.detacher(t) for t in cas})
    v.ok(oreilles.retirer_reveil("Nova, ouvre le bloc-notes.") == "Ouvre le bloc-notes."
         and oreilles.retirer_reveil("rvis, ouvre le bloc-notes") == "Rvis, ouvre le bloc-notes",
         "après un réveil, le prénom est retiré ; la coupe « …rvis » ne vaut que pour Jarvis")
    attendus = {"Nova, éteins-toi": "extinction", "Jarvis, éteins-toi": "extinction", "Nova, passe en mode coach": "personnalite",
                "appelle-toi Jarvis": "prenom", "Nova, oublie tout": "oublier", "appelle-moi madame": "titre_madame"}
    vus = {t: commandes.analyser(t)[0] for t in attendus}
    v.ok(vus == attendus, "les commandes marchent sous le nouveau prénom (et « Jarvis, … » aussi)", vus)
    v.ok("Vous êtes Nova" in cerveau.personnage() and "Vous êtes Jarvis" not in cerveau.personnage(),
         "la consigne du cerveau porte le prénom")
    CONFIG["personnage"]["prenom"] = "Jarvis"

    for phrase, nom in (("appelle-toi Nova", "Nova"), ("ton nouveau nom est Friday", "Friday"),
                        ("je vais t'appeler Mister Robot", "Mister Robot"), ("redeviens Jarvis", "Jarvis")):
        v.ok(commandes.analyser(phrase) == ("prenom", nom), f"« {phrase} » -> {nom}", commandes.analyser(phrase))
    v.ok(commandes.analyser("appelle-moi monsieur")[0] == "titre_monsieur", "« appelle-moi monsieur » reste le titre")

    fichier = RACINE / "config.json"
    avant = fichier.read_bytes()
    try:
        ok, propre = prenom.definir("nova")
        relu = json.loads(fichier.read_text(encoding="utf-8"))["personnage"]["prenom"]
        v.ok(ok and propre == "Nova" and relu == "Nova" and prenom.actuel() == "Nova", "« appelle-toi Nova » est écrit dans config.json", relu)
        v.ok(prenom.definir("Le") == (False, prenom.valider("Le")[1]) and prenom.actuel() == "Nova", "un prénom refusé laisse l'ancien")
    finally:
        fichier.write_bytes(avant)
        CONFIG["personnage"]["prenom"] = "Jarvis"


def au_micro(v: Verifs) -> dict:
    appels = [phrase_wav(f"prenom_appel_{i:02d}", [(debut, "ff_siwis", "fr-fr"), (q, "ff_siwis", "fr-fr")],
                         silence_avant=0.5, silence_apres=0.1) for i, (debut, q) in enumerate(APPELS)]
    conversation = [phrase_wav(f"prenom_conv_{i:02d}", [(p, "ff_siwis", "fr-fr")], silence_avant=0.3, silence_apres=0.1)
                    for i, p in enumerate(CONVERSATION)]
    oreilles.prechauffer_whisper()
    CONFIG["personnage"]["prenom"] = NOM
    micro, evts, recus = SourceRapide(), Collecteur(), []
    o = oreilles.Oreilles(sur_evenement=evts, sur_texte=lambda t, i: recus.append((t, i["mode"])), source=micro.generateur,
                          jarvis_parle=lambda: False, phrases_dites=lambda: [])
    o.start()
    resultats = {"prenom": NOM}
    try:
        attendre(lambda: o.etat == "veille", 60)
        reveils, details, t0 = 0, [], time.time()
        for (chemin, _), (debut, q) in zip(appels, APPELS):
            recus.clear()
            micro.jouer(chemin)
            micro.silence(1.5)
            arrive = attendre(lambda: recus, 20)
            attendre(lambda: o.etat == "veille" and micro.file.empty(), 10)
            texte = recus[-1][0] if recus else ""
            juste = arrive and NOM.lower() not in texte.lower() and texte.split()[:1] != []
            reveils += bool(juste)
            details.append({"dit": f"{debut} {q}", "recu": texte, "mode": recus[-1][1] if recus else None})
            if not juste:
                entendu = [e.get("texte") for e in evts.de_type("phrase_ignoree")[-1:]]
                v.info(f"raté : « {debut} {q} » -> reçu {recus} ; entendu {entendu}")
        resultats["reveils"] = {"reussis": reveils, "sur": len(APPELS), "duree_s": round(time.time() - t0, 1), "details": details}
        v.ok(reveils >= 18, f"{reveils}/{len(APPELS)} phrases commençant par « {NOM} » le réveillent (au moins 18)")

        recus.clear()
        n_evts = len(evts.evenements)
        t0, parole = time.time(), 0.0
        for chemin, duree in conversation:
            micro.jouer(chemin)
            micro.silence(1.2)
            parole += duree + 1.2
        micro.attendre_vide(900)
        attendre(lambda: o.etat == "veille", 30)
        ignorees = [e["texte"] for e in evts.evenements[n_evts:] if e["type"] == "phrase_ignoree"]
        resultats["faux_reveils"] = {"nombre": len(recus), "conversation_s": round(parole, 1), "phrases": len(CONVERSATION),
                                     "transcrites_ignorees": len(ignorees), "livrees": [t for t, _ in recus],
                                     "traitement_s": round(time.time() - t0, 1)}
        v.info(f"{len(ignorees)} phrases entendues et ignorées sur {len(CONVERSATION)} ({parole / 60:.1f} min de conversation)")
        v.ok(parole >= 300, f"au moins 5 minutes de conversation jouées ({parole / 60:.1f} min)")
        v.ok(not recus, f"{len(recus)} faux réveil en {parole / 60:.1f} min de conversation sans le prénom", [t for t, _ in recus])
    finally:
        o.arreter()
        CONFIG["personnage"]["prenom"] = "Jarvis"
    return resultats


def main() -> int:
    v = Verifs("Le prénom · « appelle-toi Nova »")
    sans_modele(v)
    if "--sans-micro" not in sys.argv:
        resultats = au_micro(v)
        resultats["date"] = time.strftime("%Y-%m-%d %H:%M")
        ecrire_mesures("prenom", resultats)
        v.info(f"mesures écrites dans {MESURES.relative_to(RACINE)}")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
