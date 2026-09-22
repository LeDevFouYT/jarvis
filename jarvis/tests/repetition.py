"""La répétition générale (v3, consigne 10) : le final de la vidéo, joué en entier, chronométré.

    python -m jarvis.tests.repetition [--vite]      (--vite : saute la vidéo Wan, qui dure trois minutes)

Ce n'est pas un test de plus : c'est la vraie scène, dans l'ordre, **sans clavier ni souris**.
  1. réveil à la main ouverte (caméra simulée par une vidéo de main : personne n'est filmé) ;
  2. « montre-toi »                          → le visage de particules ;
  3. « passe en armure Mark III »            → le HUD bascule ;
  4. « montre-moi un casque d'Iron Man »     → hologramme (sculpté si besoin) ;
  5. attraper et faire tourner l'hologramme  → à la main, par gestes ;
  6. « montre-moi la Terre »                 → le globe ;
  7. « fais-moi une vidéo d'une armure qui décolle » → Wan 2.2, panneau vidéo.
Chaque attente est mesurée (de la demande à ce qu'on voit vraiment à l'écran) et le bilan dit ce qui a échoué.

Le HUD tourne dans un vrai navigateur (Edge sans fenêtre, WebGL) branché sur le VRAI serveur Jarvis : les phrases
partent par /parler, comme si elles étaient dites, et le HUD réagit aux événements comme en direct.
"""
import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from ._commun import Verifs
from .cadence import Edge

SERVEUR = "http://127.0.0.1:8765"
VIDEOS_MAINS = Path(__file__).resolve().parent / "mains"
POINTS = (Path(__file__).resolve().parent / "gestes.py").read_text(encoding="utf-8").split('POINTS = """')[1].split('"""')[0]


def parler(texte: str, delai: float = 120) -> dict:
    corps = json.dumps({"texte": texte}).encode("utf-8")
    requete = urllib.request.Request(SERVEUR + "/parler", data=corps, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=delai) as r:
        return json.loads(r.read())


def serveur_vivant() -> bool:
    try:
        with urllib.request.urlopen(SERVEUR + "/etat", timeout=5) as r:
            return json.loads(r.read()).get("pret", {}).get("cerveau", False)
    except (urllib.error.URLError, OSError, ValueError):
        return False


async def attendre(edge: Edge, expression: str, delai: float = 30, pas: float = 0.25) -> float:
    """Attend que le HUD dise oui. Rend le temps écoulé, ou -1 si ça n'arrive jamais."""
    debut = time.time()
    while time.time() - debut < delai:
        if await edge.evaluer(f"(() => {{ try {{ return !!({expression}); }} catch (e) {{ return false; }} }})()"):
            return time.time() - debut
        await asyncio.sleep(pas)
    return -1.0


async def scene(v: Verifs, edge: Edge, vite: bool) -> list:
    """La scène, dans l'ordre. Rend la liste des étapes mesurées."""
    etapes = []

    def noter(nom, attendu, mesure, detail=""):
        etapes.append({"etape": nom, "attente_s": round(mesure, 2) if mesure >= 0 else None,
                       "vu": mesure >= 0, "attendu_max_s": attendu, "detail": detail})
        if mesure < 0:
            v.ok(False, f"{nom} : rien ne se passe", f"attendu sous {attendu} s · {detail}")
        else:
            v.ok(mesure <= attendu, f"{nom} : {mesure:.1f} s", f"seuil {attendu} s · {detail}")

    # 1. le réveil, main ouverte trois secondes devant la caméra
    t = time.time()
    r = await edge.evaluer(POINTS + """(async () => {
        const J = window.__jarvis, M = J.mains;
        M.remettre();
        let reveil = null;
        for (let x = 0; x <= 3.4; x += 0.1) {
          const g = M.rejouer([main({ x: 0.5 + Math.sin(x) * 0.001 })], x);
          const r = g.find(y => y.type === "reveil");
          if (r) { reveil = r; break; }
        }
        return { reveil, ecoute: document.body.classList.contains("ecoute") }; })()""")
    noter("réveil à la main ouverte", 4.0, (time.time() - t) if r["reveil"] else -1,
          f"main tenue {r['reveil']['tenue'] if r['reveil'] else '?'} s")

    # 2. « montre-toi »
    t = time.time()
    rep = parler("Montre-toi")
    forme = await attendre(edge, "window.__jarvis.reacteur.formeVisage >= 0.999", 8)
    noter("« montre-toi » → visage", 6.0, (time.time() - t) if forme >= 0 else -1, rep["reponse"][:60])

    # 3. « passe en armure Mark III »
    t = time.time()
    rep = parler("Passe en armure Mark III")
    bascule = await attendre(edge, 'document.documentElement.dataset.theme === "mark3"', 8)
    noter("« armure Mark III » → HUD rouge et or", 6.0, (time.time() - t) if bascule >= 0 else -1, rep["reponse"][:60])

    # 4. « montre-moi un casque d'Iron Man » (sculpté la première fois : deux à cinq minutes)
    t = time.time()
    rep = parler("Montre-moi un casque d'Iron Man en hologramme", delai=60)
    en_cache = "Voici" in rep["reponse"]
    vu = await attendre(edge, 'window.__jarvis.reacteur.etatHologramme.visible', 420 if not en_cache else 20, 0.5)
    noter("« un casque d'Iron Man » → hologramme", 25.0 if en_cache else 400.0, (time.time() - t) if vu >= 0 else -1,
          ("déjà sculpté" if en_cache else "sculpté à la demande") + " · " + rep["reponse"][:50])

    # 5. attraper l'hologramme et le faire tourner, à la main
    t = time.time()
    r = await edge.evaluer(POINTS + """(async () => {
        const J = window.__jarvis, R = J.reacteur, M = J.mains;
        M.remettre();
        const avant = { x: R.reglageHologramme.x, rotation: R.etatHologramme.rotation };
        M.rejouer([main({ x: 0.5, y: 0.5 })], 0);
        M.rejouer([main({ x: 0.5, y: 0.5, pince: 0.1 })], 0.1);       // pince : on attrape
        M.rejouer([main({ x: 0.62, y: 0.45, pince: 0.1 })], 0.2);     // on déplace
        const deplace = R.reglageHologramme.x - avant.x;
        M.rejouer([main({ x: 0.62, y: 0.45, pince: 0.1, angle: -Math.PI / 2 + 0.6 })], 0.3);  // on tourne le poignet
        const tourne = R.etatHologramme.rotation - avant.rotation;
        M.rejouer([main({ x: 0.62, y: 0.45 })], 0.4);                 // on lâche
        return { deplace, tourne }; })()""")
    ok_geste = abs(r["deplace"]) > 0.2 and abs(r["tourne"]) > 0.4
    noter("attraper et tourner l'hologramme", 3.0, (time.time() - t) if ok_geste else -1,
          f"déplacé de {r['deplace']:.2f}, tourné de {r['tourne']:.2f} rad")

    # 6. « montre-moi la Terre »
    t = time.time()
    rep = parler("Montre-moi la Terre")
    globe = await attendre(edge, 'window.__jarvis.reacteur.etatGlobe.visible', 20, 0.3)
    noter("« montre-moi la Terre » → globe", 12.0, (time.time() - t) if globe >= 0 else -1, rep["reponse"][:60])

    # 7. « fais-moi une vidéo d'une armure qui décolle »
    if vite:
        v.info("vidéo Wan sautée (--vite)")
        return etapes
    t = time.time()
    rep = parler("Fais-moi une vidéo d'une armure qui décolle", delai=60)
    panneau = await attendre(edge, 'window.__jarvis.panneaux.ouvertDeGenre("video")', 10, 0.2)
    noter("« fais-moi une vidéo » → réponse et panneau", 8.0, (time.time() - t) if panneau >= 0 else -1,
          rep["reponse"][:70])
    t = time.time()
    film = await attendre(edge, '(() => { const p = window.__jarvis.panneaux.ouvertDeGenre("video");'
                                ' const f = p && p.querySelector("video"); return f && f.src && f.duration > 1; })()',
                          480, 1.0)
    noter("la vidéo tourne dans le panneau", 300.0, (time.time() - t) if film >= 0 else -1,
          "rendu Wan 2.2 de bout en bout")
    return etapes


async def repetition(v: Verifs, vite: bool) -> list:
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_repetition_"))
    edge = None
    try:
        edge = Edge(1920, 1080)
        await edge.ouvrir()
        await edge.aller(SERVEUR + "/?repetition=1")
        await asyncio.sleep(4)
        pret = await edge.evaluer("!!(window.__jarvis && window.__jarvis.reacteur)")
        v.ok(pret, "le HUD est en place, branché sur le vrai Jarvis", SERVEUR)
        if not pret:
            return []
        return await scene(v, edge, vite)
    finally:
        if edge:
            edge.fermer()
        shutil.rmtree(dossier, ignore_errors=True)


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--vite", action="store_true", help="saute la vidéo Wan (trois minutes)")
    o = a.parse_args()
    v = Verifs("Répétition générale · le final, sans clavier ni souris")
    if not serveur_vivant():
        v.ok(False, "Jarvis tourne et son cerveau est chargé", f"{SERVEUR} ne répond pas : lancez Jarvis d'abord")
        return v.fin()
    etapes = asyncio.run(repetition(v, o.vite))
    if etapes:
        mesures = Path(__file__).resolve().parents[2] / "workspace" / "mesures" / "repetition.json"
        mesures.parent.mkdir(parents=True, exist_ok=True)
        mesures.write_text(json.dumps({"quand": time.strftime("%Y-%m-%d %H:%M"), "etapes": etapes},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
        v.info("— bilan de la répétition —")
        for e in etapes:
            v.info(f"{e['etape']:45s} {('%.1f s' % e['attente_s']) if e['vu'] else 'ÉCHEC':>10s}"
                   f"   (seuil {e['attendu_max_s']:.0f} s) {e['detail']}")
        rates = [e for e in etapes if not e["vu"] or e["attente_s"] > e["attendu_max_s"]]
        v.info("tout est passé" if not rates else "à revoir : " + ", ".join(e["etape"] for e in rates))
        v.info(f"mesures écrites : {mesures}")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
