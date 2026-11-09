"""Test de la brique crypto 2 : le graphique géant (vidéo 4).

    python -m jarvis.tests.crypto_graphique

1. l'outil ouvre un panneau « cours » pour chaque période (24 h, 7 jours, 30 jours), choisie à la voix ;
2. dans un vrai navigateur (Edge sans fenêtre, aucune fenêtre ouverte à l'écran) : le panneau est un grand panneau,
   le prix et la variation sont énormes (lisibles sur un téléphone : le prix fait plus de 8 % de la hauteur de
   l'écran), en vert en hausse et en rouge en baisse, la courbe se trace puis s'arrête, rien ne dépasse — aussi en
   mode vidéo ;
3. une capture 1920 × 1080 par période dans workspace/captures/crypto/ : de quoi faire une miniature ;
4. la cadence (règle v3) : le graphique ouvert ne dégrade pas le HUD, ni pendant son ouverture animée ;
5. plusieurs graphiques côte à côte (2, 4, 6) : à la voix, dans un seul panneau, chacun vert ou rouge, rien ne dépasse.
Les mesures vont dans workspace/mesures/crypto.json (section 2_graphique)."""
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, mesurer, serveur_fichiers

CAPTURES = Path(__file__).resolve().parents[2] / "workspace" / "captures" / "crypto"
PAGE = "/hud/index.html?demo=1&etat=repos"


def voix(v: Verifs):
    from .. import commandes
    attendus = {"Montre-moi l'Ethereum sur 7 jours.": "7j", "Montre-moi le Bitcoin sur une semaine": "7j",
                "Affiche le Solana sur un mois": "30j", "Montre-moi le bitcoin sur 30 jours": "30j",
                "Combien vaut le Bitcoin ?": "24h", "Montre-moi le Bitcoin sur 24 heures": "24h"}
    faux = {p: commandes.analyser(p) for p, per in attendus.items() if commandes.analyser(p)[1].get("periode") != per}
    v.ok(not faux, "la période se choisit à la voix (24 h, 7 jours, 30 jours)", faux or f"{len(attendus)} phrases")


def evenements(v: Verifs) -> dict:
    from .. import outils
    from ..outils import crypto as outil_crypto
    recus = []
    ancien = outils.sur_evenement
    outils.sur_evenement = recus.append
    try:
        par_periode = {}
        for crypto, periode in (("bitcoin", "24h"), ("ethereum", "7j"), ("solana", "30j")):
            phrase = outil_crypto.executer("cours", crypto, periode)
            if "ne répondent" in phrase:
                v.info("pas d'Internet : essai ignoré")
                return {}
            e = [x for x in recus if x.get("genre") == "cours"][-1]
            par_periode[periode] = e
        attendu = {"24h": 96, "7j": 168, "30j": 180}
        v.ok(all(len(e["points"]) >= attendu[p] for p, e in par_periode.items()), "un panneau « cours » par période, courbe complète",
             " · ".join(f"{p} : {len(e['points'])} points" for p, e in par_periode.items()))
        v.ok(all(e["bas"] <= e["prix"] <= e["haut"] and e["points"][-1][1] == e["prix"] for e in par_periode.values()),
             "la courbe finit au prix du moment, entre le plus bas et le plus haut")
        v.ok(all(e["points"][0][0] < e["points"][-1][0] for e in par_periode.values()), "les points sont dans l'ordre du temps")
        return par_periode
    finally:
        outils.sur_evenement = ancien


async def navigateur(v: Verifs, par_periode: dict, mesures: dict):
    CAPTURES.mkdir(parents=True, exist_ok=True)
    s, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{PAGE}")
        erreurs = await edge.evaluer("window.__erreursCours = []; window.addEventListener('error', e => window.__erreursCours.push(e.message)); 1")
        base = await mesurer(edge, "", 4000)
        v.info(f"réacteur seul : {base['moyenne_ms']} ms/image, pire {base['pire_ms']} ms")
        captures = []
        for periode, e in par_periode.items():
            ouverture = await edge.evaluer(f"""(() => {{ const t = performance.now(); window.__jarvis.recevoir({json.dumps(e)});
                return performance.now() - t; }})()""")
            if periode == "24h":
                pendant = await mesurer(edge, "", 2200)               # l'ouverture animée (dépliage, tracé, chiffres)
            await asyncio.sleep(2.6)
            r = await edge.evaluer("""(() => {
                const p = document.querySelector('.holo.genre-cours:not(.ferme)'); if (!p) return null;
                const H = innerHeight, W = innerWidth, rect = x => x.getBoundingClientRect();
                const prix = p.querySelector('.h-cours-prix'), vari = p.querySelector('.h-cours-var'), fig = p.querySelector('.h-cours-fig');
                const trait = p.querySelector('.trait');
                const dehors = [...p.querySelectorAll('*')].filter(x => { const b = rect(x); return b.width && (b.right > W + 1 || b.bottom > H + 1 || b.left < -1); })
                                 .map(x => x.className.baseVal ?? x.className).slice(0, 5);
                return { grand: p.classList.contains('grand'), prix: prix.textContent, variation: vari.firstChild.textContent,
                         hPrix: rect(prix).height / H, hVar: rect(vari).height / H, hFig: rect(fig).height / H, lPanneau: rect(p).width / W,
                         couleur: getComputedStyle(vari).color, points: trait ? trait.getAttribute('points').trim().split(' ').length : 0,
                         trace: trait ? parseFloat(getComputedStyle(trait).strokeDashoffset) : 1, dehors,
                         defile: document.documentElement.scrollWidth > W || document.documentElement.scrollHeight > H };
            })()""")
            if not r:
                v.ok(False, f"{periode} : le panneau s'ouvre")
                continue
            hausse = e["variation"] >= 0
            vert = r["couleur"].startswith("rgb(53, 242, 154")
            rouge = r["couleur"].startswith("rgb(255, 77, 94")
            v.ok(r["grand"] and r["lPanneau"] > 0.5, f"{periode} : grand panneau, plus de la moitié de l'écran", f"{r['lPanneau']:.0%} de la largeur")
            v.ok(r["prix"].replace(" ", " ") and r["prix"].split(" €")[0].replace(" ", "").replace(",", ".") and r["hPrix"] > 0.08,
                 f"{periode} : prix énorme, lisible sur un téléphone", f"« {r['prix']} », {r['hPrix']:.1%} de la hauteur, variation {r['hVar']:.1%}")
            v.ok((hausse and vert) or (not hausse and rouge), f"{periode} : {'vert en hausse' if hausse else 'rouge en baisse'}", f"{r['variation']} · {r['couleur']}")
            v.ok(r["points"] == len(e["points"]) and r["trace"] < 0.01 and r["hFig"] > 0.35, f"{periode} : la courbe s'est tracée en entier, sur plus d'un tiers de l'écran",
                 f"{r['points']} points, courbe {r['hFig']:.0%} de la hauteur")
            v.ok(not r["dehors"] and not r["defile"], f"{periode} : rien ne dépasse de l'écran", r["dehors"] or "")
            image = (await edge.envoyer("Page.captureScreenshot", format="png"))["data"]
            chemin = CAPTURES / f"cours_{e['symbole'].lower()}_{periode}.png"
            chemin.write_bytes(base64.b64decode(image))
            captures.append(str(chemin.relative_to(CAPTURES.parents[1])).replace("\\", "/"))
            mesures.setdefault("ouverture_ms", round(ouverture, 1))
        avec = await mesurer(edge, "", 4000)
        v.info(f"graphique ouvert : {avec['moyenne_ms']} ms/image, pire {avec['pire_ms']} ms ; pendant l'ouverture : "
               f"{pendant['moyenne_ms']} ms/image, pire {pendant['pire_ms']} ms")
        v.ok(avec["moyenne_ms"] <= max(base["moyenne_ms"] * MARGE, base["moyenne_ms"] + 0.1) and avec["pire_ms"] < 18,
             "cadence : le graphique ouvert ne dégrade pas le HUD", f"{base['moyenne_ms']} → {avec['moyenne_ms']} ms/image, p99 {avec['p99_ms']} ms")
        v.ok(pendant["pire_ms"] < 18 and pendant["p99_ms"] < BUDGET_144_MS, "cadence : aucune saccade pendant l'ouverture animée",
             f"pire {pendant['pire_ms']} ms, p99 {pendant['p99_ms']} ms")

        # mode vidéo (lettres deux fois plus grosses) : toujours rien qui dépasse
        await edge.evaluer("window.__jarvis.video(true)", False)
        await edge.evaluer(f"window.__jarvis.recevoir({json.dumps(par_periode['24h'])})")
        await asyncio.sleep(2.6)
        r = await edge.evaluer("""(() => { const p = document.querySelector('.holo.genre-cours:not(.ferme)'); const W = innerWidth, H = innerHeight;
            const dehors = [...p.querySelectorAll('*')].filter(x => { const b = x.getBoundingClientRect(); return b.width && (b.right > W + 1 || b.bottom > H + 1); }).length;
            return { dehors, hPrix: p.querySelector('.h-cours-prix').getBoundingClientRect().height / H }; })()""")
        v.ok(r["dehors"] == 0, "mode vidéo : rien ne dépasse", f"prix {r['hPrix']:.1%} de la hauteur")
        image = (await edge.envoyer("Page.captureScreenshot", format="png"))["data"]
        (CAPTURES / "cours_btc_24h_video.png").write_bytes(base64.b64decode(image))
        captures.append("captures/crypto/cours_btc_24h_video.png")
        erreurs = await edge.evaluer("window.__erreursCours")
        v.ok(not erreurs, "aucune erreur JavaScript", erreurs or "")
        mesures.update(ms_par_image={"reacteur_seul": base["moyenne_ms"], "avec_graphique": avec["moyenne_ms"],
                                     "pendant_ouverture": pendant["moyenne_ms"], "pire_ouverture": pendant["pire_ms"]},
                       animation_s=1.85, captures=captures)
    finally:
        edge.fermer()
        s.shutdown()


async def grille(v: Verifs, mesures: dict):
    """Plusieurs graphiques côte à côte : « montre-moi le Bitcoin, l'Ethereum et le Solana », « montre-moi les cryptos »."""
    from .. import commandes, outils
    from ..outils import crypto as outil_crypto
    from ..youtube import verification
    attendus = {"Montre-moi le Bitcoin, l'Ethereum et le Solana.": (["BTC", "ETH", "SOL"], "24h"),
                "Compare le Bitcoin et l'Ethereum sur 7 jours": (["BTC", "ETH"], "7j"),
                "Montre-moi les cryptos": ([], "24h"), "Montre-moi plusieurs graphiques sur 30 jours": ([], "30j")}
    faux = {p: commandes.analyser(p) for p, (c, per) in attendus.items()
            if commandes.analyser(p) != ("crypto", {"action": "comparer", "cryptos": c, "periode": per})}
    v.ok(not faux, "plusieurs graphiques se demandent à la voix", faux or f"{len(attendus)} phrases")
    v.ok(commandes.analyser("Montre-moi l'Ethereum sur 7 jours.")[1].get("action") == "cours", "une seule crypto garde son graphique géant")

    recus = []
    ancien = outils.sur_evenement
    outils.sur_evenement = recus.append
    try:
        t = time.time()
        phrase = outil_crypto.executer("comparer", cryptos=["bitcoin", "ethereum", "solana", "xrp"], periode="7j")
        duree = time.time() - t
        phrase_toutes = outil_crypto.executer("comparer", periode="24h")
    finally:
        outils.sur_evenement = ancien
    if "ne répondent" in phrase:
        v.info("pas d'Internet : grille ignorée")
        return
    quatre = [e for e in recus if e.get("genre") == "multicours"][0]
    res = verification.verifier(phrase, [{"id": "F1", "texte": "", "sujet": "", "valeurs": {"g": [abs(g["variation"]) for g in quatre["graphiques"]], "j": 7}}])
    v.ok([g["symbole"] for g in quatre["graphiques"]] == ["BTC", "ETH", "SOL", "XRP"] and all(len(g["points"]) >= 168 for g in quatre["graphiques"]),
         "quatre cryptos, quatre courbes complètes, un seul panneau", f"{duree:.1f} s · {phrase}")
    v.ok(not res["ecarts"], "chaque variation dite est celle du graphique", f"{res['trouves']}/{res['total']}")
    v.ok(phrase_toutes.startswith("Sur 24 heures") and len([e for e in recus if e.get("genre") == "multicours"][1]["graphiques"]) == 4,
         "« montre-moi les cryptos » : les quatre plus échangées", phrase_toutes)

    s_, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{PAGE}")
        for _ in range(40):
            if await edge.evaluer("typeof window.__jarvis") == "object":
                break
            await asyncio.sleep(0.5)
        await edge.evaluer("window.__err = []; addEventListener('error', e => __err.push(e.message)); 1")
        base = await mesurer(edge, "", 3000)
        resultats = {}
        for n, gs in ((4, quatre["graphiques"]), (2, quatre["graphiques"][:2]), (6, None)):
            e = dict(quatre, graphiques=gs) if gs else None
            if e is None:                                    # six : on double les quatre avec deux autres
                e = dict(quatre, graphiques=quatre["graphiques"] + [dict(g, symbole=g["symbole"] + "2") for g in quatre["graphiques"][:2]])
            await edge.evaluer(f"window.__jarvis.recevoir({json.dumps(e)})")
            pendant = await mesurer(edge, "", 2500) if n == 4 else None
            await asyncio.sleep(2.8)
            r = await edge.evaluer("""(() => { const p = document.querySelector('.holo.genre-multicours:not(.ferme)'); if (!p) return null;
                const W = innerWidth, H = innerHeight;
                const cel = [...p.querySelectorAll('.h-multi-cellule')];
                const dehors = [...p.querySelectorAll('*')].filter(x => { const b = x.getBoundingClientRect(); return b.width && (b.right > W + 1 || b.bottom > H + 1); }).length;
                return { grand: p.classList.contains('grand'), cellules: cel.length,
                         couleurs: cel.map(c => [c.classList.contains('hausse'), getComputedStyle(c.querySelector('.h-multi-var')).color]),
                         traces: cel.map(c => parseFloat(getComputedStyle(c.querySelector('.trait:not(.lueur)')).strokeDashoffset)),
                         degrades: new Set(cel.map(c => c.querySelector('linearGradient').id)).size,
                         hPrix: Math.min(...cel.map(c => c.querySelector('.h-multi-prix').getBoundingClientRect().height)) / H,
                         hFig: Math.min(...cel.map(c => c.querySelector('.h-multi-fig').getBoundingClientRect().height)) / H, dehors }; })()""")
            bonnes = r and all((h and col.startswith("rgb(53, 242, 154")) or (not h and col.startswith("rgb(255, 77, 94")) for h, col in r["couleurs"])
            v.ok(r and r["grand"] and r["cellules"] == n and r["degrades"] == n, f"{n} graphiques : un grand panneau, {n} cellules, un dégradé chacune",
                 r and f"prix {r['hPrix']:.1%} de la hauteur, courbes {r['hFig']:.0%}")
            v.ok(bonnes and max(r["traces"]) < 0.01 and r["dehors"] == 0, f"{n} graphiques : chacun vert ou rouge selon sa variation, courbes tracées, rien ne dépasse",
                 r and [("▲" if h else "▼") for h, _ in r["couleurs"]])
            image = (await edge.envoyer("Page.captureScreenshot", format="png"))["data"]
            (CAPTURES / f"multicours_{n}.png").write_bytes(base64.b64decode(image))
            resultats[n] = r
            if pendant:
                avec = await mesurer(edge, "", 3000)
                v.ok(avec["moyenne_ms"] <= max(base["moyenne_ms"] * MARGE, base["moyenne_ms"] + 0.1) and avec["pire_ms"] < 18 and pendant["pire_ms"] < 18,
                     "cadence : quatre graphiques ouverts ne dégradent pas le HUD",
                     f"{base['moyenne_ms']} → {avec['moyenne_ms']} ms/image ; ouverture : pire {pendant['pire_ms']} ms, p99 {pendant['p99_ms']} ms")
                mesures["multicours_ms_par_image"] = {"base": base["moyenne_ms"], "quatre_graphiques": avec["moyenne_ms"],
                                                      "pire_ouverture": pendant["pire_ms"]}
        await edge.evaluer("window.__jarvis.video(true)", False)
        await edge.evaluer(f"window.__jarvis.recevoir({json.dumps(quatre)})")
        await asyncio.sleep(3)
        d = await edge.evaluer("""(() => { const p = document.querySelector('.holo.genre-multicours:not(.ferme)'); const W = innerWidth, H = innerHeight;
            return [...p.querySelectorAll('*')].filter(x => { const b = x.getBoundingClientRect(); return b.width && (b.right > W + 1 || b.bottom > H + 1); }).length; })()""")
        v.ok(d == 0, "mode vidéo : quatre graphiques, rien ne dépasse")
        image = (await edge.envoyer("Page.captureScreenshot", format="png"))["data"]
        (CAPTURES / "multicours_4_video.png").write_bytes(base64.b64decode(image))
        err = await edge.evaluer("window.__err")
        v.ok(not err, "aucune erreur JavaScript (grille)", err or "")
        mesures["multicours"] = {"exemple": phrase, "duree_s": round(duree, 2),
                                 "captures": [f"captures/crypto/multicours_{n}.png" for n in (2, 4, 6)] + ["captures/crypto/multicours_4_video.png"]}
    finally:
        edge.fermer()
        s_.shutdown()


def main() -> int:
    from ..crypto import mesures as fichier
    v = Verifs("Crypto 2 · le graphique géant")
    mesures: dict = {}
    voix(v)
    par_periode = evenements(v)
    if par_periode:
        asyncio.run(navigateur(v, par_periode, mesures))
        asyncio.run(grille(v, mesures))
    code = v.fin()
    fichier.ecrire("2_graphique", resultat_test=f"{v.total - len(v.echecs)}/{v.total}", quand=time.strftime("%Y-%m-%d %H:%M"), **mesures)
    return code


if __name__ == "__main__":
    sys.exit(main())
