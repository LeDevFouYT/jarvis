"""Outil ouvrir_site : ouvre un site web par son nom (YouTube, Google, Gmail…) ou une adresse, avec au besoin
une recherche dedans (« cherche des vidéos de chats sur YouTube », « cherche la météo à Brest »)."""
import re
import unicodedata
import urllib.parse
import webbrowser

NOM = "ouvrir_site"
DESCRIPTION = ("Ouvre un site web dans le navigateur par son nom (YouTube, Google, Gmail, Netflix, Twitch, "
               "Wikipédia, Amazon, GitHub, ChatGPT… ou n'importe quel nom de site ou adresse) et, si monsieur "
               "le demande, lance une recherche dedans. Pour « va sur », « ouvre », « cherche … sur … », "
               "« mets une vidéo de … ».")
PARAMETRES = {
    "site": {"type": "string", "description": "Nom du site (youtube, google, gmail…) ou adresse complète"},
    "recherche": {"type": "string", "description": "Texte à chercher sur ce site (facultatif)"},
}
REQUIS = ["site"]

SITES = {
    "google": "https://www.google.fr",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "maps": "https://www.google.fr/maps",
    "drive": "https://drive.google.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
    "wikipedia": "https://fr.wikipedia.org",
    "amazon": "https://www.amazon.fr",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "spotify": "https://open.spotify.com",
    "deezer": "https://www.deezer.com",
    "instagram": "https://www.instagram.com",
    "tiktok": "https://www.tiktok.com",
    "facebook": "https://www.facebook.com",
    "discord": "https://discord.com/app",
    "leboncoin": "https://www.leboncoin.fr",
    "runpod": "https://www.runpod.io/console",
    "huggingface": "https://huggingface.co",
    "civitai": "https://civitai.com",
    "comfyui": "http://127.0.0.1:8188",
    "jarvis": "http://127.0.0.1:8765",
}
RECHERCHES = {
    "google": "https://www.google.fr/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "wikipedia": "https://fr.wikipedia.org/w/index.php?search={q}",
    "amazon": "https://www.amazon.fr/s?k={q}",
    "github": "https://github.com/search?q={q}",
    "maps": "https://www.google.fr/maps/search/{q}",
    "twitch": "https://www.twitch.tv/search?term={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "spotify": "https://open.spotify.com/search/{q}",
    "leboncoin": "https://www.leboncoin.fr/recherche?text={q}",
    "huggingface": "https://huggingface.co/search/full-text?q={q}",
    "civitai": "https://civitai.com/search/models?query={q}",
    "tiktok": "https://www.tiktok.com/search?q={q}",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={q}",
}


ARTICLES = {"le", "la", "les", "l", "un", "une", "du", "de", "des", "site", "sitede", "sur", "vers", "page", "web", "lesite"}


def _normaliser(t: str) -> str:
    """Minuscules sans accents ; les petits mots (le, la, site de…) sont retirés en tête et en queue."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"^(https?://)?(www\.)?", "", t.strip())
    mots = [m for m in re.split(r"[\s']+", t) if m]
    while mots and mots[0] in ARTICLES:
        mots.pop(0)
    while mots and mots[-1] in ARTICLES:
        mots.pop()
    return " ".join(mots).rstrip("/")


def _ouvrir(url: str) -> bool:
    import os
    try:
        os.startfile(url)
        return True
    except OSError:
        return webbrowser.open(url)


def adresse(site: str, recherche: str | None = None) -> tuple[str, str]:
    """Retourne (URL, libellé parlable)."""
    s = _normaliser(site)
    if recherche:
        recherche = urllib.parse.unquote_plus(recherche)   # le modèle encode parfois lui-même les accents
    compact = re.sub(r"[^a-z0-9.:/\-]+", "", s)
    cle = compact.split(".")[0] if "." in compact else compact
    if cle.startswith("wiki"):
        cle = "wikipedia"
    q = urllib.parse.quote_plus(recherche.strip()) if recherche and recherche.strip() else ""
    if cle in SITES:
        if q and cle in RECHERCHES:
            return RECHERCHES[cle].format(q=q), f"recherche « {recherche.strip()} » sur {cle}"
        if q:
            domaine = SITES[cle].split("//")[1].split("/")[0]
            url = RECHERCHES["google"].format(q=urllib.parse.quote_plus(f"{recherche.strip()} site:{domaine}"))
            return url, f"recherche « {recherche.strip()} » sur {cle} via Google"
        return SITES[cle], cle
    if "." in compact and " " not in s:
        return f"https://{compact}", compact
    if q:
        url = RECHERCHES["google"].format(q=urllib.parse.quote_plus(f"{recherche.strip()} {s}"))
        return url, f"recherche « {recherche.strip()} » sur Google"
    if " " in s:
        # Plusieurs mots (« mairie de Brest ») : une recherche Google vaut mieux qu'un .com deviné.
        return RECHERCHES["google"].format(q=urllib.parse.quote_plus(s)), f"recherche « {s} » sur Google"
    # Un seul mot inconnu : on tente le .com, ce qui couvre la plupart des sites.
    return f"https://www.{compact}.com", f"{compact}.com"


def executer(site: str, recherche: str | None = None) -> str:
    url, libelle = adresse(site, recherche)
    if not _ouvrir(url):
        return f"Le navigateur n'a pas voulu s'ouvrir pour {libelle}, monsieur."
    return f"Ouvert dans le navigateur : {libelle}."
