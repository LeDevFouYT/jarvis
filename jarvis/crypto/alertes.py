"""Les alertes de cours (consigne 5) : « préviens-moi si le Bitcoin passe sous 70 000 € », « …s'il prend 5 % dans
la journée », « …s'il perd 1 % dans l'heure ».

Surveillance toutes les 30 s, et seulement s'il y a des alertes (sinon aucune requête ne part). Une alerte se déclenche
une fois : dite à voix haute, envoyée sur Telegram si c'est configuré, puis retirée et gardée dans l'historique.
Gardées dans workspace/alertes_crypto.json : elles survivent au redémarrage de Jarvis, comme les rappels.

Un seuil déjà franchi au moment où on le demande n'alerte pas tout de suite : l'alerte s'arme quand le cours repasse
de l'autre côté (sinon « préviens-moi s'il passe sous 70 000 » dit à 69 000 sonnerait dans la seconde)."""
import json
import logging
import threading
import time

from ..config import CONFIG, RACINE
from . import actifs, bourse, cours

FICHIER = RACINE / "workspace" / "alertes_crypto.json"
INTERVALLE_S = 30
journal = logging.getLogger("crypto")
sur_alerte = lambda alerte, texte: None          # branché par le serveur : voix + Telegram + historique
_verrou = threading.Lock()
_etat = {"alertes": [], "declenchees": []}
_fil: dict = {}


def actif() -> bool:
    return bool(CONFIG.get("crypto", {}).get("actif", True)) and bool(CONFIG.get("crypto", {}).get("alertes", True))


def charger():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        with _verrou:
            _etat["alertes"], _etat["declenchees"] = d.get("alertes", []), d.get("declenchees", [])[-50:]
    except Exception:
        pass


def _sauver():
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    temporaire = FICHIER.with_suffix(".tmp")
    temporaire.write_text(json.dumps({"_lisez_moi": "Alertes de cours de Jarvis (lecture des cours publics, aucun ordre).", **_etat},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    temporaire.replace(FICHIER)


def _seuil_dit(a: dict) -> str:
    return f"{cours.nombre(a['seuil_eur'], 0 if a['seuil_eur'] >= 100 else 2)} {actifs.mot_unite(a.get('unite', 'EUR'), a['seuil_eur'])}"


def decrire(a: dict) -> str:
    nom = actifs.nom_avec_article(a["symbole"])
    if a["type"] == "seuil":
        return f"{nom} passe {'sous' if a['direction'] == 'sous' else 'au-dessus de'} {_seuil_dit(a)}"
    duree = "dans l'heure" if a["fenetre_s"] <= 3600 else "en 24 heures"
    if a.get("dans_les_deux_sens"):
        return f"{nom} bouge de {cours.pourcent(a['pourcent'], signe=False)} {duree}"
    return f"{nom} {'perd' if a['pourcent'] < 0 else 'prend'} {cours.pourcent(a['pourcent'], signe=False)} {duree}"


def variation(symbole: str, fenetre_s: int, prix_actuel: float | None = None) -> float:
    """En pourcentage : sur 24 h, la variation du ticker ; sur une heure, le prix d'il y a 60 minutes (bougies d'une minute).
    Un actif de bourse : la journée, ou l'heure sur les bougies de 5 minutes (actifs.variation)."""
    if not actifs.est_crypto(symbole):
        return actifs.variation(symbole, fenetre_s, prix_actuel)
    if fenetre_s > 3600:
        return cours.prix(symbole)[symbole]["variation_24h"]
    b = cours.bougies(symbole, "1m", 61)
    actuel = prix_actuel if prix_actuel is not None else b[-1]["c"]
    return (actuel / b[0]["o"] - 1) * 100


def _condition(a: dict, prix: float, var: float | None) -> bool:
    if a["type"] == "seuil":
        return prix <= a["seuil_eur"] if a["direction"] == "sous" else prix >= a["seuil_eur"]
    if var is None:
        return False
    if a.get("dans_les_deux_sens"):
        return abs(var) >= abs(a["pourcent"])
    return var <= a["pourcent"] if a["pourcent"] < 0 else var >= a["pourcent"]


def creer(symbole: str, type_: str, seuil_eur: float | None = None, direction: str = "sous", pourcent: float | None = None,
          fenetre_s: int = 86400, dans_les_deux_sens: bool = False, prix=None, var=None) -> dict:
    a = {"id": f"a{int(time.time() * 1000)}", "symbole": symbole, "type": type_, "cree": time.time()}
    if type_ == "seuil":
        a.update(seuil_eur=float(seuil_eur), direction="sous" if direction == "sous" else "dessus")
    else:
        a.update(pourcent=float(pourcent), fenetre_s=int(fenetre_s), dans_les_deux_sens=bool(dans_les_deux_sens))
    p = prix if prix is not None else actifs.prix_natif([symbole])[symbole]
    a["unite"] = "EUR" if actifs.est_crypto(symbole) else (actifs.unite(symbole) if prix is None else "EUR")
    v = var if var is not None or type_ == "seuil" else variation(symbole, a.get("fenetre_s", 86400), p)
    a["prix_a_la_creation"] = p
    a["armee"] = not _condition(a, p, v)          # déjà franchi : s'arme quand le cours repasse de l'autre côté
    a["texte"] = decrire(a)
    with _verrou:
        _etat["alertes"].append(a)
        _sauver()
    demarrer()
    return a


def lister() -> list[dict]:
    with _verrou:
        return list(_etat["alertes"])


def supprimer(symbole: str | None = None) -> list[dict]:
    with _verrou:
        retirees = [a for a in _etat["alertes"] if symbole is None or a["symbole"] == symbole]
        _etat["alertes"] = [a for a in _etat["alertes"] if a not in retirees]
        _sauver()
    return retirees


def declenchees() -> list[dict]:
    with _verrou:
        return list(_etat["declenchees"])


def tour(prix_de=None, variation_de=None, maintenant: float | None = None) -> list[dict]:
    """Une vérification. `prix_de(symboles)` et `variation_de(symbole, fenetre, prix)` sont remplaçables (tests)."""
    alertes = lister()
    if not alertes:
        return []
    prix_de = prix_de or actifs.prix_natif
    variation_de = variation_de or variation
    prix = prix_de(sorted({a["symbole"] for a in alertes}))
    sonnent = []
    for a in alertes:
        p = prix.get(a["symbole"])
        if p is None:
            continue
        v = None if a["type"] == "seuil" else variation_de(a["symbole"], a["fenetre_s"], p)
        if not _condition(a, p, v):
            if not a.get("armee"):
                a["armee"] = True
                with _verrou:
                    _sauver()
            continue
        if not a.get("armee"):
            continue
        a.update(declenchee=maintenant or time.time(), prix=p, variation=v)
        sonnent.append(a)
    if sonnent:
        with _verrou:
            _etat["alertes"] = [x for x in _etat["alertes"] if x["id"] not in {a["id"] for a in sonnent}]
            _etat["declenchees"] = (_etat["declenchees"] + sonnent)[-50:]
            _sauver()
        for a in sonnent:
            sur_alerte(a, phrase(a))
    return sonnent


def phrase(a: dict) -> str:
    nom = actifs.nom_avec_article(a["symbole"], majuscule=False)
    euros_dits = lambda x: actifs.valeur_dite(x, a.get("unite", "EUR"))
    if a["type"] == "seuil":
        sens = "passer sous" if a["direction"] == "sous" else "passer au-dessus de"
        return f"Alerte {'crypto' if actifs.est_crypto(a['symbole']) else 'bourse'} : {nom} vient de {sens} {_seuil_dit(a)}. {'Il est à' if a.get('unite') == 'pts' else 'Il vaut'} {euros_dits(a['prix'])}."
    duree = "en une heure" if a["fenetre_s"] <= 3600 else "en 24 heures"
    sens = "perd" if a["variation"] < 0 else "prend"
    return f"Alerte {'crypto' if actifs.est_crypto(a['symbole']) else 'bourse'} : {nom} {sens} {cours.pourcent(a['variation'], signe=False)} {duree}. {'Il est à' if a.get('unite') == 'pts' else 'Il vaut'} {euros_dits(a['prix'])}."


def _boucle():
    while not _fil.get("arret"):
        try:
            if actif() and lister():
                tour()
        except (cours.Indisponible, bourse.Indisponible):
            journal.warning("alertes : aucune source de cours ne répond")
        except Exception:
            journal.exception("alertes crypto")
        _fil["dernier_tour"] = time.time()
        for _ in range(INTERVALLE_S * 10):
            if _fil.get("arret"):
                return
            time.sleep(0.1)


def demarrer():
    """Lancé par le serveur au démarrage (alertes relues depuis le fichier) et à chaque nouvelle alerte."""
    if _fil.get("fil") and _fil["fil"].is_alive():
        return
    if not _etat["alertes"] and not _etat["declenchees"]:
        charger()
    _fil["arret"] = False
    _fil["fil"] = threading.Thread(target=_boucle, daemon=True, name="alertes-crypto")
    _fil["fil"].start()


def arreter():
    _fil["arret"] = True
