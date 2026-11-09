"""Test de la brique crypto 1 : les cours (vidéo 4).

    python -m jarvis.tests.crypto_cours

1. les noms dits à l'oral sont reconnus (« bitcoin », « l'éther », « solana »), et les phrases de la consigne vont à
   l'outil sans passer par le cerveau, jamais une phrase ordinaire ;
2. Binance en vrai : prix en euros plausibles, variation sur 24 h, bougies 1 h et 1 jour dans l'ordre et au passé ;
3. le cache court : une seconde question dans les 20 s ne repart pas sur Internet ; chaque requête est comptée ;
4. Kraken en repli quand Binance ne répond pas, au même prix à 2 % près ;
5. rien ne part ailleurs que vers les deux API publiques, sans clé ni en-tête d'authentification ;
6. la phrase dite : en euros (pas « € », mal lu par la voix), aucun conseil, et chaque chiffre retrouvé par le
   vérificateur dans les faits de l'outil.
Les mesures vont dans workspace/mesures/crypto.json (section 1_cours)."""
import re
import statistics
import sys
import time
from urllib.parse import urlparse

import requests

from ._commun import Verifs


def noms(v: Verifs):
    from ..crypto.cours import reconnaitre
    attendus = {"bitcoin": "BTC", "Combien vaut le Bitcoin ?": "BTC", "l'éther": "ETH", "l’Ethereum": "ETH", "étherium": "ETH",
                "solana": "SOL", "Solana": "SOL", "le Bitcoin Cash": "BCH", "du XRP": "XRP", "le ripple": "XRP",
                "dogecoin": "DOGE", "Cardano": "ADA", "BTC": "BTC"}
    faux = {t: reconnaitre(t) for t, s in attendus.items() if reconnaitre(t) != s}
    v.ok(not faux, "les noms dits à l'oral sont reconnus", faux or f"{len(attendus)} variantes")
    v.ok(reconnaitre("Ouvre le bloc-notes") is None and reconnaitre("le soleil se lève") is None,
         "une phrase sans crypto n'en trouve pas")


def phrases(v: Verifs):
    from .. import commandes
    attendus = {
        "Combien vaut le Bitcoin ?": ("crypto", "cours", "BTC", "24h"),
        "Jarvis, combien vaut le bitcoin": ("crypto", "cours", "BTC", "24h"),
        "Comment va l'Ethereum aujourd'hui ?": ("crypto", "cours", "ETH", "24h"),
        "Montre-moi l'Ethereum sur 7 jours.": ("crypto", "cours", "ETH", "7j"),
        "Quel est le cours du Solana sur 30 jours ?": ("crypto", "cours", "SOL", "30j"),
        "Et l'éther ?": ("crypto", "cours", "ETH", "24h"),
        "Qu'est-ce qui monte le plus ?": ("crypto", "classement", None, None),
        "Quelle crypto baisse le plus aujourd'hui ?": ("crypto", "classement", None, None),
    }
    faux = {}
    for p, (c, action, s, periode) in attendus.items():
        r = commandes.analyser(p)
        if r[0] != c or r[1].get("action") != action or (s and r[1].get("crypto") != s) or (periode and r[1].get("periode") != periode):
            faux[p] = r
    v.ok(not faux, "les phrases de la consigne vont à l'outil crypto, avec la bonne période", faux or f"{len(attendus)} phrases")
    ordinaires = ["Quelle heure est-il ?", "Ouvre le bloc-notes", "Combien vaut un euro en dollars ?",
                  "Parle-moi de l'histoire du Bitcoin", "Montre-moi la Terre", "Retiens que j'aime le bitcoin",
                  "Qui a inventé le Bitcoin ?"]
    faux = {p: commandes.analyser(p) for p in ordinaires if (commandes.analyser(p)[0] or "").startswith("crypto")}
    v.ok(not faux, "une phrase ordinaire ne déclenche pas l'outil crypto", faux or "aucune")


def sources(v: Verifs, mesures: dict):
    from .. import compteur
    from ..crypto import cours
    envois = []
    vrai_get = requests.get

    def espion(url, **kw):                 # tout ce qui part vraiment sur le réseau
        envois.append({"url": url, "entetes": kw.get("headers") or {}, "params": kw.get("params") or {}})
        return vrai_get(url, **kw)

    requests.get = espion
    try:
        avant = compteur.sorties
        t = time.time()
        try:
            p = cours.prix(["BTC", "ETH", "SOL"])
        except cours.Indisponible:
            v.info("ni Binance ni Kraken ne répondent : pas d'Internet, l'essai réseau est ignoré")
            return
        ms_binance = round((time.time() - t) * 1000)
        btc = p["BTC"]
        v.ok(btc["source"] == "Binance", "la source principale est Binance", btc["source"])
        v.ok(1_000 < btc["prix"] < 1_000_000 and 10 < p["ETH"]["prix"] < 100_000 and 1 < p["SOL"]["prix"] < 10_000,
             "les prix en euros sont plausibles", f"BTC {cours.euros(btc['prix'])} · ETH {cours.euros(p['ETH']['prix'])} · SOL {cours.euros(p['SOL']['prix'])}")
        v.ok(all(abs(x["variation_24h"]) < 60 for x in p.values()), "la variation sur 24 h est donnée",
             " · ".join(f"{s} {cours.pourcent(x['variation_24h'])}" for s, x in p.items()))
        v.ok(compteur.sorties == avant + 1 and compteur.details.get("crypto_binance"),
             "la requête compte une sortie Internet", f"{compteur.sorties - avant} sortie(s)")

        avant = compteur.sorties
        t = time.time()
        cours.prix(["SOL", "ETH", "BTC"])
        ms_cache = round((time.time() - t) * 1000, 2)
        v.ok(compteur.sorties == avant, "une seconde question dans les 20 s vient du cache", f"{ms_cache} ms, 0 sortie")

        h = cours.bougies("BTC", "1h", 48)
        j = cours.bougies("ETH", "1d", 30)
        maintenant = time.time()
        v.ok(len(h) == 48 and len(j) == 30, "bougies 1 h et 1 jour reçues", f"{len(h)} × 1 h, {len(j)} × 1 j")
        v.ok(all(a["t"] < b["t"] for a, b in zip(h, h[1:])) and h[-1]["t"] <= maintenant and h[-1]["t"] > maintenant - 7200,
             "les bougies sont dans l'ordre, au passé, la dernière a moins de 2 h")
        v.ok(all(b["l"] <= min(b["o"], b["c"]) <= max(b["o"], b["c"]) <= b["h"] for b in h + j), "chaque bougie tient debout (bas ≤ ouverture, clôture ≤ haut)")

        # Kraken en repli : Binance rendu injoignable
        ancien = cours.BINANCE
        cours.BINANCE = "https://127.0.0.1:9/api/v3"
        cours._cache.clear()
        replis = cours.statistiques["replis"]
        try:
            t = time.time()
            k = cours.prix("BTC")["BTC"]
            ms_kraken = round((time.time() - t) * 1000)
            kb = cours.bougies("BTC", "1h", 48)
        finally:
            cours.BINANCE = ancien
            cours._cache.clear()
        ecart = abs(k["prix"] / btc["prix"] - 1) * 100
        v.ok(k["source"] == "Kraken" and cours.statistiques["replis"] >= replis + 2, "Binance muet : Kraken prend le relais",
             f"{cours.euros(k['prix'])}, {ms_kraken} ms, variation {k['periode']}")
        v.ok(ecart < 2, "Kraken et Binance donnent le même prix à 2 % près", f"écart {ecart:.2f} %")
        v.ok(len(kb) == 48 and kb[-1]["t"] > maintenant - 7200, "les bougies aussi en repli", f"{len(kb)} × 1 h")

        hotes = {urlparse(e["url"]).hostname for e in envois}
        v.ok(hotes <= {"api.binance.com", "api.kraken.com", "127.0.0.1"}, "rien ne part ailleurs que vers les deux API publiques", sorted(hotes))
        cles = [e for e in envois if any(x.lower() in ("authorization", "x-mbx-apikey", "api-key", "api-sign") for x in e["entetes"])
                or any(x in e["params"] for x in ("signature", "apikey", "nonce"))]
        v.ok(not cles, "aucune clé, aucune signature, aucun ordre : des lectures publiques", f"{len(envois)} requêtes GET")
        mesures.update(prix_lus={s: x["prix"] for s, x in p.items()}, variation_24h={s: round(x["variation_24h"], 2) for s, x in p.items()},
                       kraken_btc=k["prix"], ecart_kraken_pct=round(ecart, 3),
                       temps_reponse_ms={"binance": ms_binance, "kraken": ms_kraken, "cache": ms_cache})
    finally:
        requests.get = vrai_get


def outil(v: Verifs, mesures: dict):
    from ..crypto import cours
    from ..outils import crypto as outil_crypto
    from ..youtube import verification
    exemples = []
    for crypto, periode in (("bitcoin", "24h"), ("l'éther", "7j"), ("solana", "30j")):
        phrase = outil_crypto.executer("cours", crypto, periode)
        if "ne répondent" in phrase:
            v.info("pas d'Internet : l'essai de l'outil est ignoré")
            return
        resultat = verification.verifier(phrase, outil_crypto.faits())
        exemples.append({"question": f"{crypto} {periode}", "phrase": phrase, "chiffres": resultat["total"], "trouves": resultat["trouves"]})
        v.ok(resultat["total"] >= 2 and not resultat["ecarts"], f"« {crypto} » ({periode}) : chaque chiffre dit est dans les faits",
             f"{resultat['trouves']}/{resultat['total']} · {phrase}")
    v.ok(all("euros" in e["phrase"] and "€" not in e["phrase"] for e in exemples), "les prix sont dits « euros » (la voix lit « € » de travers)")
    phrase = outil_crypto.executer("classement")
    resultat = verification.verifier(phrase, outil_crypto.faits())
    v.ok("le plus" in phrase and not resultat["ecarts"], "« qu'est-ce qui monte le plus » : classement vérifié",
         f"{resultat['trouves']}/{resultat['total']} · {phrase}")
    exemples.append({"question": "classement", "phrase": phrase, "chiffres": resultat["total"], "trouves": resultat["trouves"]})
    conseils = [e["phrase"] for e in exemples if re.search(r"\b(achetez|vendez|investissez|je vous conseille|bonne affaire|c'est le moment)\b", e["phrase"], re.I)]
    v.ok(not conseils, "des faits seulement : aucun conseil dans les réponses", conseils or "aucun")
    v.ok("Je ne connais pas" in outil_crypto.executer("cours", "patate"), "une crypto inconnue est dite inconnue, pas inventée")
    mesures.update(exemples=exemples, cryptos_suivies=list(cours.CRYPTOS))


def main() -> int:
    from ..crypto import cours, mesures as fichier
    v = Verifs("Crypto 1 · les cours")
    mesures: dict = {}
    noms(v)
    phrases(v)
    sources(v, mesures)
    outil(v, mesures)
    st = cours.statistiques
    code = v.fin()
    fichier.ecrire("1_cours", resultat_test=f"{v.total - len(v.echecs)}/{v.total}", quand=time.strftime("%Y-%m-%d %H:%M"),
                   replis_kraken=st["replis"], sorties_internet=st["binance"] + st["kraken"],
                   mediane_ms={k: statistics.median(x) if x else None for k, x in st["ms"].items()}, **mesures)
    return code


if __name__ == "__main__":
    sys.exit(main())
