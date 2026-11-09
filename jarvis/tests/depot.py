"""Test du dossier glissé : python -m jarvis.tests.depot   (le résumé appelle le cerveau ; `--sans-cerveau` sinon)
Demande des utilisateurs (vidéo 5) : « lui envoyer un dossier du PC ».

Le HUD n'envoie que ce que le navigateur donne : noms relatifs, tailles, dates. Le test fabrique exactement ce message
à partir de vrais dossiers, comme le ferait un glisser-déposer, puis vérifie :
1. le dossier de démonstration (39 fichiers) est retrouvé sur le disque, le bilan dit est juste ;
2. « cherche les factures dedans », « range-le » (puis « annule » : tout revient), les commandes à la voix ;
3. un dossier inconnu : bilan quand même, rangement refusé ; des fichiers seuls : leur dossier retrouvé par l'index ;
   un dossier de Jarvis lui-même : retrouvé, mais rangement refusé (les règles de sûreté de `ranger`) ;
4. « résume-le » par le cerveau.
Mesures dans workspace/mesures/tournoi.json (« depot »)."""
import os
import sys
import time
from pathlib import Path

from ._commun import Verifs

from .. import commandes, depot  # noqa: E402
from ..config import RACINE  # noqa: E402
from ..outils import chercher_fichiers, ranger  # noqa: E402
from .prenom import ecrire_mesures  # noqa: E402


def message_du_hud(dossier: Path, seuls: list[str] | None = None) -> dict:
    """Ce que le HUD envoie pour un glisser-déposer de `dossier` (ou de quelques fichiers `seuls` de ce dossier)."""
    fichiers = []
    if seuls:
        for nom in seuls:
            st = (dossier / nom).stat()
            fichiers.append({"chemin": nom, "taille": st.st_size, "modifie": int(st.st_mtime * 1000)})
        return {"nom": None, "dossier": False, "fichiers": fichiers}
    for racine, sous, noms in os.walk(dossier):
        sous[:] = [s for s in sous if s != "__pycache__"]
        for n in noms:
            p = Path(racine) / n
            rel = p.relative_to(dossier.parent).as_posix()
            fichiers.append({"chemin": rel, "taille": p.stat().st_size, "modifie": int(p.stat().st_mtime * 1000)})
    return {"nom": dossier.name, "dossier": True, "fichiers": fichiers}


def main() -> int:
    v = Verifs("Le dossier glissé · « range ce que je viens de te donner »")
    mesures = {}
    t = time.time()
    n = chercher_fichiers.construire()
    v.info(f"index des fichiers : {n} fichiers en {time.time() - t:.1f} s (comme au démarrage de Jarvis)")

    # ------------------------------------------------------------------ 1. le dossier de démonstration
    demo = ranger.creer_demo()
    m = message_du_hud(demo)
    t = time.time()
    r = depot.recevoir(**m)
    mesures["localisation_s"] = round(time.time() - t, 2)
    v.info(f"dit : « {r['phrase']} »")
    v.ok(r["chemin"] and Path(r["chemin"]).resolve() == demo.resolve(),
         f"le dossier glissé est retrouvé sur le disque en {mesures['localisation_s']} s, d'après les seuls noms et tailles",
         {**r["localisation"], "chemin": r["chemin"]})
    v.ok(r["bilan"]["nombre"] == 39 and "39 fichiers" in r["phrase"] and "Je le résume, je le range" in r["phrase"],
         "le bilan dit : 39 fichiers, leurs types, et la question", r["bilan"]["familles"])

    # ------------------------------------------------------------------ 2. chercher, ranger, annuler, à la voix
    attendus = {"range ce que je viens de te donner": ("depot_ranger", ""), "Range-le.": ("depot_ranger", ""),
                "Jarvis, résume-le": ("depot_resumer", ""), "cherche les factures dedans": ("depot_chercher", "les factures"),
                "est-ce qu'il y a un contrat dans ce dossier ?": ("depot_chercher", "un contrat")}
    vus = {t_: commandes.analyser(t_) for t_ in attendus}
    v.ok(vus == attendus, "les commandes à la voix", {k: vus[k] for k in attendus if vus[k] != attendus[k]} or "toutes justes")
    pas_depot = ["range mes téléchargements", "résume ce que j'ai copié", "cherche une recette de crêpes"]
    v.ok(not any((commandes.analyser(p)[0] or "").startswith("depot_") for p in pas_depot),
         "« range mes téléchargements », « résume ce que j'ai copié » ne visent pas le dépôt",
         {p: commandes.analyser(p)[0] for p in pas_depot})
    c = depot.chercher("les factures")
    v.ok(sorted(Path(x["chemin"]).name for x in c["trouves"]) == ["facture_electricite_juin.pdf", "facture_internet_juillet.pdf"],
         f"« cherche les factures dedans » : « {c['phrase']} »")
    avant = sorted(p.name for p in demo.iterdir())
    t = time.time()
    phrase = depot.ranger()
    mesures["rangement_s"] = round(time.time() - t, 2)
    v.info(f"dit : « {phrase} »")
    a_la_racine = [p for p in demo.iterdir() if p.is_file()]
    v.ok("est rangé" in phrase and len(a_la_racine) <= 2, f"« range-le » : rangé en {mesures['rangement_s']} s, par type et par mois",
         [p.name for p in demo.iterdir()][:8])
    annule = ranger.annuler()
    v.ok(sorted(p.name for p in demo.iterdir()) == avant, f"« annule » : tout est revenu ({annule['message']})")

    # ------------------------------------------------------------------ 3. inconnu, fichiers seuls, dossier protégé
    r = depot.recevoir("vacances_2019_clé_usb", [{"chemin": f"vacances_2019_clé_usb/IMG_{i:04d}.jpg", "taille": 3_000_000 + i}
                                                 for i in range(12)], True)
    v.ok(r["chemin"] is None and "ne le retrouve pas" in r["phrase"], "un dossier introuvable : bilan quand même, et il le dit", r["phrase"])
    v.ok("ne peux pas le ranger" in depot.ranger(), "et il refuse de le ranger")
    seuls = ["facture_electricite_juin.pdf", "cv_2026.docx", "recette_crepes.md"]
    r = depot.recevoir(**message_du_hud(demo, seuls))
    v.ok(r["chemin"] and Path(r["chemin"]).resolve() == demo.resolve() and "3 fichiers" in r["phrase"],
         "trois fichiers seuls : leur dossier est retrouvé par l'index", r["localisation"])
    v.ok("dossier entier" in depot.ranger(), "fichiers seuls : il ne range pas tout le dossier autour d'eux")
    hud = RACINE / "jarvis" / "hud"
    r = depot.recevoir(**message_du_hud(hud))
    v.ok(r["chemin"] and Path(r["chemin"]).resolve() == hud.resolve(), "un dossier de Jarvis lui-même est retrouvé", r["localisation"])
    refus = depot.ranger()
    v.ok("refuse" in refus.lower() and sorted(p.name for p in hud.iterdir()) == sorted(p.name for p in hud.iterdir()),
         f"… mais il refuse de le ranger : « {refus} »")

    # ------------------------------------------------------------------ 4. le résumé, par le cerveau
    if "--sans-cerveau" not in sys.argv:
        from ..cerveau import CERVEAU
        depot.recevoir(**message_du_hud(demo))
        t = time.time()
        resume = depot.resumer(lambda c_, t_: CERVEAU.generer(c_, t_, delai=180))
        mesures["resume_s"] = round(time.time() - t, 1)
        v.info(f"résumé ({mesures['resume_s']} s) : « {resume} »")
        v.ok(20 < len(resume) < 700 and not any(x in resume for x in ("**", "\n-", "# ")),
             "« résume-le » : deux ou trois phrases à l'oral, sans liste ni markdown")
    mesures["date"] = time.strftime("%Y-%m-%d %H:%M")
    ecrire_mesures("depot", mesures)
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
