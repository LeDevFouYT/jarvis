"""Test de la bourse (après la vidéo 4) : indices, actions, or, pétrole, devises, portefeuille et alertes.

    python -m jarvis.tests.crypto_bourse

1. les phrases : « combien vaut le CAC 40 ? », « montre-moi Apple sur un an », « comment vont les marchés ? »,
   « combien vaut le dollar ? », « compare Apple et le Bitcoin », « achète pour 1 000 € d'Apple », « préviens-moi si le
   CAC 40 passe sous 7 900 », « je devrais acheter des actions Tesla ? » (garde-fou) ; jamais une phrase ordinaire ;
2. les sources en vrai (Yahoo Finance, BCE) : prix plausibles, comptés dans les sorties Internet, cache, repli sur
   query2, rien d'autre ne part ;
3. l'outil : chaque chiffre dit est dans les faits (vérificateur), unités justes (points, dollars, euros) ;
4. le portefeuille fictif et les alertes avec des actions (fichiers temporaires) ; un indice ne s'achète pas ;
5. le HUD (Edge sans fenêtre) : graphique en points et en dollars, cinq périodes, grille mêlant bourse et crypto.
Les mesures vont dans workspace/mesures/crypto.json (section 7_bourse)."""
import asyncio
import base64
import json
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from ._commun import Verifs

CAPTURES = Path(__file__).resolve().parents[2] / "workspace" / "captures" / "crypto"


def phrases(v: Verifs):
    from .. import commandes
    attendus = {
        "Combien vaut le CAC 40 ?": ("bourse", {"action": "cours", "actif": "^FCHI", "periode": "jour"}),
        "Montre-moi Apple sur un an": ("bourse", {"action": "cours", "actif": "AAPL", "periode": "1a"}),
        "Et Nvidia sur 5 ans ?": ("bourse", {"action": "cours", "actif": "NVDA", "periode": "5a"}),
        "Quel est le cours de l'or ?": ("bourse", {"action": "cours", "actif": "GC=F", "periode": "jour"}),
        "Comment vont les marchés ?": ("bourse", {"action": "point"}),
        "Combien vaut le dollar ?": ("bourse", {"action": "change", "devise": "USD"}),
        "Montre-moi le CAC 40, le Dow Jones et le Nasdaq": ("bourse", {"action": "comparer", "actifs": ["^FCHI", "^DJI", "^IXIC"], "periode": "jour"}),
        "Compare Apple et le Bitcoin sur un mois": ("bourse", {"action": "comparer", "actifs": ["AAPL", "BTC"], "periode": "1m"}),
        "Montre-moi les indices": ("bourse", {"action": "comparer", "actifs": [], "periode": "jour"}),
        "Qu'est-ce qui monte le plus en bourse ?": ("bourse", {"action": "classement"}),
        "Achète pour 1 000 € d'Apple": ("crypto_ordre", {"sens": "achat", "crypto": "AAPL", "montant_eur": 1000.0}),
        "Vends la moitié de mes actions LVMH": ("crypto_ordre", {"sens": "vente", "crypto": "MC.PA", "fraction": 0.5}),
        "Préviens-moi si le CAC 40 passe sous 7 900": ("crypto_alerte", {"action": "creer", "crypto": "^FCHI", "type": "seuil",
                                                                         "seuil_eur": 7900.0, "direction": "sous"}),
        "Je devrais acheter des actions Tesla ?": ("crypto_conseil", "TSLA"),
        "Combien vaut le Bitcoin ?": ("crypto", {"action": "cours", "crypto": "BTC", "periode": "24h"}),
    }
    faux = {p: commandes.analyser(p) for p, a in attendus.items() if commandes.analyser(p) != a}
    v.ok(not faux, "les phrases de la bourse sont comprises (et les cryptos toujours)", faux or f"{len(attendus)} phrases")
    ordinaires = ["Il est d'or ce garçon", "Ouvre le bloc-notes", "Quelle heure est-il ?", "Montre-moi la Terre", "J'ai mangé une orange",
                  "Les actions de mon équipe sont bonnes"]
    faux = {p: commandes.analyser(p) for p in ordinaires if (commandes.analyser(p)[0] or "") in ("bourse", "crypto_ordre", "crypto_alerte")}
    v.ok(not faux, "une phrase ordinaire ne touche pas à la bourse", faux or "aucune")


def sources(v: Verifs, mesures: dict) -> bool:
    from .. import compteur
    from ..crypto import bourse as B
    envois, vrai_get = [], requests.get

    def espion(url, **kw):
        envois.append({"url": url, "entetes": kw.get("headers") or {}, "params": kw.get("params") or {}})
        return vrai_get(url, **kw)

    requests.get = espion
    try:
        avant = compteur.sorties
        t = time.time()
        try:
            cac = B.cotation("^FCHI")
        except B.Indisponible:
            v.info("Yahoo Finance ne répond pas : essai réseau ignoré")
            return False
        ms = round((time.time() - t) * 1000)
        apple, lvmh, orr = B.cotation("AAPL"), B.cotation("MC.PA"), B.cotation("GC=F")
        v.ok(1000 < cac["prix"] < 30000 and cac["unite"] == "pts" and abs(cac["variation"]) < 15, "le CAC 40 en points, variation du jour",
             f"{cac['prix']:.0f} pts, {cac['variation']:+.2f} %, {'ouvert' if cac['ouvert'] else 'fermé'}, {ms} ms")
        v.ok(apple["devise"] == "USD" and 0.5 < apple["taux_eur"] < 1.5 and abs(apple["prix_eur"] - apple["prix"] * apple["taux_eur"]) < 1e-6,
             "Apple en dollars, converti en euros au taux de la BCE", f"{apple['prix']:.2f} $ = {apple['prix_eur']:.2f} € (taux {apple['taux_eur']})")
        v.ok(lvmh["devise"] == "EUR" and lvmh["prix_eur"] == lvmh["prix"] and orr["prix"] > 500, "LVMH en euros, l'or plausible",
             f"LVMH {lvmh['prix']:.2f} €, or {orr['prix']:.0f} $")
        v.ok(compteur.sorties >= avant + 4 and compteur.details.get("bourse_yahoo"), "chaque requête compte une sortie Internet",
             f"{compteur.sorties - avant} sorties")
        avant = compteur.sorties
        B.cotation("^FCHI")
        v.ok(compteur.sorties == avant, "une seconde question dans la minute vient du cache")
        ancien = B.YAHOO[0]
        B.YAHOO[0] = "https://127.0.0.1:9/v8/finance/chart/"
        B._cache.clear()
        try:
            x = B.cotation("^FCHI")
        finally:
            B.YAHOO[0] = ancien
        v.ok(abs(x["prix"] - cac["prix"]) < 1 and B.statistiques["repli_query2"] >= 1, "query1 muet : query2 prend le relais")
        hotes = {urlparse(e["url"]).hostname for e in envois}
        v.ok(hotes <= {"query1.finance.yahoo.com", "query2.finance.yahoo.com", "api.frankfurter.app", "127.0.0.1"},
             "rien ne part ailleurs que vers Yahoo Finance et les taux de la BCE", sorted(hotes))
        v.ok(not any(k.lower() in ("authorization", "cookie") for e in envois for k in e["entetes"]), "aucune clé, aucun cookie, aucun compte")
        mesures.update(cac={"prix": cac["prix"], "variation": round(cac["variation"], 2), "ouvert": cac["ouvert"]},
                       apple={"usd": apple["prix"], "eur": round(apple["prix_eur"], 2), "taux": apple["taux_eur"]}, yahoo_ms=ms)
        return True
    finally:
        requests.get = vrai_get


def outil(v: Verifs, mesures: dict):
    from ..crypto import actions
    from ..outils import bourse as outil_bourse
    from ..youtube import verification
    exemples = []
    for c, a, doit in (("bourse", {"action": "cours", "actif": "^FCHI", "periode": "jour"}, "points"),
                       ("bourse", {"action": "cours", "actif": "AAPL", "periode": "1a"}, "dollars, soit"),
                       ("bourse", {"action": "cours", "actif": "MC.PA", "periode": "1m"}, "euros"),
                       ("bourse", {"action": "comparer", "actifs": ["AAPL", "BTC"], "periode": "1m"}, "Bitcoin"),
                       ("bourse", {"action": "classement"}, "monte le plus"),
                       ("bourse", {"action": "point"}, "Le point des marchés")):
        t = time.time()
        phrase = actions.executer(c, a)
        res = verification.verifier(phrase, outil_bourse.faits())
        exemples.append({"demande": a, "phrase": phrase, "chiffres": res["total"], "trouves": res["trouves"], "duree_s": round(time.time() - t, 2)})
        v.ok(doit in phrase and not res["ecarts"], f"{a['action']} {a.get('actif') or a.get('actifs') or ''} : unités justes, chaque chiffre dans les faits",
             f"{res['trouves']}/{res['total']} · {phrase[:160]}")
    phrase = actions.executer("bourse", {"action": "change", "devise": "USD"})
    taux = outil_bourse.faits()[0]["valeurs"]
    v.ok("Banque centrale européenne" in phrase and abs(taux["taux"] * taux["inverse"] - 1) < 1e-9, "« combien vaut le dollar ? » : taux BCE, dans les deux sens", phrase)
    r = actions.executer("crypto_conseil", "TSLA")
    v.ok("pas conseiller en investissement" in r and "dollars" in r, "garde-fou sur une action : les chiffres, pas de conseil", r)
    mesures["exemples"] = exemples + [{"demande": "change USD", "phrase": phrase}, {"demande": "conseil Tesla", "phrase": r}]


def portefeuille_et_alertes(v: Verifs, mesures: dict):
    from .. import confirmations
    from ..crypto import actions, alertes as A, bourse as B, portefeuille as P
    from ..outils import portefeuille as outil
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_bourse_"))
    vrais = (P.FICHIER, outil.ARCHIVES, A.FICHIER)
    P.FICHIER, outil.ARCHIVES, A.FICHIER = dossier / "p.json", dossier / "arch", dossier / "a.json"
    A._etat["alertes"], A._etat["declenchees"] = [], []
    parlees = []
    ancien_sur = A.sur_alerte
    A.sur_alerte = lambda a, t: parlees.append(t)
    try:
        q = actions.executer("crypto_ordre", {"sens": "achat", "crypto": "AAPL", "montant_eur": 1000.0})
        v.ok("fictif" in q and "Oui ou non" in q and "BCE" in q, "acheter des actions Apple : confirmation, prix converti au taux BCE", q)
        r = confirmations.confirmer()
        livre = P.charger()
        prix_eur = B.cotation("AAPL")["prix_eur"]
        v.ok(abs(livre.positions["AAPL"] - 999 / livre.journal[-1]["prix"]) < 1e-9 and abs(livre.journal[-1]["prix"] / prix_eur - 1) < 0.01,
             "1 000 € d'Apple : 0,1 % de frais, au prix réel en euros", r)
        val = outil.valeur()
        v.ok("Apple" in val and "fictif" in val, "« combien je vaux ? » compte les actions", val)
        r = actions.executer("crypto_ordre", {"sens": "achat", "crypto": "^FCHI", "montant_eur": 500.0})
        v.ok("indice" in r and not confirmations.en_attente(), "un indice ne s'achète pas, même en fictif", r)
        r = actions.executer("crypto_alerte", {"action": "creer", "crypto": "^FCHI", "type": "seuil", "seuil_eur": 1000.0, "direction": "sous"})
        a = A.lister()[-1]
        v.ok("points" in r and a.get("unite") == "pts", "alerte sur le CAC 40 : en points", r)
        sonne = A.tour(prix_de=lambda s: {k: 900.0 for k in s}, variation_de=lambda *x: 0.0)
        v.ok(sonne and parlees and parlees[-1].startswith("Alerte bourse") and "1 000 points" in parlees[-1],
             "elle sonne en disant « Alerte bourse » et les points", parlees[-1] if parlees else "")
        mesures["portefeuille_actions"] = {"ordre": livre.journal[-1], "valeur": val, "alerte": parlees[-1] if parlees else None}
    finally:
        A.sur_alerte = ancien_sur
        A.arreter()
        P.FICHIER, outil.ARCHIVES, A.FICHIER = vrais
        A._etat["alertes"], A._etat["declenchees"] = [], []


async def hud(v: Verifs, mesures: dict):
    from .. import outils
    from ..crypto import actions
    from .cadence import Edge, mesurer, serveur_fichiers
    recus = []
    ancien = outils.sur_evenement
    outils.sur_evenement = recus.append
    try:
        actions.executer("bourse", {"action": "cours", "actif": "^FCHI", "periode": "jour"})
        actions.executer("bourse", {"action": "cours", "actif": "NVDA", "periode": "5a"})
        actions.executer("bourse", {"action": "comparer", "actifs": ["^FCHI", "^GSPC", "AAPL", "BTC"], "periode": "1m"})
    finally:
        outils.sur_evenement = ancien
    panneaux_ = [e for e in recus if e.get("genre") in ("cours", "multicours")]
    s, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}/hud/index.html?demo=1&etat=repos")
        for _ in range(40):
            if await edge.evaluer("typeof window.__jarvis") == "object":
                break
            await asyncio.sleep(0.5)
        await edge.evaluer("window.__err = []; addEventListener('error', e => __err.push(e.message)); 1")
        base = await mesurer(edge, "", 3000)
        noms = ["bourse_cac40_jour", "bourse_nvidia_5ans", "bourse_grille"]
        for e, nom in zip(panneaux_, noms):
            await edge.evaluer(f"window.__jarvis.recevoir({json.dumps(e)})")
            await asyncio.sleep(3)
            r = await edge.evaluer("""(() => { const p = document.querySelector('.holo.grand:not(.ferme)'); const W = innerWidth, H = innerHeight;
                const prix = [...p.querySelectorAll('.h-cours-prix, .h-multi-prix')].map(x => x.textContent);
                const dehors = [...p.querySelectorAll('*')].filter(x => { const b = x.getBoundingClientRect(); return b.width && (b.right > W + 1 || b.bottom > H + 1); }).length;
                return { genre: p.className, prix, periodes: [...p.querySelectorAll('.h-cours-periodes span')].map(x => x.textContent),
                         depuis: p.querySelector('.h-cours-dates span')?.textContent, dehors }; })()""")
            if e["genre"] == "cours":
                unite = "pts" if e["unite"] == "pts" else "$"
                v.ok(r["prix"][0].endswith(unite) and len(r["periodes"]) == 5 and r["dehors"] == 0,
                     f"HUD {e['nom']} : prix en {unite}, cinq périodes, rien ne dépasse", f"{r['prix'][0]} · {r['periodes']} · depuis {r['depuis']}")
            else:
                v.ok(len(r["prix"]) == 4 and r["prix"][0].endswith("pts") and r["prix"][2].endswith("$") and r["prix"][3].endswith("€") and r["dehors"] == 0,
                     "HUD : une grille qui mêle indices, action et crypto, chacun dans son unité", r["prix"])
            image = (await edge.envoyer("Page.captureScreenshot", format="png"))["data"]
            (CAPTURES / f"{nom}.png").write_bytes(base64.b64decode(image))
        avec = await mesurer(edge, "", 3000)
        v.ok(avec["pire_ms"] < 18, "cadence : grille de bourse ouverte, aucune saccade", f"{base['moyenne_ms']} → {avec['moyenne_ms']} ms/image, pire {avec['pire_ms']} ms")
        err = await edge.evaluer("window.__err")
        v.ok(not err, "aucune erreur JavaScript", err or "")
        mesures["hud"] = {"ms_par_image": {"base": base["moyenne_ms"], "grille": avec["moyenne_ms"]}, "captures": [f"captures/crypto/{n}.png" for n in noms]}
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    from ..crypto import mesures as fichier
    v = Verifs("Bourse · indices, actions, or, devises")
    mesures: dict = {}
    phrases(v)
    if sources(v, mesures):
        outil(v, mesures)
        portefeuille_et_alertes(v, mesures)
        asyncio.run(hud(v, mesures))
    code = v.fin()
    fichier.ecrire("7_bourse", test="python -m jarvis.tests.crypto_bourse", resultat_test=f"{v.total - len(v.echecs)}/{v.total}",
                   quand=time.strftime("%Y-%m-%d %H:%M"), **mesures)
    return code


if __name__ == "__main__":
    sys.exit(main())
