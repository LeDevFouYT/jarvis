"""Test de la brique crypto 3 : le portefeuille fictif (vidéo 4).

    python -m jarvis.tests.crypto_portefeuille

Sur un fichier temporaire (le vrai workspace/portefeuille.json n'est pas touché) :
1. les phrases de la consigne sont comprises (« achète pour 500 € de Bitcoin », « vends la moitié de mon Ethereum »,
   « combien je vaux ? », « remets le portefeuille à zéro »), et une demande de conseil n'est jamais un ordre ;
2. chaque ordre attend le « oui » : rien ne change avant, rien ne change sur un « non » ;
3. les comptes sont justes au centime : 0,1 % de frais, quantités, euros restants, valeur, plus et moins-values ;
4. Jarvis dit toujours que c'est de l'argent fictif, et chaque chiffre de « combien je vaux » est vérifiable ;
5. le portefeuille survit à un redémarrage (relu depuis le fichier), le journal garde chaque ordre, la remise à
   zéro archive l'ancien ;
6. un ordre au prix réel du moment (Binance) ; aucune requête autre qu'une lecture publique ne part.
Les mesures vont dans workspace/mesures/crypto.json (section 3_portefeuille)."""
import json
import sys
import tempfile
import time
from pathlib import Path

import requests

from ._commun import Verifs


def phrases(v: Verifs):
    from .. import commandes
    attendus = {
        "Achète pour 500 € de Bitcoin": ("crypto_ordre", {"sens": "achat", "crypto": "BTC", "montant_eur": 500.0}),
        "Jarvis, achète pour 1 000 euros de Solana.": ("crypto_ordre", {"sens": "achat", "crypto": "SOL", "montant_eur": 1000.0}),
        "achète pour 250€ d'Ethereum": ("crypto_ordre", {"sens": "achat", "crypto": "ETH", "montant_eur": 250.0}),
        "Vends la moitié de mon Ethereum": ("crypto_ordre", {"sens": "vente", "crypto": "ETH", "fraction": 0.5}),
        "vends tout mon bitcoin": ("crypto_ordre", {"sens": "vente", "crypto": "BTC", "fraction": 1.0}),
        "vends pour 200 € de Solana": ("crypto_ordre", {"sens": "vente", "crypto": "SOL", "montant_eur": 200.0}),
        "Combien je vaux ?": ("portefeuille", {"action": "valeur"}),
        "Jarvis, combien vaut mon portefeuille ?": ("portefeuille", {"action": "valeur"}),
        "Remets le portefeuille à zéro": ("portefeuille", {"action": "zero"}),
        "remets mon portefeuille à 10 000 euros": ("portefeuille", {"action": "zero"}),
    }
    faux = {p: commandes.analyser(p) for p, a in attendus.items() if commandes.analyser(p) != a}
    v.ok(not faux, "les ordres et questions de la consigne sont compris", faux or f"{len(attendus)} phrases")
    conseils = ["Je devrais acheter du Bitcoin ?", "Est-ce que je dois vendre mon Ethereum ?", "Tu me conseilles d'acheter du Solana ?"]
    faux = {p: commandes.analyser(p) for p in conseils if commandes.analyser(p)[0] != "crypto_conseil"}
    v.ok(not faux, "une demande de conseil n'est jamais un ordre (garde-fou)", faux or "3 questions")
    v.ok(commandes.analyser("Achète du pain")[0] is None, "« achète du pain » n'est pas un ordre crypto")


def comptes(v: Verifs, mesures: dict):
    from .. import confirmations
    from ..crypto import actions, cours
    from ..crypto import portefeuille as P
    from ..outils import portefeuille as outil
    from ..youtube import verification

    prix = {"BTC": 72_000.0, "ETH": 2_000.0, "SOL": 90.0}
    vrai_prix = cours.prix
    cours.prix = lambda symboles: {s: {"symbole": s, "prix": prix[s], "variation_24h": 0.0, "source": "essai", "periode": "24 h",
                                       "quand": time.time()} for s in ([symboles] if isinstance(symboles, str) else symboles)}
    try:
        v.ok(P.charger().valeur({}) == 10_000, "départ : 10 000 € fictifs", P.charger().euros)
        q = actions.executer("crypto_ordre", {"sens": "achat", "crypto": "BTC", "montant_eur": 500.0})
        v.ok("fictif" in q and q.endswith("Oui ou non ?") and confirmations.en_attente(), "l'achat demande une confirmation oui / non", q)
        v.ok(P.charger().euros == 10_000 and not P.FICHIER.exists(), "rien ne change avant le « oui »")
        r = confirmations.confirmer()
        livre = P.charger()
        attendu = 499.5 / 72_000
        v.ok(abs(livre.euros - 9_500) < 1e-9 and abs(livre.positions["BTC"] - attendu) < 1e-12,
             "après le « oui » : 500 € dépensés, 0,1 % de frais, la bonne quantité", f"{livre.positions['BTC']:.8f} BTC · {r}")
        v.ok("argent fictif" in r and "50 centimes de frais" in r, "la réponse dit « argent fictif » et les frais", r)

        actions.executer("crypto_ordre", {"sens": "achat", "crypto": "ETH", "montant_eur": 1000.0})
        r = confirmations.refuser()
        v.ok(P.charger().euros == 9_500 and "ETH" not in P.charger().positions, "sur un « non », rien ne change", r)
        actions.executer("crypto_ordre", {"sens": "achat", "crypto": "ETH", "montant_eur": 1000.0})
        confirmations.confirmer()

        prix.update(BTC=75_000.0, ETH=1_900.0)
        q = actions.executer("crypto_ordre", {"sens": "vente", "crypto": "ETH", "fraction": 0.5})
        v.ok("la moitié de votre Ethereum" in q and "fictif" in q, "la vente de la moitié est confirmée avant", q)
        confirmations.confirmer()
        livre = P.charger()
        eth = 999.0 / 2_000
        attendu_euros = 8_500 + eth / 2 * 1_900 * 0.999
        v.ok(abs(livre.positions["ETH"] - eth / 2) < 1e-12 and abs(livre.euros - attendu_euros) < 1e-6,
             "la moitié vendue au nouveau prix, frais déduits", f"{livre.euros:.4f} € (attendu {attendu_euros:.4f})")

        phrase = outil.executer("valeur")
        valeur_attendue = attendu_euros + 499.5 / 72_000 * 75_000 + eth / 2 * 1_900
        v.ok(abs(livre.valeur({"BTC": 75_000, "ETH": 1_900}) - valeur_attendue) < 1e-6 and "fictif" in phrase,
             "« combien je vaux » : la valeur est juste et dite fictive", phrase)
        res = verification.verifier(phrase, outil.faits())
        v.ok(res["total"] >= 3 and not res["ecarts"], "chaque chiffre de la réponse est dans les faits", f"{res['trouves']}/{res['total']}")
        gain = valeur_attendue - 10_000
        v.ok(("hausse" in phrase) == (gain > 0), "la plus ou moins-value est dans le bon sens", f"{gain:+.2f} €")

        q = actions.executer("crypto_ordre", {"sens": "vente", "crypto": "SOL", "fraction": 0.5})
        v.ok("ne contient pas de Solana" in q and not confirmations.en_attente(), "vendre ce qu'on n'a pas : refusé sans question", q)
        actions.executer("crypto_ordre", {"sens": "achat", "crypto": "SOL", "montant_eur": 50_000.0})
        r = confirmations.confirmer()
        v.ok(P.charger().euros < 0.01 and "SOL" in P.charger().positions, "acheter plus que ce qu'on a : réduit aux euros restants", r)

        # redémarrage : tout est relu depuis le fichier
        relu = json.loads(P.FICHIER.read_text(encoding="utf-8"))
        v.ok(len(relu["journal"]) == 4 and all(k in relu["journal"][0] for k in ("prix", "frais_eur", "quantite", "quand")),
             "le journal garde chaque ordre (prix, quantité, frais, heure)", f"{len(relu['journal'])} ordres")
        v.ok(P.charger().positions == livre.positions | {"SOL": P.charger().positions["SOL"]}, "le portefeuille survit à un redémarrage")
        mesures["ordres"] = [{k: o[k] for k in ("sens", "symbole", "prix", "montant_eur", "frais_eur")} for o in relu["journal"]]

        phrase = actions.executer("portefeuille", {"action": "zero"})
        archives = list(outil.ARCHIVES.glob("portefeuille_*.json"))
        v.ok(P.charger().euros == 10_000 and not P.charger().positions and not P.charger().journal and archives,
             "« remets le portefeuille à zéro » : 10 000 €, ancien journal archivé", phrase)
    finally:
        cours.prix = vrai_prix


def prix_reel(v: Verifs, mesures: dict):
    from .. import confirmations
    from ..crypto import actions, cours
    from ..crypto import portefeuille as P
    postes = []
    vrai_post = requests.post
    requests.post = lambda *a, **k: postes.append(a) or (_ for _ in ()).throw(RuntimeError("POST interdit"))
    try:
        try:
            binance = cours.prix("SOL")["SOL"]["prix"]
        except cours.Indisponible:
            v.info("pas d'Internet : l'ordre au prix réel est ignoré")
            return
        t = time.time()
        actions.executer("crypto_ordre", {"sens": "achat", "crypto": "SOL", "montant_eur": 1000.0})
        r = confirmations.confirmer()
        duree = time.time() - t
        o = P.charger().journal[-1]
        v.ok(abs(o["prix"] / binance - 1) < 0.01, "l'ordre passe au prix réel du moment", f"{cours.euros(o['prix'])} (Binance {cours.euros(binance)}) · {r}")
        v.ok(not postes, "aucune requête d'écriture n'est partie : aucun ordre réel", f"{len(postes)} POST")
        phrase = actions.executer("portefeuille", {"action": "valeur"})
        v.info(phrase)
        mesures.update(ordre_reel={"symbole": "SOL", "montant_eur": 1000, "prix": o["prix"], "frais_eur": o["frais_eur"],
                                   "duree_ms": round(duree * 1000)}, valeur_eur=round(P.charger().valeur({"SOL": binance}), 2),
                       exemple_valeur=phrase)
    finally:
        requests.post = vrai_post


def main() -> int:
    from ..crypto import mesures as fichier
    from ..crypto import portefeuille as P
    from ..outils import portefeuille as outil
    v = Verifs("Crypto 3 · le portefeuille fictif")
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_portefeuille_"))
    vrai_fichier, vraies_archives = P.FICHIER, outil.ARCHIVES
    P.FICHIER, outil.ARCHIVES = dossier / "portefeuille.json", dossier / "archives"
    mesures: dict = {}
    try:
        phrases(v)
        comptes(v, mesures)
        prix_reel(v, mesures)
    finally:
        P.FICHIER, outil.ARCHIVES = vrai_fichier, vraies_archives
    v.ok(not vrai_fichier.exists() or json.loads(vrai_fichier.read_text(encoding="utf-8")).get("_lisez_moi"),
         "le vrai portefeuille n'a pas été touché par le test")
    code = v.fin()
    fichier.ecrire("3_portefeuille", resultat_test=f"{v.total - len(v.echecs)}/{v.total}", quand=time.strftime("%Y-%m-%d %H:%M"), **mesures)
    return code


if __name__ == "__main__":
    sys.exit(main())
