"""Test du pouvoir v3-8 : la vidéo tournée par Jarvis (Wan 2.2).

    python -m jarvis.tests.video_ia

1. le graphe envoyé à ComfyUI : bon modèle, dimensions multiples de 32 (sinon l'image sort verdâtre), longueur
   4k+1 images à 24 i/s, texte enrichi et négatif de Wan ;
2. la réponse est immédiate et annonce un délai tiré des mesures réelles, pas une promesse en l'air ;
3. l'alternance de mémoire vidéo : cerveau déchargé → ComfyUI seul → modèles libérés → cerveau rechargé, dans cet
   ordre, même si le rendu échoue ;
4. les vraies mesures (workspace/mesures/videos.json) : une vidéo a bien été tournée sur cette machine ;
5. le HUD : le panneau s'ouvre avec sa barre de progression, se met à jour, puis joue le film ; cadence tenue."""
import asyncio
import json
import sys
import time

from ._commun import Verifs
from .cadence import BUDGET_144_MS, MARGE, Edge, SCENE, mesurer, serveur_fichiers


def graphe(v: Verifs):
    from ..outils import generer_video as V
    g = V.graphe("a red car driving", 4.0, 42)
    v.ok(g["1"]["inputs"]["unet_name"] == V.MODELE and "wan" in V.MODELE.lower(), "le modèle Wan 2.2 est demandé", V.MODELE)
    v.ok(V.LARGEUR % 32 == 0 and V.HAUTEUR % 32 == 0, "dimensions multiples de 32 (sinon l'image sort verdâtre)",
         f"{V.LARGEUR}×{V.HAUTEUR}")
    longueur = g["8"]["inputs"]["length"]
    v.ok(longueur % 4 == 1 and 70 <= longueur <= 130, "longueur en 4k+1 images, soit environ 4 s à 24 i/s", f"{longueur} images")
    v.ok("start_image" not in g["8"]["inputs"], "texte vers vidéo : aucune image de départ")
    v.ok(g["6"]["inputs"]["text"].startswith("a red car driving") and "cinematic" in g["6"]["inputs"]["text"],
         "la demande est enrichie (lumière, mouvement, netteté)", g["6"]["inputs"]["text"][:70])
    v.ok("text, watermark" in g["7"]["inputs"]["text"], "le négatif officiel de Wan est en place")
    v.ok(g["12"]["inputs"]["format"] == "mp4" and g["11"]["inputs"]["fps"] == 24, "sortie mp4 à 24 images par seconde")


def attente(v: Verifs):
    from ..outils import generer_video as V
    v.ok(V.phrase_attente(90).startswith("Comptez une minute et demie"), "sous 105 s : une minute et demie", V.phrase_attente(90))
    v.ok("deux" in V.phrase_attente(140), "vers 140 s : deux minutes", V.phrase_attente(140))
    v.ok("disque" in V.phrase_attente(240), "au-delà : il dit pourquoi c'est long", V.phrase_attente(240))
    v.info(f"annonce actuelle, d'après ses dernières vidéos : « {V.phrase_attente(V.attente_probable())} » "
           f"({V.attente_probable():.0f} s)")


def alternance(v: Verifs):
    """La mémoire vidéo : on remplace ComfyUI par un faux et on regarde l'ordre des opérations."""
    from .. import cerveau as module_cerveau
    from ..outils import generer_image, generer_video as V
    ordre = []
    faux_reponse = type("R", (), {"status_code": 200, "text": "", "json": lambda self: {"prompt_id": "essai"}})()
    anciens = (module_cerveau.CERVEAU.decharger, module_cerveau.CERVEAU.charger, generer_image.liberer_avant,
               V._suivre, V._recuperer, V.sur_evenement, generer_image.comfyui_present)
    import requests
    ancien_post = requests.post
    evenements = []
    try:
        module_cerveau.CERVEAU.decharger = lambda: ordre.append("cerveau déchargé")
        module_cerveau.CERVEAU.charger = lambda: ordre.append("cerveau rechargé")
        generer_image.liberer_avant = lambda: ordre.append("ComfyUI libéré")
        generer_image.comfyui_present = lambda: True
        requests.post = lambda *a, **k: (ordre.append("graphe envoyé"), faux_reponse)[1]
        V._suivre = lambda *a, **k: ordre.append("avancement suivi")
        V._recuperer = lambda pid: (_ for _ in ()).throw(RuntimeError("essai : pas de vraie vidéo"))
        V.sur_evenement = evenements.append
        t = time.time()
        phrase = V.executer("a test clip", 4)
        immediat = time.time() - t
        for _ in range(60):
            if any(e["type"] == "video_ia_fin" for e in evenements):
                break
            time.sleep(0.1)
    finally:
        (module_cerveau.CERVEAU.decharger, module_cerveau.CERVEAU.charger, generer_image.liberer_avant,
         V._suivre, V._recuperer, V.sur_evenement, generer_image.comfyui_present) = anciens
        requests.post = ancien_post
    v.ok(immediat < 1.0 and "tourne" in phrase, "la réponse part tout de suite", f"{immediat * 1000:.0f} ms · {phrase}")
    v.ok(ordre[:4] == ["cerveau déchargé", "ComfyUI libéré", "graphe envoyé", "avancement suivi"],
         "le cerveau quitte la carte avant que Wan s'en serve", ordre[:4])
    v.ok(ordre[-2:] == ["ComfyUI libéré", "cerveau rechargé"],
         "et il revient après, même quand le rendu échoue", ordre[-2:])
    v.ok(any(e["type"] == "video_ia_erreur" for e in evenements), "l'échec est annoncé, pas avalé",
         [e["type"] for e in evenements])


def mesures_reelles(v: Verifs) -> str:
    from ..outils import generer_video as V
    if not V.MESURES.exists():
        v.ok(False, "une vidéo a été tournée pour de vrai sur cette machine", "aucune mesure")
        return ""
    liste = json.loads(V.MESURES.read_text(encoding="utf-8"))
    for m in liste[-2:]:
        v.info(f"« {m['prompt'][:46]} » : {m.get('total')} s au total "
               f"(dont {m.get('chargement_modele')} s de lecture du modèle et {m.get('rendu')} s de rendu)")
    m = liste[-1]
    v.ok(m.get("rendu", 0) > 0 and m.get("total", 0) > 0, "une vidéo a été tournée pour de vrai sur cette machine", m["quand"])
    v.ok(m.get("chargement_modele", 999) < m.get("total", 0), "le temps se partage entre lecture du modèle et rendu",
         f"{m.get('chargement_modele')} s + {m.get('rendu')} s")
    from ..config import RACINE
    videos = sorted((RACINE / "workspace" / "videos").glob("*.mp4"))
    v.ok(videos and videos[-1].stat().st_size > 50_000, "le fichier est là et n'est pas vide",
         f"{videos[-1].name}, {videos[-1].stat().st_size // 1024} Ko" if videos else "aucun")
    return f"/workspace/videos/{videos[-1].name}" if videos else ""


async def hud(v: Verifs, url: str):
    s, port = serveur_fichiers()
    edge = Edge(1600, 1000)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        r = await edge.evaluer(f"""(async () => {{
            const J = window.__jarvis;
            J.recevoir({{ type: "video_debut", prompt: "a test clip" }});
            await new Promise(r => setTimeout(r, 300));
            const p = J.panneaux.ouvertDeGenre("video");
            const barre = p && p.querySelector(".h-progression");
            const debut = {{ ouvert: !!p, barre: !!barre, largeur: barre && barre.querySelector(".h-avance").style.width }};
            J.recevoir({{ type: "video_avance", pourcent: 45, etape: "rendu" }});
            await new Promise(r => setTimeout(r, 600));
            const milieu = {{ largeur: barre.querySelector(".h-avance").style.width,
                             texte: barre.querySelector(".h-etape").textContent }};
            J.recevoir({{ type: "video_prete", url: "{url}", duree: 4, chrono: {{ total: 190, rendu: 120 }} }});
            await new Promise(r => setTimeout(r, 1500));
            const film = p.querySelector("video");
            const fin = {{ src: (film.src || "").slice(-30), duree: film.duration, joue: !film.paused,
                          boucle: film.loop, muet: film.muted, barreCachee: barre.classList.contains("finie"),
                          largeurAffichee: film.getBoundingClientRect().width }};
            return {{ debut, milieu, fin }}; }})()""")
        v.ok(r["debut"]["ouvert"] and r["debut"]["barre"], "le panneau s'ouvre tout de suite avec sa barre", r["debut"])
        v.ok(r["milieu"]["largeur"] == "45%" and "45" in r["milieu"]["texte"],
             "la barre suit l'avancement du rendu", r["milieu"])
        v.ok(r["fin"]["duree"] > 3 and r["fin"]["joue"] and r["fin"]["boucle"] and r["fin"]["muet"],
             "la vidéo se joue en boucle dans le panneau", r["fin"])
        v.ok(r["fin"]["barreCachee"] and r["fin"]["largeurAffichee"] > 200, "la barre laisse la place au film",
             f"{r['fin']['largeurAffichee']:.0f} px de large")

        await edge.aller(f"http://127.0.0.1:{port}{SCENE}")
        base = await mesurer(edge, "", 4000)
        v.info(f"cadence du HUD seul : {base['moyenne_ms']} ms/image, p99 {base['p99_ms']} ms")
        r = await mesurer(edge, f"""(() => {{ const J = window.__jarvis;
            J.recevoir({{ type: "video_debut", prompt: "essai" }});
            J.recevoir({{ type: "video_prete", url: "{url}", duree: 4, chrono: {{ total: 190 }} }}); }})()""", 5000)
        v.ok(r["moyenne_ms"] <= base["moyenne_ms"] * MARGE + 0.15 and r["pire_ms"] < 18,
             "le HUD garde sa cadence pendant que la vidéo tourne en boucle",
             f"{base['moyenne_ms']} → {r['moyenne_ms']} ms/image, pire {r['pire_ms']} ms")
        v.ok(r["p99_ms"] < BUDGET_144_MS, "budget 144 Hz tenu", f"p99 {r['p99_ms']} ms")
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    v = Verifs("Pouvoir v3-8 · la vidéo tournée par Jarvis")
    graphe(v)
    attente(v)
    alternance(v)
    url = mesures_reelles(v)
    if url:
        asyncio.run(hud(v, url))
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
