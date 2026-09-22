"""Test du pouvoir v3-1 : les armures du HUD et le mode vidéo.

    python -m jarvis.tests.armures

1. la commande vocale « passe en armure Mark III » (et ses variantes), jamais sur une phrase ordinaire ;
2. le serveur : l'armure dite est mémorisée (config.json, rendue par /etat) et envoyée au HUD, Jarvis la confirme ;
3. le HUD dans un vrai navigateur (Edge sans fenêtre, WebGL sur la carte) : les quatre armures changent le réacteur,
   les panneaux et les sons ; la transition recharge le réacteur et bascule l'interface au creux de l'extinction ;
   une armure retrouvée au chargement s'affiche sans éclair ; le mode vidéo double les textes, garde un seul
   panneau, retire la trame, et se défait ;
4. la cadence (règle v3) : chaque armure, la transition et le mode vidéo coûtent au plus 15 % de temps d'image de
   plus que le réacteur de base, sans aucune image au-delà de 18 ms."""
import asyncio
import json
import sys
import time

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, SCENE, mesurer, serveur_fichiers


def commandes(v: Verifs):
    from .. import commandes as c
    attendus = {
        "Passe en armure Mark III": "mark3", "Jarvis, passe en armure Mark 3.": "mark3", "Enfile l'armure marque trois": "mark3",
        "Mets l'armure Friday": "friday", "Tu peux passer en armure Friday ?": "friday", "Armure Ultron": "ultron",
        "Jarvis, peux-tu activer l'armure Ultron ?": "ultron", "Passe en armure classique": "jarvis", "Retire l'armure": "jarvis",
    }
    obtenus = {p: c.analyser(p) for p in attendus}
    v.ok(all(obtenus[p] == ("armure", n) for p, n in attendus.items()), "les façons de demander une armure sont comprises",
         {p: o[1] for p, o in obtenus.items() if o != ("armure", attendus[p])} or "toutes")
    ordinaires = ["Parle-moi de l'armure Mark III dans le film", "Passe en armure Iron Patriot", "Combien pèse une armure ?",
                  "Passe en mode coach"]
    faux = {p: c.analyser(p) for p in ordinaires if c.analyser(p)[0] == "armure"}
    v.ok(not faux, "une phrase ordinaire (ou une armure inconnue) n'en change jamais", faux or "aucune")


def serveur(v: Verifs):
    from .. import armures, serveur as S, voix
    avant = armures.actuelle()
    evenements, dits = [], []
    ancien_emettre, ancien_dire = S.EMETTEUR.emettre, voix.VOIX.dire
    S.EMETTEUR.emettre = evenements.append
    voix.VOIX.dire = lambda texte, *a, **k: dits.append(texte)
    try:
        r = S._dialoguer("Jarvis, passe en armure Mark III", source="texte")
        v.ok(any(e.get("type") == "theme" and e.get("theme") == "mark3" for e in evenements), "le HUD reçoit l'armure (événement theme)")
        v.ok("Mark III" in r["reponse"], "Jarvis confirme", r["reponse"])
        v.ok(armures.actuelle() == "mark3" and json.loads((S.RACINE / "config.json").read_text(encoding="utf-8"))["hud"]["theme"] == "mark3",
             "l'armure est mémorisée dans config.json (hud.theme)")
        v.ok(S.etat()["theme"] == "mark3", "/etat la rend : chaque onglet du HUD la retrouve au chargement")
    finally:
        armures.definir(avant)
        S.EMETTEUR.emettre, voix.VOIX.dire = ancien_emettre, ancien_dire


async def hud(v: Verifs):
    from ..armures import ARMURES
    s, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        themes = await edge.evaluer("Object.keys(window.__jarvis.THEMES)")
        v.ok(sorted(themes) == sorted(ARMURES), "les mêmes armures côté serveur et côté HUD", themes)

        # chaque armure, posée d'un coup : réacteur, panneaux (variable CSS), sans éclair
        couleurs = {}
        for nom in themes:
            r = await edge.evaluer(f"""(async () => {{ const J = window.__jarvis; J.theme("{nom}", true);
                await new Promise(r => setTimeout(r, 1500));
                return {{ reacteur: J.reacteur.couleurActuelle, css: getComputedStyle(document.documentElement).getPropertyValue("--cyan").trim(),
                  bord: getComputedStyle(document.querySelector("#gauche")).borderTopColor, eclair: document.body.classList.contains("recharge"),
                  attendu: "#" + J.THEMES["{nom}"].principal.toString(16).padStart(6, "0") }}; }})()""")
            couleurs[nom] = r
        v.ok(all(abs(int(r["reacteur"][1:], 16) - int(r["attendu"][1:], 16)) < 0x030303 for r in couleurs.values()),
             "le réacteur prend la couleur de chaque armure", {n: r["reacteur"] for n, r in couleurs.items()})
        v.ok(len({r["css"] for r in couleurs.values()}) == len(themes) and len({r["bord"] for r in couleurs.values()}) == len(themes),
             "les panneaux changent de couleur avec l'armure", {n: r["css"] for n, r in couleurs.items()})
        v.ok(not any(r["eclair"] for r in couleurs.values()), "une armure posée au chargement s'affiche sans éclair ni recharge")

        # la transition animée : l'ancienne armure jusqu'au creux de l'extinction, puis la nouvelle, recharge finie vers 1,8 s
        t = await edge.evaluer("""(async () => { const J = window.__jarvis; J.theme("jarvis", true); await new Promise(r => setTimeout(r, 300));
            const debut = performance.now(), releves = []; J.theme("mark3");
            for (const ms of [150, 700, 2300]) { while (performance.now() - debut < ms) await new Promise(r => setTimeout(r, 10));
              releves.push({ ms, css: document.documentElement.dataset.theme, recharge: J.reacteur.enRecharge, eclair: document.body.classList.contains("recharge") }); }
            return releves; })()""")
        v.ok(t[0]["css"] == "jarvis" and t[0]["recharge"], "transition : l'ancienne armure pendant l'extinction du réacteur", t[0])
        v.ok(t[1]["css"] == "mark3" and t[1]["recharge"] and t[1]["eclair"], "au creux de l'extinction : l'interface bascule, l'éclair part, le réacteur recharge", t[1])
        v.ok(t[2]["css"] == "mark3" and not t[2]["recharge"], "recharge terminée en moins de 2,3 s", t[2])

        # les sons d'interface : un timbre par armure, jouables, coupables par S
        sons = await edge.evaluer("""(async () => { const J = window.__jarvis; document.dispatchEvent(new KeyboardEvent("keydown", { code: "Tab" }));
            await new Promise(r => setTimeout(r, 200));
            const joue = Object.keys(J.THEMES).map(n => J.sons.jouer("reveil", n));
            const formes = Object.values(J.THEMES).map(t => t.son.forme);
            J.sons.basculer(false); const coupe = J.sons.jouer("panneau", "jarvis"); J.sons.basculer(true);
            return { joue, formes, coupe }; })()""")
        v.ok(all(sons["joue"]), "chaque armure joue ses sons d'interface (Web Audio, rien de téléchargé)", sons["joue"])
        v.ok(len(set(sons["formes"])) == len(themes), "un timbre différent par armure", sons["formes"])
        v.ok(sons["coupe"] is False, "S coupe les sons")

        # le mode vidéo
        m = await edge.evaluer("""(async () => { const J = window.__jarvis; J.theme("jarvis", true);
            const taille = () => parseFloat(getComputedStyle(document.querySelector("#transcription p") || document.body).fontSize);
            const avant = taille(); J.panneaux.ouvrir(J.DEMO.texte); await new Promise(r => setTimeout(r, 200));
            const panneauxAvant = J.panneaux.nombre;
            document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyV" })); await new Promise(r => setTimeout(r, 300));
            J.panneaux.ouvrir(J.DEMO.liste); await new Promise(r => setTimeout(r, 300));
            const r = { avant, pendant: taille(), panneauxAvant, panneauxPendant: J.panneaux.nombre,
              trame: getComputedStyle(document.getElementById("trame")).display, verre: getComputedStyle(document.body).getPropertyValue("--verre").trim() };
            document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyV" })); await new Promise(r => setTimeout(r, 300));
            r.apres = taille(); return r; })()""")
        v.ok(abs(m["pendant"] / m["avant"] - 2) < 0.05, "mode vidéo (V) : textes deux fois plus gros", f"{m['avant']} -> {m['pendant']} px")
        v.ok(m["panneauxAvant"] >= 2 and m["panneauxPendant"] == 1, "mode vidéo : un panneau à la fois", f"{m['panneauxAvant']} -> {m['panneauxPendant']}")
        v.ok(m["trame"] == "none" and ".96" in m["verre"], "mode vidéo : contraste renforcé (trame retirée, verre opaque)", m["verre"])
        v.ok(abs(m["apres"] - m["avant"]) < 0.5, "V de nouveau : tout redevient normal", f"{m['apres']} px")

        # la cadence : aucune armure ne dégrade le HUD (règle v3)
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "window.__jarvis.theme('jarvis', true)", 4000)
        v.info(f"cadence du réacteur de base : {base['moyenne_ms']} ms/image, p99 {base['p99_ms']} ms, pire {base['pire_ms']} ms")
        pires = {}
        for nom in themes:
            r = await mesurer(edge, f"window.__jarvis.theme('{nom}', true)", 4000)
            pires[nom] = r
        v.ok(all(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.05 and r["pire_ms"] < 18 for r in pires.values()),
             "chaque armure garde la cadence du réacteur de base", {n: f"{r['moyenne_ms']} ms, pire {r['pire_ms']}" for n, r in pires.items()})
        r = await mesurer(edge, "window.__jarvis.theme('ultron')", 2200)
        v.ok(r["pire_ms"] < 18 and r["p99_ms"] < BUDGET_144_MS, "pendant la recharge : aucune saccade, budget 144 Hz tenu",
             f"p99 {r['p99_ms']} ms, pire {r['pire_ms']} ms")
        r = await mesurer(edge, "window.__jarvis.video(true)", 4000)
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.05 and r["pire_ms"] < 18, "le mode vidéo garde la cadence",
             f"{r['moyenne_ms']} ms/image, pire {r['pire_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-1 · armures et mode vidéo")
    commandes(v)
    serveur(v)
    asyncio.run(hud(v))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
