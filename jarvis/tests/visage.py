"""Test du pouvoir v3-2 : le visage de particules.

    python -m jarvis.tests.visage

1. la commande vocale « montre-toi » (et « cache-toi » pour revenir), jamais sur une phrase ordinaire ;
2. le serveur : l'ordre part au HUD (événement visage) et Jarvis parle pendant la transformation ;
3. le HUD dans un vrai navigateur (Edge sans fenêtre, WebGL sur la carte) : le réacteur s'éteint et ses particules
   forment le visage en moins de 2,5 s ; la bouche suit le niveau sonore de la voix (diffusé 20 fois par seconde),
   s'ouvre sur les syllabes et se ferme dans les silences ; les yeux clignent ; le visage redevient réacteur ;
   la touche J fait de même ;
4. la cadence (règle v3) : visage au repos, visage qui parle et transition coûtent au plus 15 % de temps d'image de
   plus que le réacteur de base, sans aucune image au-delà de 18 ms."""
import asyncio
import math
import sys

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, SCENE, mesurer, serveur_fichiers


def commandes(v: Verifs):
    from .. import commandes as c
    montrer = ["Montre-toi", "Jarvis, montre-toi.", "Montre toi", "Montre-moi ton visage", "Tu peux te montrer ?",
               "Jarvis, affiche ton visage"]
    cacher = ["Cache-toi", "Redeviens le réacteur", "Jarvis, retourne dans ton réacteur", "Reprends ta forme normale"]
    faux = {p: c.analyser(p) for p in montrer if c.analyser(p) != ("visage", "on")}
    faux |= {p: c.analyser(p) for p in cacher if c.analyser(p) != ("visage", "off")}
    v.ok(not faux, "« montre-toi » et « cache-toi » sont compris", faux or "toutes les variantes")
    ordinaires = ["Montre-moi tes fichiers", "Montre-toi plus poli avec lui", "Je me cache toi aussi",
                  "Comment dessiner un visage ?", "Montre-moi le réacteur nucléaire le plus puissant"]
    faux = {p: c.analyser(p) for p in ordinaires if c.analyser(p)[0] == "visage"}
    v.ok(not faux, "une phrase ordinaire ne change jamais de forme", faux or "aucune")


def serveur(v: Verifs):
    from .. import serveur as S, voix
    evenements, dits = [], []
    ancien_emettre, ancien_dire = S.EMETTEUR.emettre, voix.VOIX.dire
    S.EMETTEUR.emettre = evenements.append
    voix.VOIX.dire = lambda texte, *a, **k: dits.append(texte)
    try:
        r = S._dialoguer("Jarvis, montre-toi", source="texte")
        v.ok(any(e.get("type") == "visage" and e.get("actif") is True for e in evenements), "le HUD reçoit l'ordre (événement visage)")
        v.ok(r["reponse"].startswith("Me voici"), "Jarvis parle pendant qu'il se transforme", r["reponse"])
        evenements.clear()
        r = S._dialoguer("Cache-toi", source="texte")
        v.ok(any(e.get("type") == "visage" and e.get("actif") is False for e in evenements), "« cache-toi » le rend au réacteur", r["reponse"])
    finally:
        S.EMETTEUR.emettre, voix.VOIX.dire = ancien_emettre, ancien_dire


def correlation(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b) or 1)


async def hud(v: Verifs):
    s, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}/hud/index.html?demo=1")
        # la transformation, relevée tous les 100 ms
        t = await edge.evaluer("""(async () => { const J = window.__jarvis, R = J.reacteur, debut = performance.now(), releves = [];
            J.recevoir({ type: "visage", actif: true });
            while (performance.now() - debut < 2600) { releves.push([performance.now() - debut, R.formeVisage]); await new Promise(r => setTimeout(r, 100)); }
            return { releves, actif: R.visageActif }; })()""")
        milieu = [f for ms, f in t["releves"] if 500 < ms < 1100]
        fini = next((ms for ms, f in t["releves"] if f >= 0.999), None)
        v.ok(t["actif"] and milieu and 0.1 < milieu[0] < 0.9, "l'événement visage lance la transformation, progressive", f"forme {milieu[0]:.2f} vers 0,5 s" if milieu else t)
        v.ok(fini is not None and fini < 2500, "le visage est formé en moins de 2,5 s", f"{fini:.0f} ms" if fini else "jamais")

        # les lèvres : on rejoue une vraie courbe de parole (syllabes à ~5 Hz, silences entre les mots), 20 niveaux/s
        l = await edge.evaluer("""(async () => { const J = window.__jarvis, R = J.reacteur; J.recevoir({ type: "parole_debut" });
            const niveaux = [], bouches = [];
            for (let i = 0; i < 80; i++) {
              const t = i / 20, mot = Math.floor(t / 0.8) % 2 === 0 || (t % 0.8) < 0.55;
              const n = mot ? Math.max(0, Math.sin(t * Math.PI * 5)) * (0.55 + 0.4 * Math.sin(t * 1.7) ** 2) : 0;
              J.recevoir({ type: "niveau", valeur: n }); niveaux.push(n);
              await new Promise(r => setTimeout(r, 50)); bouches.push(R.boucheVisage);
            }
            J.recevoir({ type: "parole_fin" }); await new Promise(r => setTimeout(r, 400));
            return { niveaux, bouches, apres: R.boucheVisage }; })()""")
        c = correlation(l["niveaux"], l["bouches"])
        ouvertes = sum(b > 0.5 for b in l["bouches"])
        fermees = sum(b < 0.1 for b in l["bouches"])
        v.ok(c > 0.8, "la bouche suit le niveau de la voix", f"corrélation {c:.2f}")
        v.ok(ouvertes >= 10 and fermees >= 10, "elle s'ouvre sur les syllabes et se ferme entre elles", f"{ouvertes} images ouvertes, {fermees} fermées sur 80")
        v.ok(l["apres"] < 0.05, "bouche fermée quand Jarvis se tait", f"{l['apres']:.3f}")

        cl = await edge.evaluer("""(async () => { const R = window.__jarvis.reacteur, debut = performance.now(); let vu = false;
            while (performance.now() - debut < 7000 && !vu) { await new Promise(r => setTimeout(r, 20));
              vu = R.formeVisage === 1 && R.clignement > 0.5; }
            return vu; })()""")
        v.ok(cl, "les yeux clignent (toutes les 3 à 6 s)")

        # retour au réacteur, puis la touche J
        r = await edge.evaluer("""(async () => { const J = window.__jarvis, R = J.reacteur;
            J.recevoir({ type: "visage", actif: false }); await new Promise(r => setTimeout(r, 2200));
            const retour = { forme: R.formeVisage, actif: R.visageActif, anneaux: R.anneauxVisibles };
            document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyJ" })); await new Promise(r => setTimeout(r, 2200));
            retour.touche = R.formeVisage;
            document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyJ" })); await new Promise(r => setTimeout(r, 2200));
            retour.touche2 = R.formeVisage; return retour; })()""")
        v.ok(r["forme"] == 0 and not r["actif"] and r["anneaux"], "« cache-toi » : le visage redevient réacteur, anneaux rallumés", r)
        v.ok(r["touche"] == 1 and r["touche2"] == 0, "la touche J montre et cache le visage")

        # la cadence (règle v3) : même scène que les armures (parole, trois panneaux ouverts)
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "", 4000)
        v.info(f"cadence du réacteur de base : {base['moyenne_ms']} ms/image, p99 {base['p99_ms']} ms, pire {base['pire_ms']} ms")
        r = await mesurer(edge, "window.__jarvis.reacteur.visage(true)", 2200)
        v.ok(r["pire_ms"] < 18 and r["p99_ms"] < BUDGET_144_MS, "pendant la transformation : aucune saccade, budget 144 Hz tenu",
             f"p99 {r['p99_ms']} ms, pire {r['pire_ms']} ms")
        r = await mesurer(edge, "", 4000)
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.05 and r["pire_ms"] < 18, "le visage qui parle garde la cadence du réacteur",
             f"{r['moyenne_ms']} ms/image ({r['ips']} i/s possibles), pire {r['pire_ms']} ms")
        r = await mesurer(edge, "window.__jarvis.reacteur.visage(false)", 2200)
        v.ok(r["pire_ms"] < 18 and r["p99_ms"] < BUDGET_144_MS, "retour au réacteur : aucune saccade", f"p99 {r['p99_ms']} ms, pire {r['pire_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-2 · le visage de particules")
    commandes(v)
    serveur(v)
    asyncio.run(hud(v))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
