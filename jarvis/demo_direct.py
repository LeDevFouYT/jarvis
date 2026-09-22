"""La démo en direct, à l'écran — celle qu'on filme.

    python -m jarvis.demo_direct                 tous les chapitres, à la suite
    python -m jarvis.demo_direct --liste         la liste des chapitres, avec leur durée
    python -m jarvis.demo_direct --chapitre 5    un seul (pour refaire une prise)
    python -m jarvis.demo_direct --depuis 7      à partir de celui-là
    python -m jarvis.demo_direct --sans-video    saute le rendu Wan 2.2 (cinq minutes)
    python -m jarvis.demo_direct --pauses        attend une touche entre deux chapitres

`python -m jarvis demo` vérifie la veille que tout est prêt, `DEMO.md` donne le déroulé écrit ; ceci le **joue**.
Rien n'est simulé : le vrai serveur Jarvis (déjà lancé), le vrai HUD plein écran, les vraies phrases, la vraie
carte graphique. Le terminal sert de conducteur — il annonce le chapitre, ce qu'il faut regarder, et mesure
l'attente réelle. Ces chiffres-là sont ceux qu'on peut montrer sans mentir ; ils finissent dans
`workspace/mesures/demo_direct.json`.

**Vous n'avez rien à faire** : la démo se joue seule, du début à la fin. Les gestes sont rejoués point par point
(la même main que dans les tests — personne n'est filmé) et le scan regarde ce qui est déjà devant la caméra.
La superposition Windows n'est pas dans la démo : elle passe par-dessus tout, y compris ce qu'on filme.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
# la main des tests, reprise telle quelle : vingt-et-un points, comme MediaPipe les donne
POINTS = (Path(__file__).resolve().parent / "tests" / "gestes.py").read_text(encoding="utf-8")     .split('POINTS = """')[1].split('"""')[0]
SERVEUR = "http://127.0.0.1:8765"
EDGE = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
GRIS, CYAN, AMBRE, VERT, ROUGE, GRAS, FIN = "\033[90m", "\033[96m", "\033[93m", "\033[92m", "\033[91m", "\033[1m", "\033[0m"


# Le rythme. Une démo n'est pas un test : ce qui compte n'est pas d'aller vite, c'est que le spectateur ait
# le temps de VOIR. On ne demande jamais rien pendant que Jarvis parle ou qu'une carte graphique travaille.
TENUE = 7.0            # secondes de plan tenu après chaque effet
RESPIRE = 3.0          # souffle avant de dire la phrase suivante
RYTHME = 1.0           # multiplié par --rythme (1,5 = plus lent, 0,5 = plus vif)

# ----------------------------------------------------------------- parler au vrai Jarvis
def poster(route: str, corps: dict, delai: float = 180) -> dict:
    # On ne parle jamais par-dessus Jarvis : /parler et /dire font taire ce qui est en cours, et la phrase
    # précédente serait coupée en plein milieu (montage du 20/09).
    if route in ("/parler", "/dire"):
        fin = time.time() + 120
        while time.time() < fin and etat().get("parle"):
            time.sleep(0.25)
    requete = urllib.request.Request(SERVEUR + route, data=json.dumps(corps).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=delai) as r:
        return json.loads(r.read())


def etat() -> dict:
    try:
        with urllib.request.urlopen(SERVEUR + "/etat", timeout=10) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return {}


def silence(maxi: float = 180, calme_voulu: float = 3.0) -> None:
    """Attend que Jarvis ait VRAIMENT fini de parler.

    Trois secondes de calme d'affilée : Jarvis met un court instant à enchaîner deux morceaux de phrase, et
    deux secondes suffisaient à croire qu'il avait fini — la phrase suivante lui coupait alors la parole
    (montage du 20/09 : « des fois la voix se coupe »).
    """
    time.sleep(1.0)
    fin = time.time() + maxi
    calme = 0.0
    while time.time() < fin:
        if etat().get("parle"):
            calme = 0.0
        else:
            calme += 0.25
            if calme >= calme_voulu:
                return
        time.sleep(0.25)


async def tenir(c, secondes: float = TENUE, pourquoi: str = "") -> None:
    """Le plan tenu : rien ne se passe, exprès. C'est là que le spectateur regarde ce qui vient d'arriver."""
    duree = secondes * RYTHME
    if duree <= 0:
        return
    c.temps(f"{pourquoi or 'on laisse voir'} · {duree:.0f} s")
    await asyncio.sleep(duree)


class Conducteur:
    """Ce qui s'écrit dans le terminal pendant la prise, et le bilan de fin."""

    def __init__(self):
        self.lignes = []
        self.debut = time.time()

    def chapitre(self, n: int, titre: str, a_filmer: str):
        print(f"\n{CYAN}{GRAS}━━ {n:02d} · {titre.upper()}{FIN}")
        print(f"   {GRIS}à filmer : {a_filmer}{FIN}", flush=True)

    def phrase(self, texte: str):
        print(f"   {AMBRE}« {texte} »{FIN}", flush=True)

    def reponse(self, texte: str):
        if texte:
            print(f"   {GRIS}Jarvis :{FIN} {texte[:160]}", flush=True)

    def vous(self, consigne: str, secondes: int):
        print(f"   {GRAS}À VOUS{FIN} — {consigne}  {GRIS}({secondes} s){FIN}", flush=True)

    def mesure(self, quoi: str, secondes: float, seuil: float = 0, unite: str = "s"):
        couleur = ROUGE if secondes < 0 else (AMBRE if seuil and secondes > seuil else VERT)
        valeur = "rien ne vient" if secondes < 0 else f"{secondes:.1f} {unite}"
        print(f"   {couleur}▸ {quoi} : {valeur}{FIN}", flush=True)
        self.lignes.append({"quoi": quoi, "valeur": None if secondes < 0 else round(secondes, 2),
                            "unite": unite, "seuil": seuil or None})

    def temps(self, texte: str):
        print(f"   {GRIS}⏸  {texte}{FIN}", flush=True)

    def note(self, texte: str):
        print(f"   {GRIS}{texte}{FIN}", flush=True)

    def bilan(self):
        print(f"\n{CYAN}{GRAS}━━ BILAN{FIN}   {GRIS}{(time.time() - self.debut) / 60:.0f} min de démo{FIN}")
        for l in self.lignes:
            v = "—" if l["valeur"] is None else f"{l['valeur']:.1f} {l['unite']}"
            print(f"   {l['quoi']:<48s} {v:>10s}")
        fichier = RACINE / "workspace" / "mesures" / "demo_direct.json"
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps({"quand": time.strftime("%Y-%m-%d %H:%M"), "mesures": self.lignes},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   {GRIS}mesures écrites : {fichier}{FIN}")


# ----------------------------------------------------------------- la fenêtre qu'on filme
class Fenetre:
    """Le HUD en vrai, plein écran, regardé par le protocole DevTools (pour mesurer, pas pour tricher)."""

    def __init__(self, camera: str | bool):
        """`camera` : un fichier .y4m joué comme une webcam. Cette machine n'a pas de caméra, et beaucoup de
        machines n'en ont pas : le scan et les gestes se montrent quand même, sur une vraie image (la vidéo de
        bureau des tests). Rien n'est filmé, et le chemin du code exercé est exactement le même."""
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.profil = tempfile.mkdtemp(prefix="jarvis_demo_")
        options = [str(EDGE), f"--app={SERVEUR}/", "--start-fullscreen", f"--remote-debugging-port={self.port}",
                   f"--user-data-dir={self.profil}", "--use-angle=d3d11", "--ignore-gpu-blocklist",
                   "--enable-gpu-rasterization", "--autoplay-policy=no-user-gesture-required",
                   "--no-first-run", "--no-default-browser-check"]
        if camera:              # l'autorisation accordée d'office : aucune boîte de dialogue à l'image
            options.append("--use-fake-ui-for-media-stream")
            if isinstance(camera, str):
                options += ["--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={camera}"]
        self.proc = subprocess.Popen(options, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws, self.n = None, 0

    async def ouvrir(self, patience: int = 60):
        """Le canal de mesure. `ping_interval=None` : sans ça, la bibliothèque ferme la connexion au bout de
        vingt secondes sans trafic — et un chapitre qui laisse Jarvis parler reste muet plus longtemps que ça
        (c'est ce qui a coupé la première prise du 20/09)."""
        import websockets
        for _ in range(patience):
            try:
                pages = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=2).read())
                page = next(p for p in pages if p.get("type") == "page" and "127.0.0.1:8765" in p.get("url", ""))
                self.ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=2 ** 24,
                                                   ping_interval=None, close_timeout=2)
                return
            except Exception:
                await asyncio.sleep(0.5)
        raise RuntimeError("le HUD ne s'est pas ouvert")

    async def evaluer(self, expression: str, rattrapage: bool = True):
        try:
            self.n += 1
            await self.ws.send(json.dumps({"id": self.n, "method": "Runtime.evaluate",
                                           "params": {"expression": expression, "awaitPromise": True,
                                                      "returnByValue": True}}))
            while True:
                m = json.loads(await self.ws.recv())
                if m.get("id") == self.n:
                    r = m.get("result", {})
                    return None if r.get("exceptionDetails") else r.get("result", {}).get("value")
        except Exception:
            if not rattrapage:
                return None
            await self.ouvrir(10)                       # la fenêtre est toujours là : on se rebranche et on continue
            return await self.evaluer(expression, rattrapage=False)

    async def attendre(self, expression: str, delai: float = 30, pas: float = 0.25) -> float:
        """Attend que le HUD dise oui, et rend le temps que ça a pris (−1 s'il ne le dit jamais)."""
        debut = time.time()
        while time.time() - debut < delai:
            if await self.evaluer(f"(() => {{ try {{ return !!({expression}); }} catch (e) {{ return false; }} }})()"):
                return time.time() - debut
            await asyncio.sleep(pas)
        return -1.0

    def fermer(self):
        self.proc.kill()


async def _dire_et_voir(f: Fenetre, c: Conducteur, phrase: str, attendu: str, quoi: str,
                        seuil: float = 8, delai: float = 30, pas: float = 0.25, tenue: float = TENUE) -> float:
    """Une phrase, une seule chose à regarder, et le temps de la regarder.

    L'ordre compte : on dit la phrase, on attend que ça apparaisse à l'écran, on attend que Jarvis ait fini de
    parler, **puis** on tient le plan. Rien d'autre n'est lancé pendant ce temps-là.
    """
    await asyncio.sleep(RESPIRE * RYTHME)
    c.phrase(phrase)
    debut = time.time()
    r = poster("/parler", {"texte": phrase}, delai=max(180, delai))
    vu = await f.attendre(attendu, delai, pas) if attendu else 0
    c.reponse(r.get("reponse", ""))
    c.mesure(quoi, (time.time() - debut) if vu >= 0 else -1, seuil)
    silence()
    await tenir(c, tenue)
    return vu


# ----------------------------------------------------------------- ce que le spectateur lit à l'écran
STYLE_LEGENDE = """
#demo-legende { position: fixed; left: 50%; bottom: 7vh; transform: translateX(-50%); z-index: 90;
  width: min(78vw, 1500px); padding: 18px 28px 20px; border: 1px solid rgba(var(--c), .55);
  border-left: 4px solid var(--cyan); background: rgba(3, 10, 16, .88); box-shadow: 0 0 40px rgba(0,0,0,.6);
  opacity: 0; transition: opacity .45s; pointer-events: none; }
#demo-legende.visible { opacity: 1; }
#demo-legende .titre { font-family: Consolas, monospace; font-size: .8rem; letter-spacing: .32em;
  text-transform: uppercase; color: var(--cyan); margin-bottom: 8px; }
#demo-legende .texte { font-size: 1.25rem; line-height: 1.45; color: #eaffff; }
#demo-legende .note { margin-top: 10px; font-size: .95rem; color: var(--ambre); }
"""


async def legende(f: "Fenetre", titre: str, texte: str, note: str = "") -> None:
    """Écrit la bande de légende dans le HUD. Sans elle, le spectateur voit des choses bouger sans savoir
    pourquoi — c'est ce qu'a montré le montage du 20/09 : « on comprend pas trop »."""
    await f.evaluer("""(() => {
      if (!document.getElementById("demo-legende-style")) {
        const st = document.createElement("style"); st.id = "demo-legende-style";
        st.textContent = %s; document.head.appendChild(st);
      }
      let b = document.getElementById("demo-legende");
      if (!b) { b = document.createElement("div"); b.id = "demo-legende";
        b.innerHTML = '<div class="titre"></div><div class="texte"></div><div class="note"></div>';
        document.body.appendChild(b); }
      b.querySelector(".titre").textContent = %s;
      b.querySelector(".texte").textContent = %s;
      const n = b.querySelector(".note"); n.textContent = %s; n.style.display = %s ? "block" : "none";
      b.classList.add("visible");
      return 1; })()""" % (json.dumps(STYLE_LEGENDE), json.dumps(titre), json.dumps(texte),
                           json.dumps(note), json.dumps(bool(note))))


async def effacer_legende(f: "Fenetre") -> None:
    await f.evaluer("""(() => { const b = document.getElementById("demo-legende");
                               if (b) b.classList.remove("visible"); return 1; })()""")


# ----------------------------------------------------------------- les chapitres
async def ch_ouverture(f: Fenetre, c: Conducteur, o):
    c.chapitre(1, "la salle de briefing", "le réacteur qui tourne, le HUD au complet — tout tourne ici")
    await f.evaluer("window.__jarvis.video(true)")
    await legende(f, "1 · la salle de briefing",
                  "Tout ce que vous allez voir tourne sur cet ordinateur : le cerveau, la voix, l'oreille, "
                  "les images. Rien n'est envoyé sur internet — le compteur, en bas à droite, le prouve en direct.")
    await asyncio.sleep(1.5)
    carte = await f.evaluer("window.__jarvis.reacteur.carte()")
    mesure = await f.evaluer("window.__jarvis.reacteur.mesurer(3000)")
    e = etat()
    c.note(f"carte : {carte}")
    c.note(f"cerveau {e.get('modele')} · {e.get('souvenirs', 0)} souvenirs · "
           f"{e.get('sorties_internet', 0)} sortie internet depuis le démarrage")
    c.mesure("images par seconde du HUD", mesure["ips"], unite="i/s")
    await tenir(c, 8, "le réacteur tourne, on installe le plan")
    await _dire_et_voir(f, c, "Jarvis, dans quel état est la machine ?", "", "question → réponse (cerveau local)", 8,
                        tenue=9)


async def ch_bases(f: Fenetre, c: Conducteur, o):
    c.chapitre(2, "les bases", "réponse sans le cerveau, mémoire qui s'allume, fenêtres de Windows")
    await legende(f, "2 · les bases",
                  "Il répond, il retient, et il tient vraiment la machine : ouvrir une fenêtre, la ranger, "
                  "la fermer. Les questions simples ne réveillent même pas le cerveau.")
    await _dire_et_voir(f, c, "Jarvis, quelle heure est-il ?", "", "réflexe (sans le cerveau)", 2)
    await _dire_et_voir(f, c, "Retiens que je tourne une vidéo YouTube ce soir", "", "un souvenir est écrit", 8)
    await _dire_et_voir(f, c, "Qu'est-ce que tu sais de moi ?", "", "la mémoire relue", 12)
    await _dire_et_voir(f, c, "Ouvre le bloc-notes", "", "une fenêtre s'ouvre", 8)
    await _dire_et_voir(f, c, "Mets-le à droite", "", "elle se range à droite", 8)
    await _dire_et_voir(f, c, "Ferme le bloc-notes", "", "elle se ferme", 8)


async def ch_armures(f: Fenetre, c: Conducteur, o):
    c.chapitre(3, "les armures", "tout le HUD change de couleur : Mark III, Friday, Ultron, puis retour")
    await legende(f, "3 · les armures",
                  "Une phrase, et toute l'interface change d'habit : Mark III, Friday, Ultron, puis retour. "
                  "Les couleurs, les sons et les animations suivent.")
    if await f.evaluer('document.documentElement.dataset.theme') == "mark3":
        poster("/parler", {"texte": "Passe en armure Jarvis"})     # on part toujours du bleu : la bascule se voit
        silence()
        await asyncio.sleep(2)
    for phrase, theme in [("Passe en armure Mark III", "mark3"), ("Passe en mode Friday", "friday"),
                          ("Passe en armure Ultron", "ultron"), ("Reviens à l'armure Jarvis", "jarvis")]:
        await _dire_et_voir(f, c, phrase, f'document.documentElement.dataset.theme === "{theme}"',
                            f"bascule vers {theme}", 4, 15, tenue=8)


async def ch_visage(f: Fenetre, c: Conducteur, o):
    c.chapitre(4, "le visage", "le réacteur se défait en particules et devient un visage qui bouge les lèvres")
    await legende(f, "4 · le visage",
                  "Le réacteur se défait en sept mille particules et devient un visage. Ses lèvres suivent "
                  "le son de sa voix, image par image — et le tout continue de tourner à 144 images par seconde.")
    await _dire_et_voir(f, c, "Montre-toi", "window.__jarvis.reacteur.formeVisage >= 0.999",
                        "réacteur → visage", 6, 12)
    await tenir(c, 6, "le visage est là, on le regarde")
    await asyncio.sleep(RESPIRE * RYTHME)
    c.phrase("Raconte-moi en deux phrases ce que tu sais faire.")
    c.note("regardez les lèvres : elles suivent le niveau de la voix, image par image")
    poster("/parler", {"texte": "Raconte-moi en deux phrases ce que tu sais faire."})
    await asyncio.sleep(3)
    mesure = await f.evaluer("window.__jarvis.reacteur.mesurer(2500)")
    c.mesure("images par seconde avec le visage", mesure["ips"], unite="i/s")
    silence(120)
    await tenir(c, 6)
    await _dire_et_voir(f, c, "Redeviens le réacteur", "window.__jarvis.reacteur.formeVisage <= 0.001",
                        "visage → réacteur", 6, 12)


async def ch_majordome(f: Fenetre, c: Conducteur, o):
    c.chapitre(5, "la voix du majordome", "la même phrase, deux voix : la locale, puis le majordome britannique")
    texte = "Bonsoir monsieur. Tout est en ordre à la maison."
    await legende(f, "5 · deux voix, la même phrase",
                  "D'abord la voix locale, rapide et légère. Puis la voix de majordome, fabriquée ici même par "
                  "description (aucune voix réelle n'est imitée) — écoutez la différence sur la MÊME phrase.",
                  "La voix de majordome doit d'abord se charger sur la carte graphique : comptez une minute.")
    poster("/reglages", {"voix": {"moteur": "local"}})
    c.phrase(f"(voix locale) {texte}")
    poster("/dire", {"texte": texte})
    silence(60)
    await tenir(c, 5, "on vient d'entendre la voix locale")
    poster("/reglages", {"voix": {"moteur": "majordome"}}, delai=300)
    c.note("chargement de Qwen3-TTS sur la carte — on ne lui demande rien d'autre pendant ce temps-là")
    debut = time.time()
    while time.time() - debut < 180 and not etat().get("voix", {}).get("majordome"):
        time.sleep(1)
    c.mesure("la voix du majordome est prête", time.time() - debut, 90)
    debut = time.time()
    poster("/dire", {"texte": texte, "moteur": "majordome"}, delai=300)
    c.phrase(f"(majordome) {texte}")
    premier = -1.0
    for _ in range(1200):                      # le premier mot : l'attente que le spectateur ressent vraiment
        if etat().get("parle"):
            premier = time.time() - debut
            break
        time.sleep(0.05)
    c.mesure("premier mot du majordome", premier, 6)
    silence(150)
    await tenir(c, 6, "la différence entre les deux voix")
    poster("/reglages", {"voix": {"moteur": "local"}})


async def ch_hologramme(f: Fenetre, c: Conducteur, o):
    c.chapitre(6, "les hologrammes", "l'objet s'imprime du bas vers le haut, en matière cyan translucide")
    await legende(f, "6 · les hologrammes",
                  "On lui demande un objet : il le dessine, le sculpte en 3D, et l'imprime devant vous du bas "
                  "vers le haut. Tout est calculé sur cette machine, sans aucun service en ligne.")
    c.note("si l'objet n'a jamais été sculpté : une image, puis Hunyuan3D — plusieurs minutes, et on attend")
    await _dire_et_voir(f, c, "Montre-moi un casque d'Iron Man en hologramme",
                        "window.__jarvis.reacteur.etatHologramme.visible",
                        "demande → hologramme à l'écran", 30, 900, 0.5, tenue=0)
    fini = await f.attendre("window.__jarvis.reacteur.etatHologramme.impression >= 0.999", 30, 0.2)
    c.mesure("impression de l'hologramme (du bas vers le haut)", fini, 12)
    await tenir(c, 12, "il tourne sur lui-même : on le laisse tourner")
    c.note(await f.evaluer("JSON.stringify(window.__jarvis.reacteur.etatHologramme)") or "")


async def ch_gestes(f: Fenetre, c: Conducteur, o):
    c.chapitre(7, "les gestes", "un curseur holographique suit la main, la pince attrape l'hologramme, "
                                "le poignet le fait tourner, les deux mains le zooment")
    await legende(f, "7 · piloter à la main, sans rien toucher",
                  "Une webcam suffit : votre main devient la souris. On pince pour attraper l'hologramme, on "
                  "tourne le poignet pour le faire tourner, on écarte les deux mains pour l'agrandir.",
                  "Cet ordinateur n'a pas de webcam : les mouvements de main sont rejoués ici, "
                  "et c'est le vrai moteur de gestes qui répond. Chez vous, c'est votre main qui les produit.")
    vue = await _dire_et_voir(f, c, "Active les gestes", "window.__jarvis.mains && window.__jarvis.mains.actif",
                              "caméra allumée, modèle des mains chargé", 12, 30, tenue=5)
    if vue < 0:
        # la caméra peut être prise par un autre programme (OBS, Teams…) : les gestes se montrent quand même,
        # puisque ce qu'on regarde est le moteur de gestes, pas l'image de la caméra
        c.note("la caméra n'a pas répondu (un autre programme la tient ?) — les gestes se jouent sans elle")
    # un chapitre doit tenir debout tout seul : s'il n'y a pas d'hologramme (on a pu reprendre la démo ici),
    # on en fait venir un, sinon la pince se referme sur du vide
    if not await f.evaluer("window.__jarvis.reacteur.etatHologramme.visible"):
        c.note("aucun hologramme à l'écran : on en fait venir un avant d'y toucher")
        await _dire_et_voir(f, c, "Montre-moi un casque d'Iron Man en hologramme",
                            "window.__jarvis.reacteur.etatHologramme.visible", "l'hologramme revient", 30, 900, 0.5,
                            tenue=4)
    # La caméra et la main rejouée ne peuvent pas cohabiter : la vidéo de démonstration ne contient aucune main,
    # donc à chaque image la caméra annonce « plus de main » et relâche la pince entre deux gestes rejoués
    # (vu le 20/09 : l'objet tournait mais ne se déplaçait jamais). On montre la caméra, puis on la coupe.
    await _dire_et_voir(f, c, "Coupe les gestes", "", "la caméra s'éteint", 6, 15, tenue=3)
    c.note("la main est rejouée point par point (la même que dans les tests) : personne n'est filmé, "
           "et ce qui bouge à l'écran est le vrai code des gestes")
    # où pincer ? `attraper()` prend d'abord un panneau s'il y en a un sous le curseur : si on pince au milieu de
    # l'écran, on déplace un panneau au lieu de l'hologramme (vu le 20/09). On cherche donc un point vide.
    vide = await f.evaluer("""(() => {
      const candidats = [];
      for (let x = 0.3; x <= 0.7; x += 0.05) for (let y = 0.3; y <= 0.75; y += 0.05) {
        const n = document.elementFromPoint(x * innerWidth, y * innerHeight);
        if (!n || !n.closest(".holo, #gauche, #barre, #saisie, #entete")) candidats.push([+x.toFixed(2), +y.toFixed(2)]);
      }
      // le plus proche du centre : l'hologramme y est, et c'est là que le spectateur regarde
      candidats.sort((a, b) => (Math.hypot(a[0] - .5, a[1] - .5) - Math.hypot(b[0] - .5, b[1] - .5)));
      return candidats[0] || [0.5, 0.5]; })()""") or [0.5, 0.5]
    px, py = vide
    c.note(f"la main pince à {px:.2f}, {py:.2f} — un endroit libre, sinon c'est un panneau qu'elle attraperait")
    # chaque geste est joué lentement, un par un, avec le temps de le voir
    gestes = [("la main entre dans le champ", [(f"{{ x: {px - 0.15:.2f}, y: {py + 0.06:.2f} }}", 0.0),
                                               (f"{{ x: {px - 0.07:.2f}, y: {py + 0.02:.2f} }}", 0.2),
                                               (f"{{ x: {px:.2f}, y: {py:.2f} }}", 0.4)]),
              ("on pince : l'hologramme est attrapé", [(f"{{ x: {px:.2f}, y: {py:.2f}, pince: 0.1 }}", 0.6)]),
              ("on le déplace", [(f"{{ x: {px + 0.04:.2f}, y: {py - 0.02:.2f}, pince: 0.1 }}", 0.8),
                                 (f"{{ x: {px + 0.08:.2f}, y: {py - 0.04:.2f}, pince: 0.1 }}", 1.0)]),
              ("on tourne le poignet", [(f"{{ x: {px + 0.08:.2f}, y: {py - 0.04:.2f}, pince: 0.1,"
                                         " angle: -Math.PI / 2 + 0.35 }", 1.2),
                                        (f"{{ x: {px + 0.08:.2f}, y: {py - 0.04:.2f}, pince: 0.1,"
                                         " angle: -Math.PI / 2 + 0.8 }", 1.4)]),
              ("on lâche", [(f"{{ x: {px + 0.08:.2f}, y: {py - 0.04:.2f} }}", 1.6)])]
    await f.evaluer(POINTS + "window.__jarvis.mains.remettre(), 1")
    avant = await f.evaluer("JSON.stringify({ x: window.__jarvis.reacteur.reglageHologramme.x,"
                            " r: window.__jarvis.reacteur.etatHologramme.rotation })")
    for titre, pas in gestes:
        c.note(titre)
        await legende(f, "7 · les gestes", titre[0].upper() + titre[1:],
                      "mouvements de main rejoués : cet ordinateur n'a pas de webcam")
        for main, t in pas:
            await f.evaluer(POINTS + f"window.__jarvis.mains.rejouer([main({main})], {t}), 1")
            await asyncio.sleep(0.7 * RYTHME)
        await tenir(c, 4)
    # le zoom à deux mains : on écarte les mains, l'objet grandit — sinon la légende parle d'un geste qu'on ne
    # voit jamais (montage du 20/09 : « on zoome sur le truc en 3D et ça bouge pas »)
    await legende(f, "7 · les gestes", "On écarte les deux mains : l'hologramme grandit",
                  "mouvements de main rejoués : cet ordinateur n'a pas de webcam")
    avant_echelle = await f.evaluer("window.__jarvis.reacteur.reglageHologramme.echelle")
    for i, ecart in enumerate([0.10, 0.16, 0.24, 0.32, 0.40]):
        deux = (f"[main({{ x: {px - ecart:.2f}, y: {py:.2f}, pince: 0.1 }}), "
                f"main({{ x: {px + ecart:.2f}, y: {py:.2f}, pince: 0.1 }})]")
        await f.evaluer(POINTS + f"window.__jarvis.mains.rejouer({deux}, {2.0 + i * 0.2}), 1")
        await asyncio.sleep(0.8 * RYTHME)
    apres_echelle = await f.evaluer("window.__jarvis.reacteur.reglageHologramme.echelle")
    grandi = abs((apres_echelle or 1) - (avant_echelle or 1)) > 0.05
    c.mesure("l'hologramme a grandi entre les deux mains", 0.0 if grandi else -1)
    c.note(f"échelle {avant_echelle} → {apres_echelle}")
    await tenir(c, 6)
    apres = await f.evaluer("JSON.stringify({ x: window.__jarvis.reacteur.reglageHologramme.x,"
                            " r: window.__jarvis.reacteur.etatHologramme.rotation })")
    a, b = json.loads(avant or "{}"), json.loads(apres or "{}")
    bouge = abs(b.get("x", 0) - a.get("x", 0)) > 0.1 or abs(b.get("r", 0) - a.get("r", 0)) > 0.3
    c.mesure("l'hologramme a suivi la main", 0.0 if bouge else -1)
    c.note(f"déplacé de {b.get('x', 0) - a.get('x', 0):+.2f}, tourné de {b.get('r', 0) - a.get('r', 0):+.2f} rad")


async def ch_scan(f: Fenetre, c: Conducteur, o):
    c.chapitre(8, "le scan de la pièce", "la ligne de balayage, puis les cadres autour de ce qu'il reconnaît")
    await legende(f, "8 · scanner la pièce",
                  "Il regarde par la webcam, balaie l'image, et encadre ce qu'il reconnaît en le nommant. "
                  "Tout est reconnu sur la machine : aucune image ne part, rien n'est enregistré.",
                  "Cet ordinateur n'a pas de webcam : c'est une vidéo de bureau qui est donnée au navigateur "
                  "à la place. Chez vous, c'est votre pièce, en direct.")
    await _dire_et_voir(f, c, "Scanne la pièce", "document.querySelectorAll('#scan .cadre').length > 0",
                        "demande → objets encadrés", 25, 120, 0.3, tenue=0)
    # les noms se lisent pendant que les cadres sont à l'écran : après le plan tenu, le scan les a déjà retirés
    trouves = await f.evaluer("[...document.querySelectorAll('#scan .cadre .nom')].map(n => n.textContent).join(', ')")
    await tenir(c, TENUE, "les cadres et leurs noms")
    c.note(f"reconnus : {trouves or '—'} · rien n'est enregistré, rien ne sort de la machine")
    poster("/parler", {"texte": "Cache l'hologramme"})
    silence()


async def ch_globe(f: Fenetre, c: Conducteur, o):
    c.chapitre(9, "le globe", "la Terre en hologramme, la Station spatiale en direct, les séismes du jour")
    await legende(f, "9 · le globe",
                  "La Terre en hologramme, la Station spatiale à sa vraie position en ce moment, et les séismes "
                  "du jour qui pulsent là où ils ont eu lieu.",
                  "Ce sont les SEULES sorties internet de toute la démonstration, et elles sont comptées "
                  "en bas à droite.")
    avant = etat().get("sorties_internet", 0)
    await _dire_et_voir(f, c, "Montre-moi la Terre", "window.__jarvis.reacteur.etatGlobe.visible",
                        "la Terre tourne", 12, 60, 0.3, tenue=9)
    await _dire_et_voir(f, c, "Où est la Station spatiale ?", "window.__jarvis.reacteur.etatGlobe.station",
                        "position de l'ISS en direct", 20, 60, 0.3, tenue=9)
    await _dire_et_voir(f, c, "Montre-moi les séismes du jour", "window.__jarvis.reacteur.etatGlobe.seismes > 0",
                        "séismes du jour (USGS)", 20, 60, 0.3, tenue=12)
    c.note(f"compteur de sorties internet : {avant} → {etat().get('sorties_internet', 0)} "
           f"— il est en bas à droite, et il ne bouge que là")


async def ch_video(f: Fenetre, c: Conducteur, o):
    c.chapitre(10, "la vidéo générée", "Wan 2.2 dessine un plan puis l'anime — sur cette carte, pas dans le nuage")
    await legende(f, "10 · il tourne une vidéo",
                  "On lui demande un plan : il le dessine, puis il l'anime image par image. Cinq secondes de "
                  "film, calculées ici, sur la carte graphique de cette maison.",
                  "Comptez quatre à cinq minutes : il répond tout de suite et continue à vous parler pendant "
                  "que ça calcule.")
    debut = time.time()
    r = poster("/parler", {"texte": "Fais-moi une vidéo d'une armure qui décolle"}, delai=120)
    c.phrase("Fais-moi une vidéo d'une armure qui décolle")
    c.reponse(r.get("reponse", ""))
    panneau = await f.attendre('window.__jarvis.panneaux.ouvertDeGenre("video")', 20, 0.2)
    c.mesure("réponse immédiate et barre de progression", (time.time() - debut) if panneau >= 0 else -1, 8)
    c.note("le rendu tourne : on ne demande plus rien à Jarvis jusqu'à ce que la vidéo soit là")
    silence()
    debut, dernier = time.time(), 0.0
    film = -1.0
    while time.time() - debut < 900:
        pret = await f.evaluer('(() => { const p = window.__jarvis.panneaux.ouvertDeGenre("video");'
                               ' const v = p && p.querySelector("video");'
                               ' return v && v.src && v.duration > 1 ? 1 : 0; })()')
        if pret:
            film = time.time() - debut
            break
        if time.time() - dernier > 30:                 # un point d'avancement toutes les trente secondes
            dernier = time.time()
            avance = await f.evaluer('(() => { const p = window.__jarvis.panneaux.ouvertDeGenre("video");'
                                     ' const b = p && p.querySelector(".h-progres, progress, .barre");'
                                     ' return b ? (b.getAttribute("aria-valuenow") || b.value || b.style.width || "")'
                                     ' + "" : ""; })()')
            c.temps(f"rendu en cours · {time.time() - debut:.0f} s" + (f" · {avance}" if avance else ""))
        await asyncio.sleep(1.0)
    c.mesure("rendu complet (dessin puis animation)", film, 360)
    await tenir(c, 12, "la vidéo tourne en boucle dans le panneau")


async def ch_final(f: Fenetre, c: Conducteur, o):
    c.chapitre(11, "le mot de la fin", "le compteur de sorties internet, et le réacteur qui reste allumé")
    await legende(f, "11 · et tout ça, chez vous",
                  "Le cerveau, la voix, l'oreille, les images, la 3D, la vidéo : tout tourne sur cette machine. "
                  "Le compteur, en bas à droite, dit combien de fois Jarvis est sorti sur internet.")
    e = etat()
    c.note(f"sorties internet pendant toute la démo : {e.get('sorties_internet', 0)} "
           f"(le globe et l'ISS — tout le reste tourne ici)")
    await _dire_et_voir(f, c, "Merci Jarvis. Dis-nous au revoir.", "", "le mot de la fin", 12)
    silence(60)


CHAPITRES = [
    ("la salle de briefing", "1 min", ch_ouverture),
    ("les bases", "2 min 30", ch_bases),
    ("les armures", "1 min 30", ch_armures),
    ("le visage", "2 min", ch_visage),
    ("la voix du majordome", "3 min", ch_majordome),
    ("les hologrammes", "1 min (10 si l'objet n'est pas encore sculpté)", ch_hologramme),
    ("les gestes", "2 min", ch_gestes),
    ("le scan de la pièce", "1 min 30", ch_scan),
    ("le globe", "2 min 30", ch_globe),
    ("la vidéo générée", "5 à 6 min", ch_video),
    ("le mot de la fin", "1 min", ch_final),
]


def camera_de_demonstration() -> str:
    """La vidéo de bureau des tests, convertie en .y4m pour Edge. Chaîne vide si ffmpeg ou la vidéo manquent."""
    source = RACINE / "jarvis" / "tests" / "piece" / "bureau.mp4"
    if not source.exists():
        return ""
    from .config import CONFIG
    ffmpeg = CONFIG.get("chemins", {}).get("ffmpeg", "ffmpeg")
    y4m = Path(tempfile.mkdtemp(prefix="jarvis_demo_camera_")) / "camera.y4m"
    try:
        subprocess.run([str(ffmpeg), "-stream_loop", "20", "-i", str(source), "-pix_fmt", "yuv420p",
                        "-f", "yuv4mpegpipe", "-y", "-loglevel", "error", str(y4m)], check=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return str(y4m)
    except (OSError, subprocess.SubprocessError):
        return ""


def _comfyui() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=4):
            return True
    except (urllib.error.URLError, OSError):
        return False


def avant_le_tournage(o) -> list:
    """Ce qui doit être debout AVANT de filmer. On ne lance pas une démo sur une brique absente : la panne
    n'arriverait qu'au milieu de la prise, et la prise serait perdue (20/09 : ComfyUI éteint, la vidéo s'est
    arrêtée au chapitre 10 après vingt minutes de tournage)."""
    manque = []
    e = etat()
    if not e.get("pret", {}).get("cerveau"):
        manque.append(f"Jarvis ne répond pas sur {SERVEUR}, ou son cerveau n'est pas chargé (lancer.bat)")
    for quoi, ok in (("Whisper n'est pas prêt", "whisper"), ("la voix n'est pas prête", "voix")):
        if not e.get("pret", {}).get(ok):
            manque.append(quoi)
    if not o.sans_video and not _comfyui():
        from .config import CONFIG
        ou = CONFIG.get("chemins", {}).get("comfyui", "")
        manque.append("ComfyUI n'est pas lancé (sans lui, ni vidéo ni hologramme à sculpter) : lancez-le"
                      + (f" ({ou})" if ou else "") + ", ou passez --sans-video")
    return manque


async def jouer(o) -> int:
    manque = avant_le_tournage(o)
    if manque:
        print(f"{ROUGE}{GRAS}On ne tourne pas : il manque de quoi jouer la démo.{FIN}")
        for m in manque:
            print(f"   {ROUGE}✗ {m}{FIN}")
        return 1
    print(f"{VERT}tout est debout : cerveau, Whisper, voix"
          + (", ComfyUI" if not o.sans_video else "") + f"{FIN}")
    c = Conducteur()
    camera = "" if o.sans_camera else camera_de_demonstration()
    if not o.sans_camera and not camera:
        print(f"{ROUGE}pas d'image de caméra pour la démo (ffmpeg ou bureau.mp4 manquant) : "
              f"les gestes et le scan sont sautés{FIN}")
        o.sans_camera = True
    f = Fenetre(camera=camera)
    try:
        await f.ouvrir()
        await asyncio.sleep(3)
        if not await f.evaluer("!!(window.__jarvis && window.__jarvis.reacteur)"):
            print(f"{ROUGE}le HUD ne s'est pas ouvert{FIN}")
            return 1
        print(f"{GRIS}Le HUD est plein écran. Lancez l'enregistrement : ça commence dans "
              f"{o.compte_a_rebours:.0f} s.{FIN}", flush=True)
        await asyncio.sleep(o.compte_a_rebours)
        for n, (titre, _, fonction) in enumerate(CHAPITRES, 1):
            if n < o.depuis or (o.chapitre and n != o.chapitre):
                continue
            if o.sans_video and fonction is ch_video:
                continue
            if o.sans_camera and fonction in (ch_gestes, ch_scan):
                continue
            try:
                await fonction(f, c, o)
            except Exception as erreur:                  # une prise ratée n'arrête pas le tournage
                print(f"   {ROUGE}ce chapitre a échoué : {type(erreur).__name__} : {erreur}{FIN}", flush=True)
            if o.pauses and n < len(CHAPITRES):
                input(f"   {GRIS}(entrée pour le chapitre suivant){FIN}")
            else:
                await tenir(c, 4, "fin de chapitre")
        c.bilan()
        return 0
    finally:
        if not o.garder:
            f.fermer()


def main() -> int:
    a = argparse.ArgumentParser(description="La démo de Jarvis, en direct à l'écran")
    a.add_argument("--liste", action="store_true")
    a.add_argument("--chapitre", type=int, default=0)
    a.add_argument("--depuis", type=int, default=1)
    a.add_argument("--sans-video", action="store_true")
    a.add_argument("--sans-camera", action="store_true", help="ni gestes ni scan (aucune caméra ouverte)")
    a.add_argument("--pauses", action="store_true", help="attend une touche entre deux chapitres")
    a.add_argument("--garder", action="store_true", help="laisse la fenêtre ouverte à la fin")
    a.add_argument("--compte-a-rebours", type=float, default=10, help="secondes avant le premier chapitre")
    a.add_argument("--rythme", type=float, default=1.0,
                   help="1 = le rythme normal (plans tenus de 7 s), 1.5 = plus lent, 0.5 = plus vif")
    o = a.parse_args()
    global RYTHME
    RYTHME = max(0.2, o.rythme)
    if o.liste:
        print(f"{CYAN}{GRAS}Les chapitres de la démo{FIN}")
        for n, (titre, duree, _) in enumerate(CHAPITRES, 1):
            print(f"  {n:2d}. {titre:<28s} {GRIS}{duree}{FIN}")
        return 0
    return asyncio.run(jouer(o))


if __name__ == "__main__":
    sys.exit(main())
