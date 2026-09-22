"""Test du pouvoir v3-7 : le globe.

    python -m jarvis.tests.globe

1. les trois phrases de la consigne sont comprises, jamais une phrase ordinaire ;
2. l'outil : « terre » ne touche pas à Internet ; « station » et « séismes » appellent une source publique,
   **chaque appel est compté dans les sorties Internet**, et **aucune position de l'utilisateur** n'est envoyée ;
3. les données rendues tiennent debout (latitudes, longitudes, altitude de la Station, magnitudes) ;
4. le HUD dans un vrai navigateur : le globe s'affiche avec ses côtes et tourne, la Station est posée au bon
   endroit avec sa trajectoire, les séismes battent, et le HUD ne demande jamais la position de la machine ;
5. la cadence (règle v3) : le globe et quarante séismes ne dégradent pas le HUD."""
import asyncio
import sys

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, SCENE, mesurer, serveur_fichiers

# une position connue, pour vérifier que les points tombent au bon endroit sans dépendre d'Internet
STATION_ESSAI = [{"lat": 0, "lon": 0, "altitude_km": 420, "t": 1}, {"lat": 10, "lon": 20, "altitude_km": 421, "t": 2}]
SEISMES_ESSAI = [{"lat": 35.6, "lon": 139.7, "magnitude": 6.1, "lieu": "Japon"},
                 {"lat": -33.4, "lon": -70.6, "magnitude": 4.2, "lieu": "Chili"}]


def commande(v: Verifs):
    from .. import commandes as c
    attendus = {"Montre-moi la Terre": "terre", "affiche le globe": "terre", "Jarvis, montre-moi la planète": "terre",
                "Où est la Station spatiale ?": "station", "montre-moi la station spatiale": "station",
                "où se trouve l'ISS": "station", "Les séismes du jour": "seismes",
                "les tremblements de terre récents": "seismes", "montre-moi les séismes": "seismes"}
    faux = {p: c.analyser(p) for p, a in attendus.items() if c.analyser(p) != ("globe", a)}
    v.ok(not faux, "les trois demandes du globe sont comprises", faux or "toutes les variantes")
    ordinaires = ["Parle-moi de la Terre", "Montre-moi un dragon", "Où est mon fichier ?",
                  "Explique-moi comment naissent les séismes", "Montre-moi la carte de ma mémoire"]
    faux = {p: c.analyser(p) for p in ordinaires if c.analyser(p)[0] == "globe"}
    v.ok(not faux, "une phrase ordinaire n'affiche pas le globe", faux or "aucune")


def outil(v: Verifs) -> dict:
    from .. import compteur
    from ..outils import globe as G
    evenements = []
    ancien = G.sur_evenement
    G.sur_evenement = evenements.append
    envois = []
    import requests
    vrai_get = requests.get

    def espion(url, **kw):                  # on regarde tout ce qui part vraiment sur le réseau
        envois.append({"url": url, "params": kw.get("params") or {}})
        return vrai_get(url, **kw)

    requests.get = espion
    donnees = {}
    try:
        avant = compteur.sorties
        phrase = G.executer("terre")
        v.ok(phrase.startswith("Voici la Terre") and compteur.sorties == avant and not envois,
             "« la Terre » n'appelle rien sur Internet", f"{phrase} · {compteur.sorties - avant} sortie(s)")
        v.ok(any(e["quoi"] == "terre" for e in evenements), "le HUD reçoit l'ordre d'afficher le globe")

        avant = compteur.sorties
        phrase = G.executer("station")
        v.info("station : " + phrase)
        if "n'ai pas pu joindre" in phrase:
            v.info("source publique injoignable : le reste de l'essai réseau est ignoré")
            return donnees
        v.ok(compteur.sorties == avant + 1 and compteur.details.get("station_spatiale"),
             "la Station spatiale compte une sortie Internet", compteur.details)
        e = [x for x in evenements if x["quoi"] == "station"][-1]
        a = e["actuelle"]
        donnees["station"] = e
        v.ok(-90 <= a["lat"] <= 90 and -180 <= a["lon"] <= 180 and 350 < a["altitude_km"] < 500,
             "position et altitude plausibles pour l'ISS", f"{a['lat']}, {a['lon']}, {a['altitude_km']} km")
        v.ok(len(e["donnees"]) >= 3 and len(e["avenir"]) >= 3 and all(p["t"] > a["t"] for p in e["avenir"]),
             "la trajectoire est fournie, passé et à venir", f"{len(e['donnees'])} points + {len(e['avenir'])} à venir")
        v.ok(f"{abs(a['lat']):.1f}".replace(".", ",") in phrase and "altitude" in phrase,
             "la phrase dite donne la position et l'altitude, en français", phrase[:90])

        avant = compteur.sorties
        phrase = G.executer("seismes")
        v.info("séismes : " + phrase)
        v.ok(compteur.sorties == avant + 1 and compteur.details.get("seismes_usgs"),
             "les séismes comptent une sortie Internet", compteur.details)
        e = [x for x in evenements if x["quoi"] == "seismes"][-1]
        donnees["seismes"] = e
        liste = e["donnees"]
        v.ok(liste and all(-90 <= s["lat"] <= 90 and -180 <= s["lon"] <= 180 and 2.5 <= s["magnitude"] <= 10 for s in liste),
             "les séismes ont un lieu, une magnitude et des coordonnées valides", liste[0] if liste else "aucun")
        v.ok(liste == sorted(liste, key=lambda s: -s["magnitude"]), "du plus fort au plus faible")

        # ce qui est vraiment parti sur le réseau : aucune coordonnée, aucun identifiant de la machine
        hotes = {x["url"].split("/")[2] for x in envois}
        v.ok(len(envois) == 2 and hotes == {"api.wheretheiss.at", "earthquake.usgs.gov"},
             "deux appels seulement, aux deux sources publiques", sorted(hotes))
        # ce qui est envoyé EN PLUS de l'adresse : seulement des horodatages et l'unité
        envoye = {c: str(val) for x in envois for c, val in x["params"].items()}
        v.ok(set(envoye) <= {"timestamps", "units"},
             "aucune position ni identifiant de l'utilisateur n'est envoyé", envoye or "rien du tout")
        v.ok(all(str(G.ISS) in x["url"] or not x["params"] for x in envois),
             "l'appel de la Station ne porte que le numéro public du satellite", f"satellite {G.ISS}")
    finally:
        requests.get = vrai_get
        G.sur_evenement = ancien
    return donnees


async def hud(v: Verifs, donnees: dict):
    s, port = serveur_fichiers()
    edge = Edge(1600, 1000)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        # la géolocalisation ne doit jamais être demandée
        r = await edge.evaluer(f"""(async () => {{
            let geo = 0;
            if (navigator.geolocation) {{
              const vrai = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation);
              navigator.geolocation.getCurrentPosition = (...a) => {{ geo++; return vrai(...a); }};
              navigator.geolocation.watchPosition = () => {{ geo++; return 0; }};
            }}
            const J = window.__jarvis, R = J.reacteur;
            const infos = await R.globe("terre");
            await new Promise(r => setTimeout(r, 1200));
            const tourne1 = R.etatGlobe.rotation;
            await new Promise(r => setTimeout(r, 900));
            const apres = R.etatGlobe;
            // la Station, à une position connue
            await R.globe("station", {STATION_ESSAI[:1]!r}.map(o => o), {STATION_ESSAI[1:]!r});
            await new Promise(r => setTimeout(r, 400));
            const station = R.etatGlobe.station;
            const surEcran = R.globeEcran(0, 0), derriere = R.globeEcran(0, 180);
            const mod = await import("/hud/globe.js"), surSphere = mod.surLaSphere;
            const rayon = surSphere(12, 34).length(), pole = surSphere(90, 0).toArray().map(x => +x.toFixed(3));
            // les séismes
            await R.globe("seismes", {SEISMES_ESSAI!r});
            await new Promise(r => setTimeout(r, 600));
            const seismes = R.etatGlobe.seismes;
            // on le retire
            R.globe("cacher");
            await new Promise(r => setTimeout(r, 900));
            const cache = R.etatGlobe;
            return {{ infos, tourne1, apres, station, surEcran, derriere, seismes, cache, geo, rayon, pole }}; }})()""".replace("'", '"'))
        v.ok(r["infos"]["cotes"] > 5000, "les côtes du monde sont tracées (Natural Earth, en local)",
             f"{r['infos']['cotes']} segments")
        v.ok(r["apres"]["rotation"] > r["tourne1"] > 0 and r["apres"]["visible"], "le globe tourne lentement sur lui-même",
             f"{r['tourne1']:.2f} → {r['apres']['rotation']:.2f} rad")
        v.ok(r["station"] and abs(r["station"]["lat"] - 0) < 0.01 and abs(r["station"]["lon"] - 0) < 0.01
             and r["station"]["points"] == 2, "la Station est posée à sa position, trajectoire comprise", r["station"])
        v.ok(r["surEcran"]["devant"] != r["derriere"]["devant"],
             "un point et son antipode ne sont jamais du même côté du globe (il tourne)",
             [r["surEcran"]["devant"], r["derriere"]["devant"]])
        v.ok(abs(r["rayon"] - 1) < 0.001 and r["pole"] == [0, 1, 0],
             "latitude et longitude tombent bien sur la sphère (pôle nord en haut)", [r["rayon"], r["pole"]])
        v.ok(r["seismes"] == len(SEISMES_ESSAI), "un battement par séisme", r["seismes"])
        v.ok(not r["cache"]["visible"], "le globe se retire", r["cache"]["etat"])
        v.ok(r["geo"] == 0, "le HUD ne demande jamais la position de la machine", f"{r['geo']} appel(s) à la géolocalisation")

        # la cadence avec le globe et quarante séismes
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "", 4000)
        v.info(f"cadence du HUD seul : {base['moyenne_ms']} ms/image, p99 {base['p99_ms']} ms")
        quarante = [{"lat": (i * 7) % 170 - 85, "lon": (i * 23) % 350 - 175, "magnitude": 2.5 + (i % 5),
                     "lieu": f"essai {i}"} for i in range(40)]
        r = await mesurer(edge, f'window.__jarvis.reacteur.globe("seismes", {quarante!r})'.replace("'", '"'), 5000)
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.1 and r["pire_ms"] < 18,
             "le globe et quarante séismes gardent la cadence",
             f"{base['moyenne_ms']} → {r['moyenne_ms']} ms/image, pire {r['pire_ms']} ms")
        v.ok(r["p99_ms"] < BUDGET_144_MS, "budget 144 Hz tenu avec le globe", f"p99 {r['p99_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-7 · le globe")
    commande(v)
    donnees = outil(v)
    asyncio.run(hud(v, donnees))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
