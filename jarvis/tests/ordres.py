"""Test « il obéit » : python -m jarvis.tests.ordres
Vu en direct le 17/09 : « Jarvis, ouvre le bloc-notes » dit d'une traite arrivait au cerveau réduit à « le bloc note »,
le cerveau répondait « Ouvrir_application, bloc-notes » en texte, et l'historique ainsi empoisonné faisait échouer
toutes les demandes suivantes. Jarvis arrêté (ce test charge Whisper et Kokoro).

1. Oreilles : la phrase jouée au micro de test d'une traite (« Hey Jarvis, ouvre le bloc-notes »), le début de la
   question n'est plus perdu ; « Hey Jarvis » seul puis une pause : Jarvis attend la question.
2. Cerveau : la session réelle rejouée (sans rien exécuter sur le PC) ; chaque demande d'action appelle son outil,
   aucun nom d'outil n'est dit, une question sans action n'appelle rien."""
import sys
import time

from ._commun import Collecteur, SourceScenario, Verifs, attendre, faux_haut_parleur, phrase_wav

faux_haut_parleur()

from .. import oreilles, outils  # noqa: E402
from ..cerveau import CERVEAU  # noqa: E402


def main() -> int:
    v = Verifs("Il obéit · la question entière, l'outil appelé")

    cas = {"Hey Jarvis, ouvre le bloc-notes.": "Ouvre le bloc-notes.", "rvis, ouvre le bloc-notes": "Ouvre le bloc-notes",
           "Ouvre le bloc-notes": "Ouvre le bloc-notes", "Jarvis.": "", "Avis de passage demain": "Avis de passage demain"}
    v.ok(all(oreilles.retirer_reveil(t) == attendu for t, attendu in cas.items()), "le mot de réveil (même coupé) est retiré, rien d'autre",
         {t: oreilles.retirer_reveil(t) for t in cas})

    # ------------------------------------------------------------------ 1. les oreilles
    d_une_traite, _ = phrase_wav("ordre_d_une_traite", [("Hey Jarvis,", "am_michael", "en-us"), ("ouvre le bloc-notes.", "ff_siwis", "fr-fr")],
                                 silence_avant=0.6, silence_apres=0.4)
    reveil_seul, _ = phrase_wav("ordre_reveil_seul", [("Hey Jarvis.", "am_michael", "en-us")], silence_avant=0.6, silence_apres=0.1)
    question, _ = phrase_wav("ordre_question", [("Quelle heure est-il ?", "ff_siwis", "fr-fr")], silence_avant=0.1)
    oreilles.prechauffer_whisper()
    micro, evts, recus = SourceScenario(), Collecteur(), []
    o = oreilles.Oreilles(sur_evenement=evts, sur_texte=lambda t, i: recus.append((t, i["mode"])), source=micro.generateur,
                          jarvis_parle=lambda: False, phrases_dites=lambda: [])
    o.start()
    try:
        attendre(lambda: o.etat == "veille", 60)
        micro.silence(1.0)
        micro.jouer(d_une_traite)
        micro.silence(2.5)
        v.ok(attendre(lambda: recus, 20), "d'une traite : une question arrive au cerveau", recus)
        texte = recus[-1][0] if recus else ""
        v.ok("ouvr" in texte.lower() and "bloc" in texte.lower() and not texte.lower().startswith(("hey", "jarvis")),
             "la question est entière (« ouvre » compris) et sans le mot de réveil", recus[-1] if recus else "")
        attendre(lambda: o.etat == "veille", 10)
        recus.clear()
        evts.evenements.clear()
        micro.jouer(reveil_seul)
        micro.silence(1.4)
        micro.jouer(question)
        micro.silence(2.5)
        v.ok(attendre(lambda: recus, 25), "« Hey Jarvis » seul, une pause, puis la question : elle arrive", recus)
        v.ok(recus and "heure" in recus[-1][0].lower() and not evts.de_type("rien_entendu"),
             "sans « rien entendu » entre les deux", [e["type"] for e in evts.evenements if e["type"] in ("mot_detecte", "rien_entendu", "transcription")])
    finally:
        o.arreter()

    # ------------------------------------------------------------------ 2. le cerveau, la session du 17/09 rejouée
    appels = []
    ancien = outils.executer
    from ..outils import etat_machine
    # rien n'est exécuté sur le PC, sauf l'état de la machine (lecture seule) : un faux résultat sans chiffres pousserait le cerveau à en inventer
    outils.executer = lambda nom, args: appels.append((nom, args)) or (
        "J'ouvre le bloc-notes, monsieur." if nom == "ouvrir_application" else etat_machine.executer() if nom == "etat_machine" else f"{nom} : fait.")
    CERVEAU.oublier()
    try:
        session = [("T'es là Jarvis ?", False), ("le bloc note", None), ("Tu peux m'ouvrir le bloc-notes ?", True),
                   ("Ouvre le bloc note.", True), ("Mets le bloc-notes à droite.", True), ("Dans quel état est la machine ?", True),
                   ("Propose-moi une idée de dîner rapide.", False)]
        for q, attendu in session:
            n, dites, t = len(appels), [], time.time()
            reponse = CERVEAU.repondre(q, journal=lambda a, b: None, sur_phrase=dites.append)
            faits = [a[0] for a in appels[n:]]
            v.info(f"« {q} » -> « {reponse} » ; outils {faits} ; {time.time() - t:.1f} s")
            dit = " ".join(dites).lower()
            v.ok(not any(nom in dit or nom.replace("_", " ") in dit for nom in outils.OUTILS if "_" in nom), f"« {q} » : aucun nom d'outil dit", dites)
            if attendu is True:
                v.ok(faits, f"« {q} » : l'outil est appelé", faits)
            elif attendu is False:
                v.ok(not faits or q.startswith("Dans"), f"« {q} » : aucune action inventée", faits)
    finally:
        outils.executer = ancien
        CERVEAU.oublier()

    ouvrir_des_fichiers(v)
    deux_micros(v)
    pour_de_vrai(v)
    return v.fin()


def ouvrir_des_fichiers(v: Verifs):
    """3. Les fichiers dits à voix haute (dossier temporaire), puis les phrases du 17/09 avec le vrai cerveau et le vrai bureau."""
    import tempfile
    from pathlib import Path
    from ..outils import ouvrir_application, ouvrir_fichier, ouvrir_site
    bureau = Path(tempfile.mkdtemp(prefix="jarvis_bureau_"))
    for nom in ("JE SUIS BEAU.txt", "notes réunion lundi.md", "photo vacances.jpg", "facture.pdf", "Capture.PNG"):
        (bureau / nom).write_text("essai", encoding="utf-8")
    (bureau / "DRIVER").mkdir()
    cas = [("je suis bon", "texte", "JE SUIS BEAU.txt"), ("document texte je suis bon", "", "JE SUIS BEAU.txt"),
           ("notes de réunion", "", "notes réunion lundi.md"), ("ma photo de vacances", "", "photo vacances.jpg"),
           ("la facture", "pdf", "facture.pdf"), ("le dossier driver", "dossier", "DRIVER"), ("facture EDF", "", None),
           ("recette de crêpes", "", None)]
    resultats = {dit: [p.name for _, p in ouvrir_fichier.choisir(dit, t, racines=[bureau])[0][:1]] for dit, t, _ in cas}
    v.ok(all((resultats[dit][:1] == [attendu]) if attendu else not resultats[dit] for dit, _, attendu in cas),
         "chaque nom dit (même mal entendu) retrouve le bon fichier, et rien n'est inventé", resultats)
    ouverts = []
    r = ouvrir_fichier.executer("je suis bon", "texte", racines=[bureau], ouvreur=ouverts.append)
    v.ok(ouverts and ouverts[0].endswith("JE SUIS BEAU.txt") and "J'ouvre « JE SUIS BEAU.txt »" in r, "le gagnant est ouvert, et Jarvis le dit", r)
    r = ouvrir_fichier.executer("recette de crêpes", racines=[bureau], ouvreur=ouverts.append)
    v.ok(len(ouverts) == 1 and r.startswith("Je ne trouve aucun"), "rien qui ressemble : rien n'est ouvert, Jarvis le dit", r)

    # « note.md » est un fichier, jamais un site
    sites, fichiers = [], []
    ancien_site, ancien_fichier = ouvrir_site.executer, ouvrir_fichier.executer
    ouvrir_site.executer = lambda *a, **k: sites.append(a) or "site ouvert"
    ouvrir_fichier.executer = lambda nom, *a, **k: fichiers.append(nom) or f"J'ouvre « {nom} », monsieur."
    try:
        ouvrir_application.executer("note.md")
        ouvrir_application.executer("youtube.com")
    finally:
        ouvrir_site.executer, ouvrir_fichier.executer = ancien_site, ancien_fichier
    v.ok(fichiers == ["note.md"] and len(sites) == 1, "« note.md » est cherché comme fichier ; « youtube.com » reste un site", (fichiers, sites))

    # les phrases de la session, avec le vrai cerveau et le VRAI bureau ; l'ouverture est seulement notée
    ouverts.clear()
    ancien_ouvrir = ouvrir_fichier.ouvrir
    ouvrir_fichier.ouvrir = lambda chemin, ouvreur=None: ouverts.append(Path(chemin).name)
    appels = []
    ancien_executer = outils.executer

    def noter(nom, args):
        appels.append((nom, args))
        return ancien_executer(nom, args)
    outils.executer = noter
    CERVEAU.oublier()
    try:
        phrases = ["Sur le bureau, ouvre le document texte, je suis bon.", "Ouvre mes notes sur mon bureau.", "Ouvre le fichier je suis beau."]
        for q in phrases:
            n, m = len(appels), len(ouverts)
            reponse = CERVEAU.repondre(q, journal=lambda a, b: None)
            v.info(f"« {q} » -> « {reponse} » ; outils {appels[n:]} ; ouvert {ouverts[m:]}")
            v.ok(ouverts[m:] == ["JE SUIS BEAU.txt"], f"« {q} » : le fichier du bureau est ouvert", (appels[n:], ouverts[m:]))
    finally:
        outils.executer = ancien_executer
        ouvrir_fichier.ouvrir = ancien_ouvrir
        CERVEAU.oublier()


def deux_micros(v: Verifs):
    """4. Espace maintenu dans le HUD et micro du PC ouvert : une seule réponse."""
    from .. import serveur
    serveur._DERNIERES_PHRASES.clear()
    premier = serveur._doublon_vocal("Tu peux ouvrir le bloc-notes ?")
    second = serveur._doublon_vocal("Tu peux ouvrir le bloc note ?")
    autre = serveur._doublon_vocal("Quelle heure est-il ?")
    v.ok(not premier and second and not autre, "la même phrase par les deux micros : traitée une fois ; une autre phrase passe")


def pour_de_vrai(v: Verifs):
    """5. Pour de vrai, sur ce PC : le Bloc-notes et le fichier du bureau s'ouvrent, AU PREMIER PLAN, puis sont refermés.
    Lancé depuis un processus d'arrière-plan, comme le serveur de Jarvis."""
    import ctypes
    from ctypes import wintypes
    import psutil
    from ..outils import fenetres as F, ouvrir_application, ouvrir_fichier
    user32 = ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND

    def essayer(libelle, action, programme, titre=None):
        avant = {f["hwnd"] for f in F.lister_fenetres()}
        reponse = action()
        nouvelle = None
        if attendre(lambda: [f for f in F.lister_fenetres() if f["hwnd"] not in avant and programme in f["programme"]], 8):
            nouvelle = next(f for f in F.lister_fenetres() if f["hwnd"] not in avant and programme in f["programme"])
        devant = bool(nouvelle) and attendre(lambda: user32.GetForegroundWindow() == nouvelle["hwnd"], 4)
        v.ok(nouvelle and (not titre or titre in nouvelle["titre"]), f"{libelle} : la fenêtre s'ouvre", (reponse, nouvelle and nouvelle["titre"]))
        v.ok(devant, f"{libelle} : elle passe au premier plan")
        if nouvelle:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(wintypes.HWND(nouvelle["hwnd"]), ctypes.byref(pid))
            psutil.Process(pid.value).kill()

    essayer("« ouvre le bloc-notes »", lambda: ouvrir_application.executer("bloc-notes"), "notepad", "Sans titre")
    bureau = ouvrir_fichier.dossiers("bureau")
    if any((d / "JE SUIS BEAU.txt").exists() for d in bureau):
        essayer("« ouvre le document texte je suis bon »", lambda: ouvrir_fichier.executer("je suis bon", "texte", "bureau"), "notepad", "JE SUIS BEAU")
    else:
        v.info("pas de « JE SUIS BEAU.txt » sur le bureau : essai réel du fichier sauté")


if __name__ == "__main__":
    sys.exit(main())
