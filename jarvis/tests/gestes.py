"""Test du pouvoir v3-5 : les gestes de la main.

    python -m jarvis.tests.gestes

1. la caméra est éteinte par défaut : charger le HUD ne l'allume pas, et la commande vocale existe pour l'allumer ;
2. la lecture des gestes, rejouée point par point (gestes.js, calcul pur) : pince, rotation du poignet, écartement
   des deux mains, balayage, main ouverte trois secondes ;
3. ce que les gestes commandent vraiment dans le HUD : hologramme attrapé, tourné, agrandi, retiré au balayage,
   panneau attrapé, réveil demandé ;
4. **de vraies vidéos de mains** (jarvis/tests/mains/, filmées à partir de photos dessinées ici même) passées dans
   MediaPipe en local, dans un vrai navigateur : les 21 points sont trouvés et les gestes reconnus ;
5. la cadence (règle v3) : la lecture des mains à 30 Hz ne dégrade pas le HUD."""
import asyncio
import sys
from pathlib import Path

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, SCENE, mesurer, serveur_fichiers

VIDEOS = Path(__file__).resolve().parent / "mains"

# une main de 21 points, fabriquée : `pince` rapproche le pouce de l'index, `angle` incline le poignet
POINTS = """
function main({x = 0.5, y = 0.5, taille = 0.25, pince = 1, angle = -Math.PI / 2, doigtsPlies = false} = {}) {
  const p = [], ca = Math.cos(angle), sa = Math.sin(angle);
  const pose = (dx, dy) => { const X = dx * ca - dy * sa, Y = dx * sa + dy * ca;
    p.push({ x: x + X * taille, y: y + Y * taille, z: 0 }); };
  pose(0, 0);                                                        // 0 poignet
  pose(0.35, -0.15); pose(0.6, -0.3); pose(0.75, -0.42);             // 1-3 pouce
  pose(0.85 * pince + 0.22 * (1 - pince), -0.55 * pince - 1.5 * (1 - pince));   // 4 bout du pouce : rejoint l'index quand on pince
  const l = doigtsPlies ? 0.55 : 1;
  pose(0.18, -0.85); pose(0.2, -1.15 * l); pose(0.21, -1.35 * l); pose(0.22, -1.5 * l);      // 5-8 index
  pose(0, -0.9); pose(0, -1.25 * l); pose(0, -1.45 * l); pose(0, -1.6 * l);                  // 9-12 majeur
  pose(-0.18, -0.85); pose(-0.2, -1.18 * l); pose(-0.21, -1.38 * l); pose(-0.22, -1.5 * l);  // 13-16 annulaire
  pose(-0.34, -0.72); pose(-0.4, -0.98 * l); pose(-0.43, -1.14 * l); pose(-0.45, -1.25 * l); // 17-20 auriculaire
  return p;
}
"""


def commande(v: Verifs):
    from .. import commandes as c
    dits = {"Active les gestes": ("gestes", "on"), "Jarvis, allume la caméra": ("gestes", "on"),
            "démarre le suivi des mains": ("gestes", "on"), "Coupe les gestes": ("gestes", "off"),
            "éteins la caméra": ("gestes", "off")}
    faux = {p: c.analyser(p) for p, a in dits.items() if c.analyser(p) != a}
    v.ok(not faux, "« active les gestes » et « coupe la caméra » sont compris", faux or "toutes les variantes")
    ordinaires = ["Parle-moi des gestes de la main", "Active la sentinelle", "Montre-moi une caméra en hologramme"]
    faux = {p: c.analyser(p) for p in ordinaires if c.analyser(p)[0] == "gestes"}
    v.ok(not faux, "une phrase ordinaire n'allume jamais la caméra", faux or "aucune")


def serveur(v: Verifs):
    from .. import serveur as S, voix
    evenements = []
    ancien_emettre, ancien_dire = S.EMETTEUR.emettre, voix.VOIX.dire
    S.EMETTEUR.emettre = evenements.append
    voix.VOIX.dire = lambda texte, *a, **k: None
    try:
        r = S._dialoguer("Active les gestes", source="texte")
        v.ok(any(e.get("type") == "gestes" and e.get("actif") is True for e in evenements),
             "le HUD reçoit l'ordre d'allumer la caméra (événement gestes)")
        v.ok("enregistré" in r["reponse"], "Jarvis dit que rien n'est enregistré", r["reponse"])
        evenements.clear()
        S._dialoguer("Coupe les gestes", source="texte")
        v.ok(any(e.get("type") == "gestes" and e.get("actif") is False for e in evenements), "et de l'éteindre")
    finally:
        S.EMETTEUR.emettre, voix.VOIX.dire = ancien_emettre, ancien_dire


async def lecture_des_gestes(v: Verifs, edge: Edge, port: int):
    """La logique, rejouée point par point : aucune caméra, aucun modèle, juste des suites de points."""
    r = await edge.evaluer(POINTS + """(async () => {
      const { lire, etatVide, mesurer } = await import("/hud/gestes.js");
      const sortie = {};
      // pince : ouverte, puis pouce et index joints, puis rouverte
      let e = etatVide(), g = [];
      g = g.concat(lire(e, [main({ pince: 1 })], 0));
      g = g.concat(lire(e, [main({ pince: 0.1 })], 0.1));
      g = g.concat(lire(e, [main({ pince: 0.1 })], 0.2));
      g = g.concat(lire(e, [main({ pince: 1 })], 0.3));
      sortie.pince = g.map(x => x.type);
      // rotation du poignet pendant la pince
      e = etatVide(); g = [];
      lire(e, [main({ pince: 0.1, angle: -Math.PI / 2 })], 0);
      g = lire(e, [main({ pince: 0.1, angle: -Math.PI / 2 + 0.5 })], 0.1);
      sortie.rotation = g.filter(x => x.type === "rotation").map(x => +x.delta.toFixed(2));
      // deux mains qui s'écartent
      e = etatVide(); g = [];
      lire(e, [main({ x: 0.45 }), main({ x: 0.55 })], 0);
      g = lire(e, [main({ x: 0.3 }), main({ x: 0.7 })], 0.2);
      sortie.zoom = g.filter(x => x.type === "zoom").map(x => +x.facteur.toFixed(2));
      // balayage : main ouverte lancée vers la droite
      e = etatVide(); g = [];
      lire(e, [main({ x: 0.2 })], 0);
      g = g.concat(lire(e, [main({ x: 0.5 })], 0.12));
      g = g.concat(lire(e, [main({ x: 0.8 })], 0.24));
      sortie.balayage = g.filter(x => x.type === "balayage").map(x => x.sens);
      // main ouverte et immobile trois secondes
      e = etatVide(); g = [];
      for (let t = 0; t <= 3.4; t += 0.1) g = g.concat(lire(e, [main({ x: 0.5 + Math.sin(t) * 0.001 })], t));
      sortie.reveil = g.filter(x => x.type === "reveil").map(x => x.tenue);
      // une main qui bouge sans rien faire de particulier : aucun geste
      e = etatVide(); g = [];
      for (let t = 0; t <= 1; t += 0.1) g = g.concat(lire(e, [main({ x: 0.4 + t * 0.05, pince: 0.9, doigtsPlies: true })], t));
      sortie.rien = g.filter(x => x.type !== "curseur").map(x => x.type);
      // les mesures d'une main ouverte
      sortie.mesure = (({ doigts, ouverte, pince }) => ({ doigts, ouverte, pince: +pince.toFixed(2) }))(mesurer(main({})));
      return sortie; })()""")
    v.ok(r["pince"].count("pince_debut") == 1 and r["pince"].count("pince_fin") == 1,
         "pincer puis rouvrir : un début et une fin de pince", r["pince"])
    v.ok(len(r["rotation"]) == 1 and abs(r["rotation"][0] - 0.5) < 0.05,
         "tourner le poignet pendant la pince : l'angle est rendu tel quel", r["rotation"])
    v.ok(r["zoom"] and r["zoom"][0] > 1.5, "écarter les deux mains : facteur d'agrandissement", r["zoom"])
    v.ok(r["balayage"] == ["droite"], "balayer : un seul geste, dans le bon sens", r["balayage"])
    v.ok(len(r["reveil"]) == 1 and 2.9 < r["reveil"][0] < 3.3, "main ouverte trois secondes : réveil, une seule fois", r["reveil"])
    v.ok(r["rien"] == [], "une main qui bouge doigts repliés ne déclenche rien", r["rien"])
    v.ok(r["mesure"]["doigts"] == 5 and r["mesure"]["ouverte"], "une main ouverte est reconnue comme telle", r["mesure"])


async def commandes_du_hud(v: Verifs, edge: Edge, port: int):
    """Ce que les gestes font vraiment : hologramme attrapé, tourné, agrandi, retiré ; panneau attrapé ; réveil."""
    r = await edge.evaluer(POINTS + """(async () => {
      const J = window.__jarvis, R = J.reacteur, M = J.mains;
      await R.hologramme("/workspace/hologrammes/dragon.glb", "un dragon");
      await new Promise(r => setTimeout(r, 1800));
      const sortie = { curseur: {}, notes: [] };
      M.remettre();
      // le curseur suit l'index
      M.rejouer([main({ x: 0.3, y: 0.4 })], 0);
      const c = document.getElementById("curseur-main");
      sortie.curseur.visible = c && c.classList.contains("visible");
      sortie.curseur.transform = c ? c.style.transform : "";
      // pince sur l'hologramme, puis on déplace la main : l'objet suit
      const avant = R.reglageHologramme;
      M.rejouer([main({ x: 0.5, y: 0.5, pince: 0.1 })], 0.1);
      M.rejouer([main({ x: 0.62, y: 0.42, pince: 0.1 })], 0.2);
      sortie.deplace = R.reglageHologramme.x - avant.x;
      sortie.pince = c.classList.contains("pince");
      // le poignet tourne : l'hologramme aussi
      const r0 = R.etatHologramme.rotation;
      M.rejouer([main({ x: 0.62, y: 0.42, pince: 0.1, angle: -Math.PI / 2 + 0.6 })], 0.3);
      sortie.tourne = R.etatHologramme.rotation - r0;
      M.rejouer([main({ x: 0.62, y: 0.42 })], 0.4);                    // on relâche
      // deux mains qui s'écartent : l'objet grandit
      const e0 = R.reglageHologramme.echelle;
      M.rejouer([main({ x: 0.45 }), main({ x: 0.55 })], 0.5);
      M.rejouer([main({ x: 0.25 }), main({ x: 0.75 })], 0.7);
      sortie.agrandi = R.reglageHologramme.echelle / e0;
      // balayage : l'hologramme est retiré
      M.rejouer([main({ x: 0.2 })], 1.0);
      M.rejouer([main({ x: 0.5 })], 1.12);
      M.rejouer([main({ x: 0.8 })], 1.24);
      await new Promise(r => setTimeout(r, 1500));
      sortie.retire = !R.etatHologramme.visible;
      // un panneau attrapé
      J.panneaux.ouvrir(J.DEMO.texte);
      await new Promise(r => setTimeout(r, 400));
      const p = document.querySelector("#panneaux > .holo"), b = p.getBoundingClientRect();
      const px = (b.left + b.width / 2) / innerWidth, py = (b.top + b.height / 2) / innerHeight;
      M.remettre();
      // le curseur, c'est le bout de l'index : on décale la main pour que l'index tombe sur le panneau
      const g0 = M.rejouer([main({ x: px, y: py })], 2.0).find(g => g.type === "curseur");
      const dx = px - g0.x, dy = py - g0.y;
      M.rejouer([main({ x: px + dx, y: py + dy })], 2.05);
      M.rejouer([main({ x: px + dx, y: py + dy, pince: 0.1 })], 2.1);
      sortie.panneauAttrape = p.classList.contains("attrape");
      sortie.sousLeCurseur = (document.elementFromPoint(px * innerWidth, py * innerHeight) || {}).className || "rien";
      M.rejouer([main({ x: px + dx + 0.05, y: py + dy + 0.05, pince: 0.1 })], 2.2);
      sortie.panneauDeplace = p.style.transform || "";
      M.rejouer([main({ x: px + dx + 0.05, y: py + dy + 0.05 })], 2.3);
      sortie.panneauLache = !p.classList.contains("attrape");
      sortie.compteurs = M.compteurs;
      return sortie; })()""")
    v.ok(r["curseur"]["visible"] and "translate" in r["curseur"]["transform"],
         "un curseur holographique suit l'index", r["curseur"]["transform"])
    v.ok(r["pince"], "le curseur se referme quand la main pince")
    v.ok(r["deplace"] > 0.2, "pincer un hologramme et bouger la main le déplace", f"{r['deplace']:.2f} unité")
    v.ok(abs(r["tourne"]) > 0.5, "tourner le poignet le fait tourner", f"{r['tourne']:.2f} rad")
    v.ok(r["agrandi"] > 1.2, "écarter les deux mains l'agrandit", f"×{r['agrandi']:.2f}")
    v.ok(r["retire"], "balayer le retire")
    v.ok(r["panneauAttrape"] and "translate" in r["panneauDeplace"] and r["panneauLache"],
         "un panneau s'attrape, se déplace et se relâche", {k: r[k] for k in ("panneauAttrape", "panneauDeplace", "panneauLache", "sousLeCurseur")})


async def videos(v: Verifs, edge: Edge, port: int):
    """MediaPipe en local sur de vraies vidéos de main (montées à partir de photos dessinées par ComfyUI)."""
    r = await edge.evaluer("""(async () => {
      const { lire, etatVide } = await import("/hud/gestes.js");
      const { FilesetResolver, HandLandmarker } = await import("/hud/vendor/mediapipe/vision_bundle.mjs");
      const t0 = performance.now();
      const fileset = await FilesetResolver.forVisionTasks("/hud/vendor/mediapipe");
      const lm = await HandLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: "/modeles/mediapipe/hand_landmarker.task", delegate: "GPU" },
        runningMode: "VIDEO", numHands: 2 });
      const chargement = performance.now() - t0;
      let horloge = 0;               // MediaPipe veut des horodatages toujours croissants, même d'une vidéo à l'autre
      // échauffement : la toute première lecture compile les shaders (3,7 s), ce qui mangeait la première vidéo
      const chauffe = document.createElement("canvas"); chauffe.width = 640; chauffe.height = 480;
      chauffe.getContext("2d").fillRect(0, 0, 640, 480);
      for (let i = 0; i < 3; i++) lm.detectForVideo(chauffe, (horloge += 33));

      async function passer(nom) {
        // la vidéo est JOUÉE, comme une caméra : sans affichage, un saut ne décode pas de nouvelle image et
        // MediaPipe relit toujours la première (constaté le 20/09). Chaque image présentée est analysée.
        const video = document.createElement("video");
        video.src = "/tests/mains/" + nom; video.muted = true; video.playsInline = true;
        await new Promise((ok, ko) => { video.onloadeddata = ok; video.onerror = () => ko(new Error("vidéo " + nom)); });
        const etat = etatVide(), gestes = [];
        let trouvees = 0, images = 0, deuxMains = 0, calcul = 0;
        await video.play();
        await new Promise(fini => {
          const secours = setTimeout(fini, 20000);
          const pas = (_, meta) => {
            const t1 = performance.now();
            const res = lm.detectForVideo(video, (horloge += 33));
            calcul += performance.now() - t1;
            images++;
            const mains = (res.landmarks || []).map(p => p.map(q => ({ x: 1 - q.x, y: q.y, z: q.z })));
            if (mains.length) trouvees++;
            if (mains.length >= 2) deuxMains++;
            for (const g of lire(etat, mains, meta.mediaTime)) if (g.type !== "curseur") gestes.push(g);
            if (video.ended) { clearTimeout(secours); fini(); } else video.requestVideoFrameCallback(pas);
          };
          video.requestVideoFrameCallback(pas);
        });
        return { nom, images, trouvees, deuxMains, ms: Math.round(calcul / Math.max(1, images)),
                 gestes: gestes.map(g => g.type), detail: gestes.filter(g => g.type !== "rotation").slice(0, 4),
                 rotations: gestes.filter(g => g.type === "rotation").map(g => +g.delta.toFixed(2)),
                 zooms: gestes.filter(g => g.type === "zoom").map(g => +g.facteur.toFixed(2)) };
      }
      const sortie = { chargement: Math.round(chargement), videos: {} };
      for (const nom of ["main-ouverte.mp4", "pince.mp4", "balayage.mp4", "rotation.mp4", "zoom.mp4"])
        sortie.videos[nom] = await passer(nom);
      return sortie; })()""")
    v.info(f"MediaPipe chargé en local en {r['chargement']} ms")
    for nom, d in r["videos"].items():
        v.info(f"{nom} : main trouvée sur {d['trouvees']}/{d['images']} images, {d['ms']} ms par image, "
               f"{d['deuxMains']} images à deux mains, gestes {sorted(set(d['gestes'])) or 'aucun'}")
    d = r["videos"]
    v.ok(all(x["trouvees"] >= x["images"] * 0.65 and x["images"] >= 10 for x in d.values()),
         "les 21 points de la main sont trouvés sur toutes les vidéos", {n: f"{x['trouvees']}/{x['images']}" for n, x in d.items()})
    v.ok("reveil" in d["main-ouverte.mp4"]["gestes"], "vidéo « main ouverte » : réveil demandé au bout de trois secondes",
         d["main-ouverte.mp4"]["gestes"])
    v.ok("pince_debut" in d["pince.mp4"]["gestes"] and "pince_fin" in d["pince.mp4"]["gestes"],
         "vidéo « pince » : la pince est vue commencer et finir", d["pince.mp4"]["detail"])
    v.ok("balayage" in d["balayage.mp4"]["gestes"], "vidéo « balayage » : le balayage est vu", d["balayage.mp4"]["gestes"])
    v.ok(len(d["rotation.mp4"]["rotations"]) >= 2 and sum(d["rotation.mp4"]["rotations"]) != 0,
         "vidéo « rotation » : le poignet qui tourne est suivi", d["rotation.mp4"]["rotations"][:6])
    v.ok(any(z > 1 for z in d["zoom.mp4"]["zooms"]), "vidéo « deux mains » : l'écartement est vu comme un agrandissement",
         d["zoom.mp4"]["zooms"][:6])
    v.ok(max(x["ms"] for x in d.values()) < 40, "une image de caméra est lue en moins de 40 ms",
         {n: x["ms"] for n, x in d.items()})


async def camera_factice(v: Verifs):
    """Le vrai chemin caméra : Edge joue une de nos vidéos comme si c'était la webcam (personne n'est filmé),
    l'autorisation est accordée d'office, et on vérifie que `mains.demarrer()` lit bien des mains et les rend."""
    import shutil
    import subprocess
    import tempfile
    from ..config import CONFIG
    ffmpeg = CONFIG.get("chemins", {}).get("ffmpeg", "ffmpeg")
    if not shutil.which(ffmpeg) and not Path(ffmpeg).exists():
        v.info("ffmpeg introuvable : essai de la caméra factice ignoré")
        return
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_camera_"))
    y4m = dossier / "camera.y4m"
    subprocess.run([str(ffmpeg), "-stream_loop", "3", "-i", str(VIDEOS / "pince.mp4"), "-pix_fmt", "yuv420p",
                    "-f", "yuv4mpegpipe", "-y", "-loglevel", "error", str(y4m)], check=True, timeout=120)
    s, port = serveur_fichiers()
    edge = Edge(1280, 800, camera=str(y4m))
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        r = await edge.evaluer("""(async () => {
            const J = window.__jarvis;
            const allume = await J.gestes(true);
            await new Promise(r => setTimeout(r, 6000));
            const c = J.mains.compteurs, curseur = document.getElementById("curseur-main");
            const sortie = { allume, images: c.images, ms: c.ms, gestes: c.gestes, dernier: c.dernierGeste,
                             voyant: document.body.classList.contains("gestes"),
                             curseur: curseur ? curseur.style.transform : "" };
            J.gestes(false);
            await new Promise(r => setTimeout(r, 500));
            sortie.eteinte = !J.mains.actif && !document.body.classList.contains("gestes");
            return sortie; })()""")
        v.info(f"caméra factice : {r['images']} images lues, {r['ms']} ms par lecture, {r['gestes']} gestes "
               f"(dernier : {r['dernier'] or 'aucun'})")
        v.ok(r["allume"] and r["images"] > 20, "la caméra s'allume à la demande et les mains sont lues en direct",
             f"{r['images']} images en 6 s")
        v.ok(r["voyant"] and "translate" in r["curseur"], "le voyant caméra s'affiche et le curseur suit la main", r["curseur"])
        v.ok(r["gestes"] > 0, "des gestes sont reconnus sur le flux de la caméra", f"{r['gestes']} gestes, dernier {r['dernier']}")
        v.ok(r["eteinte"], "« coupe les gestes » éteint la caméra pour de bon")
    finally:
        edge.fermer()
        s.shutdown()
        shutil.rmtree(dossier, ignore_errors=True)


async def hud(v: Verifs):
    s, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        camera = await edge.evaluer("""(async () => { let demande = false;
            const vrai = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia = (...a) => { demande = true; return vrai(...a); };
            await new Promise(r => setTimeout(r, 800));
            return { demande, actif: window.__jarvis.mains.actif, curseur: !!document.getElementById("curseur-main") }; })()""")
        v.ok(not camera["demande"] and not camera["actif"],
             "au chargement du HUD, la caméra reste éteinte et n'est même pas demandée", camera)
        await lecture_des_gestes(v, edge, port)
        await commandes_du_hud(v, edge, port)
        await videos(v, edge, port)

        # la cadence pendant que les mains sont lues (30 fois par seconde, sur une vidéo faute de caméra ici)
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "", 4000)
        v.info(f"cadence du HUD seul : {base['moyenne_ms']} ms/image, p99 {base['p99_ms']} ms")
        # comme en vrai : MediaPipe dans son fil, le HUD ne fait que lui envoyer une image (tout est prêt avant)
        await edge.evaluer("""(async () => {
            window.__ouvrier = new Worker("/hud/mains_ouvrier.js");
            const pret = new Promise(ok => { window.__ouvrier.onmessage = e => { if (e.data.type === "pret") ok(); }; });
            window.__ouvrier.postMessage({ type: "init", vendor: "/hud/vendor/mediapipe",
                                           modele: "/modeles/mediapipe/hand_landmarker.task", delegate: "CPU" });
            await pret;
            const video = document.createElement("video");
            video.src = "/tests/mains/main-ouverte.mp4"; video.loop = true; video.muted = true;
            await video.play();
            window.__video = video; window.__t = 0; window.__lus = 0; window.__msMain = 0;
            window.__ouvrier.onmessage = e => { if (e.data.type === "mains") { window.__lus++; window.__msMain = e.data.ms; window.__occupe = false; } };
            for (let i = 0; i < 8; i++) {                       // échauffement hors mesure
              const b = await createImageBitmap(video);
              window.__ouvrier.postMessage({ type: "image", image: b, ts: (window.__t += 33) }, [b]);
              await new Promise(r => setTimeout(r, 60));
            }
            return true; })()""")
        r = await mesurer(edge, """window.__lus = 0; window.__minuteur = setInterval(async () => {
            if (window.__occupe || window.__video.readyState < 2) return;
            window.__occupe = true;
            const b = await createImageBitmap(window.__video);
            window.__ouvrier.postMessage({ type: "image", image: b, ts: (window.__t += 33) }, [b]);
          }, 33)""", 5000)
        lus = await edge.evaluer("clearInterval(window.__minuteur); ({ lus: window.__lus, ms: Math.round(window.__msMain) })")
        v.info(f"pendant la mesure : {lus['lus']} mains lues en 5 s ({lus['ms']} ms par lecture, dans l'autre fil)")
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.15 and r["pire_ms"] < 18,
             "lire les mains 30 fois par seconde ne dégrade pas le HUD",
             f"{base['moyenne_ms']} → {r['moyenne_ms']} ms/image, pire {r['pire_ms']} ms")
        v.ok(r["p99_ms"] < BUDGET_144_MS, "budget 144 Hz tenu avec les mains", f"p99 {r['p99_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-5 · les gestes")
    manquantes = [n for n in ("main-ouverte.mp4", "pince.mp4", "balayage.mp4", "rotation.mp4", "zoom.mp4")
                  if not (VIDEOS / n).exists()]
    if manquantes:
        v.ok(False, "les vidéos de mains sont là", manquantes)
        return v.fin()
    commande(v)
    serveur(v)
    asyncio.run(hud(v))
    asyncio.run(camera_factice(v))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
