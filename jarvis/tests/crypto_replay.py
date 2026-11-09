"""Test de la brique crypto 4 : le replay des 10 derniers jours (vidéo 4).

    python -m jarvis.tests.crypto_replay              tout, avec les 60 vraies décisions de qwen3:14b (~2 min)
    python -m jarvis.tests.crypto_replay sans_cerveau  sans le modèle (moteur, preuve, HUD avec un décideur simple)

1. « rejoue tes 10 derniers jours » et « pourquoi tu as vendu le 12 ? » sont compris ;
2. la fenêtre : 60 décisions toutes les 4 h sur les 10 derniers jours, bougies réelles (Binance, Kraken en repli) ;
3. LA PREUVE QU'IL NE VOIT PAS LE FUTUR : pour chacune des 60 décisions, on remplace toutes les bougies postérieures
   par des prix absurdes (× 100, puis ÷ 100) et la consigne envoyée au modèle reste identique au caractère près ;
   aucune bougie vue ne se clôt après l'instant de décision ; l'ordre passe au prix connu à cet instant ;
4. mêmes frais qu'en vrai (0,1 %), comparaison juste avec « garder ses euros » et « tout en Bitcoin le premier jour » ;
5. les 60 décisions de qwen3:14b (température 0, JSON), avec leurs raisons, chronométrées, et un seul modèle en
   mémoire (Ollama ne recharge pas, ne charge rien d'autre) ;
6. « pourquoi tu as vendu le… » relit la vraie raison ; le commentaire final ne dit que des chiffres du bilan ;
7. le HUD (Edge sans fenêtre) : la courbe avance, un point par ordre, le résultat tombe, rien ne dépasse, cadence tenue.
Tout va dans workspace/mesures/crypto.json (section 4_replay), décisions et raisons comprises."""
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

import requests

from ._commun import Verifs

CAPTURES = Path(__file__).resolve().parents[2] / "workspace" / "captures" / "crypto"


def phrases(v: Verifs):
    from .. import commandes
    attendus = {"Jarvis, rejoue tes 10 derniers jours.": ("crypto_replay", {"action": "lancer"}),
                "Rejoue tes dix derniers jours": ("crypto_replay", {"action": "lancer"}),
                "montre-moi tes 10 derniers jours": ("crypto_replay", {"action": "lancer"}),
                "Pourquoi tu as vendu le 12 ?": ("crypto_replay", {"action": "pourquoi", "verbe": "vendu", "jour": 12}),
                "pourquoi as-tu acheté du solana le 9": ("crypto_replay", {"action": "pourquoi", "verbe": "achete", "jour": 9})}
    faux = {p: commandes.analyser(p) for p, a in attendus.items() if commandes.analyser(p) != a}
    v.ok(not faux, "« rejoue tes 10 derniers jours » et « pourquoi tu as vendu le 12 » sont compris", faux or f"{len(attendus)} phrases")


def decideur_simple(consigne: str):
    """Sans modèle : achète du BTC si sa variation 24 h est négative, vend la moitié si elle dépasse +1 %."""
    ligne = next(l for l in consigne.splitlines() if l.startswith("BTC "))
    var = float(ligne.split("24 h ")[1].split(" %")[0].replace("−", "-").replace("+", "").replace(",", ".").replace(" ", ""))
    if var < 0 and "disponibles" in consigne and not consigne.split("PORTEFEUILLE FICTIF : ")[1].startswith("0,"):
        return {"action": "acheter", "crypto": "BTC", "montant_eur": 1500, "raison": f"le BTC perd {var} % sur 24 h"}, {}
    if var > 1:
        return {"action": "vendre", "crypto": "BTC", "fraction": 0.5, "raison": f"le BTC prend {var} % sur 24 h"}, {}
    return {"action": "attendre", "crypto": "aucune", "raison": "rien de net"}, {}


def moteur(v: Verifs, mesures: dict):
    from ..crypto import replay as R
    from ..crypto.portefeuille import FRAIS
    debut, fin = R.fenetre()
    t = time.time()
    marche = R.Marche.telecharger(debut, fin)
    mesures["telechargement_s"] = round(time.time() - t, 2)
    jeu = R.Replay(marche, debut, fin, decider=decideur_simple)
    inst = jeu.instants()
    v.ok(len(inst) == 60 and inst[0] == debut and inst[-1] == fin - R.PAS and fin % R.PAS == 0 and fin - debut == 10 * 86400,
         "60 décisions, toutes les 4 h, sur les 10 derniers jours", f"{R.date_fr(debut)} → {R.date_fr(fin)}")
    v.ok(all(len(marche.series[s]) >= 10 * 24 + 7 * 24 for s in R.UNIVERS) and all(marche.series[s][-1]["t"] + 3600 == fin for s in R.UNIVERS),
         "bougies réelles d'une heure pour BTC, ETH, SOL, jusqu'à la fin de la fenêtre",
         " · ".join(f"{s} {len(marche.series[s])}" for s in R.UNIVERS))

    # aucune bougie vue ne se clôt après l'instant de décision
    trop_tard = [(i, s) for i, ti in enumerate(inst) for s, bs in marche.vue(ti).items() if bs[-1]["t"] + 3600 > ti]
    v.ok(not trop_tard, "à chaque décision, la dernière bougie vue est close avant l'instant de décision", trop_tard[:3] or "60/60")

    b = jeu.jouer()
    consignes = jeu.consignes
    # la preuve : tout le futur remplacé par des prix absurdes -> consigne identique
    differences = []
    for facteur in (100.0, 0.01):
        for k, tk in enumerate(inst):
            faux = {s: [dict(x, o=x["o"] * facteur, h=x["h"] * facteur, l=x["l"] * facteur, c=x["c"] * facteur) if x["t"] + 3600 > tk else x
                        for x in bs] for s, bs in marche.series.items()}
            essai = R.Replay(R.Marche(faux), debut, fin, decider=decideur_simple)
            essai.instants = lambda k=k: inst[:k + 1]
            essai.jouer()
            if essai.consignes[k] != consignes[k]:
                differences.append((facteur, k))
    v.ok(not differences, "PREUVE : futur remplacé par des prix ×100 puis ÷100, les 60 consignes restent identiques au caractère près",
         differences[:3] or "120 comparaisons, 0 différence")
    ordres = [d for d in b["decisions"] if d["action"] in ("achat", "vente")]
    v.ok(all(abs(d["prix"] - marche.prix(d["t"])[d["crypto"]]) < 1e-9 for d in ordres), "chaque ordre passe au prix connu à l'instant de décision",
         f"{len(ordres)} ordres")
    v.ok(all(abs(o["frais_eur"] - o["montant_eur"] * FRAIS) < 1e-3 for o in jeu.livre.journal), "mêmes frais qu'en vrai : 0,1 % par ordre")
    p0, p1 = marche.prix(debut)["BTC"], marche.prix(fin)["BTC"]
    btc_attendu = round((p1 / p0 * (1 - FRAIS) - 1) * 100, 2)
    v.ok(b["comparaison"]["tout_en_btc_pct"] == btc_attendu and b["comparaison"]["garder_ses_euros_pct"] == 0,
         "« tout en Bitcoin le premier jour » et « garder ses euros » calculés juste", f"BTC {p0:,.0f} → {p1:,.0f} € : {btc_attendu:+.2f} %")
    v.info("première consigne envoyée au modèle :\n      " + consignes[0].replace("\n", "\n      "))
    mesures.update(preuve_sans_futur={"comparaisons": 120, "differences": len(differences),
                                      "methode": "futur remplacé par ×100 puis ÷100 : consigne identique"},
                   consigne_exemple=consignes[0])
    return marche, debut, fin


def avec_cerveau(v: Verifs, marche, debut, fin, mesures: dict) -> dict | None:
    from ..cerveau import MODELE
    from ..config import CONFIG
    from ..crypto import replay as R
    ollama = CONFIG["ollama"]["url"]
    try:
        avant = requests.get(f"{ollama}/api/ps", timeout=5).json().get("models", [])
    except Exception:
        v.info("Ollama ne répond pas : les vraies décisions sont ignorées")
        return None
    v.info(f"modèles en mémoire avant : {[m['name'] for m in avant] or 'aucun'} · décisions de {MODELE}, température 0")
    etapes = []
    jeu = R.Replay(marche, debut, fin, emettre=etapes.append)
    surveillance = {"max_modeles": 0, "noms": set()}

    import threading
    fini = threading.Event()

    def surveiller():                      # un seul gros modèle en mémoire pendant tout le replay
        while not fini.is_set():
            try:
                m = requests.get(f"{ollama}/api/ps", timeout=5).json().get("models", [])
                surveillance["max_modeles"] = max(surveillance["max_modeles"], len(m))
                surveillance["noms"] |= {x["name"] for x in m}
            except Exception:
                pass
            fini.wait(3)

    threading.Thread(target=surveiller, daemon=True).start()
    t = time.time()
    b = jeu.jouer()
    fini.set()
    duree = time.time() - t
    valides = [d for d in b["decisions"] if "erreur" not in d]
    v.ok(len(b["decisions"]) == 60 and len(valides) == 60, "60 décisions de qwen3:14b, toutes en JSON valide",
         f"{len(valides)}/60 en {duree:.0f} s · médiane {b['secondes_par_decision']['mediane']} s, pire {b['secondes_par_decision']['pire']} s")
    v.ok(all(len(d["raison"]) > 10 for d in b["decisions"]), "chaque décision a sa phrase de raison",
         f"ex. « {next((d['raison'] for d in b['decisions'] if d['action'] != 'attendre'), b['decisions'][0]['raison'])} »")
    v.ok(surveillance["max_modeles"] <= 1 and surveillance["noms"] <= {MODELE}, "un seul gros modèle en mémoire pendant tout le replay",
         sorted(surveillance["noms"]))
    v.ok(len(etapes) == 61, "le HUD reçoit le début puis chaque décision", f"{len(etapes)} événements")
    c = b["comparaison"]
    v.info(f"RÉSULTAT : {b['valeur_finale_eur']:,.2f} € ({c['jarvis_pct']:+.2f} %) en {b['ordres']} ordres "
           f"({b['achats']} achats, {b['ventes']} ventes) · garder ses euros 0 % · tout en BTC {c['tout_en_btc_pct']:+.2f} %")
    for d in b["decisions"]:
        if d["action"] != "attendre":
            v.info(f"{d['i']:>2} {d['date']:<26} {d['action']:<6} {d['crypto']} {d.get('montant_eur', 0):>9,.2f} € — {d['raison']}")
    attentes = sum(d["action"] == "attendre" for d in b["decisions"])
    impossibles = [d for d in b["decisions"] if d.get("note")]
    v.info(f"{attentes} « attendre », {len(impossibles)} ordre(s) impossible(s) changé(s) en attente")
    R.sauver(b)
    mesures.update({k: val for k, val in b.items() if k not in ("prix_debut",)})
    mesures.update(modele=MODELE, temperature=0, attentes=attentes, ordres_impossibles=len(impossibles), mode="calculé par le test",
                   modeles_en_memoire_pendant=sorted(surveillance["noms"]), etapes_hud=etapes)
    return b


def relire(v: Verifs, b: dict, mesures: dict):
    from datetime import datetime
    from ..crypto import replay as R
    from ..outils import replay_crypto
    from ..youtube import verification
    ventes = [d for d in b["decisions"] if d["action"] == "vente"]
    achats = [d for d in b["decisions"] if d["action"] == "achat"]
    cible = (ventes or achats or b["decisions"])[0]
    verbe = {"vente": "vendu", "achat": "acheté"}.get(cible["action"], "attendu")
    jour = datetime.fromtimestamp(cible["t"]).day
    r = replay_crypto.pourquoi(verbe, jour, bilan=b)
    v.ok(cible["raison"].rstrip(" .") in r, f"« pourquoi tu as {verbe} le {jour} ? » relit la vraie raison", r)
    # un jour où il a attendu plusieurs fois : les raisons identiques sont regroupées, jamais relues deux fois
    par_jour: dict = {}
    for d in b["decisions"]:
        if d["action"] == "attendre":
            par_jour.setdefault(datetime.fromtimestamp(d["t"]).day, []).append(d)
    jour_att, ds = max(par_jour.items(), key=lambda x: len(x[1]), default=(None, []))
    if len(ds) > 1:
        r3 = replay_crypto.pourquoi("attendu", jour_att, bilan=b)
        cites = [x for x in r3.split("« ")[1:]]
        v.ok(f"j'ai attendu {len(ds)} fois" in r3 and len(cites) == len(set(cites)) and len(cites) <= 2,
             f"« pourquoi tu as attendu le {jour_att} ? » : {len(ds)} attentes regroupées, aucune raison répétée", r3[:200])
    absent = next(j for j in range(1, 32) if j not in {datetime.fromtimestamp(d["t"]).day for d in b["decisions"]})
    r2 = replay_crypto.pourquoi("vendu", absent, bilan=b)
    v.ok(r2.startswith("Je n'ai rien vendu"), "un jour sans vente : il le dit, il n'invente pas de raison", r2)
    texte = R.commentaire(b)
    c = b["comparaison"]
    faits = [{"id": "F1", "texte": "valeur finale", "sujet": "valeur", "valeurs": {"v": b["valeur_finale_eur"], "capital": 10000, "ecart": round(abs(10000 - b["valeur_finale_eur"]), 2)}},
             {"id": "F2", "texte": "Jarvis", "sujet": "jarvis", "valeurs": {"p": abs(c["jarvis_pct"])}},
             {"id": "F3", "texte": "tout en Bitcoin", "sujet": "bitcoin", "valeurs": {"p": abs(c["tout_en_btc_pct"])}},
             {"id": "F4", "texte": "ordres", "sujet": "ordres", "valeurs": {"n": b["ordres"], "jours": 10}}]
    m = b.get("meilleure_decision")
    if m:
        faits.append({"id": "F5", "texte": m["date"], "sujet": "meilleure décision", "valeurs": {}})
    res = verification.verifier(texte, faits)
    v.ok(not res["ecarts"], "le commentaire final ne dit que des chiffres du bilan", f"{res['trouves']}/{res['total']} · {texte}")
    mesures["commentaire"] = texte
    mesures["pourquoi_exemple"] = r


async def hud(v: Verifs, b: dict, mesures: dict):
    from .cadence import Edge, mesurer, serveur_fichiers
    from ..crypto import replay as R
    s, port = serveur_fichiers()
    edge = Edge(1920, 1080)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    try:
        await edge.ouvrir()
        await edge.aller(f"http://127.0.0.1:{port}/hud/index.html?demo=1&etat=repos")
        for _ in range(40):                       # la carte peut être occupée par le cerveau : on attend le HUD
            if await edge.evaluer("typeof window.__jarvis") == "object":
                break
            await asyncio.sleep(0.5)
        await edge.evaluer("window.__err = []; addEventListener('error', e => __err.push(e.message)); 1")
        base = await mesurer(edge, "", 3000)
        debut = {"type": "panneau", "genre": "replay", "titre": "Replay · 10 jours · argent fictif", "debut": b["debut"], "fin": b["fin"],
                 "capital": 10000, "decisions": 60}
        await edge.evaluer(f"window.__jarvis.recevoir({json.dumps(debut)})")
        await asyncio.sleep(0.8)
        etapes = [{"type": "replay_etape", **{k: d.get(k) for k in ("i", "t", "date", "action", "crypto", "raison", "valeur", "btc", "euros", "montant_eur", "prix")}}
                  for d in b["decisions"]]
        # lecture accélérée (200 ms par décision) ; la cadence est mesurée pendant que la courbe avance
        await edge.evaluer(f"""(() => {{ const E = {json.dumps(etapes)}; let i = 0;
            window.__lecture = setInterval(() => {{ if (i < E.length) window.__jarvis.recevoir(E[i++]); else clearInterval(window.__lecture); }}, 200); return 1; }})()""")
        pendant = await mesurer(edge, "", 6000)
        await asyncio.sleep(7.0)
        image = (await edge.envoyer("Page.captureScreenshot", format="png"))["data"]
        (CAPTURES / "replay_en_cours.png").write_bytes(base64.b64decode(image))
        fin = {"type": "replay_fin", **{k: b[k] for k in ("comparaison", "valeur_finale_eur", "ordres", "decisions_faites")}}
        await edge.evaluer(f"window.__jarvis.recevoir({json.dumps(fin)})")
        await asyncio.sleep(1.0)
        r = await edge.evaluer("""(() => { const p = document.querySelector('.holo.genre-replay:not(.ferme)'); if (!p) return null;
            const W = innerWidth, H = innerHeight;
            const dehors = [...p.querySelectorAll('*')].filter(x => { const b = x.getBoundingClientRect(); return b.width && (b.right > W + 1 || b.bottom > H + 1); }).length;
            return { points: p.querySelector('polyline.jarvis').getAttribute('points').trim().split(' ').length,
                     btc: p.querySelector('polyline.btc').getAttribute('points').trim().split(' ').length,
                     marques: p.querySelectorAll('.h-replay-marque').length, valeur: p.querySelector('.h-replay-valeur').textContent,
                     cartes: [...p.querySelectorAll('.h-replay-fin b')].map(x => x.textContent), gagne: p.querySelector('.h-replay-fin .gagne small')?.textContent,
                     hValeur: p.querySelector('.h-replay-valeur').getBoundingClientRect().height / H, dehors }; })()""")
        ordres = b["ordres"]
        v.ok(r and r["points"] == 62 and r["btc"] == 62, "HUD : les deux courbes ont avancé jusqu'au bout (départ, 60 décisions, fin)", r and f"{r['points']} / {r['btc']}")
        v.ok(r and r["marques"] == ordres, "HUD : un point par achat ou vente", r and f"{r['marques']} points pour {ordres} ordres")
        v.ok(r and len(r["cartes"]) == 3 and r["hValeur"] > 0.06, "HUD : le résultat tombe, Jarvis / tout en Bitcoin / garder ses euros",
             r and f"{r['valeur']} · {r['cartes']} · meilleur : {r['gagne']}")
        v.ok(r and r["dehors"] == 0, "HUD : rien ne dépasse de l'écran")
        v.ok(pendant["pire_ms"] < 18, "cadence : aucune saccade pendant que la courbe avance",
             f"{base['moyenne_ms']} → {pendant['moyenne_ms']} ms/image, pire {pendant['pire_ms']} ms, p99 {pendant['p99_ms']} ms")
        err = await edge.evaluer("window.__err")
        v.ok(not err, "aucune erreur JavaScript", err or "")
        image = (await edge.envoyer("Page.captureScreenshot", format="png"))["data"]
        (CAPTURES / "replay_resultat.png").write_bytes(base64.b64decode(image))
        mesures["hud"] = {"ms_par_image_base": base["moyenne_ms"], "ms_par_image_pendant": pendant["moyenne_ms"], "pire_ms": pendant["pire_ms"],
                          "lecture_s": R.DECISIONS * 1.0 + 1, "captures": ["captures/crypto/replay_en_cours.png", "captures/crypto/replay_resultat.png"]}
    finally:
        edge.fermer()
        s.shutdown()


def main() -> int:
    from ..crypto import cours, mesures as fichier
    v = Verifs("Crypto 4 · le replay des 10 derniers jours")
    mesures: dict = {}
    phrases(v)
    try:
        marche, debut, fin = moteur(v, mesures)
    except cours.Indisponible:
        v.info("pas d'Internet : le replay est ignoré")
        return v.fin()
    b = None
    if "sans_cerveau" not in sys.argv[1:]:
        b = avec_cerveau(v, marche, debut, fin, mesures)
    if b is None:
        from ..crypto import replay as R
        b = R.Replay(marche, debut, fin, decider=decideur_simple).jouer()
    relire(v, b, mesures)
    asyncio.run(hud(v, b, mesures))
    code = v.fin()
    fichier.ecrire("4_replay", resultat_test=f"{v.total - len(v.echecs)}/{v.total}", quand=time.strftime("%Y-%m-%d %H:%M"), **mesures)
    return code


if __name__ == "__main__":
    sys.exit(main())
