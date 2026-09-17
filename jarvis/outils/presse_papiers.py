"""Outil presse_papiers : lit ce que la personne a copié, le résume ou le reformule avec le cerveau local, et remet
le résultat dans le presse-papiers (prêt à coller). Le texte copié ne sort jamais de la machine en mode local.
Résumer et reformuler sont des réponses directes : le résultat est dit tel quel, sans second passage du cerveau."""
import ctypes
import time
from ctypes import wintypes

NOM = "presse_papiers"
DESCRIPTION = ("Travaille sur le texte copié dans le presse-papiers : le lire, le résumer, ou le reformuler (plus clair, plus "
               "poli, plus court, en anglais…). Le résultat d'un résumé ou d'une reformulation est remis dans le "
               "presse-papiers, prêt à coller.")
PARAMETRES = {
    "action": {"type": "string", "enum": ["lire", "resumer", "reformuler"]},
    "consigne": {"type": "string", "description": "Précision facultative : « plus poli », « en trois phrases », « en anglais »…"},
}
REQUIS = ["action"]
direct_dernier = False                 # lu par le registre : le dernier appel donne-t-il la réponse finale ?

CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]


def _ouvrir() -> bool:
    for _ in range(20):                    # une autre application peut tenir le presse-papiers un instant
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def lire() -> str:
    if not _ouvrir():
        raise RuntimeError("presse-papiers occupé")
    try:
        poignee = user32.GetClipboardData(CF_UNICODETEXT)
        if not poignee:
            return ""
        pointeur = kernel32.GlobalLock(poignee)
        try:
            return ctypes.wstring_at(pointeur)
        finally:
            kernel32.GlobalUnlock(poignee)
    finally:
        user32.CloseClipboard()


def ecrire(texte: str):
    donnees = (texte + "\0").encode("utf-16-le")
    if not _ouvrir():
        raise RuntimeError("presse-papiers occupé")
    try:
        user32.EmptyClipboard()
        poignee = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(donnees))
        pointeur = kernel32.GlobalLock(poignee)
        ctypes.memmove(pointeur, donnees, len(donnees))
        kernel32.GlobalUnlock(poignee)
        if not user32.SetClipboardData(CF_UNICODETEXT, poignee):
            raise RuntimeError("Windows a refusé l'écriture")
    finally:
        user32.CloseClipboard()


CONSIGNES = {
    "resumer": ("Résume le texte fourni en français : l'essentiel seulement, en {mots} mots au plus, fidèle, sans rien "
                "inventer. Un résumé nettement plus court que l'original, pas une réécriture. "
                "Pas de titre, pas de liste, pas de markdown. {precision}"),
    "reformuler": ("Reformule le texte fourni : même sens, même langue que l'original sauf demande contraire, plus clair et "
                   "mieux écrit. Rends uniquement le texte reformulé, sans introduction ni guillemets. {precision}"),
}


def executer(action: str = "lire", consigne: str = "") -> str:
    global direct_dernier
    direct_dernier = False
    try:
        texte = lire().strip()
    except Exception as e:
        return f"Je n'arrive pas à lire le presse-papiers ({e})."
    if not texte:
        return "Le presse-papiers est vide, ou ne contient pas de texte."
    from . import panneaux
    if action == "lire":
        panneaux.texte("Presse-papiers", texte[:4000], source=f"{len(texte)} caractères copiés")
        return f"Texte copié ({len(texte)} caractères) : {texte[:1500]}"
    if action not in CONSIGNES:
        return "Je sais lire, résumer ou reformuler le presse-papiers."
    from ..cerveau import CERVEAU
    precision = f"Précision de la personne : {consigne}." if consigne else ""
    try:
        # un budget de mots : sans lui, un texte court revenait « résumé » presque à sa longueur d'origine
        mots = max(15, min(120, len(texte[:12000].split()) // 3))
        resultat = CERVEAU.generer(CONSIGNES[action].format(precision=precision, mots=mots), texte[:12000], delai=120)
    except Exception as e:
        return f"Le cerveau n'a pas pu traiter le texte copié ({type(e).__name__})."
    ecrire(resultat)
    titre = "Résumé du presse-papiers" if action == "resumer" else "Reformulation"
    panneaux.texte(titre, resultat, source="remis dans le presse-papiers, prêt à coller")
    direct_dernier = True
    if action == "resumer":
        return f"Voici le résumé, il est aussi dans le presse-papiers. {resultat}"
    return "C'est reformulé et remis dans le presse-papiers, prêt à coller." + (
        f" {resultat}" if len(resultat) < 300 else " Le texte est affiché à l'écran.")
