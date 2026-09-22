"""Les armures du HUD côté serveur (v3, consigne 1) : la commande vocale « passe en armure Mark III », l'armure
mémorisée dans config.json (`hud.theme`) et rendue par /etat, pour que chaque onglet du HUD la retrouve.
Les couleurs, le réacteur et les sons sont dans jarvis/hud/themes.js ; ici, seulement les noms et leur façon d'être dits."""
import json
import re
import unicodedata

from .config import CONFIG, RACINE

DEFAUT = "jarvis"
# nom -> (libellé, phrase de Jarvis, manières de le dire après « armure ») ; Whisper écrit « Mark 3 », « Mark III »,
# « marque trois »… : on compare en minuscules, sans accents
ARMURES = {
    "jarvis": ("Jarvis", "Retour à l'armure d'origine, {titre}.",
               ["jarvis", "d'origine", "d origine", "origine", "classique", "normale", "de base", "par defaut", "bleue", "cyan"]),
    "mark3": ("Mark III", "Armure Mark III en place, {titre}.",
              ["mark 3", "mark iii", "mark trois", "mark3", "marc 3", "marc trois", "marque 3", "marque trois", "mk3", "mk 3",
               "rouge et or", "rouge"]),
    "friday": ("Friday", "Protocole Friday activé.", ["friday", "fraidai", "fraide", "violette", "violet"]),
    "ultron": ("Ultron", "Armure Ultron. Je reste de votre côté, rassurez-vous.", ["ultron", "ultrone", "ultra"]),
}


def _normaliser(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower().replace("’", "'"))
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip(" .!?,")


def nom_depuis(dit: str) -> str | None:
    """« Mark 3 » -> mark3 ; None si ce n'est aucune armure connue."""
    d = _normaliser(dit)
    d = re.sub(r"^(?:l'|la |le |l |une |un |mon |ma |ton |ta )", "", d)
    for nom, (libelle, _, formes) in ARMURES.items():
        if d == _normaliser(libelle) or any(d == f or d.startswith(f + " ") for f in formes):
            return nom
    return None


def actuelle() -> str:
    nom = CONFIG.get("hud", {}).get("theme", DEFAUT)
    return nom if nom in ARMURES else DEFAUT


def definir(nom: str) -> bool:
    """Change l'armure et l'écrit dans config.json. Faux si le nom est inconnu."""
    if nom not in ARMURES:
        return False
    CONFIG.setdefault("hud", {})["theme"] = nom
    chemin = RACINE / "config.json"
    fichier = json.loads(chemin.read_text(encoding="utf-8"))
    fichier.setdefault("hud", {})["theme"] = nom
    chemin.write_text(json.dumps(fichier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def phrase(nom: str, titre: str) -> str:
    return ARMURES[nom][1].format(titre=titre)
