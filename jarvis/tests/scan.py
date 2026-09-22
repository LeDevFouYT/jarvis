"""Test du pouvoir v3-6 : le scan de la pièce.

    python -m jarvis.tests.scan

1. les noms : les 80 catégories du modèle ont un nom français, et l'énumération se dit bien (« deux tasses et… ») ;
2. la commande « scanne la pièce », jamais sur une phrase ordinaire, et ce que le serveur en fait (ordre au HUD,
   puis Jarvis dit ce qui a été vu — des noms, jamais une image) ;
3. le scan dans un vrai navigateur avec une **caméra simulée** (Edge joue une vidéo de bureau : personne n'est
   filmé) : la caméra s'allume, la ligne de balayage descend, les objets sont reconnus et encadrés avec leur nom,
   la caméra s'éteint seule à la fin, et **rien n'est enregistré** (seuls des noms sortent de la page) ;
4. la cadence (règle v3) : le scan ne dégrade pas le HUD."""
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, SCENE, mesurer, serveur_fichiers

VIDEO = Path(__file__).resolve().parent / "piece" / "bureau.mp4"
ATTENDUS = {"laptop", "cup", "chair", "potted plant", "tv", "dining table", "keyboard"}


async def enumeration(v: Verifs, edge: Edge, port: int):
    r = await edge.evaluer("""(async () => {
        const { enumerer, nomFrancais, NOMS } = await import("/hud/objets.js");
        return { categories: Object.keys(NOMS).length,
                 anglais: Object.entries(NOMS).filter(([c, n]) => n[0] === c).map(([c]) => c),
                 bureau: ["laptop", "cup", "chair", "potted plant", "tv", "dining table", "keyboard"].filter(c => !NOMS[c]),
                 un: enumerer([{ nom: "laptop" }]),
                 deux: enumerer([{ nom: "cup" }, { nom: "cup" }, { nom: "laptop" }]),
                 trois: enumerer([{ nom: "chair" }, { nom: "chair" }, { nom: "potted plant" }, { nom: "tv" }]),
                 vide: enumerer([]), inconnu: nomFrancais("licorne"), clavier: nomFrancais("keyboard") }; })()""")
    v.ok(r["categories"] >= 80 and not r["anglais"], "les 80 catégories du modèle ont un nom français",
         f"{r['categories']} noms" + (f", restées en anglais : {r['anglais']}" if r["anglais"] else ""))
    v.ok(not r["bureau"], "les objets d'un bureau ont le leur", r["bureau"] or "tous")
    v.ok(r["un"] == "un ordinateur portable", "un objet seul se dit avec son article", r["un"])
    v.ok(r["deux"] == "deux tasses et un ordinateur portable", "plusieurs objets s'énumèrent en français", r["deux"])
    v.ok(r["trois"] == "deux chaises, une plante et un écran", "trois sortes, séparées par des virgules puis « et »", r["trois"])
    v.ok(r["vide"] == "" and r["inconnu"] == "licorne" and r["clavier"] == "un clavier",
         "rien à dire quand rien n'est vu ; un nom inconnu reste tel quel", [r["vide"], r["inconnu"], r["clavier"]])


def commande(v: Verifs):
    from .. import commandes as c
    dits = ["Scanne la pièce", "Jarvis, analyse la pièce.", "scanne la salle", "regarde autour de toi",
            "examine la chambre", "balaie le bureau"]
    faux = {p: c.analyser(p) for p in dits if c.analyser(p) != ("scan", "")}
    v.ok(not faux, "« scanne la pièce » et ses variantes sont comprises", faux or "toutes")
    ordinaires = ["Analyse cette photo", "scanne mon disque dur", "Regarde mon écran", "Parle-moi de la pièce",
                  "Montre-moi une pièce en hologramme"]
    faux = {p: c.analyser(p) for p in ordinaires if c.analyser(p)[0] == "scan"}
    v.ok(not faux, "une phrase ordinaire n'allume pas la caméra", faux or "aucune")


def serveur(v: Verifs):
    from .. import serveur as S, voix
    evenements, dits = [], []
    ancien_emettre, ancien_dire = S.EMETTEUR.emettre, voix.VOIX.dire
    S.EMETTEUR.emettre = evenements.append
    voix.VOIX.dire = lambda texte, *a, **k: dits.append(texte)
    try:
        r = S._dialoguer("Scanne la pièce", source="texte")
        v.ok(any(e.get("type") == "scan" and e.get("actif") for e in evenements), "le HUD reçoit l'ordre de scanner")
        v.ok("enregistré" in r["reponse"], "Jarvis prévient que rien n'est enregistré", r["reponse"])
        evenements.clear()
        rep = S.scan_resultat(S.ResultatScan(phrase="un ordinateur portable et deux tasses",
                                             objets=[{"nom": "laptop", "score": 0.7, "x": 0.2, "y": 0.3}]))
        v.ok(dits and dits[-1].startswith("Je vois un ordinateur portable et deux tasses"),
             "le HUD lui renvoie des noms, qu'il dit", dits[-1] if dits else "rien")
        v.ok(any(e.get("type") == "scan_resultat" for e in evenements) and rep["ok"], "le résultat est aussi affiché")
        dits.clear()
        S.scan_resultat(S.ResultatScan(phrase="", objets=[]))
        v.ok("ne reconnais rien" in dits[-1], "et il le dit quand il ne reconnaît rien", dits[-1])
    finally:
        S.EMETTEUR.emettre, voix.VOIX.dire = ancien_emettre, ancien_dire


async def scan_camera(v: Verifs, y4m: Path):
    """Le vrai chemin : caméra (simulée par la vidéo de bureau), balayage, cadres, extinction."""
    s, port = serveur_fichiers()
    edge = Edge(1600, 1000, camera=str(y4m))
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        await enumeration(v, edge, port)
        r = await edge.evaluer("""(async () => {
            const J = window.__jarvis;
            // rien ne doit sortir de la page à part des noms : on garde ce que le HUD envoie
            const envois = [];
            const vrai = window.fetch;
            window.fetch = (u, o) => { envois.push({ url: String(u), corps: o && o.body ? String(o.body) : "" }); return Promise.resolve({ ok: true, json: async () => ({}) }); };
            const depart = performance.now();
            const liste = await J.scan.lancer();
            const pendant = { balaye: false, ligne: "" };
            const mesures = { duree: performance.now() - depart };
            const boite = document.getElementById("scan");
            const cadres = [...boite.querySelectorAll(".cadre")].map(c => ({
                nom: c.querySelector(".nom").textContent, gauche: c.style.left, haut: c.style.top, largeur: c.style.width }));
            mesures.fige = boite.classList.contains("fige");
            mesures.visible = boite.classList.contains("visible");
            mesures.videoArretee = !boite.querySelector("video").srcObject ||
                boite.querySelector("video").srcObject.getVideoTracks().every(t => t.readyState === "ended");
            window.fetch = vrai;
            return { liste, cadres, mesures, envois, compteurs: J.scan.compteurs, phrase: J.scan.phrase }; })()""")
        trouves = {o["nom"] for o in r["liste"]}
        v.info(f"scan : {r['compteurs']['lectures']} lectures ({r['compteurs']['ms']} ms chacune), "
               f"{len(r['liste'])} objets · « {r['phrase']} »")
        v.ok(len(trouves & ATTENDUS) >= 3, "les objets de la pièce sont reconnus par le modèle local",
             f"{sorted(trouves)} (attendus : {sorted(ATTENDUS)})")
        v.ok(all(c["nom"] and "%" in c["nom"] for c in r["cadres"]) and r["cadres"],
             "chaque objet a son cadre, avec son nom en français et sa confiance", [c["nom"] for c in r["cadres"][:4]])
        v.ok(all("%" in c["gauche"] and "%" in c["largeur"] for c in r["cadres"]),
             "les cadres sont posés à la bonne place sur l'image", r["cadres"][0] if r["cadres"] else "aucun")
        v.ok(3.5 > r["mesures"]["duree"] / 1000 > 2.2, "le balayage dure environ deux secondes et demie",
             f"{r['mesures']['duree'] / 1000:.1f} s")
        v.ok(r["mesures"]["videoArretee"] and r["mesures"]["fige"],
             "la caméra est rendue dès la fin du balayage, l'image reste figée le temps de lire", r["mesures"])
        # le HUD interroge /etat en fond : on ne regarde que ce qui part AVEC un contenu
        envois = [e for e in r["envois"] if e["corps"]]
        v.ok(len(envois) == 1 and envois[0]["url"].endswith("/scan/resultat"),
             "un seul envoi de données : le résultat du scan", [e["url"] for e in r["envois"]])
        corps = json.loads(envois[0]["corps"] or "{}") if envois else {}
        v.ok("phrase" in corps and corps.get("objets") and all(set(o) <= {"nom", "score", "x", "y"} for o in corps["objets"]),
             "ce qui sort de la page : des noms et des positions, aucune image", str(corps)[:160])
        v.ok(all(not any(m in e["corps"] for m in ("data:image", "base64", "blob:")) for e in r["envois"]),
             "aucune image ni aucun extrait d'image n'est envoyé")

        # la cadence du HUD pendant un scan
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "", 4000)
        v.info(f"cadence du HUD seul : {base['moyenne_ms']} ms/image, p99 {base['p99_ms']} ms")
        r = await mesurer(edge, "window.__jarvis.scan.lancer()", 3000)
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.15 and r["pire_ms"] < 18,
             "le HUD garde sa cadence pendant le scan",
             f"{base['moyenne_ms']} → {r['moyenne_ms']} ms/image, pire {r['pire_ms']} ms")
        v.ok(r["p99_ms"] < BUDGET_144_MS, "budget 144 Hz tenu pendant le scan", f"p99 {r['p99_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-6 · le scan de la pièce")
    if not VIDEO.exists():
        v.ok(False, "la vidéo de pièce du test est là", str(VIDEO))
        return v.fin()
    commande(v)
    serveur(v)
    from ..config import CONFIG
    ffmpeg = CONFIG.get("chemins", {}).get("ffmpeg", "ffmpeg")
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_piece_"))
    y4m = dossier / "camera.y4m"
    try:
        subprocess.run([str(ffmpeg), "-stream_loop", "4", "-i", str(VIDEO), "-pix_fmt", "yuv420p",
                        "-f", "yuv4mpegpipe", "-y", "-loglevel", "error", str(y4m)], check=True, timeout=180)
        asyncio.run(scan_camera(v, y4m))
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
