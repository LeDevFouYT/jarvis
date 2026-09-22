"""Cadence du HUD : le réacteur 3D mesuré dans Edge sans fenêtre (vrai WebGL sur la carte graphique), pendant que
qwen3:14b occupe la mémoire vidéo. Règle v3 : aucun nouveau pouvoir ne dégrade la cadence (144 i/s le 16/09).

    python -m jarvis.tests.cadence              la scène la plus chargée (3 panneaux, parole), réacteur de base
    python -m jarvis.tests.cadence themes       la même chose pour chaque armure, et pendant une transition

Deux mesures par configuration :
- sans synchronisation (--disable-gpu-vsync --disable-frame-rate-limit) : le temps de calcul réel d'une image, que
  l'on compare au budget d'un écran 144 Hz (6,94 ms) et à la référence ;
- le nombre d'images à plus de 18 ms (les saccades visibles), qui doit rester à 0.
Les pages sont servies par un petit serveur de fichiers local : la mesure ne dépend ni du Jarvis ouvert ni du réseau."""
import asyncio
import functools
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from ._commun import Verifs

RACINE_HUD = Path(__file__).resolve().parents[1]           # jarvis/ : la page charge /hud/...
EDGE = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
SCENE = "/hud/index.html?demo=1&etat=parole&panneaux=graphique,liste,frise"
BUDGET_144_MS = 1000 / 144
MARGE = 1.15                     # une armure ne coûte pas plus de 15 % de temps d'image que le réacteur de base


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Silencieux(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, chemin):
        # /workspace/... et /modeles/... vivent à côté du paquet (hologrammes, modèle des mains) : chemins absolus
        if chemin.split("?")[0].startswith(("/workspace/", "/modeles/")):
            return str(RACINE_HUD.parent / chemin.split("?")[0].lstrip("/").replace("/", os.sep))
        return super().translate_path(chemin)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def serveur_fichiers() -> tuple[http.server.ThreadingHTTPServer, int]:
    import mimetypes
    mimetypes.add_type("text/javascript", ".js")
    port = _port_libre()
    s = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(_Silencieux, directory=str(RACINE_HUD)))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, port


class Edge:
    """Edge sans fenêtre piloté par le protocole DevTools (websockets)."""

    def __init__(self, largeur=2560, hauteur=1440, camera=None):
        """`camera` : un fichier .y4m joué comme si c'était la webcam (sans filmer personne), et l'autorisation
        accordée d'office — pour exercer le vrai chemin getUserMedia des gestes."""
        self.port = _port_libre()
        self.profil = tempfile.mkdtemp(prefix="jarvis_cadence_")
        options = [str(EDGE), "--headless=new", f"--remote-debugging-port={self.port}",
                   f"--user-data-dir={self.profil}", f"--window-size={largeur},{hauteur}",
                   "--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
                   "--disable-gpu-vsync", "--disable-frame-rate-limit", "--autoplay-policy=no-user-gesture-required",
                   "--no-first-run", "--no-default-browser-check"]
        if camera:
            options += ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                        f"--use-file-for-fake-video-capture={camera}"]
        self.proc = subprocess.Popen(options + ["about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws, self.n = None, 0

    async def ouvrir(self):
        import websockets
        for _ in range(60):
            try:
                pages = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=2).read())
                page = next(p for p in pages if p.get("type") == "page")
                self.ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=2 ** 24)
                return
            except Exception:
                await asyncio.sleep(0.5)
        raise RuntimeError("Edge sans fenêtre n'a pas démarré")

    async def envoyer(self, methode, **params):
        self.n += 1
        ident = self.n
        await self.ws.send(json.dumps({"id": ident, "method": methode, "params": params}))
        while True:
            m = json.loads(await self.ws.recv())
            if m.get("id") == ident:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    async def evaluer(self, expression, attendre=True):
        r = await self.envoyer("Runtime.evaluate", expression=expression, awaitPromise=attendre, returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
        return r.get("result", {}).get("value")

    async def aller(self, url, attente=4.0):
        await self.envoyer("Page.enable")
        await self.envoyer("Page.navigate", url=url)
        await asyncio.sleep(attente)

    def fermer(self):
        self.proc.kill()


async def mesurer(edge: Edge, avant: str = "", duree_ms: int = 6000) -> dict:
    if avant:
        await edge.evaluer(avant)
    return await edge.evaluer(f"window.__jarvis.reacteur.mesurer({duree_ms})")


async def principal(themes: bool) -> int:
    v = Verifs("Cadence du HUD (réacteur 3D, carte graphique)")
    s, port = serveur_fichiers()
    edge = Edge()
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        carte = await edge.evaluer("window.__jarvis.reacteur.carte()")
        v.ok(carte and "aucune" not in str(carte).lower() and "swiftshader" not in str(carte).lower(),
             "le réacteur tourne sur la vraie carte graphique (WebGL)", carte)
        try:
            vram = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"],
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            vram = "?"
        v.info(f"mémoire vidéo pendant la mesure : {vram}")
        base = await mesurer(edge)
        v.info(f"réacteur de base : {base}")
        v.ok(base["p99_ms"] < BUDGET_144_MS, "une image se calcule dans le budget d'un écran 144 Hz (p99)",
             f"p99 {base['p99_ms']} ms pour {BUDGET_144_MS:.2f} ms")
        v.ok(base["pire_ms"] < 18, "aucune saccade visible (image > 18 ms)", f"pire {base['pire_ms']} ms")
        resultats = {"base": base}
        if themes:
            noms = await edge.evaluer("Object.keys(window.__jarvis.THEMES || {})") or []
            v.ok(len(noms) >= 4, "les armures sont déclarées", noms)
            for nom in noms:
                m = await mesurer(edge, f"window.__jarvis.theme('{nom}', true)")
                resultats[nom] = m
                v.ok(m["moyenne_ms"] <= base["moyenne_ms"] * MARGE and m["pire_ms"] < 18,
                     f"armure « {nom} » : même cadence que le réacteur de base",
                     f"{m['moyenne_ms']} ms/image (base {base['moyenne_ms']}), pire {m['pire_ms']} ms, p99 {m['p99_ms']} ms")
            # pendant une transition animée (le réacteur « recharge ») : mesurée sur sa durée entière
            m = await mesurer(edge, f"window.__jarvis.theme('{noms[1] if len(noms) > 1 else noms[0]}')", 2500)
            resultats["transition"] = m
            v.ok(m["pire_ms"] < 18 and m["p99_ms"] < BUDGET_144_MS, "pendant la transition d'armure : aucune saccade",
                 f"pire {m['pire_ms']} ms, p99 {m['p99_ms']} ms")
            await edge.evaluer("window.__jarvis.video(true)", False)
            await asyncio.sleep(0.5)
            m = await mesurer(edge)
            resultats["video"] = m
            v.ok(m["pire_ms"] < 18 and m["moyenne_ms"] <= base["moyenne_ms"] * MARGE, "mode vidéo : même cadence",
                 f"{m['moyenne_ms']} ms/image, pire {m['pire_ms']} ms")
        (Path(__file__).resolve().parents[2] / "workspace" / "mesures").mkdir(parents=True, exist_ok=True)
        (Path(__file__).resolve().parents[2] / "workspace" / "mesures" / "cadence.json").write_text(
            json.dumps({"quand": time.strftime("%Y-%m-%d %H:%M"), "carte": carte, "vram": vram, **resultats}, indent=1), encoding="utf-8")
    finally:
        edge.fermer()
        s.shutdown()
    return v.fin()


def main() -> int:
    return asyncio.run(principal("themes" in sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
