"""Outil chercher_web : une recherche sur Internet affichée dans l'onglet intégré du HUD.
  sur = web      DuckDuckGo (page HTML, sans clé), résultats parsés et rendus par le HUD ; Jarvis lit les premiers.
  sur = youtube  lecteur YouTube intégré sur la liste de résultats (paramètre officiel listType=search).
Chaque recherche web compte une requête sortie sur Internet."""
import html
import logging
import re
import time
import urllib.parse

import requests

from .. import compteur

NOM = "chercher_web"
DESCRIPTION = ("Cherche sur Internet et affiche les résultats dans l'onglet intégré de l'interface : "
               "sur le web (moteur de recherche) ou sur YouTube (lecteur intégré). À utiliser quand monsieur "
               "ou madame demande de chercher, de trouver ou de mettre une vidéo. Renvoie les premiers résultats "
               "pour les résumer à l'oral.")
PARAMETRES = {
    "requete": {"type": "string", "description": "Ce qu'il faut chercher"},
    "sur": {"type": "string", "enum": ["web", "youtube"], "description": "web (par défaut) ou youtube"},
}
REQUIS = ["requete"]

sur_evenement = lambda e: None
journal = logging.getLogger("chercher_web")
ENTETES = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0"}


def _texte(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _url(brute: str) -> str:
    u = html.unescape(brute)
    if u.startswith("//"):
        u = "https:" + u
    if "duckduckgo.com/l/" in u:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        if "uddg" in q:
            return q["uddg"][0]
    return u


def rechercher(requete: str, nombre: int = 8) -> list[dict]:
    compteur.compter("recherche_web")
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": requete, "kl": "fr-fr"},
                      headers=ENTETES, timeout=15)
    r.raise_for_status()
    liens = re.findall(r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>', r.text, re.S)
    extraits = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S)
    resultats = []
    for (u, t), s in zip(liens, extraits + [""] * len(liens)):
        url = _url(u)
        domaine = urllib.parse.urlparse(url).netloc.replace("www.", "")
        if "duckduckgo.com" in domaine or not domaine:
            continue      # publicité ou lien interne du moteur
        resultats.append({"titre": _texte(t), "url": url, "extrait": _texte(s), "domaine": domaine})
        if len(resultats) >= nombre:
            break
    return resultats


def executer(requete: str, sur: str = "web") -> str:
    requete = urllib.parse.unquote_plus(requete or "").strip()
    if not requete:
        return "Que dois-je chercher ?"
    if (sur or "web").lower().startswith("you"):
        url = "https://www.youtube.com/embed?listType=search&list=" + urllib.parse.quote_plus(requete)
        sur_evenement({"type": "panneau", "t": time.time(), "genre": "youtube", "titre": f"YouTube : {requete}",
                       "url": url, "externe": "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(requete)})
        return f"Lecteur YouTube ouvert dans l'interface sur « {requete} »."
    resultats = rechercher(requete)
    sur_evenement({"type": "panneau", "t": time.time(), "genre": "recherche", "titre": f"Recherche : {requete}",
                   "requete": requete, "resultats": resultats,
                   "externe": "https://duckduckgo.com/?q=" + urllib.parse.quote_plus(requete)})
    if not resultats:
        return f"Aucun résultat pour « {requete} »."
    lignes = [f"{i + 1}. {r['titre']} ({r['domaine']}) : {r['extrait'][:160]}" for i, r in enumerate(resultats[:5])]
    return f"Résultats affichés dans l'interface pour « {requete} ». Les premiers : " + " | ".join(lignes)
