"""Rien ne doit dépasser de l'écran : python -m jarvis.tests.mise_en_page

Le HUD est fait pour être filmé : en **mode vidéo** (touche V) les lettres doublent de taille, et c'est là que
la mise en page casse sans prévenir. Le 20/09, la barre d'état sortait de l'écran par la droite — le compteur de
sorties internet débordait de 148 px, hors champ.

Ce test ouvre le vrai HUD dans un vrai navigateur, à cinq tailles d'écran, en mode normal puis en mode vidéo, avec
des panneaux ouverts, et vérifie qu'aucun élément ne passe le bord droit ou le bas, et que la page ne défile pas
(un HUD qui défile, c'est un HUD dont on a perdu un morceau).
"""
import asyncio
import json
import sys

from ._commun import Verifs
from .cadence import Edge, serveur_fichiers

SCENE = "/hud/index.html?demo=1&etat=parole&panneaux=graphique,liste,frise"
TAILLES = [(1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440)]

MESURE = r"""(async (video) => {
  const J = window.__jarvis;
  document.documentElement.classList.toggle("video", video);
  document.body.classList.toggle("video", video);
  J.panneaux.ouvrir({ titre: "ARMURE QUI DÉCOLLE", genre: "video", video: { url: "", duree: 5 }, texte: "Wan 2.2" });
  J.panneaux.ouvrir({ titre: "RAPPORT DE LA SEMAINE", genre: "texte",
                      texte: "Une phrase longue, avec des mots qui ne se coupent pas, comme anticonstitutionnellement." });
  await new Promise(r => setTimeout(r, 1200));
  const W = innerWidth, H = innerHeight, debord = [];
  document.querySelectorAll("body *").forEach(n => {
    const r = n.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    const d = Math.round(r.right - W), b = Math.round(r.bottom - H);
    if (d > 1 || b > 1) debord.push((n.id ? "#" + n.id : n.tagName.toLowerCase())
      + (d > 1 ? ` dépasse de ${d} px à droite` : "") + (b > 1 ? ` dépasse de ${b} px en bas` : ""));
  });
  const e = document.scrollingElement;
  return { W, H, debord: debord.slice(0, 6), defile: [e.scrollWidth - W, e.scrollHeight - H] };
})(%s)"""


async def mesurer(v: Verifs, port: int, largeur: int, hauteur: int, video: bool):
    edge = Edge(largeur, hauteur)
    mode = "mode vidéo" if video else "mode normal"
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        await asyncio.sleep(2.5)
        r = await edge.evaluer(MESURE % ("true" if video else "false"))
        v.ok(not r["debord"], f"{largeur}×{hauteur}, {mode} : rien ne dépasse de l'écran",
             "; ".join(r["debord"]) if r["debord"] else f"fenêtre utile {r['W']}×{r['H']}")
        v.ok(r["defile"][0] <= 1 and r["defile"][1] <= 1, f"{largeur}×{hauteur}, {mode} : la page ne défile pas",
             f"{r['defile'][0]} px de trop en largeur, {r['defile'][1]} en hauteur")
    finally:
        edge.fermer()


async def tout(v: Verifs):
    s, port = serveur_fichiers()
    try:
        for largeur, hauteur in TAILLES:
            for video in (False, True):
                await mesurer(v, port, largeur, hauteur, video)
    finally:
        s.shutdown()


def main() -> int:
    v = Verifs("Mise en page · rien ne dépasse, même en mode vidéo")
    asyncio.run(tout(v))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
