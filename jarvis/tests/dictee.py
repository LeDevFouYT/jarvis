"""Test du pouvoir 11, dictée et presse-papiers : python -m jarvis.tests.dictee
1. ecrire : un Bloc-notes ouvert par le test passe au premier plan, le texte (accents, ponctuation, emoji) y est
   tapé, puis relu dans la fenêtre. Si Windows refuse le premier plan, la frappe n'est PAS lancée (elle irait dans
   une autre application) et le test le dit.
2. presse_papiers : lire, résumer, reformuler avec le vrai cerveau ; le résultat revient dans le presse-papiers.
   Le contenu du presse-papiers de l'utilisateur est remis à la fin."""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

import psutil

from ._commun import Verifs, attendre, faux_haut_parleur

faux_haut_parleur()

from ..outils import ecrire, fenetres as F, presse_papiers as P  # noqa: E402

WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E
user32 = ctypes.WinDLL("user32")
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_ssize_t

TEXTE = "Bonjour Jarvis, voilà une dictée : « accents é è à ç ù », 42 % et un emoji 🚀."
LONG = ("Le télétravail s'est largement répandu depuis 2020. Beaucoup d'entreprises ont découvert que leurs équipes "
        "restaient productives à distance, à condition d'avoir de bons outils de communication. Cependant, l'isolement "
        "et la difficulté à séparer vie professionnelle et vie personnelle pèsent sur certains salariés. De nombreuses "
        "sociétés adoptent aujourd'hui un modèle hybride, avec deux ou trois jours au bureau par semaine.")


def main() -> int:
    v = Verifs("Pouvoir 11 · dictée et presse-papiers")
    proc = None
    try:
        avant = {f["hwnd"] for f in F.lister_fenetres() if f["programme"] == "notepad"}
        proc = subprocess.Popen(["notepad.exe"])
        attendre(lambda: any(f["programme"] == "notepad" and f["hwnd"] not in avant for f in F.lister_fenetres()), 10)
        bn = next(f for f in F.lister_fenetres() if f["programme"] == "notepad" and f["hwnd"] not in avant)
        F.premier_plan(bn["hwnd"])
        au_premier_plan = attendre(lambda: user32.GetForegroundWindow() == bn["hwnd"], 3)
        if v.ok(au_premier_plan, "le Bloc-notes du test est la fenêtre active"):
            resultat = ecrire.executer(TEXTE)
            v.ok("C'est écrit" in resultat, "ecrire : texte tapé", resultat)
            edit = user32.FindWindowExW(bn["hwnd"], None, "Edit", None)

            def relire() -> str:
                n = user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, None)
                tampon = ctypes.create_unicode_buffer(n + 1)
                user32.SendMessageW(edit, WM_GETTEXT, n + 1, ctypes.addressof(tampon))
                return tampon.value
            # SendInput rend la main avant que la fenêtre ait lu sa file de touches : relire trop tôt coupe le texte
            attendre(lambda: relire() == TEXTE, 5)
            v.ok(relire() == TEXTE, "le texte relu dans la fenêtre est identique, accents et emoji compris", relire())
        else:
            v.info("frappe non lancée : elle serait partie dans une autre fenêtre")
        v.ok("Jarvis lui-même" in _refus_hud(), "refus de taper dans le HUD de Jarvis")
    finally:
        if proc:
            try:
                psutil.Process(proc.pid).kill()
            except Exception:
                pass

    sauvegarde = None
    try:
        sauvegarde = P.lire()
    except Exception:
        pass
    try:
        P.ecrire(LONG)
        lu = P.executer("lire")
        v.ok("télétravail" in lu, "presse_papiers lire : le texte copié", lu[:60])
        resume = P.executer("resumer")
        dans_presse_papiers = P.lire()
        v.info(f"résumé : {dans_presse_papiers}")
        v.ok(resume.startswith("Voici le résumé") and len(dans_presse_papiers) < 0.6 * len(LONG) and "hybride" in dans_presse_papiers.lower(),
             "résumer : nettement plus court (moins de 60 %), fidèle, et remis dans le presse-papiers")
        v.ok(P.direct_dernier, "un résumé est dit tel quel, sans second passage du cerveau")
        P.ecrire("salut, t'aurais pas le rapport de hier, il me le faut vite")
        reformule = P.executer("reformuler", "plus poli et professionnel")
        nouveau = P.lire()
        v.info(f"reformulé : {nouveau}")
        v.ok("reformulé" in reformule and nouveau != "salut, t'aurais pas le rapport de hier, il me le faut vite"
             and ("vous" in nouveau.lower() or "pourriez" in nouveau.lower() or "bonjour" in nouveau.lower()),
             "reformuler « plus poli » : reformulé et prêt à coller")
    finally:
        if sauvegarde is not None:
            P.ecrire(sauvegarde)
            v.info("presse-papiers de l'utilisateur remis")
    return v.fin()


def _refus_hud() -> str:
    ancien = ecrire.titre_actif
    ecrire.titre_actif = lambda: "Jarvis - Google Chrome"
    try:
        return ecrire.executer("test")
    finally:
        ecrire.titre_actif = ancien


if __name__ == "__main__":
    sys.exit(main())
