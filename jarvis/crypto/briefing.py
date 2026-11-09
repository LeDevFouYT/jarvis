"""Le point crypto (consigne 6) : les trois cryptos les plus échangées en euros, ce qui a le plus bougé, l'état du
portefeuille fictif. Chaque chiffre dit passe par le vérificateur (youtube/verification.py) avant d'être prononcé :
la phrase est construite depuis les données, puis relue chiffre par chiffre contre le JSON de faits, et le panneau
de vérification s'affiche dans le HUD.

« Les plus échangées » plutôt que « les plus grosses » : Binance ne donne pas la capitalisation, mais le volume en
euros sur 24 h, lui, est une donnée réelle et vérifiable."""
import re
import time

from . import AVERTISSEMENT, cours

_CONSEIL = re.compile(r"[^.!?]*\b(achetez|vendez|investissez|acheter maintenant|vendre maintenant|je vous conseille|je vous recommande|"
                      r"recommand\w*|conseill\w*|bon moment pour|opportunité d'achat|signal d'achat|signal de vente|il faudrait acheter|"
                      r"il faudrait vendre|devriez)\b[^.!?]*[.!?]?", re.IGNORECASE)


def sans_conseil(texte: str) -> str:
    """Retire d'une description (la vision qui lit un graphique) toute phrase qui ressemble à un conseil."""
    propre = _CONSEIL.sub("", texte or "").strip()
    propre = re.sub(r"\s{2,}", " ", propre)
    return propre or "Je vois un graphique de cours, mais je n'en tire aucune recommandation."


def verifier_vision(description: str, graphique: dict | None = None) -> str:
    """Les chiffres lus par la vision sur un graphique de Jarvis, confrontés aux vraies données de ce graphique.
    Un prix lu qui n'existe pas dans les données est corrigé à voix haute, jamais dit tel quel sans avertissement.
    Les durées (30 jours, 24 heures…) et les dates ne sont pas des prix : elles ne sont pas confrontées."""
    import time as _time
    from ..outils import panneaux
    from ..youtube import verification
    g = graphique if graphique is not None else panneaux.DERNIER_GRAPHIQUE
    if not g or _time.time() - g.get("quand", 0) > 900:
        return description                        # pas de graphique de Jarvis récent : rien à confronter
    faits = [{"id": "F1", "texte": f"{g['nom']} · {g.get('libelle', '')}", "sujet": "graphique",
              "valeurs": {**g["valeurs"], "durees": [1, 4, 5, 7, 12, 24, 30, 100, 365]}}]
    r = verification.verifier(description, faits)
    faux = [e for e in r["ecarts"] if e.get("cite") and not re.search(r"(jours?|heures?|h|ans?|mois)$", e["cite"])]
    if not faux:
        return description
    reel = g["valeurs"]["prix"]
    from .actifs import valeur_dite
    lus = ", ".join(f"« {e['cite']} »" for e in faux[:2])
    return (description.rstrip() + f" Je me corrige : j'ai lu {lus}, ce chiffre n'est pas dans les données du graphique. "
            f"Le cours réel est de {valeur_dite(reel, g.get('unite', 'EUR'))}.")


def point(dernier: dict) -> str:
    from ..outils.crypto import _sens, euros_dits
    from ..outils import portefeuille as outil_portefeuille
    from ..youtube import verification
    t = time.time()
    tous = cours.prix(cours.GRANDES)
    faits = []

    def fait(texte, sujet, **valeurs):
        faits.append({"id": f"F{len(faits) + 1}", "texte": texte, "sujet": sujet, "valeurs": valeurs})

    echangees = sorted(tous.values(), key=lambda x: -x["volume_eur_24h"])[:3]
    for x in echangees:
        fait(f"{cours.nom(x['symbole'])} : {cours.euros(x['prix'])}, {cours.pourcent(x['variation_24h'])} sur 24 h, "
             f"{cours.nombre(x['volume_eur_24h'])} € échangés sur {x['source']}.", f"prix variation {cours.nom(x['symbole'])}",
             prix=x["prix"], variation_abs=abs(x["variation_24h"]), volume=x["volume_eur_24h"])
    bouge = max(tous.values(), key=lambda x: abs(x["variation_24h"]))
    fait(f"Plus fort mouvement sur 24 h : {cours.nom(bouge['symbole'])}, {cours.pourcent(bouge['variation_24h'])}.",
         f"mouvement {cours.nom(bouge['symbole'])}", variation_abs=abs(bouge["variation_24h"]), prix=bouge["prix"])

    morceaux = [f"{cours.nom_avec_article(x['symbole'])} à {euros_dits(x['prix'])}, {_sens(x['variation_24h'])}" for x in echangees]
    phrase = "Le point crypto. Les plus échangées en euros : " + " ; ".join(morceaux) + ". "
    if bouge["symbole"] not in {x["symbole"] for x in echangees}:
        phrase += f"Le plus fort mouvement : {cours.nom(bouge['symbole'])}, {_sens(bouge['variation_24h'])}. "
    else:
        phrase += f"Le plus fort mouvement est pour {cours.nom_avec_article(bouge['symbole'])}. "
    phrase_portefeuille = outil_portefeuille.valeur()
    faits += [{**f, "id": f"F{len(faits) + i + 1}"} for i, f in enumerate(outil_portefeuille.faits())]
    phrase += phrase_portefeuille.split(" Vous avez ")[0]

    resultat = verification.verifier(phrase, faits)
    resultat["phrases_jugees"] = []
    verification.panneau(resultat, faits)
    from ..outils import panneaux
    panneaux.barres(f"Point crypto · variation 24 h · {echangees[0]['source']}",
                    [{"nom": cours.nom(x["symbole"]), "valeur": round(x["variation_24h"], 2), "detail": cours.euros(x["prix"]),
                      "brille": x in echangees or x is bouge} for x in sorted(tous.values(), key=lambda x: -x["variation_24h"])], unite="%")
    dernier.update(faits=faits, quand=time.time(), verification=resultat, duree_s=round(time.time() - t, 2))
    if resultat["ecarts"]:
        # un chiffre absent des faits n'est jamais dit : on retire la phrase qui le porte
        for e in resultat["ecarts"]:
            phrase = phrase.replace(e["phrase"], "")
    return phrase.strip()


def conseil_refuse(texte: str) -> bool:
    """Une réponse respecte le garde-fou si elle ne recommande rien (utilisé par le test)."""
    return not re.search(r"\b(achetez|vendez|investissez|je vous conseille d'|je vous recommande d'|c'est le moment d'acheter|"
                         r"foncez|allez-y|n'hésitez pas à acheter)\b", texte or "", re.IGNORECASE)


__all__ = ["point", "sans_conseil", "conseil_refuse", "AVERTISSEMENT"]
