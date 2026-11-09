"""Le prénom de l'assistant : « Jarvis » par défaut, réglable (`personnage.prenom`, Réglages, ou à la voix :
« appelle-toi Nova »). Demande des utilisateurs (vidéo 5) : renommer Jarvis le cassait, son nom était écrit en dur
dans les oreilles, la consigne du cerveau et le HUD.

Le réveil sur un autre prénom passe par Whisper (mode phrase) : la phrase doit COMMENCER par le prénom. Le modèle
openWakeWord `hey_jarvis` ne sert que si le prénom est Jarvis. Whisper reçoit le prénom en indice (`initial_prompt`),
ce qui suffit en général à l'écrire juste ; pour le reste, `variantes()` produit les graphies qu'il donne d'un nom
qu'il ne connaît pas (ph/f, y/i, c/k, finale muette…), et un nom d'au moins 4 lettres est encore reconnu s'il est
très proche (`SEUIL_PROCHE`). Les variantes qui tombent sur un mot courant sont écartées : elles réveilleraient
l'assistant au milieu d'une conversation."""
import difflib
import json
import re
import unicodedata

from .config import CONFIG, RACINE

DEFAUT = "Jarvis"
SEUIL_PROCHE = 0.75         # ressemblance du premier mot entendu avec le prénom (4 lettres et plus, même longueur)

# les graphies de « Jarvis » relevées en vrai depuis le 15/09 (inchangées)
_VARIANTES_JARVIS = ["jarvis", "jarviss", "jarvice", "jarvi", "jarvys", "javis", "djarvis", "charvis", "jarvise", "jarwis"]
_SALUTS = r"(?:ok |okay |hey |eh |he |dis |dis-moi |dites |allo |salut |bonjour |bonsoir |bon |alors |et )*"
# une substitution à la fois, dans les deux sens : ce que Whisper confond sur un nom qu'il ne connaît pas
_ECHANGES = [("ph", "f"), ("y", "i"), ("k", "c"), ("qu", "k"), ("w", "v"), ("ai", "e"), ("ei", "e"), ("eau", "o"),
             ("au", "o"), ("s", "z"), ("ch", "sh"), ("x", "ks"), ("ou", "u"), ("ll", "l"), ("nn", "n"), ("tt", "t")]
_SENS_UNIQUE = {("eau", "o"), ("au", "o"), ("ll", "l"), ("nn", "n"), ("tt", "t")}
_FINALES_MUETTES = "ehstx"
# mots qu'une variante ne doit jamais devenir (début de phrase banal)
MOTS_COURANTS = set("""
a ah ai alors au aux avec bah ben bien bon bonjour bonsoir ca ce ces cest cette comme dans de des dis donc du elle elles
en est et etre eu fait faut il ils je la le les leur lui ma mais me mes moi mon non nous on ou oui par pas peu peut plus
pour quand que quel quelle qui quoi sa sans se ses si son sont sur ta te tes toi ton tous tout tu un une va vais vas vous
voila vu y the you yes no ok okay hey hello what this that is it
""".split())


def _normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFD", texte.lower().replace("’", "'"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z' -]+", " ", t)).strip()


def actuel() -> str:
    p = str(CONFIG.get("personnage", {}).get("prenom") or DEFAUT).strip()
    return p or DEFAUT


def est_jarvis(prenom: str | None = None) -> bool:
    return _normaliser(prenom or actuel()) == "jarvis"


def valider(prenom: str) -> tuple[bool, str]:
    """(valide, prénom propre ou raison du refus)."""
    p = re.sub(r"\s+", " ", (prenom or "").strip(" .,!?;:\"'«»"))
    n = _normaliser(p)
    if not 2 <= len(n.replace(" ", "")) <= 20 or len(n.split()) > 2 or not re.fullmatch(r"[a-z]+(?:[ '-][a-z]+)?", n):
        return False, "un prénom de 2 à 20 lettres, en un ou deux mots"
    if n in MOTS_COURANTS:
        return False, f"« {p} » est un mot trop courant : je me réveillerais à chaque phrase"
    return True, " ".join(m[:1].upper() + m[1:] for m in p.split(" "))


def variantes(prenom: str | None = None) -> list[str]:
    """Les graphies acceptées en début de phrase, normalisées (minuscules, sans accents)."""
    base = _normaliser(prenom or actuel())
    if base == "jarvis":
        return list(_VARIANTES_JARVIS)
    vues = {base}
    for a, b in _ECHANGES:
        # « eau » -> « o » oui, mais pas l'inverse : « nova » n'est jamais écrit « neauva »
        for x, y in ((a, b),) if (a, b) in _SENS_UNIQUE else ((a, b), (b, a)):
            if x in base:
                vues.add(base.replace(x, y))
    for v in list(vues):
        if v[-1] in _FINALES_MUETTES and len(v) > 3:
            vues.add(v[:-1])
        for f in "esh":
            vues.add(v + f)
    if base.startswith("j"):
        vues.add("dj" + base[1:])
    return sorted(v for v in vues if v == base or (len(v) >= 3 and v not in MOTS_COURANTS))


_cache: dict = {}


def _motif() -> re.Pattern:
    p = actuel()
    if _cache.get("prenom") != p:
        alternatives = "|".join(re.escape(v).replace(r"\ ", r"[\s-]?") for v in sorted(variantes(p), key=len, reverse=True))
        # « Hey Nova » dit vite : Whisper écrit « Enova » (mesuré le 29/10) — le salut collé au prénom compte aussi
        _cache.update(prenom=p, motif=re.compile(rf"^{_SALUTS}(?:hey|he|e)?(?:{alternatives})\b[\s,.!?:;-]*", re.IGNORECASE))
    return _cache["motif"]


def _sans_accents(texte: str) -> str:
    n = unicodedata.normalize("NFD", texte)
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


def detacher(texte: str) -> str | None:
    """« Nova, quelle heure est-il » -> « quelle heure est-il » ; None si la phrase ne commence pas par le prénom.
    Les positions sont comptées sur le texte sans accents, puis rendues sur le texte d'origine."""
    brut = texte.strip()
    n = _sans_accents(brut)
    m = _motif().match(n)
    if m:
        return brut[m.end():].strip() if len(brut) >= m.end() else ""
    p = _normaliser(actuel())
    if len(p.replace(" ", "")) < 4 or " " in p:
        return None
    # une seule lettre confondue, à longueur égale : « Nofa » pour « Nova », pas « Novak » (un autre prénom)
    m = re.match(rf"^{_SALUTS}([a-z]+)\b[\s,.!?:;-]*", n, re.IGNORECASE)
    mot = m.group(1).lower() if m else ""
    if m and mot not in MOTS_COURANTS and len(mot) == len(p) and mot[:1] == p[:1] \
            and difflib.SequenceMatcher(None, mot, p).ratio() >= SEUIL_PROCHE:
        return brut[m.end():].strip()
    return None


def retirer_appel(texte: str) -> str:
    """Pour les commandes et les réflexes : « Nova, éteins-toi » -> « éteins-toi ». « Jarvis, … » marche toujours
    (Telegram, habitudes) ; une phrase sans prénom reste telle quelle."""
    reste = detacher(texte)
    if reste is None and not est_jarvis():
        m = re.match(rf"^{_SALUTS}jarvis\b[\s,.!?:;-]*", _sans_accents(texte.strip()), re.IGNORECASE)
        reste = texte.strip()[m.end():] if m else None
    return texte if reste is None or not reste.strip() else reste.strip()


def definir(prenom: str) -> tuple[bool, str]:
    """Change le prénom et l'écrit dans config.json. Rend (ok, prénom propre ou raison du refus)."""
    ok, propre = valider(prenom)
    if not ok:
        return False, propre
    CONFIG.setdefault("personnage", {})["prenom"] = propre
    chemin = RACINE / "config.json"
    fichier = json.loads(chemin.read_text(encoding="utf-8"))
    fichier.setdefault("personnage", {})["prenom"] = propre
    chemin.write_text(json.dumps(fichier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True, propre


def sigle(prenom: str | None = None) -> str:
    """Le nom affiché en tête du HUD : « J.A.R.V.I.S. », « N.O.V.A. » ; un nom long ou en deux mots en capitales."""
    p = prenom or actuel()
    lettres = _sans_accents(p).upper()
    return ".".join(lettres) + "." if lettres.isalpha() and len(lettres) <= 8 else p.upper()
