"""Outil alerte_crypto (vidéo 4, consigne 5) : « préviens-moi si le Bitcoin passe sous 70 000 € », « quelles sont mes
alertes ? », « supprime l'alerte Bitcoin ». La surveillance (toutes les 30 s) est dans jarvis/crypto/alertes.py."""
from ..crypto import alertes, cours

NOM = "alerte_crypto"
DESCRIPTION = ("Alertes de cours crypto, dites à voix haute et envoyées sur Telegram : « creer » un seuil (seuil_eur et direction "
               "sous ou dessus) ou une variation (pourcent, négatif pour une baisse ; fenetre_s 3600 pour une heure, 86400 pour "
               "une journée) ; « lister » ; « supprimer » (une crypto, ou toutes).")
PARAMETRES = {
    "action": {"type": "string", "enum": ["creer", "lister", "supprimer"]},
    "crypto": {"type": "string"},
    "type": {"type": "string", "enum": ["seuil", "variation"]},
    "seuil_eur": {"type": "number"}, "direction": {"type": "string", "enum": ["sous", "dessus"]},
    "pourcent": {"type": "number"}, "fenetre_s": {"type": "integer"},
}
REQUIS = ["action"]
DIRECT = True


def _panneau():
    from ..crypto import actifs
    from . import panneaux
    a = alertes.lister()
    panneaux.liste(f"Alertes crypto · {len(a)}", [{"titre": x["texte"][:1].upper() + x["texte"][1:],
                                                  "detail": f"créée à {actifs.valeur_ecrite(x['prix_a_la_creation'], x.get('unite', 'EUR'))}" + ("" if x.get("armee") else " · déjà franchi, s'armera au retour"),
                                                  "meta": "30 s"} for x in a],
                   vide="Aucune alerte.", cle="alertes_crypto")


def executer(action: str = "lister", crypto: str = "", type: str = "seuil", seuil_eur=None, direction: str = "sous",
             pourcent=None, fenetre_s=86400, dans_les_deux_sens: bool = False, toutes: bool = False) -> str:
    from ..crypto import actifs
    symbole = crypto if crypto and (actifs.est_crypto(crypto) or actifs.est_bourse(crypto)) else (
        (crypto or "").upper() if (crypto or "").upper() in cours.CRYPTOS else actifs.reconnaitre(crypto or ""))
    try:
        if action == "lister":
            a = alertes.lister()
            _panneau()
            if not a:
                return "Vous n'avez aucune alerte crypto."
            return f"Vous avez {len(a)} alerte{'s' if len(a) > 1 else ''} : " + " ; ".join(x["texte"] for x in a) + "."
        if action == "supprimer":
            retirees = alertes.supprimer(None if toutes or not symbole else symbole)
            _panneau()
            if not retirees:
                return "Il n'y avait aucune alerte à supprimer."
            return f"J'ai supprimé {len(retirees)} alerte{'s' if len(retirees) > 1 else ''} : " + " ; ".join(x["texte"] for x in retirees) + "."
        if not symbole:
            return f"Je ne connais pas la crypto « {crypto} »."
        if type == "seuil":
            if not seuil_eur:
                return "À quel prix, monsieur ?"
            a = alertes.creer(symbole, "seuil", seuil_eur=float(seuil_eur), direction=direction)
        else:
            if not pourcent:
                return "De combien de pour cent, monsieur ?"
            a = alertes.creer(symbole, "variation", pourcent=float(pourcent), fenetre_s=int(fenetre_s or 86400),
                              dans_les_deux_sens=bool(dans_les_deux_sens))
        _panneau()
        deja = "" if a["armee"] else " C'est déjà le cas : je vous préviendrai la prochaine fois que ça arrivera."
        verbe = "Il est à" if a.get("unite") == "pts" else "Il vaut"
        return (f"C'est noté : je vous préviens si {a['texte']}. {verbe} {actifs.valeur_dite(a['prix_a_la_creation'], a.get('unite', 'EUR'))} ; "
                f"je vérifie toutes les 30 secondes, et l'alerte survit à mon redémarrage.{deja}")
    except Exception as e:
        if type(e).__name__ != "Indisponible":
            raise
        return "Aucune source de cours ne répond : je ne peux pas poser d'alerte sans cours réel."
