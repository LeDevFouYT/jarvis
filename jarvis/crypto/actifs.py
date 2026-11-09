"""Une seule porte pour tout ce qui a un cours : les cryptos (cours.py) et la bourse (bourse.py).

Le portefeuille fictif et les alertes passent par ici : « achète pour 500 € d'Apple » marche comme pour le Bitcoin,
au prix réel converti en euros (taux BCE), avec les mêmes 0,1 % de frais. Un indice (CAC 40…) se suit et déclenche des
alertes, mais ne s'achète pas : ce n'est pas un titre."""
from . import bourse, cours

MOTS_UNITES = {"EUR": ("euro", "euros"), "USD": ("dollar", "dollars"), "GBP": ("livre", "livres"), "JPY": ("yen", "yens"),
               "pts": ("point", "points"), "GBp": ("penny", "pence")}


def est_crypto(s: str) -> bool:
    return s in cours.CRYPTOS


def est_bourse(s: str) -> bool:
    return s in bourse.ACTIFS


def reconnaitre(texte: str) -> str | None:
    """La crypto ou l'actif de bourse nommé ; s'il y a les deux, celui dont le nom dit est le plus long."""
    c, b = cours.reconnaitre(texte), bourse.reconnaitre(texte)
    if c and b:
        n = cours._normaliser(texte)
        lc = max((len(m) for m in cours.CRYPTOS[c][2] + [c.lower()] if f" {m} " in n), default=0)
        lb = max((len(m) for m in bourse.ACTIFS[b][3] if f" {m} " in bourse._normaliser(texte)), default=0)
        return c if lc >= lb else b
    return c or b


def reconnaitre_tous(texte: str) -> list[str]:
    n = cours._normaliser(texte)
    tous = cours.reconnaitre_tous(texte) + bourse.reconnaitre_tous(texte)
    # dans l'ordre où ils sont dits
    def position(s):
        mots = cours.CRYPTOS[s][2] + [s.lower()] if est_crypto(s) else bourse.ACTIFS[s][3]
        return min((n.find(f" {m} ") for m in mots if f" {m} " in n), default=10 ** 6)
    return sorted(dict.fromkeys(tous), key=position)


def nom(s: str) -> str:
    return cours.nom(s) if est_crypto(s) else bourse.nom(s)


def nom_avec_article(s: str, majuscule: bool = False) -> str:
    return cours.nom_avec_article(s, majuscule) if est_crypto(s) else bourse.nom_avec_article(s, majuscule)


def achetable(s: str) -> bool:
    return est_crypto(s) or (est_bourse(s) and bourse.genre(s) != "indice")


def cotation(s: str) -> dict:
    """{prix (dans son unité), unite, variation (24 h pour une crypto, la journée pour la bourse), prix_eur, source, ouvert}."""
    if est_crypto(s):
        p = cours.prix(s)[s]
        return {"prix": p["prix"], "unite": "EUR", "variation": p["variation_24h"], "prix_eur": p["prix"], "source": p["source"],
                "ouvert": True, "quand": p["quand"]}
    c = bourse.cotation(s)
    return {"prix": c["prix"], "unite": c["unite"], "variation": c["variation"], "prix_eur": c["prix_eur"], "source": c["source"],
            "ouvert": c["ouvert"], "quand": c["quand"]}


def prix_natif(symboles: list[str]) -> dict[str, float]:
    cryptos = [s for s in symboles if est_crypto(s)]
    sortie = {s: x["prix"] for s, x in cours.prix(cryptos).items()} if cryptos else {}
    for s in symboles:
        if est_bourse(s):
            sortie[s] = bourse.cotation(s)["prix"]
    return sortie


def prix_eur(symboles: list[str]) -> dict[str, float]:
    cryptos = [s for s in symboles if est_crypto(s)]
    sortie = {s: x["prix"] for s, x in cours.prix(cryptos).items()} if cryptos else {}
    sortie.update(bourse.prix_eur([s for s in symboles if est_bourse(s)]))
    return sortie


def unite(s: str) -> str:
    return "EUR" if est_crypto(s) else bourse.cotation(s)["unite"]


def variation(s: str, fenetre_s: int, prix_actuel: float | None = None) -> float:
    """En % : sur une heure (bougies d'une minute pour une crypto, de 5 minutes pour la bourse) ou sur 24 h / la journée."""
    if est_crypto(s):
        if fenetre_s > 3600:
            return cours.prix(s)[s]["variation_24h"]
        b = cours.bougies(s, "1m", 61)
        return ((prix_actuel if prix_actuel is not None else b[-1]["c"]) / b[0]["o"] - 1) * 100
    c = bourse.cotation(s)
    if fenetre_s > 3600 or len(c["bougies_jour"]) < 13:
        return c["variation"]
    b = c["bougies_jour"]
    return ((prix_actuel if prix_actuel is not None else c["prix"]) / b[-13]["c"] - 1) * 100


def mot_unite(u: str, x: float) -> str:
    un, plusieurs = MOTS_UNITES.get(u, (u, u))
    return plusieurs if abs(x) >= 2 else un


def valeur_dite(x: float, u: str) -> str:
    """« 7 957 points », « 343,46 dollars », « 72 655 euros », « 1,16 euro »."""
    texte = cours.euros(x).replace(" €", "") if u != "pts" else cours.nombre(x)
    return f"{texte} {mot_unite(u, x)}"


def valeur_ecrite(x: float, u: str) -> str:
    symbole = {"EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥", "pts": "pts"}.get(u, u)
    texte = cours.euros(x).replace(" €", "") if u != "pts" else cours.nombre(x)
    return f"{texte} {symbole}"
