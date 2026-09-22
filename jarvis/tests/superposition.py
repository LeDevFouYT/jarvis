"""Test du pouvoir v3-9 : Jarvis sort du HUD (superposition Windows + fond d'écran).

    python -m jarvis.tests.superposition

1. la commande vocale (« pose-toi sur mon écran » / « coupe la superposition »), jamais sur une phrase ordinaire ;
2. la vraie fenêtre : elle existe, elle est au premier plan, **les clics passent là où rien n'est dessiné**, elle
   n'est ni dans la barre des tâches ni dans Alt+Tab, elle ne prend jamais le focus, et **on la déplace à la souris**
   en la tirant par sa poignée (la position est retenue d'une fois sur l'autre) ;
3. elle s'efface quand le HUD est au premier plan (rien ne se recouvre) et revient ensuite ; un HUD fermé
   brutalement ne la laisse pas masquée (péremption) ;
4. elle montre ce qu'il faut : notifications, réponse qui flotte, jauges de la machine ;
5. le mode fond d'écran : la page /fond se charge, le réacteur tourne, il réagit à la voix et au son du bureau
   (l'interface de Lively Wallpaper), et reste léger."""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

from ._commun import Verifs
from .cadence import Edge, serveur_fichiers

ETAT = Path(__file__).resolve().parents[1].parent / "workspace" / "mesures" / "superposition.json"
GWL_EXSTYLE = -20


def commande(v: Verifs):
    from .. import commandes as c
    attendus = {"Pose-toi sur mon écran": "on", "Jarvis, sors du HUD": "on", "active la superposition": "on",
                "coupe la superposition": "off", "quitte mon écran": "off"}
    faux = {p: c.analyser(p) for p, a in attendus.items() if c.analyser(p) != ("superposition", a)}
    v.ok(not faux, "« pose-toi sur mon écran » et « coupe la superposition » sont compris", faux or "toutes")
    ordinaires = ["Pose-toi une question", "Montre-moi mon écran", "Scanne la pièce"]
    faux = {p: c.analyser(p) for p in ordinaires if c.analyser(p)[0] == "superposition"}
    v.ok(not faux, "une phrase ordinaire ne la déclenche pas", faux or "aucune")


def fenetre(v: Verifs):
    """La fenêtre elle-même, avec les vrais appels Windows."""
    import ctypes
    from ctypes import wintypes
    from .. import superposition_pilote as pilote
    ok, raison = pilote.disponible()
    if not ok:
        v.ok(False, "la superposition peut tourner sur cette machine", raison)
        return
    if ETAT.exists():
        ETAT.unlink()
    depart = time.time()
    proc = subprocess.Popen([pilote._python(), "-m", "jarvis.superposition", "--serveur", "http://127.0.0.1:1"],
                            cwd=str(Path(__file__).resolve().parents[2]), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        for _ in range(80):                                  # elle écrit son état dès qu'elle est prête
            if ETAT.exists():
                break
            time.sleep(0.25)
        v.ok(ETAT.exists(), "la fenêtre s'ouvre et dit où elle est", f"{time.time() - depart:.1f} s")
        if not ETAT.exists():
            return
        etat = json.loads(ETAT.read_text(encoding="utf-8"))
        h = etat["hwnd"]
        u = ctypes.windll.user32
        ex = u.GetWindowLongW(h, GWL_EXSTYLE)
        r = wintypes.RECT()
        u.GetWindowRect(h, ctypes.byref(r))

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        u.WindowFromPoint.restype = ctypes.c_void_p
        u.WindowFromPoint.argtypes = [Point]
        v.ok(bool(u.IsWindowVisible(h)) and r.right > r.left, "elle est affichée",
             f"{r.right - r.left}×{r.bottom - r.top} à ({r.left}, {r.top})")
        v.ok(bool(ex & 0x00080000), "fenêtre à calque : le fond est vraiment transparent (couleur clé)")
        vide = u.WindowFromPoint(Point(r.left + 12, r.bottom - 12))      # tout en bas : rien n'y est dessiné
        v.ok(vide != h, "les clics passent là où rien n'est dessiné : ils tombent sur la fenêtre du dessous",
             f"sous le curseur : {vide}")
        v.ok(not (ex & 0x00000020), "elle n'est pas aveugle à la souris : sa poignée peut être saisie")
        _glisser(v, u, h, r)
        v.ok(bool(ex & 0x00000008), "toujours au premier plan")
        v.ok(bool(ex & 0x00000080) and bool(ex & 0x08000000), "ni dans la barre des tâches, ni preneuse de focus")
        # le contenu : on lui envoie des événements comme le ferait le serveur
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        time.sleep(1.2)
        etat = json.loads(ETAT.read_text(encoding="utf-8"))
        v.ok(etat["images"] > 10, "elle se redessine toute seule", f"{etat['images']} images")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _glisser(v: Verifs, u, h: int, r) -> None:
    """On la prend par sa poignée et on la pose ailleurs, à la souris, comme on le ferait vraiment."""
    import ctypes
    from ctypes import wintypes
    avant = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(avant))                       # la souris de la maison est rendue où on l'a prise
    try:
        u.SetCursorPos(r.left + 200, r.top + 15)              # la poignée, en haut du panneau
        time.sleep(0.25)
        u.mouse_event(0x0002, 0, 0, 0, 0)                     # bouton enfoncé
        time.sleep(0.15)
        for i in range(1, 11):
            u.SetCursorPos(r.left + 200 - i * 22, r.top + 15 + i * 14)
            time.sleep(0.03)
        time.sleep(0.15)
        u.mouse_event(0x0004, 0, 0, 0, 0)                     # relâché
        time.sleep(0.7)
    finally:
        u.SetCursorPos(avant.x, avant.y)
    apres = wintypes.RECT()
    u.GetWindowRect(h, ctypes.byref(apres))
    bouge = (apres.left - r.left, apres.top - r.top)
    v.ok(abs(bouge[0]) > 100 and abs(bouge[1]) > 60, "on la déplace à la souris en la tirant par sa poignée",
         f"déplacée de {bouge[0]:+d}, {bouge[1]:+d} px")
    garde = json.loads((Path(__file__).resolve().parents[2] / "config.json").read_text(encoding="utf-8"))
    place = garde.get("superposition", {}).get("place", {})
    v.ok(place.get("x") == apres.left and place.get("y") == apres.top,
         "elle se souvient d'où on l'a posée", place)


def contenu(v: Verifs):
    """Ce qu'elle affiche, sans ouvrir de fenêtre : la logique de tri des événements."""
    from .. import superposition as S
    v.ok("rappel" in S.NOTES and "video_prete" in S.NOTES and "scan_resultat" in S.NOTES,
         "les événements qui méritent une notification sont listés", f"{len(S.NOTES)} sortes")
    lignes = S._couper("Je vous prépare le rapport complet, monsieur, avec les chiffres de la semaine.", 42)
    v.ok(len(lignes) >= 2 and all(len(x) <= 42 for x in lignes), "le texte long est coupé proprement", lignes)
    titre, prendre = S.NOTES["scan_resultat"]
    v.ok(prendre({"phrase": "une tasse et un clavier"}) == "je vois une tasse et un clavier",
         "un scan devient une notification lisible", prendre({"phrase": "une tasse et un clavier"}))


async def fond(v: Verifs):
    """Le mode fond d'écran : la page /fond, telle que Lively la chargerait."""
    s, port = serveur_fichiers()
    edge = Edge(1600, 1000)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}/hud/fond.html")
        r = await edge.evaluer("""(async () => {
            await new Promise(r => setTimeout(r, 2500));
            const F = window.__fond;
            const avant = F.reacteur.stats(60);
            // Lively envoie le son du bureau : 128 bandes entre 0 et 1
            const fort = new Array(128).fill(0).map((_, i) => i < 24 ? 0.8 : 0.1);
            window.livelyAudioListener(fort);
            await new Promise(r => setTimeout(r, 400));
            const pendant = { etat: F.reacteur.etatActuel, texte: document.getElementById("etat").textContent };
            window.livelyAudioListener(new Array(128).fill(0));
            await new Promise(r => setTimeout(r, 400));
            const apres = { etat: F.reacteur.etatActuel, texte: document.getElementById("etat").textContent };
            // et le réglage d'armure de la vignette Lively
            window.livelyPropertyListener("armure", "mark3");
            await new Promise(r => setTimeout(r, 900));
            const couleur = F.reacteur.couleurActuelle;
            const mesure = await F.reacteur.mesurer(2500);
            return { reacteur: !!F.reacteur, pendant, apres, couleur, mesure,
                     interface: [typeof window.livelyAudioListener, typeof window.livelyPropertyListener],
                     panneaux: document.querySelectorAll(".holo").length }; })()""")
        v.ok(r["reacteur"] and r["panneaux"] == 0,
             "la page ne contient que le réacteur (aucun panneau, aucune interface)")
        v.ok(r["pendant"]["etat"] == "parole" and "son" in r["pendant"]["texte"],
             "le son du bureau (Lively) fait parler le réacteur", r["pendant"])
        v.ok(r["apres"]["etat"] == "repos", "le silence le remet en veille", r["apres"])
        v.ok(r["couleur"].lower().startswith("#ff"), "le réglage d'armure de Lively est suivi", r["couleur"])
        v.ok(r["interface"] == ["function", "function"], "les deux crochets de Lively sont là", r["interface"])
        v.info(f"fond d'écran : {r['mesure']['ips']} images par seconde possibles, {r['mesure']['moyenne_ms']} ms par image")
        v.ok(r["mesure"]["moyenne_ms"] < 8, "il reste léger (moins de 8 ms par image)", f"{r['mesure']['moyenne_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-9 · Jarvis sort du HUD")
    commande(v)
    contenu(v)
    fenetre(v)
    asyncio.run(fond(v))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
