"""Les cours des cryptos en euros, depuis des API publiques sans clé (consigne 1).

Source : api.binance.com (paires EUR), Kraken (api.kraken.com) en repli si Binance ne répond pas. Rien que des GET
publics : aucune clé, aucun compte, aucun ordre. Chaque requête qui part compte dans les sorties Internet du HUD,
et un cache court (20 s pour les prix, 1 à 10 min pour les bougies) évite de marteler les sources.

Une bougie : {"t": ouverture en secondes, "o", "h", "l", "c" (euros), "v" (volume)}."""
import logging
import re
import threading
import time
import unicodedata

import requests

from .. import compteur

journal = logging.getLogger("crypto")
DELAI = 8
BINANCE = "https://api.binance.com/api/v3"
KRAKEN = "https://api.kraken.com/0/public"

# symbole -> (nom dit, article, mots reconnus à l'oral, après normalisation : minuscules sans accents)
CRYPTOS = {
    "BTC": ("Bitcoin", "le", ["bitcoin", "bitcoins", "bit coin", "bitcoine", "btc", "bitcoïn"]),
    "ETH": ("Ethereum", "l'", ["ethereum", "etherium", "etereum", "ethereom", "etherum", "ether", "eth"]),
    "SOL": ("Solana", "le", ["solana", "solanas", "sol"]),
    "XRP": ("XRP", "le", ["xrp", "ripple", "x r p", "ixe air pe"]),
    "BNB": ("BNB", "le", ["bnb", "binance coin", "b n b"]),
    "ADA": ("Cardano", "le", ["cardano", "ada"]),
    "DOGE": ("Dogecoin", "le", ["dogecoin", "doge coin", "doge", "dodgecoin"]),
    "TRX": ("Tron", "le", ["tron", "trx"]),
    "AVAX": ("Avalanche", "l'", ["avalanche", "avax"]),
    "LINK": ("Chainlink", "le", ["chainlink", "chain link"]),
    "DOT": ("Polkadot", "le", ["polkadot", "polka dot"]),
    "LTC": ("Litecoin", "le", ["litecoin", "lite coin", "ltc"]),
    "SUI": ("Sui", "le", ["sui"]),
    "XLM": ("Stellar", "le", ["stellar", "xlm"]),
    "BCH": ("Bitcoin Cash", "le", ["bitcoin cash", "bch"]),
    "SHIB": ("Shiba Inu", "le", ["shiba inu", "shiba", "shib"]),
    "PEPE": ("Pepe", "le", ["pepe"]),
    "NEAR": ("Near", "le", ["near protocol"]),
    "ATOM": ("Cosmos", "le", ["cosmos", "atom"]),
    "APT": ("Aptos", "l'", ["aptos"]),
}
GRANDES = ["BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX", "XLM", "SUI", "BCH", "LTC", "DOT"]
_KRAKEN_NOM = {"BTC": "XBT", "DOGE": "XDG"}
_KRAKEN_INTERVALLE = {"1m": 1, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
SECONDES = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
TTL_PRIX = 20
TTL_BOUGIES = {"1m": 25, "15m": 60, "1h": 120, "4h": 300, "1d": 600}

_cache: dict = {}
_verrou = threading.Lock()
statistiques = {"binance": 0, "kraken": 0, "cache": 0, "replis": 0, "ms": {"binance": [], "kraken": []}}


class Indisponible(Exception):
    """Ni Binance ni Kraken n'ont répondu."""


def _normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFD", (texte or "").lower().replace("’", "'"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"[^a-z0-9]+", " ", t).strip() + " "


def reconnaitre(texte: str) -> str | None:
    """« l'éther » -> ETH ; « bitcoin cash » -> BCH (le nom le plus long gagne) ; rien de connu -> None."""
    n = _normaliser(texte)
    meilleur, longueur = None, 0
    for symbole, (_, _, mots) in CRYPTOS.items():
        for mot in mots + [symbole.lower()]:
            if f" {mot} " in n and len(mot) > longueur:
                meilleur, longueur = symbole, len(mot)
    return meilleur


def reconnaitre_tous(texte: str) -> list[str]:
    """« le Bitcoin, l'Ethereum et le Solana » -> [BTC, ETH, SOL], dans l'ordre dit. « bitcoin cash » ne compte pas
    aussi pour « bitcoin » : un nom plus long qui recouvre un plus court l'emporte."""
    n = _normaliser(texte)
    trouves = []                                   # (début, fin, symbole)
    for symbole, (_, _, mots) in CRYPTOS.items():
        for mot in mots + [symbole.lower()]:
            cible, depart = f" {mot} ", 0
            while (i := n.find(cible, depart)) >= 0:
                trouves.append((i, i + len(cible), symbole))
                depart = i + 1
    trouves.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    gardes, fin = [], -1
    for debut, f, s in trouves:
        if debut + 1 >= fin:                       # ne recouvre pas le nom précédent
            gardes.append(s)
            fin = f
    return list(dict.fromkeys(gardes))


def nom(symbole: str) -> str:
    return CRYPTOS.get(symbole, (symbole,))[0]


def nom_avec_article(symbole: str, majuscule: bool = False) -> str:
    n, article, _ = CRYPTOS.get(symbole, (symbole, "le", []))
    texte = f"l'{n}" if article == "l'" else f"le {n}"
    return texte[:1].upper() + texte[1:] if majuscule else texte


# --- les nombres, tels que Jarvis les dit et que la vérification sait relire -------------------------------------
def nombre(x: float, decimales: int = 0) -> str:
    """72655.05 -> « 72 655 » ; 2,14 avec decimales=2 (la forme que la vérification sait relire)."""
    if decimales == 0:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def euros(x: float) -> str:
    """Le prix d'une crypto, à la précision qui a du sens : 72 655 € ; 2 147 € ; 92,53 € ; 0,2003 € ; 0,00000612 €."""
    if x >= 1000:
        return f"{nombre(x)} €"
    if x >= 1:
        return f"{nombre(x, 2)} €"
    if x <= 0:
        return "0 €"
    import math
    decimales = min(10, max(2, 3 - int(math.floor(math.log10(x)))))
    return f"{nombre(x, decimales)} €"


def pourcent(x: float, signe: bool = True) -> str:
    """« +2,3 % » ; « −0,04 % » (deux décimales sous 0,1 %, sinon une perte de 4 € sur 10 000 s'affichait « −0,0 % »)."""
    a = abs(x)
    texte = nombre(a, 0 if a >= 100 else 2 if 0 < a < 0.1 else 1)
    return (("+" if x >= 0 else "−") if signe else "") + texte + " %"


# --- réseau ------------------------------------------------------------------------------------------------------
def _get(source: str, url: str, params: dict) -> dict | list:
    compteur.compter(f"crypto_{source}")
    debut = time.time()
    r = requests.get(url, params=params, timeout=DELAI, headers={"User-Agent": "Jarvis (assistant local)"})
    r.raise_for_status()
    donnees = r.json()
    ms = round((time.time() - debut) * 1000)
    statistiques[source] += 1
    statistiques["ms"][source] = (statistiques["ms"][source] + [ms])[-50:]
    if source == "kraken" and donnees.get("error"):
        raise ValueError(f"Kraken : {donnees['error']}")
    return donnees


def _en_cache(cle, ttl):
    with _verrou:
        x = _cache.get(cle)
        if x and time.time() - x[0] < ttl:
            statistiques["cache"] += 1
            return x[1]
    return None


def _garder(cle, valeur):
    with _verrou:
        _cache[cle] = (time.time(), valeur)
    return valeur


def _kraken_base(cle: str) -> str:
    """« XXBTZEUR » -> BTC ; « SOLEUR » -> SOL ; « XDGEUR » -> DOGE."""
    base = cle[:-3]
    if len(base) == 5 and base.endswith("Z"):
        base = base[:-1]
    if len(base) == 4 and base[0] == "X" and base not in ("XRP",):
        base = base[1:]
    return {"XBT": "BTC", "XDG": "DOGE"}.get(base, base)


def _prix_binance(symboles: list[str]) -> dict:
    import json
    donnees = _get("binance", f"{BINANCE}/ticker/24hr",
                   {"symbols": json.dumps([s + "EUR" for s in symboles], separators=(",", ":"))})
    sortie = {}
    for x in donnees:
        s = x["symbol"][:-3]
        sortie[s] = {"symbole": s, "prix": float(x["lastPrice"]), "variation_24h": float(x["priceChangePercent"]),
                     "haut_24h": float(x["highPrice"]), "bas_24h": float(x["lowPrice"]),
                     "volume_eur_24h": float(x["quoteVolume"]), "source": "Binance", "periode": "24 h", "quand": time.time()}
    return sortie


def _prix_kraken(symboles: list[str]) -> dict:
    """Kraken ne donne pas la variation sur 24 h glissantes dans son « Ticker » (seulement l'ouverture du jour UTC) :
    on la recalcule sur les bougies d'une heure quand on ne demande qu'une crypto, sinon on dit « depuis minuit UTC »."""
    paires = ",".join(_KRAKEN_NOM.get(s, s) + "EUR" for s in symboles)
    donnees = _get("kraken", f"{KRAKEN}/Ticker", {"pair": paires})["result"]
    sortie = {}
    for cle, x in donnees.items():
        s = _kraken_base(cle)
        prix, ouverture = float(x["c"][0]), float(x["o"])
        sortie[s] = {"symbole": s, "prix": prix, "variation_24h": (prix / ouverture - 1) * 100 if ouverture else 0.0,
                     "haut_24h": float(x["h"][1]), "bas_24h": float(x["l"][1]), "volume_eur_24h": float(x["v"][1]) * float(x["p"][1]),
                     "source": "Kraken", "periode": "depuis minuit UTC", "quand": time.time()}
    if len(symboles) == 1 and symboles[0] in sortie:
        b = _bougies_kraken(symboles[0], "1h")
        if len(b) >= 25:
            reference = b[-25]["c"]
            sortie[symboles[0]].update(variation_24h=(sortie[symboles[0]]["prix"] / reference - 1) * 100, periode="24 h")
    return sortie


def prix(symboles: list[str] | str) -> dict:
    """{symbole: {prix, variation_24h, haut_24h, bas_24h, volume_eur_24h, source, periode, quand}}."""
    if isinstance(symboles, str):
        symboles = [symboles]
    symboles = [s for s in dict.fromkeys(symboles) if s in CRYPTOS]
    cle = ("prix", tuple(sorted(symboles)))
    if (x := _en_cache(cle, TTL_PRIX)) is not None:
        return x
    try:
        return _garder(cle, _prix_binance(symboles))
    except Exception as e:
        journal.warning("Binance ne répond pas (%s) : repli sur Kraken", e)
        statistiques["replis"] += 1
    try:
        return _garder(cle, _prix_kraken(symboles))
    except Exception as e:
        journal.warning("Kraken ne répond pas non plus (%s)", e)
        raise Indisponible("ni Binance ni Kraken ne répondent")


def _bougies_binance(symbole: str, intervalle: str, nombre_: int, fin: float | None = None) -> list[dict]:
    params = {"symbol": symbole + "EUR", "interval": intervalle, "limit": min(1000, nombre_)}
    if fin:
        params["endTime"] = int(fin * 1000)
    brut = _get("binance", f"{BINANCE}/klines", params)
    return [{"t": k[0] // 1000, "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])}
            for k in brut]


def _bougies_kraken(symbole: str, intervalle: str) -> list[dict]:
    donnees = _get("kraken", f"{KRAKEN}/OHLC", {"pair": _KRAKEN_NOM.get(symbole, symbole) + "EUR",
                                                 "interval": _KRAKEN_INTERVALLE[intervalle]})["result"]
    serie = next(v for k, v in donnees.items() if k != "last")
    return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[6])}
            for k in serie]


def bougies(symbole: str, intervalle: str = "1h", nombre_: int = 168, fin: float | None = None) -> list[dict]:
    """Les `nombre_` dernières bougies (closes ou en cours), de la plus ancienne à la plus récente.
    `fin` (horodatage) : s'arrêter là, pour le replay. Binance, Kraken en repli (720 bougies au plus)."""
    if intervalle not in SECONDES:
        raise ValueError(f"intervalle inconnu : {intervalle}")
    cle = ("bougies", symbole, intervalle, nombre_, int(fin // SECONDES[intervalle]) if fin else None)
    if (x := _en_cache(cle, TTL_BOUGIES[intervalle] if not fin else 3600)) is not None:
        return x
    try:
        return _garder(cle, _bougies_binance(symbole, intervalle, nombre_, fin))
    except Exception as e:
        journal.warning("Binance (bougies) ne répond pas (%s) : repli sur Kraken", e)
        statistiques["replis"] += 1
    try:
        serie = _bougies_kraken(symbole, intervalle)
        if fin:
            serie = [b for b in serie if b["t"] <= fin]
        return _garder(cle, serie[-nombre_:])
    except Exception as e:
        journal.warning("Kraken (bougies) ne répond pas non plus (%s)", e)
        raise Indisponible("ni Binance ni Kraken ne répondent")


PERIODES = {"24h": ("15m", 96, "24 heures"), "7j": ("1h", 168, "7 jours"), "30j": ("4h", 180, "30 jours")}


def periode_depuis(texte: str | None) -> str:
    n = _normaliser(texte or "")
    if re.search(r" (30|trente) ?j| mois | 1 mois | 30 jours ", n):
        return "30j"
    if re.search(r" (7|sept) ?j| semaine | 7 jours | sept jours ", n):
        return "7j"
    return "24h"


def classement(symboles: list[str] | None = None) -> list[dict]:
    """Les grandes cryptos triées de la plus forte hausse à la plus forte baisse (sur 24 h)."""
    p = prix(symboles or GRANDES)
    return sorted(p.values(), key=lambda x: -x["variation_24h"])
