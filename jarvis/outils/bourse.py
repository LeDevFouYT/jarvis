"""Outil bourse : indices, actions, or, pétrole, devises. Le cours en direct, le graphique géant, plusieurs graphiques
côte à côte, le point des marchés, ce qui monte et ce qui baisse, le taux d'une devise. Des faits, jamais un conseil.

Sources : Yahoo Finance (interface publique non officielle, sans clé) et les taux de la BCE (Frankfurter). Chaque
phrase est construite depuis les données et dite telle quelle (DIRECT) ; chaque chiffre est rangé dans `faits()`
pour le vérificateur."""
import time
from concurrent.futures import ThreadPoolExecutor

from ..crypto import actifs, bourse as B, cours

NOM = "bourse"
DESCRIPTION = ("La bourse en direct (sans conseil) : indices (CAC 40, S&P 500, Nasdaq, Dow Jones, DAX…), actions (LVMH, "
               "TotalEnergies, Airbus, Apple, Nvidia, Tesla…), or, pétrole, devises. « cours » : un actif et son graphique "
               "(période jour, 5j, 1m, 1a, 5a) ; « comparer » : plusieurs graphiques côte à côte ; « point » : comment vont "
               "les marchés ; « classement » : ce qui monte et baisse parmi les grandes valeurs ; « change » : le cours d'une devise.")
PARAMETRES = {
    "action": {"type": "string", "enum": ["cours", "comparer", "point", "classement", "change"]},
    "actif": {"type": "string", "description": "L'indice, l'action ou la matière première, tel que dit"},
    "actifs": {"type": "array", "items": {"type": "string"}, "description": "Pour « comparer » : plusieurs actifs"},
    "periode": {"type": "string", "enum": ["jour", "5j", "1m", "1a", "5a"]},
    "devise": {"type": "string", "description": "Pour « change » : dollar, livre, yen, franc suisse"},
}
REQUIS = ["action"]
DIRECT = True
PERIODES_UI = [["jour", "JOUR"], ["5j", "5 J"], ["1m", "1 MOIS"], ["1a", "1 AN"], ["5a", "5 ANS"]]
dernier: dict = {"faits": []}


def faits() -> list[dict]:
    return dernier.get("faits", [])


def _fait(faits_: list, texte: str, sujet: str, **valeurs):
    faits_.append({"id": f"F{len(faits_) + 1}", "texte": texte, "sujet": sujet, "valeurs": valeurs})


def _sens(v: float, libelle: str = "") -> str:
    if abs(v) < 0.05:
        return "stable" + (f" sur {libelle}" if libelle else "")
    return f"en {'hausse' if v > 0 else 'baisse'} de {cours.pourcent(v, signe=False)}" + (f" sur {libelle}" if libelle else "")


def _serie(ident: str, periode: str) -> dict:
    """Un graphique, crypto ou bourse, dans le même format : {symbole, nom, prix, unite, variation, points, source}."""
    if actifs.est_crypto(ident):
        intervalle, n = {"jour": ("15m", 96), "5j": ("1h", 120), "1m": ("4h", 180), "1a": ("1d", 365), "5a": ("1d", 1000)}[periode]
        p = cours.prix(ident)[ident]
        serie = cours.bougies(ident, intervalle, n)
        points = [[b["t"], b["c"]] for b in serie] + [[int(p["quand"]), p["prix"]]]
        variation = p["variation_24h"] if periode == "jour" else (p["prix"] / serie[0]["o"] - 1) * 100
        return {"symbole": ident, "nom": cours.nom(ident), "prix": p["prix"], "unite": "EUR", "variation": variation,
                "points": points, "source": p["source"], "ouvert": True, "prix_eur": p["prix"]}
    c = B.cotation(ident)
    if periode == "jour":
        bougies = c["bougies_jour"]
        variation = c["variation"]
    else:
        _, bougies = B.historique(ident, periode)
        variation = (c["prix"] / bougies[0]["c"] - 1) * 100 if bougies else c["variation"]
    points = [[b["t"], b["c"]] for b in bougies]
    if not points or c["quand"] > points[-1][0]:
        points.append([int(c["quand"]), c["prix"]])
    return {"symbole": ident, "nom": B.nom(ident), "prix": c["prix"], "unite": c["unite"], "variation": variation, "points": points,
            "source": c["source"], "ouvert": c["ouvert"], "prix_eur": c["prix_eur"], "veille": c["veille"], "place": c["place"]}


def _depuis(points: list, periode: str) -> str:
    from datetime import datetime
    d = datetime.fromtimestamp(points[0][0])
    return f"{d.hour} h {d.minute:02d}" if periode == "jour" else d.strftime("%d/%m/%Y")


def _cours(ident: str, periode: str) -> str:
    g = _serie(ident, periode)
    libelle = B.PERIODES[periode][2]
    faits_ = []
    nom = actifs.nom_avec_article(ident, majuscule=True)
    verbe = "est à" if g["unite"] == "pts" else "vaut"
    phrase = f"{nom} {verbe} {actifs.valeur_dite(g['prix'], g['unite'])}"
    _fait(faits_, f"{actifs.nom(ident)} : {actifs.valeur_ecrite(g['prix'], g['unite'])} ({g['source']}).", f"prix {actifs.nom(ident)}", prix=g["prix"])
    if g["unite"] not in ("EUR", "pts") and g.get("prix_eur"):
        phrase += f", soit {actifs.valeur_dite(g['prix_eur'], 'EUR')}"
        _fait(faits_, f"En euros : {actifs.valeur_ecrite(g['prix_eur'], 'EUR')} (taux BCE).", "prix en euros", prix_eur=g["prix_eur"])
    if actifs.est_bourse(ident):
        c = B.cotation(ident)
        _fait(faits_, f"Variation de la journée : {cours.pourcent(c['variation'])}.", "variation journée",
              variation_abs=abs(c["variation"]), arrondi=round(abs(c["variation"]), 1))
        phrase += f", {_sens(c['variation'], 'la journée')}."
        if periode != "jour":
            _fait(faits_, f"Variation sur {libelle} : {cours.pourcent(g['variation'])}.", f"variation {libelle}", variation_abs=abs(g["variation"]))
            phrase += f" Sur {libelle} : {_sens(g['variation'])}."
        if not g["ouvert"] and B.genre(ident) != "matiere":
            phrase += " Le marché est fermé : c'est le cours de clôture."
    else:
        phrase += f", {_sens(g['variation'], libelle if periode != 'jour' else '24 heures')}."
        _fait(faits_, f"Variation : {cours.pourcent(g['variation'])}.", "variation", variation_abs=abs(g["variation"]))
    dernier.update(faits=faits_, quand=time.time(), actif=ident, periode=periode)
    from . import panneaux
    panneaux.cours(g["symbole"], g["nom"], periode, libelle, {"prix": g["prix"], "variation_24h": g["variation"], "source": g["source"],
                   "quand": g["points"][-1][0]}, [{"t": t, "c": v} for t, v in g["points"][:-1]], g["variation"],
                   unite=g["unite"], periodes=PERIODES_UI, depuis=_depuis(g["points"], periode),
                   etat=("marché ouvert" if g["ouvert"] else "marché fermé") if actifs.est_bourse(ident) else "")
    return phrase


def _comparer(idents: list[str], periode: str) -> str:
    if len(idents) < 2:
        idents = B.INDICES[:4]
    idents = idents[:6]
    with ThreadPoolExecutor(max_workers=len(idents)) as fils:
        graphiques = list(fils.map(lambda i: _serie(i, periode), idents))
    libelle = B.PERIODES[periode][2]
    faits_ = []
    for g in graphiques:
        _fait(faits_, f"{g['nom']} : {actifs.valeur_ecrite(g['prix'], g['unite'])}, {cours.pourcent(g['variation'])} sur {libelle}.",
              f"variation {g['nom']}", prix=g["prix"], variation_abs=abs(g["variation"]))
    dernier.update(faits=faits_, quand=time.time(), actifs=idents, periode=periode)
    from . import panneaux
    panneaux.multicours(periode, libelle, [{"symbole": g["symbole"], "nom": g["nom"], "variation": g["variation"],
                                            "prix": {"prix": g["prix"], "quand": g["points"][-1][0], "source": g["source"]},
                                            "serie": [{"t": t, "c": v} for t, v in g["points"][:-1]], "unite": g["unite"]}
                                           for g in graphiques])
    morceaux = [f"{actifs.nom_avec_article(g['symbole'])} {_sens(g['variation'])}" for g in graphiques]
    phrase = f"Sur {libelle} : " + ", ".join(morceaux[:-1]) + f" et {morceaux[-1]}."
    if len(graphiques) > 2:
        tri = sorted(graphiques, key=lambda g: -g["variation"])
        phrase += f" Le mieux : {actifs.nom_avec_article(tri[0]['symbole'])} ; le moins bien : {actifs.nom_avec_article(tri[-1]['symbole'])}."
    return phrase


def _cotations(idents: list[str]) -> list[dict]:
    with ThreadPoolExecutor(max_workers=min(12, len(idents))) as fils:
        return [c for c in fils.map(lambda i: _sans_erreur(B.cotation, i), idents) if c]


def _sans_erreur(f, *a):
    try:
        return f(*a)
    except Exception:
        return None


def point() -> str:
    """Comment vont les marchés : quatre indices, les plus forts mouvements des grandes valeurs suivies, l'or et le pétrole.
    Chaque chiffre dit est relu par le vérificateur ; une phrase dont un chiffre manque aux faits n'est pas dite."""
    from ..youtube import verification
    t = time.time()
    indices = _cotations(["^FCHI", "^GSPC", "^IXIC", "^GDAXI"])
    valeurs = _cotations(B.CAC_SUIVIES + B.US_SUIVIES)
    matieres = _cotations(["GC=F", "BZ=F"])
    if not indices:
        raise B.Indisponible("aucun indice")
    faits_ = []
    for c in indices + valeurs + matieres:
        _fait(faits_, f"{c['nom']} : {actifs.valeur_ecrite(c['prix'], c['unite'])}, {cours.pourcent(c['variation'])} sur la journée.",
              f"variation {c['nom']}", prix=c["prix"], variation_abs=abs(c["variation"]))
    morceaux = [f"{B.nom_avec_article(c['ident'])} {_sens(c['variation'])}" for c in indices]
    phrase = "Le point des marchés. " + " ; ".join(morceaux) + ". "
    phrase = phrase.replace("Le point des marchés. le ", "Le point des marchés. Le ", 1)
    tri = sorted(valeurs, key=lambda c: -c["variation"])
    if tri:
        phrase += f"Parmi les grandes valeurs que je suis, la plus forte hausse : {tri[0]['nom']}, {cours.pourcent(tri[0]['variation'], signe=False)}"
        phrase += f" ; la plus forte baisse : {tri[-1]['nom']}, {cours.pourcent(tri[-1]['variation'], signe=False)}. " if tri[-1]["variation"] < 0 else ". "
    for c in matieres:
        phrase += f"{c['nom'][:1].upper() + c['nom'][1:]} : {actifs.valeur_dite(c['prix'], c['unite'])}, {_sens(c['variation'])}. "
    fermes = [c["nom"] for c in indices if not c["ouvert"]]
    if len(fermes) == len(indices):
        phrase += "Les marchés sont fermés : ce sont les derniers cours."
    resultat = verification.verifier(phrase, faits_)
    resultat["phrases_jugees"] = []
    verification.panneau(resultat, faits_)
    for e in resultat["ecarts"]:                       # un chiffre absent des faits n'est jamais dit
        phrase = phrase.replace(e["phrase"], "")
    from . import panneaux
    panneaux.barres("Marchés · variation de la journée · Yahoo Finance",
                    [{"nom": c["nom"], "valeur": round(c["variation"], 2), "detail": actifs.valeur_ecrite(c["prix"], c["unite"]),
                      "brille": c in indices} for c in sorted(indices + valeurs + matieres, key=lambda c: -c["variation"])], unite="%")
    dernier.update(faits=faits_, quand=time.time(), verification=resultat, duree_s=round(time.time() - t, 2))
    return phrase.strip()


def classement() -> str:
    valeurs = sorted(_cotations(B.CAC_SUIVIES + B.US_SUIVIES), key=lambda c: -c["variation"])
    if not valeurs:
        raise B.Indisponible("aucune valeur")
    faits_ = []
    for c in valeurs:
        _fait(faits_, f"{c['nom']} : {cours.pourcent(c['variation'])}.", f"variation {c['nom']}", variation_abs=abs(c["variation"]))
    dernier.update(faits=faits_, quand=time.time())
    from . import panneaux
    panneaux.barres("Grandes valeurs · variation de la journée", [{"nom": c["nom"], "valeur": round(c["variation"], 2),
                    "detail": actifs.valeur_ecrite(c["prix"], c["unite"]), "brille": i < 2 or i >= len(valeurs) - 2}
                    for i, c in enumerate(valeurs)], unite="%")
    h, b = valeurs[:2], valeurs[-2:]
    return (f"Parmi les grandes valeurs que je suis, ce qui monte le plus : {h[0]['nom']}, {_sens(h[0]['variation'])}, puis "
            f"{h[1]['nom']}, {_sens(h[1]['variation'])}. Ce qui baisse le plus : {b[-1]['nom']}, {_sens(b[-1]['variation'])}.")


def change(devise: str = "USD") -> str:
    code = (devise or "USD").upper() if (devise or "").upper() in B.DEVISES else (B.devise_dite(devise or "") or "USD")
    taux = B.taux_en_euros(code)
    un, plusieurs, _ = B.DEVISES[code]
    date = B.date_du_taux(code) or ""
    jour = f" du {date[8:10]}/{date[5:7]}" if date else ""
    inverse = 1 / taux
    dernier.update(faits=[{"id": "F1", "texte": f"1 {code} = {taux} EUR, 1 EUR = {inverse} {code} (BCE{jour}).", "sujet": "change",
                           "valeurs": {"taux": taux, "inverse": inverse}}], quand=time.time())
    d = 4 if taux < 0.1 else 3
    return (f"Un {un} vaut {cours.nombre(taux, d)} euro, et un euro vaut {cours.nombre(inverse, d if inverse < 10 else 2)} "
            f"{un if inverse < 2 else plusieurs}. Taux de référence de la Banque centrale européenne{jour}.")


def executer(action: str = "cours", actif: str = "", periode: str = "jour", actifs_=None, devise: str = "", **autres) -> str:
    actifs_liste = autres.get("actifs", actifs_)
    periode = periode if periode in B.PERIODES else B.periode_ui(periode) if periode else "jour"
    try:
        if action == "point":
            return point()
        if action == "classement":
            return classement()
        if action == "change":
            return change(devise or actif)
        if action == "comparer":
            if isinstance(actifs_liste, str):
                actifs_liste = [actifs_liste]
            idents = []
            for a in (actifs_liste or []) + ([actif] if actif else []):
                trouves = [a] if (actifs.est_crypto(a) or actifs.est_bourse(a)) else actifs.reconnaitre_tous(str(a))
                idents += [i for i in trouves if i not in idents]
            return _comparer(idents, periode)
        ident = actif if (actifs.est_bourse(actif) or actifs.est_crypto(actif)) else actifs.reconnaitre(actif or "")
        if not ident:
            return f"Je ne connais pas « {actif} ». Je suis le CAC 40, le S&P 500, une trentaine de grandes actions, l'or et le pétrole."
        return _cours(ident, periode)
    except (B.Indisponible, cours.Indisponible) as e:
        return f"Je n'ai pas de cours fiable : {e}. Yahoo Finance est une source publique non officielle, elle répond parfois mal."
