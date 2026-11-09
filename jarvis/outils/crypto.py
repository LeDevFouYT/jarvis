"""Outil crypto (vidéo 4, consignes 1, 2 et 6) : le cours d'une crypto en euros, ce qui monte le plus, le point crypto.

Des faits, jamais un conseil : l'outil dit le prix, la variation et la source, rien sur ce qu'il faudrait faire.
La phrase est dite telle quelle (DIRECT) : le cerveau ne peut pas arrondir un prix de travers. Chaque chiffre dit est
aussi rangé dans `faits()`, que le serveur confronte à la réponse (youtube/verification.py)."""
import time

from ..crypto import cours

NOM = "crypto"
DESCRIPTION = ("Cours des cryptomonnaies en euros, en direct (Binance, Kraken en repli) : prix, variation sur 24 h et "
               "graphique géant dans l'interface. « cours » : une crypto (bitcoin, ethereum, solana, xrp…), avec la "
               "période du graphique (24h, 7j, 30j). « comparer » : plusieurs cryptos côte à côte, un graphique chacune. « classement » : ce qui monte ou baisse le plus. « point » : le point "
               "crypto complet (grandes cryptos, plus forts mouvements, portefeuille fictif). Des faits, jamais un conseil.")
PARAMETRES = {
    "action": {"type": "string", "enum": ["cours", "comparer", "classement", "point"], "description": "Ce qui est demandé"},
    "crypto": {"type": "string", "description": "La crypto telle que dite (bitcoin, ethereum, solana…), pour « cours »"},
    "cryptos": {"type": "array", "items": {"type": "string"},
                "description": "Pour « comparer » : plusieurs cryptos, un graphique chacune (vide = les quatre plus échangées)"},
    "periode": {"type": "string", "enum": ["24h", "7j", "30j"], "description": "Période du graphique, 24h par défaut"},
}
REQUIS = ["action"]
DIRECT = True

dernier: dict = {"faits": []}


def faits() -> list[dict]:
    return dernier.get("faits", [])


def _fait(faits_: list, texte: str, sujet: str, **valeurs):
    faits_.append({"id": f"F{len(faits_) + 1}", "texte": texte, "sujet": sujet, "valeurs": valeurs})


def _sens(variation: float) -> str:
    if abs(variation) < 0.05:
        return "stable"
    return f"en {'hausse' if variation > 0 else 'baisse'} de {cours.pourcent(variation, signe=False)}"


def euros_dits(x: float) -> str:
    """« 72 655 euros » : la voix lit « € » de travers (« é-ro »)."""
    return cours.euros(x).replace(" €", " euros" if x >= 2 else " euro")


def _cours(symbole: str, periode: str) -> str:
    p = cours.prix(symbole)[symbole]
    intervalle, n, libelle = cours.PERIODES[periode]
    try:
        serie = cours.bougies(symbole, intervalle, n)
    except cours.Indisponible:
        serie = []
    faits_ = []
    nom = cours.nom_avec_article(symbole, majuscule=True)
    _fait(faits_, f"{nom} vaut {cours.euros(p['prix'])} (source {p['source']}).", f"prix {cours.nom(symbole)}",
          prix=p["prix"])
    _fait(faits_, f"Variation {p['periode']} : {cours.pourcent(p['variation_24h'])}.", f"variation {cours.nom(symbole)}",
          variation=p["variation_24h"], variation_abs=abs(p["variation_24h"]), arrondi=round(abs(p["variation_24h"]), 1))
    phrase = f"{nom} vaut {euros_dits(p['prix'])}, {_sens(p['variation_24h'])} {'sur 24 heures' if p['periode'] == '24 h' else p['periode']}."
    variation_periode = None
    if periode != "24h" and len(serie) >= 2:
        variation_periode = (p["prix"] / serie[0]["o"] - 1) * 100
        _fait(faits_, f"Variation sur {libelle} : {cours.pourcent(variation_periode)}.", f"variation {libelle}",
              variation=variation_periode, variation_abs=abs(variation_periode))
        phrase += f" Sur {libelle}, il est {_sens(variation_periode)}."
    dernier.update(faits=faits_, quand=time.time(), symbole=symbole, periode=periode)
    from . import panneaux
    if hasattr(panneaux, "cours"):
        panneaux.cours(symbole, cours.nom(symbole), periode, libelle, p, serie, variation_periode)
    return phrase


def _comparer(symboles: list[str], periode: str) -> str:
    """Plusieurs graphiques côte à côte (2 à 6) : chaque crypto avec son prix, sa variation et sa courbe."""
    from concurrent.futures import ThreadPoolExecutor
    if len(symboles) < 2:
        p = cours.prix(cours.GRANDES)
        symboles = [x["symbole"] for x in sorted(p.values(), key=lambda x: -x["volume_eur_24h"])[:4]]
    symboles = symboles[:6]
    intervalle, n, libelle = cours.PERIODES[periode]
    prix = cours.prix(symboles)
    with ThreadPoolExecutor(max_workers=len(symboles)) as fils:        # une requête par crypto, en même temps
        series = dict(zip(symboles, fils.map(lambda s: cours.bougies(s, intervalle, n), symboles)))
    faits_, graphiques = [], []
    for s in symboles:
        p, serie = prix[s], series[s]
        variation = p["variation_24h"] if periode == "24h" or len(serie) < 2 else (p["prix"] / serie[0]["o"] - 1) * 100
        _fait(faits_, f"{cours.nom(s)} : {cours.euros(p['prix'])}, {cours.pourcent(variation)} sur {libelle}.", f"variation {cours.nom(s)}",
              prix=p["prix"], variation=variation, variation_abs=abs(variation))
        graphiques.append({"symbole": s, "nom": cours.nom(s), "prix": p, "serie": serie, "variation": variation})
    dernier.update(faits=faits_, quand=time.time(), symboles=symboles, periode=periode)
    from . import panneaux
    panneaux.multicours(periode, libelle, graphiques)
    tri = sorted(graphiques, key=lambda g: -g["variation"])
    morceaux = [f"{cours.nom_avec_article(g['symbole'])} {_sens(g['variation'])}" for g in graphiques]
    phrase = f"Sur {libelle} : " + ", ".join(morceaux[:-1]) + f" et {morceaux[-1]}."
    if len(graphiques) > 2:
        phrase += f" Le mieux : {cours.nom_avec_article(tri[0]['symbole'])} ; le moins bien : {cours.nom_avec_article(tri[-1]['symbole'])}."
    return phrase


def _classement() -> str:
    liste = cours.classement()
    if not liste:
        return "Je n'ai reçu aucun cours."
    faits_ = []
    for x in liste:
        _fait(faits_, f"{cours.nom(x['symbole'])} : {cours.pourcent(x['variation_24h'])} ({x['periode']}), {cours.euros(x['prix'])}.",
              f"variation {cours.nom(x['symbole'])}", variation=x["variation_24h"], variation_abs=abs(x["variation_24h"]), prix=x["prix"])
    dernier.update(faits=faits_, quand=time.time())
    haut, bas = liste[:2], liste[-1]
    periode = "sur 24 heures" if liste[0]["periode"] == "24 h" else liste[0]["periode"]
    if haut[0]["variation_24h"] <= 0:
        phrase = (f"Tout baisse {periode}. Ce qui résiste le mieux : {cours.nom(haut[0]['symbole'])}, "
                  f"{_sens(haut[0]['variation_24h'])}.")
    else:
        phrase = f"Ce qui monte le plus {periode} : {cours.nom(haut[0]['symbole'])}, {_sens(haut[0]['variation_24h'])}"
        if haut[1]["variation_24h"] > 0:
            phrase += f", puis {cours.nom(haut[1]['symbole'])}, {_sens(haut[1]['variation_24h'])}"
        phrase += "."
    if bas["variation_24h"] < 0:
        phrase += f" Ce qui baisse le plus : {cours.nom(bas['symbole'])}, {_sens(bas['variation_24h'])}."
    from . import panneaux
    panneaux.barres(f"Cryptos · variation {liste[0]['periode']} · {liste[0]['source']}",
                    [{"nom": cours.nom(x["symbole"]), "valeur": round(x["variation_24h"], 2),
                      "detail": cours.euros(x["prix"]), "brille": i < 2} for i, x in enumerate(liste)], unite="%")
    return phrase


def executer(action: str = "cours", crypto: str = "", periode: str = "", cryptos=None) -> str:
    try:
        periode_ok = periode if periode in cours.PERIODES else cours.periode_depuis(periode)
        if action == "comparer":
            if isinstance(cryptos, str):
                cryptos = [cryptos]
            symboles = []
            for c in (cryptos or []) + ([crypto] if crypto else []):
                trouves = [c.upper()] if str(c).upper() in cours.CRYPTOS else cours.reconnaitre_tous(str(c))
                symboles += [s for s in trouves if s not in symboles]
            return _comparer(symboles, periode_ok)
        if action == "classement":
            return _classement()
        if action == "point":
            from ..crypto import briefing
            return briefing.point(dernier)
        symbole = cours.reconnaitre(crypto) or (crypto or "").upper().strip()
        if symbole not in cours.CRYPTOS:
            return f"Je ne connais pas la crypto « {crypto} ». Je suis le Bitcoin, l'Ethereum, Solana, XRP et une quinzaine d'autres."
        return _cours(symbole, periode if periode in cours.PERIODES else cours.periode_depuis(periode))
    except cours.Indisponible:
        return "Ni Binance ni Kraken ne répondent. Je n'ai aucun cours fiable à vous donner."
