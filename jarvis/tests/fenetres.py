"""Test du pouvoir 09, fenêtres : python -m jarvis.tests.fenetres
Sur de vraies fenêtres du Bloc-notes ouvertes par le test (aucune autre fenêtre n'est touchée) : trouver
l'application par son nom, gauche, droite, plein écran, restaurer, autre écran, réduire les autres, fermer avec
confirmation quand il y a du travail non enregistré. Les Bloc-notes du test sont fermés à la fin."""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

import psutil

from ._commun import Verifs, attendre

from .. import confirmations  # noqa: E402
from ..outils import fenetres as F  # noqa: E402

WM_SETTEXT = 0x000C
user32 = ctypes.WinDLL("user32")
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def ouvrir_bloc_notes():
    avant = {f["hwnd"] for f in F.lister_fenetres() if f["programme"] == "notepad"}
    proc = subprocess.Popen(["notepad.exe"])
    attendre(lambda: any(f["programme"] == "notepad" and f["hwnd"] not in avant for f in F.lister_fenetres()), 10)
    return proc, next(f for f in F.lister_fenetres() if f["programme"] == "notepad" and f["hwnd"] not in avant)


def main() -> int:
    v = Verifs("Pouvoir 09 · fenêtres")
    procs = []
    try:
        proc, bn = ouvrir_bloc_notes()
        procs.append(proc)
        v.ok(bn is not None, "Bloc-notes ouvert", bn["titre"] if bn else None)
        trouve = F.trouver("le bloc-notes")
        v.ok(trouve and trouve["programme"] == "notepad", "« le bloc-notes » est retrouvé par son nom de programme")

        ecran = F._ecran_de(bn["hwnd"])
        g, h, d, b = ecran["travail"]
        tolerance = 12
        F.moitie(bn, "gauche")
        time.sleep(0.3)
        r = F.rect(bn["hwnd"])
        bord = F._bordures(bn["hwnd"])
        visible = (r[0] + bord[0], r[1] + bord[1], r[2] - bord[2], r[3] - bord[3])
        v.ok(abs(visible[0] - g) <= tolerance and abs(visible[2] - (g + (d - g) // 2)) <= tolerance and abs(visible[3] - b) <= tolerance,
             "à gauche : la moitié gauche de l'écran", visible)
        F.moitie(bn, "droite")
        time.sleep(0.3)
        r = F.rect(bn["hwnd"])
        visible = (r[0] + bord[0], r[1] + bord[1], r[2] - bord[2], r[3] - bord[3])
        v.ok(abs(visible[0] - (g + (d - g) // 2)) <= tolerance and abs(visible[2] - d) <= tolerance, "à droite : la moitié droite", visible)
        F.plein_ecran(bn)
        time.sleep(0.3)
        v.ok(user32.IsZoomed(bn["hwnd"]), "plein écran")
        F.restaurer(bn)
        time.sleep(0.3)
        v.ok(not user32.IsZoomed(bn["hwnd"]), "restaurée")
        ecrans = F.ecrans()
        message = F.autre_ecran(bn)
        if len(ecrans) < 2:
            v.ok("Un seul écran" in message, "un seul écran branché : Jarvis le dit", message)
        else:
            time.sleep(0.3)
            v.ok(F._ecran_de(bn["hwnd"])["hmon"] != ecran["hmon"], "passée sur l'autre écran", message)

        proc2, bn2 = ouvrir_bloc_notes()
        procs.append(proc2)
        mes_fenetres = {bn["hwnd"], bn2["hwnd"]}
        # réduire les autres, limité aux fenêtres du test : les vraies fenêtres de l'utilisateur restent en place
        message = F.minimiser_autres(bn, F.lister_fenetres(), garder=lambda f: f["hwnd"] not in mes_fenetres)
        time.sleep(0.4)
        v.ok(user32.IsIconic(bn2["hwnd"]) and not user32.IsIconic(bn["hwnd"]), "réduire les autres : seule la fenêtre choisie reste", message)
        a_reduire = [f["titre"] for f in F.lister_fenetres() if f["hwnd"] != bn["hwnd"] and not f["reduite"]
                     and not F._normaliser(f["titre"]).startswith("jarvis")]
        v.info(f"en vrai, auraient été réduites : {len(a_reduire)} fenêtres")

        # travail non enregistré
        # une vraie frappe (WM_CHAR, sans voler le clavier) : le Bloc-notes marque le document modifié, son titre prend « * »
        edit = user32.FindWindowExW(bn2["hwnd"], None, "Edit", None)
        for c in "Texte du test Jarvis":
            user32.PostMessageW(edit, 0x0102, ord(c), 0)
        attendre(lambda: F.non_enregistre({"titre": F._titre(bn2["hwnd"])}), 3)
        bn2 = next(f for f in F.lister_fenetres() if f["hwnd"] == bn2["hwnd"])
        v.ok(F.non_enregistre(bn2), "travail non enregistré repéré dans le titre", bn2["titre"])
        question = F.fermer(bn2)
        v.ok("enregistré" in question and "*" not in question and confirmations.en_attente(), "fermer : Jarvis demande confirmation d'abord", question)
        v.ok(confirmations.refuser().startswith("Très bien") and user32.IsWindow(bn2["hwnd"]), "« non » : la fenêtre reste ouverte")
        F.fermer(bn2)
        reponse = confirmations.confirmer()
        v.ok("fermée" in reponse or "question d'enregistrement" in reponse, "« oui » : Jarvis la ferme (le Bloc-notes pose sa propre question)", reponse)

        propre = next(f for f in F.lister_fenetres() if f["hwnd"] == bn["hwnd"])
        v.ok(not F.non_enregistre(propre), "une fenêtre sans modification")
        reponse = F.fermer(propre)
        v.ok("fermée" in reponse and not confirmations.en_attente(), "est fermée sans question", reponse)
        v.ok("fenêtres ouvertes" in F.executer("lister"), "lister les fenêtres ouvertes")
    finally:
        for p in procs:
            try:
                psutil.Process(p.pid).kill()
            except Exception:
                pass
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
