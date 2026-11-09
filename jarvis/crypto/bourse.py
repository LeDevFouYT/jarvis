"""La bourse (après la vidéo 4) : indices, actions, matières premières, devises. Des faits, jamais un conseil.

Sources publiques sans clé, chaque requête comptée dans les sorties Internet :
  - Yahoo Finance, interface « chart » (query1, query2 en repli) : prix, clôture de la veille, devise, horaires du
    marché, bougies. Interface publique NON officielle : elle peut changer sans prévenir ; Jarvis le dit s'il échoue.
  - Frankfurter (taux de référence de la BCE, une fois par jour ouvré) pour convertir dollars, livres et yens en euros.
Aucun compte, aucun ordre : le portefeuille reste fictif (portefeuille.py).

Un actif : son identifiant Yahoo (« ^FCHI », « MC.PA », « AAPL », « GC=F »), son nom dit, son article, ses mots
reconnus à l'oral. Une bougie : {"t", "o", "h", "l", "c", "v"}, comme pour les cryptos (cours.py)."""
import logging
import re
import threading
import time

import requests

from .. import compteur

journal = logging.getLogger("bourse")
DELAI = 8
YAHOO = ["https://query1.finance.yahoo.com/v8/finance/chart/", "https://query2.finance.yahoo.com/v8/finance/chart/"]
FRANKFURTER = "https://api.frankfurter.app/latest"
ENTETES = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis (assistant local)"}

# identifiant -> (nom dit, article, genre, mots reconnus après normalisation)
ACTIFS = {
    # indices
    "^FCHI": ("CAC 40", "le", "indice", ["cac 40", "cac quarante", "cac", "bourse de paris"]),
    "^GSPC": ("S&P 500", "le", "indice", ["s p 500", "s and p 500", "s and p", "sp 500", "sp500", "s p", "standard and poor s"]),
    "^IXIC": ("Nasdaq", "le", "indice", ["nasdaq", "nasdaq composite"]),
    "^DJI": ("Dow Jones", "le", "indice", ["dow jones", "dow"]),
    "^GDAXI": ("DAX", "le", "indice", ["dax", "bourse de francfort"]),
    "^STOXX50E": ("Euro Stoxx 50", "l'", "indice", ["euro stoxx 50", "eurostoxx", "euro stoxx"]),
    "^N225": ("Nikkei", "le", "indice", ["nikkei", "nikkei 225", "bourse de tokyo"]),
    "^FTSE": ("FTSE 100", "le", "indice", ["ftse", "ftse 100", "footsie", "bourse de londres"]),
    # actions françaises
    "MC.PA": ("LVMH", "", "action", ["lvmh", "louis vuitton"]),
    "TTE.PA": ("TotalEnergies", "", "action", ["totalenergies", "total energies", "total"]),
    "AIR.PA": ("Airbus", "", "action", ["airbus"]),
    "OR.PA": ("L'Oréal", "", "action", ["l oreal", "loreal"]),
    "SAN.PA": ("Sanofi", "", "action", ["sanofi"]),
    "BNP.PA": ("BNP Paribas", "", "action", ["bnp paribas", "bnp"]),
    "RMS.PA": ("Hermès", "", "action", ["hermes"]),
    "SU.PA": ("Schneider Electric", "", "action", ["schneider electric", "schneider"]),
    "AI.PA": ("Air Liquide", "", "action", ["air liquide"]),
    "SAF.PA": ("Safran", "", "action", ["safran"]),
    "DG.PA": ("Vinci", "", "action", ["vinci"]),
    "CS.PA": ("AXA", "", "action", ["axa"]),
    "BN.PA": ("Danone", "", "action", ["danone"]),
    "ORA.PA": ("Orange", "", "action", ["orange telecom", "action orange", "orange"]),
    "RNO.PA": ("Renault", "", "action", ["renault"]),
    "STLAP.PA": ("Stellantis", "", "action", ["stellantis"]),
    "GLE.PA": ("Société Générale", "la", "action", ["societe generale", "socgen"]),
    "ACA.PA": ("Crédit Agricole", "le", "action", ["credit agricole"]),
    "CAP.PA": ("Capgemini", "", "action", ["capgemini", "cap gemini"]),
    "KER.PA": ("Kering", "", "action", ["kering"]),
    "UBI.PA": ("Ubisoft", "", "action", ["ubisoft"]),
    "DSY.PA": ("Dassault Systèmes", "", "action", ["dassault systemes"]),
    "EL.PA": ("EssilorLuxottica", "", "action", ["essilorluxottica", "essilor"]),
    # actions américaines
    "AAPL": ("Apple", "", "action", ["apple"]),
    "MSFT": ("Microsoft", "", "action", ["microsoft"]),
    "NVDA": ("Nvidia", "", "action", ["nvidia", "envidia", "n vidia"]),
    "TSLA": ("Tesla", "", "action", ["tesla"]),
    "AMZN": ("Amazon", "", "action", ["amazon"]),
    "GOOGL": ("Alphabet", "", "action", ["alphabet", "google"]),
    "META": ("Meta", "", "action", ["meta", "facebook"]),
    "NFLX": ("Netflix", "", "action", ["netflix"]),
    "AMD": ("AMD", "", "action", ["amd"]),
    "INTC": ("Intel", "", "action", ["intel"]),
    "DIS": ("Disney", "", "action", ["disney"]),
    "KO": ("Coca-Cola", "", "action", ["coca cola", "coca"]),
    "MCD": ("McDonald's", "", "action", ["mcdonald s", "mcdonalds", "mac do", "macdo"]),
    # matières premières
    "GC=F": ("l'or", "", "matiere", ["l or", "once d or", "prix de l or", "cours de l or"]),
    "SI=F": ("l'argent métal", "", "matiere", ["argent metal", "once d argent", "cours de l argent"]),
    "BZ=F": ("le pétrole Brent", "", "matiere", ["petrole", "brent", "baril", "petrole brent"]),
    "CL=F": ("le pétrole WTI", "", "matiere", ["wti", "petrole americain"]),
}
INDICES = ["^FCHI", "^GSPC", "^IXIC", "^DJI", "^GDAXI", "^STOXX50E"]
CAC_SUIVIES = ["MC.PA", "TTE.PA", "AIR.PA", "OR.PA", "SAN.PA", "BNP.PA", "RMS.PA", "SU.PA", "AI.PA", "SAF.PA", "DG.PA", "CS.PA"]
US_SUIVIES = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META"]
DEVISES = {"USD": ("dollar", "dollars", "$"), "GBP": ("livre sterling", "livres sterling", "£"), "JPY": ("yen", "yens", "¥"),
           "CHF": ("franc suisse", "francs suisses", "CHF"), "CNY": ("yuan", "yuans", "¥")}
_MOTS_DEVISES = {"dollar": "USD", "dollars": "USD", "livre sterling": "GBP", "livre": "GBP", "yen": "JPY", "yens": "JPY",
                 "franc suisse": "CHF", "yuan": "CNY"}

# période -> (range Yahoo, intervalle Yahoo, libellé dit)
PERIODES = {"jour": ("1d", "5m", "la journée"), "5j": ("5d", "30m", "5 jours"), "1m": ("1mo", "1d", "un mois"),
            "1a": ("1y", "1d", "un an"), "5a": ("5y", "1wk", "cinq ans")}
TTL = {"1d": 60, "5d": 300, "1mo": 900, "1y": 3600, "5y": 3600}

_cache: dict = {}
_verrou = threading.Lock()
statistiques = {"yahoo": 0, "repli_query2": 0, "frankfurter": 0, "cache": 0, "ms": []}


class Indisponible(Exception):
    pass


def _normaliser(texte: str) -> str:
    from .cours import _normaliser as n
    return n(texte.replace("&", " and "))


def reconnaitre(texte: str) -> str | None:
    """« le CAC 40 » -> ^FCHI ; « l'or » -> GC=F ; « Apple » -> AAPL. Le nom le plus long gagne."""
    n = _normaliser(texte.replace("&", " and "))
    meilleur, longueur = None, 0
    for ident, (_, _, _, mots) in ACTIFS.items():
        for mot in mots:
            if f" {mot} " in n and len(mot) > longueur:
                meilleur, longueur = ident, len(mot)
    return meilleur


def reconnaitre_tous(texte: str) -> list[str]:
    n = _normaliser(texte.replace("&", " and "))
    trouves = []
    for ident, (_, _, _, mots) in ACTIFS.items():
        for mot in mots:
            depart = 0
            while (i := n.find(f" {mot} ", depart)) >= 0:
                trouves.append((i, i + len(mot) + 2, ident))
                depart = i + 1
    trouves.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    gardes, fin = [], -1
    for debut, f, ident in trouves:
        if debut + 1 >= fin:
            gardes.append(ident)
            fin = f
    return list(dict.fromkeys(gardes))


def devise_dite(texte: str) -> str | None:
    n = _normaliser(texte)
    for mot, code in sorted(_MOTS_DEVISES.items(), key=lambda x: -len(x[0])):
        if f" {mot} " in n:
            return code
    return None


def nom(ident: str) -> str:
    return ACTIFS.get(ident, (ident,))[0]


def nom_avec_article(ident: str, majuscule: bool = False) -> str:
    n, article, genre, _ = ACTIFS.get(ident, (ident, "", "action", []))
    if genre == "matiere":
        texte = n                                   # « l'or », « le pétrole Brent » : l'article est déjà dans le nom
    elif genre == "action" and not article:
        texte = f"l'action {n}"
    else:
        texte = f"l'{n}" if article == "l'" else f"{article} {n}".strip()
    return texte[:1].upper() + texte[1:] if majuscule else texte


def genre(ident: str) -> str:
    return ACTIFS.get(ident, ("", "", "action", []))[2]


# --- réseau ------------------------------------------------------------------------------------------------------
def _yahoo(ident: str, plage: str, intervalle: str) -> dict:
    cle = ("yahoo", ident, plage, intervalle)
    with _verrou:
        x = _cache.get(cle)
        if x and time.time() - x[0] < TTL.get(plage, 120):
            statistiques["cache"] += 1
            return x[1]
    derniere = None
    for i, base in enumerate(YAHOO):
        try:
            compteur.compter("bourse_yahoo")
            t = time.time()
            r = requests.get(base + requests.utils.quote(ident, safe=""), params={"range": plage, "interval": intervalle},
                             headers=ENTETES, timeout=DELAI)
            r.raise_for_status()
            resultat = (r.json().get("chart", {}).get("result") or [None])[0]
            if not resultat:
                raise ValueError("réponse vide")
            statistiques["yahoo"] += 1
            statistiques["repli_query2"] += i
            statistiques["ms"] = (statistiques["ms"] + [round((time.time() - t) * 1000)])[-50:]
            with _verrou:
                _cache[cle] = (time.time(), resultat)
            return resultat
        except Exception as e:
            derniere = e
            journal.warning("Yahoo (%s) ne répond pas pour %s : %s", base, ident, e)
    raise Indisponible(f"Yahoo Finance ne répond pas ({type(derniere).__name__})")


def taux_en_euros(devise: str) -> float:
    """1 unité de `devise` en euros (taux BCE du jour ouvré, via Frankfurter). EUR -> 1."""
    devise = (devise or "EUR").upper()
    if devise in ("EUR", ""):
        return 1.0
    cle = ("change", devise)
    with _verrou:
        x = _cache.get(cle)
        if x and time.time() - x[0] < 3600:
            return x[1]
    compteur.compter("bourse_frankfurter")
    r = requests.get(FRANKFURTER, params={"from": devise, "to": "EUR"}, headers=ENTETES, timeout=DELAI)
    r.raise_for_status()
    taux = float(r.json()["rates"]["EUR"])
    statistiques["frankfurter"] += 1
    with _verrou:
        _cache[cle] = (time.time(), taux)
        _cache[("change_date", devise)] = (time.time(), r.json().get("date"))
    return taux


def date_du_taux(devise: str) -> str | None:
    x = _cache.get(("change_date", devise.upper()))
    return x[1] if x else None


def _bougies(resultat: dict) -> list[dict]:
    ts = resultat.get("timestamp") or []
    q = (resultat.get("indicators", {}).get("quote") or [{}])[0]
    sortie = []
    for i, t in enumerate(ts):
        c = (q.get("close") or [None] * len(ts))[i]
        if c is None:
            continue
        o, h, l = ((q.get(k) or [None] * len(ts))[i] for k in ("open", "high", "low"))
        sortie.append({"t": int(t), "o": o if o is not None else c, "h": h if h is not None else c, "l": l if l is not None else c,
                       "c": c, "v": (q.get("volume") or [0] * len(ts))[i] or 0})
    return sortie


def cotation(ident: str) -> dict:
    """Prix, variation du jour (contre la clôture de la veille), devise, marché ouvert ou fermé, prix en euros."""
    r = _yahoo(ident, "1d", "5m")
    m = r["meta"]
    prix = float(m.get("regularMarketPrice"))
    veille = float(m.get("chartPreviousClose") or m.get("previousClose") or prix)
    devise = m.get("currency") or "EUR"
    unite = "pts" if m.get("instrumentType") == "INDEX" else devise
    periode = (m.get("currentTradingPeriod") or {}).get("regular") or {}
    maintenant = time.time()
    ouvert = bool(periode) and periode.get("start", 0) <= maintenant <= periode.get("end", 0)
    taux = 1.0 if unite == "pts" else taux_en_euros(devise)
    return {"ident": ident, "nom": nom(ident), "prix": prix, "veille": veille, "variation": (prix / veille - 1) * 100 if veille else 0.0,
            "devise": devise, "unite": unite, "prix_eur": prix * taux if unite != "pts" else None, "taux_eur": taux,
            "ouvert": ouvert, "quand": float(m.get("regularMarketTime") or maintenant), "place": m.get("fullExchangeName", ""),
            "source": "Yahoo Finance", "bougies_jour": _bougies(r)}


def historique(ident: str, periode: str = "1m") -> tuple[dict, list[dict]]:
    plage, intervalle, _ = PERIODES[periode]
    r = _yahoo(ident, plage, intervalle)
    return r["meta"], _bougies(r)


def prix_eur(idents: list[str]) -> dict[str, float]:
    """Le prix en euros de chaque actif (actions et matières premières ; un indice n'a pas de prix en euros)."""
    sortie = {}
    for ident in idents:
        c = cotation(ident)
        if c["prix_eur"] is not None:
            sortie[ident] = c["prix_eur"]
    return sortie


def periode_depuis(texte: str) -> str:
    n = _normaliser(texte or "")
    if re.search(r" (5|cinq) ans ", n):
        return "5a"
    if re.search(r" (1 an|un an|l annee|12 mois|douze mois|annee) ", n):
        return "1a"
    if re.search(r" (1 mois|un mois|le mois|30 jours|trente jours|mois) ", n):
        return "1m"
    if re.search(r" (5 jours|cinq jours|la semaine|une semaine|7 jours|sept jours|semaine) ", n):
        return "5j"
    return "jour"


def periode_ui(periode: str) -> str:
    """Les périodes crypto dites à l'oral (24h, 7j, 30j) traduites vers celles de la bourse."""
    return {"24h": "jour", "7j": "5j", "30j": "1m"}.get(periode, periode if periode in PERIODES else "jour")
