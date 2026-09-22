"""Test du pouvoir v3-4 : les hologrammes.

    python -m jarvis.tests.hologramme

1. le cache : un objet déjà sculpté porte toujours le même nom de fichier, et repart tout de suite ;
2. la chaîne complète, mesurée en vrai (workspace/mesures/hologrammes.json) : dessin ComfyUI puis sculpture
   Hunyuan3D, avec l'alternance de mémoire vidéo (cerveau déchargé, ComfyUI libéré, sculpteur dans son processus) ;
3. le cerveau connaît l'outil, et « cache l'hologramme » est compris comme une commande ;
4. le HUD dans un vrai navigateur (Edge sans fenêtre, WebGL) : le .glb est lu ici même (sommets, triangles),
   l'objet s'imprime de bas en haut en 1,6 s, tourne, prend la couleur de l'armure, et se retire ;
5. la cadence (règle v3) : un hologramme affiché ne coûte pas plus de 15 % de temps d'image."""
import asyncio
import json
import sys
import time

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, SCENE, mesurer, serveur_fichiers

OBJET = "un dragon"


def cache(v: Verifs):
    from ..outils import hologramme as H
    noms = {H.nom_fichier(x) for x in ("un dragon", "Un Dragon", "le dragon", "dragon !")}
    v.ok(noms == {"dragon"}, "un même objet donne toujours le même fichier, quelle que soit la façon de le dire", noms)
    v.ok(H.nom_fichier("une épée médiévale") == "epee-medievale", "accents et espaces tenus", H.nom_fichier("une épée médiévale"))
    chemin = H.en_cache(OBJET)
    v.ok(chemin is not None and chemin.exists(), f"« {OBJET} » est en cache (sculpté lors d'un essai précédent)",
         str(chemin) if chemin else "aucun")
    if not chemin:
        return
    evenements = []
    ancien = H.sur_evenement
    H.sur_evenement = evenements.append
    try:
        t = time.time()
        phrase = H.executer(OBJET)
        duree = time.time() - t
    finally:
        H.sur_evenement = ancien
    v.ok(duree < 0.5 and any(e["type"] == "hologramme" and e["cache"] for e in evenements),
         "un objet déjà sculpté repart tout de suite, sans toucher à la carte", f"{duree * 1000:.0f} ms · {phrase}")


def chaine_complete(v: Verifs):
    from ..outils import hologramme as H
    if not H.MESURES.exists():
        v.ok(False, "la chaîne complète a déjà été mesurée (workspace/mesures/hologrammes.json)",
             "aucune mesure : demandez un objet jamais sculpté à Jarvis")
        return
    mesures = json.loads(H.MESURES.read_text(encoding="utf-8"))
    dernieres = mesures[-3:]
    for m in dernieres:
        v.info(f"« {m['objet']} » le {m['quand']} : dessin {m.get('dessin', '?')} s, sculpture {m.get('sculpture', '?')} s "
               f"(dont {m.get('chargement_modele_3d', '?')} s de chargement du sculpteur, {m.get('faces', '?')} faces), "
               f"total {m.get('total', '?')} s, {m.get('taille_mo', '?')} Mo")
    m = dernieres[-1]
    v.ok(m.get("dessin", 0) > 0 and m.get("sculpture", 0) > 0, "la chaîne complète a tourné en vrai : image puis maillage", m["objet"])
    v.ok(m.get("total", 0) < 600, "de la demande au maillage prêt : moins de dix minutes", f"{m.get('total')} s")
    ok, raison = H.outils_3d_presents()
    v.ok(ok, "le sculpteur 3D et son Python sont en place", raison or f"{H.IA3D} · {H.PYTHON_3D}")


def cerveau_et_commande(v: Verifs):
    from .. import commandes as c
    from .. import outils
    noms = [s["function"]["name"] for s in outils.SCHEMAS]
    v.ok("hologramme" in noms, "le cerveau a l'outil hologramme dans sa liste", f"{len(noms)} outils")
    v.ok(outils.est_direct("hologramme"), "sa phrase est dite telle quelle (le cerveau n'est pas rappelé avant l'image)")
    dites = {"Cache l'hologramme": "hologramme_cacher", "Jarvis, enlève l'hologramme.": "hologramme_cacher",
             "retire l'hologramme": "hologramme_cacher"}
    faux = {p: c.analyser(p) for p, a in dites.items() if c.analyser(p) != (a, "")}
    v.ok(not faux, "« cache l'hologramme » est compris", faux or "toutes les variantes")
    ordinaires = ["Montre-moi un dragon", "Cache-toi", "Parle-moi des hologrammes"]
    faux = {p: c.analyser(p) for p in ordinaires if c.analyser(p)[0] == "hologramme_cacher"}
    v.ok(not faux, "une phrase ordinaire ne le retire pas", faux or "aucune")


async def hud(v: Verifs):
    from ..outils import hologramme as H
    chemin = H.en_cache(OBJET)
    if not chemin:
        return
    s, port = serveur_fichiers()               # /hud/... et /workspace/... (le .glb) sont servis
    edge = Edge(1920, 1080)
    url = f"/workspace/hologrammes/{chemin.name}"
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        r = await edge.evaluer(f"""(async () => {{ const J = window.__jarvis, R = J.reacteur, t = performance.now();
            const infos = await R.hologramme("{url}", "{OBJET}");
            const chargement = performance.now() - t, releves = [];
            for (const ms of [200, 900, 2000]) {{ while (performance.now() - t < chargement + ms) await new Promise(r => setTimeout(r, 16));
              releves.push({{ ms, ...R.etatHologramme }}); }}
            return {{ infos, chargement, releves }}; }})()""")
        v.ok(r["infos"]["sommets"] > 1000, "le .glb est lu dans le HUD (sans chargeur extérieur)",
             f"{r['infos']['sommets']} sommets, {round(r['infos']['octets'] / 1024)} Ko, lu et posé en {r['chargement']:.0f} ms")
        debut, milieu, fin = r["releves"]
        v.ok(0.02 < milieu["impression"] < 0.98 and debut["impression"] < milieu["impression"],
             "l'objet s'imprime de bas en haut", f"{debut['impression']:.2f} → {milieu['impression']:.2f} → {fin['impression']:.2f}")
        v.ok(fin["impression"] >= 0.999 and fin["etat"] == "affiche", "impression terminée en moins de 2 s", fin["etat"])
        v.ok(fin["rotation"] > debut["rotation"] and fin["visible"], "il tourne lentement sur lui-même",
             f"{fin['rotation']:.2f} rad en 2 s")

        # le réacteur recule derrière l'objet, puis revient
        recul = await edge.evaluer("""(async () => { const R = window.__jarvis.reacteur;
            return { rayon: R.rayonEcran() }; })()""")
        v.info(f"réacteur reculé : rayon à l'écran {recul['rayon']:.0f} px")

        # la couleur suit l'armure
        c = await edge.evaluer("""(async () => { const J = window.__jarvis, R = J.reacteur;
            const avant = R.couleurActuelle; J.theme("mark3", true); await new Promise(r => setTimeout(r, 900));
            const apres = R.couleurActuelle; J.theme("jarvis", true); await new Promise(r => setTimeout(r, 900));
            return { avant, apres }; })()""")
        v.ok(c["avant"] != c["apres"], "l'hologramme prend les couleurs de l'armure (mêmes uniformes)", c)
        d = await edge.evaluer("""(async () => { const R = window.__jarvis.reacteur; R.cacherHologramme();
            const aussitot = R.etatHologramme.etat;
            await new Promise(r => setTimeout(r, 1500)); return { ...R.etatHologramme, aussitot }; })()""")
        v.ok(not d["visible"] and d["etat"] == "cache" and d["aussitot"] == "disparition",
             "« cache l'hologramme » : il s'efface en moins d'une seconde et demie", d)

        # la cadence (règle v3) : un objet de plus de 10 000 sommets affiché ne doit rien coûter de visible
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "", 4000)
        v.info(f"cadence du réacteur seul : {base['moyenne_ms']} ms/image, p99 {base['p99_ms']} ms")
        r = await mesurer(edge, f'window.__jarvis.reacteur.hologramme("{url}", "{OBJET}")', 4000)
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.05 and r["pire_ms"] < 18,
             "le HUD garde sa cadence avec l'hologramme affiché",
             f"{base['moyenne_ms']} → {r['moyenne_ms']} ms/image ({r['ips']} i/s possibles), pire {r['pire_ms']} ms")
        v.ok(r["p99_ms"] < BUDGET_144_MS, "budget 144 Hz tenu pendant l'impression", f"p99 {r['p99_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-4 · les hologrammes")
    cache(v)
    chaine_complete(v)
    cerveau_et_commande(v)
    asyncio.run(hud(v))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
