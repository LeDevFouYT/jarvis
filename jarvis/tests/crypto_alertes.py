"""Test de la brique crypto 5 : les alertes (vidéo 4).

    python -m jarvis.tests.crypto_alertes

Sur un fichier temporaire (les vraies alertes ne sont pas touchées) :
1. les phrases sont comprises : « préviens-moi si le Bitcoin passe sous 70 000 € », « …s'il prend 5 % dans la
   journée » (la crypto dont on parlait), « …perd 1 % dans l'heure », « quelles sont mes alertes ? », « supprime
   l'alerte Bitcoin » ;
2. le seuil sonne quand le cours le franchit, pas avant ; un seuil déjà franchi s'arme au retour ; une alerte sonne
   une fois, est dite à voix haute avec le vrai prix, marquée pour Telegram, puis rangée dans l'historique ;
3. les variations : sur une heure (bougies d'une minute, le prix d'il y a 60 min) et sur la journée (24 h) ;
4. les alertes survivent au redémarrage (relues depuis le fichier, le fil de surveillance repart) ;
5. la surveillance tourne toutes les 30 s et ne sort sur Internet que s'il y a des alertes ;
6. en vrai : une alerte posée au prix réel, une vérification réelle, la variation d'une heure lue sur Binance.
Les mesures vont dans workspace/mesures/crypto.json (section 5_alertes)."""
import json
import sys
import tempfile
import time
from pathlib import Path

from ._commun import Verifs


def phrases(v: Verifs):
    from .. import commandes
    from ..crypto import vocal
    attendus = {
        "Préviens-moi si le Bitcoin passe sous 70 000 €": {"action": "creer", "crypto": "BTC", "type": "seuil", "seuil_eur": 70000.0, "direction": "sous"},
        "Jarvis, préviens-moi si l'Ethereum dépasse 2 500 euros": {"action": "creer", "crypto": "ETH", "type": "seuil", "seuil_eur": 2500.0, "direction": "dessus"},
        "Préviens-moi si le Bitcoin perd 1 % dans l'heure.": {"action": "creer", "crypto": "BTC", "type": "variation", "pourcent": -1.0, "fenetre_s": 3600},
        "Quelles sont mes alertes ?": {"action": "lister"},
        "Supprime l'alerte Bitcoin": {"action": "supprimer", "crypto": "BTC", "toutes": False},
        "supprime toutes mes alertes": {"action": "supprimer", "crypto": None, "toutes": True},
    }
    faux = {}
    for p, a in attendus.items():
        r = commandes.analyser(p)
        if r[0] != "crypto_alerte" or any(r[1].get(k) != val for k, val in a.items()):
            faux[p] = r
    commandes.analyser("Combien vaut le Solana ?")             # on parle du Solana…
    r = commandes.analyser("Préviens-moi s'il prend 5 % dans la journée")
    if r[0] != "crypto_alerte" or r[1].get("crypto") != "SOL" or r[1].get("pourcent") != 5.0 or r[1].get("fenetre_s") != 86400:
        faux["…s'il prend 5 % dans la journée (après le Solana)"] = r
    v.ok(not faux, "les phrases des alertes sont comprises, « s'il » désigne la crypto dont on parlait", faux or f"{len(attendus) + 1} phrases")
    vocal.dernier_symbole = "BTC"


def logique(v: Verifs, mesures: dict):
    from ..crypto import alertes as A
    parlees = []
    A.sur_alerte = lambda a, texte: parlees.append((a, texte))
    prix = {"BTC": 72_000.0, "ETH": 2_100.0, "SOL": 92.0}
    var = {("BTC", 3600): -0.2, ("SOL", 86400): 1.0}
    pde = lambda symboles: {s: prix[s] for s in symboles}
    vde = lambda s, f, p: var.get((s, f), 0.0)

    a1 = A.creer("BTC", "seuil", seuil_eur=70_000, direction="sous", prix=prix["BTC"])
    a2 = A.creer("ETH", "seuil", seuil_eur=2_000, direction="sous", prix=prix["ETH"] * 0 + 1_950)    # déjà sous 2 000
    a3 = A.creer("BTC", "variation", pourcent=-1, fenetre_s=3600, prix=prix["BTC"], var=-0.2)
    a4 = A.creer("SOL", "variation", pourcent=5, fenetre_s=86400, prix=prix["SOL"], var=1.0)
    v.ok(a1["armee"] and not a2["armee"] and a3["armee"] and a4["armee"], "un seuil déjà franchi à la création attend d'être repassé",
         f"{a2['texte']} : armée = {a2['armee']}")
    v.ok(A.tour(pde, vde) == [] and not parlees, "rien ne sonne tant que rien n'est franchi")

    prix["BTC"] = 70_500.0
    v.ok(A.tour(pde, vde) == [], "70 500 € : pas encore sous 70 000 €")
    prix["BTC"] = 69_990.0
    sonne = A.tour(pde, vde)
    v.ok([x["id"] for x in sonne] == [a1["id"]] and len(parlees) == 1, "69 990 € : l'alerte « sous 70 000 € » sonne", parlees[-1][1] if parlees else "")
    v.ok("69 990 euros" in parlees[-1][1] and "Alerte crypto" in parlees[-1][1], "la phrase dit le vrai prix, en euros")
    v.ok(A.tour(pde, vde) == [] and a1["id"] not in [x["id"] for x in A.lister()] and A.declenchees()[-1]["id"] == a1["id"],
         "elle ne sonne qu'une fois, puis passe dans l'historique")

    prix["ETH"] = 2_050.0
    A.tour(pde, vde)
    v.ok(next(x for x in A.lister() if x["id"] == a2["id"])["armee"], "l'Ethereum repasse au-dessus de 2 000 € : l'alerte s'arme")
    prix["ETH"] = 1_990.0
    v.ok([x["id"] for x in A.tour(pde, vde)] == [a2["id"]], "puis sonne quand il repasse dessous")

    var[("BTC", 3600)] = -1.3
    sonne = A.tour(pde, vde)
    v.ok([x["id"] for x in sonne] == [a3["id"]] and "perd 1,3 % en une heure" in parlees[-1][1], "« perd 1 % dans l'heure » : sonne à −1,3 %", parlees[-1][1])
    var[("SOL", 86400)] = 5.4
    sonne = A.tour(pde, vde)
    v.ok([x["id"] for x in sonne] == [a4["id"]] and "prend 5,4 % en 24 heures" in parlees[-1][1], "« prend 5 % dans la journée » : sonne à +5,4 %", parlees[-1][1])
    mesures["declenchees_essai"] = [t for _, t in parlees]


def redemarrage(v: Verifs):
    from ..crypto import alertes as A
    from ..outils import alerte_crypto
    A.creer("BTC", "seuil", seuil_eur=50_000, direction="sous", prix=72_000.0)
    A.creer("ETH", "variation", pourcent=-3, fenetre_s=86400, prix=2_100.0, var=0.0)
    avant = [a["texte"] for a in A.lister()]
    A.arreter()
    A._etat["alertes"], A._etat["declenchees"] = [], []            # Jarvis s'éteint : plus rien en mémoire
    time.sleep(0.2)
    from .. import outils
    outils_demarrer = outils.demarrer_taches_de_fond.__code__.co_names
    A.charger()
    if A.lister():
        A.demarrer()
    apres = [a["texte"] for a in A.lister()]
    v.ok(apres == avant and "alertes" in outils_demarrer, "les alertes survivent au redémarrage (relues au démarrage du serveur)", apres)
    v.ok(A._fil.get("fil") and A._fil["fil"].is_alive(), "la surveillance repart toute seule")
    r = alerte_crypto.executer("lister")
    v.ok(r.startswith("Vous avez 2 alertes") and "Bitcoin passe sous 50 000 euros" in r, "« quelles sont mes alertes ? »", r)
    r = alerte_crypto.executer("supprimer", crypto="BTC")
    v.ok("1 alerte" in r and len(A.lister()) == 1, "« supprime l'alerte Bitcoin » ne retire que celle du Bitcoin", r)
    A.supprimer()


def surveillance(v: Verifs, mesures: dict):
    from .. import compteur
    from ..crypto import alertes as A
    from ..crypto import cours
    A.supprimer()
    avant = compteur.sorties
    A.tour()
    v.ok(compteur.sorties == avant and A.INTERVALLE_S == 30, "sans alerte, la surveillance ne sort pas sur Internet ; un tour toutes les 30 s")
    try:
        prix = cours.prix("BTC")["BTC"]["prix"]
    except cours.Indisponible:
        v.info("pas d'Internet : l'essai réel est ignoré")
        return
    from ..outils import alerte_crypto
    r = alerte_crypto.executer("creer", crypto="bitcoin", type="variation", pourcent=-1, fenetre_s=3600)
    a = A.lister()[-1]
    var = A.variation("BTC", 3600)
    v.ok("je vérifie toutes les 30 secondes" in r and a["prix_a_la_creation"] > 1000, "en vrai : alerte posée au prix réel", r)
    v.ok(-20 < var < 20, "la variation d'une heure est lue sur les bougies d'une minute de Binance", f"{cours.pourcent(var)} en une heure")
    t = time.time()
    sonne = A.tour()
    mesures["tour_reel_ms"] = round((time.time() - t) * 1000)
    v.ok(isinstance(sonne, list), "un tour de surveillance réel", f"{mesures['tour_reel_ms']} ms, {'sonne' if sonne else 'rien ne sonne'}")
    mesures.update(exemple_creation=r, variation_1h_btc=round(var, 3), prix_btc=prix)
    A.supprimer()


def main() -> int:
    from ..crypto import alertes as A
    from ..crypto import mesures as fichier
    v = Verifs("Crypto 5 · les alertes")
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_alertes_"))
    vrai = A.FICHIER
    A.FICHIER = dossier / "alertes_crypto.json"
    A._etat["alertes"], A._etat["declenchees"] = [], []
    mesures: dict = {}
    try:
        phrases(v)
        logique(v, mesures)
        redemarrage(v)
        surveillance(v, mesures)
    finally:
        A.arreter()
        A.FICHIER = vrai
    code = v.fin()
    fichier.ecrire("5_alertes", resultat_test=f"{v.total - len(v.echecs)}/{v.total}", quand=time.strftime("%Y-%m-%d %H:%M"),
                   survit_au_redemarrage=True, intervalle_s=A.INTERVALLE_S, **mesures)
    return code


if __name__ == "__main__":
    sys.exit(main())
