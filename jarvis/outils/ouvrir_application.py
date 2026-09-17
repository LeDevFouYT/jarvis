"""Outil ouvrir_application : lance une application, un dossier ou une adresse par son nom courant.
La table nom -> commande est dans config.json (`applications`) ; monsieur peut la compléter."""
import difflib
import os
import subprocess
import unicodedata
import webbrowser
from pathlib import Path

from ..config import CONFIG

NOM = "ouvrir_application"
DESCRIPTION = ("Lance une application installée ou ouvre un dossier de l'ordinateur par son nom courant : "
               "ComfyUI, explorateur, bloc-notes, calculatrice, terminal, un dossier de projet… "
               "Pas pour les sites web (YouTube, Google…) : pour eux, utiliser ouvrir_site.")
PARAMETRES = {"nom": {"type": "string", "description": "Nom courant de l'application ou du dossier"}}
REQUIS = ["nom"]

TABLE = CONFIG.get("applications", {})


def _normaliser(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def trouver(nom: str) -> tuple[str, str] | None:
    n = _normaliser(nom)
    cles = {_normaliser(k): k for k in TABLE}
    if n in cles:
        return cles[n], TABLE[cles[n]]
    for cn, k in cles.items():
        if n in cn or cn in n:
            return k, TABLE[k]
    proches = difflib.get_close_matches(n, list(cles), n=1, cutoff=0.75)
    if proches:
        return cles[proches[0]], TABLE[cles[proches[0]]]
    return None


def lancer(cible: str) -> str:
    cible = os.path.expanduser(cible)
    if cible.startswith(("http://", "https://")):
        webbrowser.open(cible)
        return "adresse ouverte dans le navigateur"
    p = Path(cible)
    if p.is_dir():
        os.startfile(str(p))
        return f"dossier {p} ouvert"
    if p.suffix.lower() in (".bat", ".cmd"):
        subprocess.Popen(["cmd", "/c", "start", "", str(p)], cwd=str(p.parent),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        return f"{p.name} lancé dans sa fenêtre"
    if p.suffix.lower() in (".exe", ".lnk") and p.exists():
        os.startfile(str(p))
        return f"{p.stem} lancé"
    subprocess.Popen(["cmd", "/c", "start", "", cible], creationflags=subprocess.CREATE_NO_WINDOW)
    return f"{cible} lancé"


_ARTICLES = {"navigateur": "le navigateur", "explorateur": "l'explorateur", "bloc-notes": "le bloc-notes", "calculatrice": "la calculatrice",
             "terminal": "le terminal", "telechargements": "le dossier Téléchargements", "comfyui": "ComfyUI", "jarvis": "Jarvis",
             "influencer studio": "Influencer Studio", "yt studio": "YT Studio"}


def _avec_article(cle: str) -> str:
    return _ARTICLES.get(cle, cle)


direct_dernier = False      # une ouverture réussie se dit telle quelle : plus rapide, et le cerveau ne la paraphrase pas en « Ouvrir, monsieur »


def executer(nom: str) -> str:
    global direct_dernier
    direct_dernier = False
    trouve = trouver(nom)
    if not trouve:
        import re
        from . import ouvrir_fichier, ouvrir_site
        n = ouvrir_site._normaliser(nom)
        # « note.md », « rapport.pdf » sont des fichiers, pas des sites (vu en direct : le site note.md s'ouvrait)
        extension = "." + n.rsplit(".", 1)[-1] if "." in n else ""
        if n in ouvrir_site.SITES or (re.search(r"\.(com|fr|net|org|io|dev|app|be|ch|ca|tv|gg|ai|co|eu|uk|de)(/|$)", n)
                                      and extension not in ouvrir_fichier.EXTENSIONS_CONNUES):
            return ouvrir_site.executer(nom)
        resultat = ouvrir_fichier.executer(nom)
        if not resultat.startswith("Je ne trouve aucun"):
            direct_dernier = True
            return resultat
        connus = ", ".join(list(TABLE)[:8])
        return f"Je ne connais pas « {nom} », monsieur. Les noms connus sont : {connus}."
    cle, cible = trouve
    if cle == "comfyui":
        import requests
        try:
            requests.get(CONFIG["comfyui"]["url"] + "/system_stats", timeout=2)
            webbrowser.open(CONFIG["comfyui"]["url"])
            direct_dernier = True
            return "ComfyUI tourne déjà, j'ai ouvert son interface."
        except requests.RequestException:
            pass
    from ..cerveau import TITRE
    from . import fenetres, ouvrir_fichier
    avant = {f["hwnd"] for f in fenetres.lister_fenetres()}
    lancer(cible)
    ouvrir_fichier.amener_devant(avant)
    direct_dernier = True
    return f"J'ouvre {_avec_article(cle)}, {TITRE}."
