"""Les commandes crypto reconnues par vocal.py, exécutées par le serveur sans le cerveau.

Chaque action passe par le registre des outils (outils.executer) : mêmes événements dans le HUD (colonne des outils),
même journal, même limite de temps que si le cerveau l'avait appelée."""
from .. import outils
from . import AVERTISSEMENT, cours


def _titre() -> str:
    from .. import cerveau
    return cerveau.TITRE


def conseil(symbole: str) -> str:
    """Le garde-fou : « je devrais acheter ? » -> les chiffres, et jamais une recommandation."""
    try:
        from . import actifs
        from ..outils.crypto import _sens
        c = actifs.cotation(symbole)
        quand = "sur 24 heures" if actifs.est_crypto(symbole) else "sur la journée"
        faits = (f"{actifs.nom_avec_article(symbole, majuscule=True)} {'est à' if c['unite'] == 'pts' else 'vaut'} "
                 f"{actifs.valeur_dite(c['prix'], c['unite'])}, {_sens(c['variation'])} {quand}. ")
    except Exception:
        faits = ""
    return (f"{faits}{AVERTISSEMENT}, {_titre()} : je vous donne les chiffres, la décision vous appartient. "
            f"Et ma seule expérience du trading, c'est de l'argent fictif.")


VISION = ("Décris ce graphique financier affiché à l'écran : l'actif et la période si on les lit, la tendance générale, "
          "le dernier prix lisible, le plus haut et le plus bas visibles. Des faits seulement : aucun conseil, aucune "
          "prédiction, ne dis jamais d'acheter ou de vendre. Trois phrases au plus, en français.")


def executer(commande: str, argument) -> str:
    if commande == "crypto":
        return outils.executer("crypto", argument)
    if commande == "bourse":
        return outils.executer("bourse", argument)
    if commande == "crypto_conseil":
        return conseil(argument)
    if commande == "crypto_ordre":
        return outils.executer("portefeuille", {"action": argument["sens"], **{k: v for k, v in argument.items() if k != "sens"}})
    if commande == "portefeuille":
        return outils.executer("portefeuille", argument)
    if commande == "crypto_replay":
        return outils.executer("replay_crypto", argument)
    if commande == "crypto_alerte":
        return outils.executer("alerte_crypto", argument)
    if commande == "crypto_vision":
        return outils.executer("voir_ecran", {"ecran": "principal", "question": VISION})
    return ""
