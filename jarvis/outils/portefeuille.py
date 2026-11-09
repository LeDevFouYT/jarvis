"""Outil portefeuille (vidéo 4, consigne 3) : le portefeuille FICTIF de 10 000 €.

« Achète pour 500 € de Bitcoin », « Vends la moitié de mon Ethereum » : l'ordre est préparé au prix réel du moment,
puis passe par la confirmation oui / non (confirmations.py). « Combien je vaux ? », « Remets le portefeuille à zéro ».
Aucun compte, aucune plateforme, aucune clé : seul workspace/portefeuille.json change. Jarvis le dit à chaque fois."""
import json
import shutil
import time

from .. import confirmations
from ..crypto import actifs, bourse, cours
from ..crypto import portefeuille as P

NOM = "portefeuille"
DESCRIPTION = ("Le portefeuille FICTIF de 10 000 € (aucun argent réel). « achat » : acheter pour un montant en euros d'une "
               "crypto ; « vente » : vendre une fraction (0,5 = la moitié, 1 = tout) ou un montant en euros ; « valeur » : "
               "combien vaut le portefeuille ; « journal » : les derniers ordres ; « zero » : repartir de 10 000 €. "
               "Chaque ordre demande une confirmation oui / non.")
PARAMETRES = {
    "action": {"type": "string", "enum": ["achat", "vente", "valeur", "journal", "zero"]},
    "crypto": {"type": "string", "description": "La crypto (bitcoin, ethereum, solana…), pour achat et vente"},
    "montant_eur": {"type": "number", "description": "Montant en euros"},
    "fraction": {"type": "number", "description": "Part de la position à vendre, entre 0 et 1"},
}
REQUIS = ["action"]
DIRECT = True
ARCHIVES = P.FICHIER.parent / "portefeuille_archives"

dernier: dict = {"faits": []}


def faits() -> list[dict]:
    return dernier.get("faits", [])


def montant_dit(x: float) -> str:
    """9 500 euros ; 12,40 euros ; 50 centimes : comme on le dit."""
    if abs(x) < 1:
        return f"{round(abs(x) * 100)} centime{'s' if round(abs(x) * 100) > 1 else ''}"
    if abs(x) >= 100 or abs(x - round(x)) < 0.005:
        return f"{cours.nombre(abs(x))} euro{'s' if round(abs(x)) >= 2 else ''}"
    return f"{cours.nombre(abs(x), 2)} euros"


def de(nom: str) -> str:
    """« de Bitcoin », « d'Ethereum »."""
    return f"d'{nom}" if nom[:1].lower() in "aeiouyé" else f"de {nom}"


def _nombre(x, defaut=None):
    try:
        return float(str(x).replace(",", ".").replace(" ", "").replace("€", "")) if x not in (None, "") else defaut
    except ValueError:
        return defaut


def _prix(symboles: list[str]) -> dict[str, float]:
    """Le prix en euros de chaque position : cryptos (Binance) et actions (Yahoo Finance, converti au taux BCE)."""
    return actifs.prix_eur(symboles) if symboles else {}


def _panneau(livre: P.Livre, prix: dict):
    from . import panneaux
    d = livre.detail(prix)
    elements = [{"titre": f"{actifs.nom(l['symbole'])} · {cours.euros(l['valeur'])}",
                 "detail": f"{l['quantite']:.8g} {l['symbole'] if actifs.est_crypto(l['symbole']) else 'titres'} à {cours.euros(l['prix'])}", "meta": f"{l['valeur'] / d['valeur']:.0%}"}
                for l in d["positions"]]
    elements.append({"titre": f"Euros fictifs · {cours.nombre(d['euros'], 2)} €",
                     "detail": f"départ {cours.nombre(d['depart'])} € · {d['ordres']} ordre(s) · {d['frais_payes']:.2f} € de frais".replace(".", ","),
                     "meta": f"{d['euros'] / d['valeur']:.0%}" if d["valeur"] else ""})
    signe = "+" if d["gain"] >= 0 else "−"
    panneaux.liste(f"Portefeuille FICTIF · {cours.euros(d['valeur'])} · {signe}{cours.pourcent(d['gain_pct'], signe=False)}", elements,
                   cle="portefeuille")


def valeur() -> str:
    livre = P.charger()
    prix = _prix(list(livre.positions))
    d = livre.detail(prix)
    faits_ = [{"id": "F1", "texte": f"Valeur du portefeuille fictif : {cours.euros(d['valeur'])}.", "sujet": "valeur portefeuille",
               "valeurs": {"valeur": d["valeur"], "depart": d["depart"]}},
              {"id": "F2", "texte": f"Gain depuis le départ : {d['gain']:.2f} €, {cours.pourcent(d['gain_pct'])}.", "sujet": "gain",
               "valeurs": {"gain": abs(d["gain"]), "gain_pct": abs(d["gain_pct"])}},
              {"id": "F3", "texte": f"Euros disponibles : {d['euros']:.2f} €.", "sujet": "euros disponibles", "valeurs": {"euros": d["euros"]}}]
    faits_ += [{"id": f"F{4 + i}", "texte": f"{actifs.nom(l['symbole'])} : {l['valeur']:.2f} €.", "sujet": actifs.nom(l["symbole"]),
                "valeurs": {"valeur": l["valeur"], "quantite": l["quantite"]}} for i, l in enumerate(d["positions"])]
    dernier.update(faits=faits_, quand=time.time())
    _panneau(livre, prix)
    if abs(d["gain"]) < 0.005:
        evolution = "exactement sa valeur de départ"
    elif abs(d["gain_pct"]) < 0.05:
        evolution = f"{montant_dit(d['gain'])} {'de plus' if d['gain'] > 0 else 'de moins'} qu'au départ"
    else:
        evolution = f"{'en hausse' if d['gain'] > 0 else 'en baisse'} de {cours.pourcent(d['gain_pct'], signe=False)} depuis le départ à {montant_dit(d['depart'])}"
    phrase = f"Votre portefeuille fictif vaut {montant_dit(d['valeur'])}, {evolution}."
    if d["positions"]:
        parts = [f"{montant_dit(l['valeur'])} {de(actifs.nom(l['symbole']))}" for l in d["positions"][:3]]
        phrase += (f" Vous avez {montant_dit(d['euros'])} disponibles"
                   + "".join(f", {x}" for x in parts[:-1]) + f" et {parts[-1]}.")
    return phrase


def _confirmer(sens: str, symbole: str, montant_eur: float | None, fraction: float | None) -> str:
    livre = P.charger()
    prix = _prix([symbole])[symbole]
    nom = actifs.nom(symbole)
    if sens == "achat":
        if montant_eur is None or montant_eur <= 0:
            return "Pour combien d'euros, monsieur ? Dites par exemple : achète pour 500 euros de Bitcoin."
        if livre.euros < P.MINIMUM_EUR:
            return f"Il ne reste que {montant_dit(livre.euros)} fictifs dans le portefeuille."
        montant = min(montant_eur, livre.euros)
        reduit = f" (il ne reste que {montant_dit(livre.euros)})" if montant < montant_eur else ""
        question = (f"Acheter pour {montant_dit(montant)} {de(nom)}{reduit}, à {montant_dit(prix)} l'unité, avec {montant_dit(montant * P.FRAIS)} "
                    f"de frais, en argent fictif ?{_ferme(symbole)} Oui ou non ?")
    else:
        detenu = livre.positions.get(symbole, 0.0)
        if detenu <= 0:
            return f"Le portefeuille fictif ne contient pas de {nom}."
        if montant_eur:
            brut = min(montant_eur, detenu * prix)
        else:
            brut = detenu * prix * max(0.0, min(1.0, fraction if fraction is not None else 1.0))
        part = {0.5: "la moitié de votre", 1.0: "tout votre", 0.25: "un quart de votre"}.get(round(fraction, 2) if fraction else None, "")
        question = (f"Vendre {part + ' ' if part else 'pour ' + montant_dit(brut) + ' de '}{nom}{', soit ' + montant_dit(brut) if part else ''}, "
                    f"à {montant_dit(prix)} l'unité, en argent fictif ? Oui ou non ?").replace("votre  ", "votre ")
        montant = brut

    def passer():
        prix_reel = _prix([symbole])[symbole]                # le prix au moment du « oui »
        try:
            if sens == "achat":
                ordre, livre_ = P.executer_ordre("achat", symbole, prix_reel, montant_eur=montant)
            else:
                ordre, livre_ = P.executer_ordre("vente", symbole, prix_reel, montant_eur=montant_eur, fraction=None if montant_eur else (fraction or 1.0))
        except P.OrdreImpossible as e:
            return f"Ordre impossible : {e}."
        prix_tous = _prix(list(livre_.positions))
        _panneau(livre_, prix_tous)
        verbe = "achetés" if sens == "achat" else "vendus"
        return (f"C'est fait, en argent fictif : {montant_dit(ordre['montant_eur'])} {de(nom)} {verbe} à {montant_dit(prix_reel)}, "
                f"dont {montant_dit(ordre['frais_eur'])} de frais. " + (f"Il vous reste {montant_dit(livre_.euros)} disponibles." if livre_.euros >= 0.01 else "Il ne vous reste plus d'euros."))

    return confirmations.demander(question, passer, refus="Très bien, je ne passe pas l'ordre. Rien n'a changé.")


def _ferme(symbole: str) -> str:
    """Une action dont le marché est fermé s'achète (fictivement) au dernier cours : on le dit dans la question."""
    if not actifs.est_bourse(symbole):
        return ""
    try:
        c = bourse.cotation(symbole)
    except Exception:
        return ""
    taux = f" Prix converti en euros au taux BCE ({c['devise']})." if c["devise"] != "EUR" else ""
    return (" La bourse est fermée : ce sera au dernier cours." if not c["ouvert"] else "") + taux


def zero() -> str:
    if P.FICHIER.exists():
        ARCHIVES.mkdir(parents=True, exist_ok=True)
        shutil.copy2(P.FICHIER, ARCHIVES / f"portefeuille_{time.strftime('%Y%m%d_%H%M%S')}.json")
    livre = P.remettre_a_zero()
    _panneau(livre, {})
    return f"Portefeuille remis à zéro : {montant_dit(P.CAPITAL)} fictifs, aucune crypto. L'ancien journal est archivé."


def journal() -> str:
    livre = P.charger()
    if not livre.journal:
        return "Aucun ordre dans le portefeuille fictif pour l'instant."
    from . import panneaux
    panneaux.liste("Journal des ordres · argent fictif",
                   [{"titre": f"{'Achat' if o['sens'] == 'achat' else 'Vente'} {actifs.nom(o['symbole'])} · {cours.euros(o['montant_eur'])}",
                     "detail": f"{o['quantite']:.8g} à {cours.euros(o['prix'])} · frais {o['frais_eur']:.2f} €".replace(".", ","),
                     "meta": time.strftime("%d/%m %H:%M", time.localtime(o["quand"]))} for o in reversed(livre.journal[-20:])])
    o = livre.journal[-1]
    return (f"{len(livre.journal)} ordre{'s' if len(livre.journal) > 1 else ''} fictif{'s' if len(livre.journal) > 1 else ''}. "
            f"Le dernier : {'achat' if o['sens'] == 'achat' else 'vente'} de {montant_dit(o['montant_eur'])} de {actifs.nom(o['symbole'])}.")


def executer(action: str = "valeur", crypto: str = "", montant_eur=None, fraction=None) -> str:
    try:
        if action == "valeur":
            return valeur()
        if action == "zero":
            return zero()
        if action == "journal":
            return journal()
        if action in ("achat", "vente"):
            symbole = crypto if (actifs.est_crypto(crypto) or actifs.est_bourse(crypto)) else (
                crypto.upper() if crypto.upper() in cours.CRYPTOS else actifs.reconnaitre(crypto))
            if not symbole:
                return f"Je ne connais pas « {crypto} »."
            if not actifs.achetable(symbole):
                return (f"{actifs.nom_avec_article(symbole, majuscule=True)} est un indice : il se suit, il ne s'achète pas. "
                        f"Même en argent fictif, il faudrait passer par un fonds qui le réplique.")
            return _confirmer(action, symbole, _nombre(montant_eur), _nombre(fraction))
        return "Je n'ai pas compris l'ordre."
    except (cours.Indisponible, bourse.Indisponible):
        return "Aucune source de cours ne répond : sans prix réel, je ne passe aucun ordre, même fictif."
