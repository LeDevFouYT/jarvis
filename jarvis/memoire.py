"""La mémoire longue : des souvenirs courts, datés, avec leur source, dans memoire/souvenirs.json.

- À la fin d'une session (extinction, « oublie tout », ou dix minutes sans échange), le cerveau lit la conversation
  et propose de nouveaux souvenirs ; seuls ceux qu'il juge stables (encore vrais dans un mois) sont gardés.
- « Retiens que… » ajoute un souvenir tout de suite ; « oublie que… » retire le plus proche ; « qu'est-ce que tu
  sais de moi » les liste et ouvre la constellation dans le HUD.
- Pour chaque question, seuls les souvenirs pertinents sont donnés au cerveau : similarité de plongements
  (qwen3-embedding:0.6b par Ollama, sur le processeur pour ne rien prendre en VRAM) entre la question et, pour chaque
  souvenir, « le fait. Concerne : les sujets où il sert » (sujets écrits une fois par le cerveau, à l'ajout).
  Mesures du 16/09 : nomic-embed-text rendait un bruit de fond (0,55) au-dessus des bonnes réponses ; le fait seul ne
  reliait pas « une idée de dîner » à « végétarien » ; des mots-clés isolés ramenaient « soirée » pour l'heure.
  Sans le modèle de plongements : recouvrement de mots. Le titre (monsieur ou madame) reste dans personne.json.
L'ancien résumé (resume.txt) est converti en souvenirs au premier démarrage, puis renommé resume.txt.importe."""
import hashlib
import json
import logging
import math
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime

import requests

from .config import CONFIG, RACINE

DOSSIER = RACINE / "memoire"
FICHIER = DOSSIER / "souvenirs.json"
VECTEURS = DOSSIER / "souvenirs_vecteurs.json"
ANCIEN_RESUME = DOSSIER / "resume.txt"
TITRE_FICHIER = DOSSIER / "personne.json"
REGLAGES = CONFIG.setdefault("memoire", {})
journal = logging.getLogger("memoire")
_verrou = threading.RLock()

sur_evenement = lambda e: None      # branché par le serveur


def _emettre(type_, **champs):
    sur_evenement({"type": type_, "t": time.time(), **champs})


# =============================================================================================
# Stockage
# =============================================================================================
def _lire_fichier() -> list[dict]:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8")).get("souvenirs", [])
    except Exception:
        return []


def _ecrire_fichier(souvenirs: list[dict]):
    DOSSIER.mkdir(exist_ok=True)
    temporaire = FICHIER.with_suffix(".tmp")
    temporaire.write_text(json.dumps({"version": 1, "souvenirs": souvenirs}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporaire.replace(FICHIER)


def lister() -> list[dict]:
    with _verrou:
        return _lire_fichier()


def nombre() -> int:
    return len(lister())


# =============================================================================================
# Plongements (qwen3-embedding par Ollama) et repli lexical
# =============================================================================================
_vecteurs_cache: dict | None = None
_modele_absent_jusqua = 0.0


def _modele() -> str:
    return REGLAGES.get("modele_plongements", "qwen3-embedding:0.6b")


# consignes des modèles de plongements : la requête porte l'intention, les souvenirs sont bruts
_INSTRUCTIONS = {
    # en anglais : sur la mesure du 16/09, la meilleure séparation entre souvenirs utiles et parasites
    "question": "Instruct: Given a request to a voice assistant, retrieve the personal facts about the user that would change the answer\nQuery: ",
    "oubli": "Instruct: Retrouve le souvenir que la personne demande d'effacer\nQuery: ",
}


def _ollama() -> str:
    return CONFIG.get("ollama", {}).get("url", "http://127.0.0.1:11434")


def plonger(textes: list[str], requete: bool | str = False) -> list[list[float]] | None:
    """Vecteurs normalisés, ou None si le modèle n'est pas disponible (on retombe sur les mots).
    `requete` : False pour des souvenirs, « question » ou « oubli » (True = question) pour une demande."""
    global _modele_absent_jusqua
    if not textes or time.time() < _modele_absent_jusqua:
        return None
    if "nomic" in _modele():
        prefixe = "search_query: " if requete else "search_document: "
    else:
        prefixe = _INSTRUCTIONS["question" if requete is True else requete] if requete else ""
    try:
        r = requests.post(f"{_ollama()}/api/embed", json={
            "model": _modele(), "input": [prefixe + t for t in textes], "keep_alive": "30m",
            "options": {"num_gpu": 0 if REGLAGES.get("plongements_sur_processeur", True) else -1}}, timeout=20)
        if r.status_code != 200:
            _modele_absent_jusqua = time.time() + 300
            return None
        vecteurs = r.json()["embeddings"]
    except Exception:
        _modele_absent_jusqua = time.time() + 60
        return None
    return [_normer(v) for v in vecteurs]


def _normer(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _cle(fait: str) -> str:
    return hashlib.sha1(f"{_modele()}|{fait}".encode("utf-8")).hexdigest()


def _charger_vecteurs() -> dict:
    global _vecteurs_cache
    if _vecteurs_cache is None:
        try:
            _vecteurs_cache = json.loads(VECTEURS.read_text(encoding="utf-8"))
        except Exception:
            _vecteurs_cache = {}
    return _vecteurs_cache


def document(s: dict) -> str:
    """Le texte plongé pour un souvenir : le fait et les sujets qu'il concerne (« Est végétarien. Concerne : repas,
    recettes, restaurants. »). Mesuré le 16/09 sur 15 questions et 7 souvenirs : le fait seul rate la moitié des cas
    utiles (« une idée de dîner » ne rejoint pas « végétarien ») ; fait + sujets : tous trouvés, 1 faux positif sur 95."""
    return f"{s['fait']}. Concerne : {', '.join(s['themes'])}." if s.get("themes") else s["fait"]


def _vecteurs_de(souvenirs: list[dict]) -> dict[str, list[float]]:
    """id -> vecteur, en calculant ceux qui manquent (une seule requête pour tous)."""
    cache = _charger_vecteurs()
    manquants = [s for s in souvenirs if _cle(document(s)) not in cache]
    if manquants:
        vecteurs = plonger([document(s) for s in manquants])
        if vecteurs is None:
            return {}
        for s, v in zip(manquants, vecteurs):
            cache[_cle(document(s))] = [round(x, 5) for x in v]
        tous = lister() + souvenirs
        valides = {_cle(document(s)) for s in tous} | {_cle("fait|" + s["fait"]) for s in tous}
        for cle in [c for c in cache if c not in valides]:
            del cache[cle]
        DOSSIER.mkdir(exist_ok=True)
        VECTEURS.write_text(json.dumps(cache), encoding="utf-8")
    return {s["id"]: cache[_cle(document(s))] for s in souvenirs if _cle(document(s)) in cache}


def _cosinus(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


_MOTS_VIDES = set("""le la les un une des du de d l et ou a au aux en dans sur pour par avec sans que qui quoi est sont
je tu il elle on nous vous ils elles me te se mon ma mes ton ta tes son sa ses notre votre leur ce cette ces ça cela
ne pas plus tres bien aussi mais donc comme quand comment pourquoi quel quelle quels quelles moi toi lui eux
the a an is are to of in on for and or my your i you it what who how""".split())


def _mots(texte: str) -> set[str]:
    t = unicodedata.normalize("NFD", texte.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {m[:6] for m in re.findall(r"[a-z0-9]+", t) if m not in _MOTS_VIDES and len(m) > 1}


def _score_mots(question: str, fait: str) -> float:
    q, f = _mots(question), _mots(fait)
    if not q or not f:
        return 0.0
    return len(q & f) / math.sqrt(len(q) * len(f))


# =============================================================================================
# Ce que le cerveau reçoit : les souvenirs pertinents pour la question
# =============================================================================================
def pertinents(question: str, maximum: int | None = None) -> list[dict]:
    """Les souvenirs utiles à cette question, du plus au moins proche, avec leur score."""
    maximum = maximum or int(REGLAGES.get("maximum_par_question", 4))
    souvenirs = lister()
    if not souvenirs or not question.strip():
        return []
    vecteurs = _vecteurs_de(souvenirs)
    requete = plonger([question], requete=True) if vecteurs else None
    if requete:
        seuil = float(REGLAGES.get("seuil_similarite", 0.39))
        notes = [(_cosinus(requete[0], vecteurs[s["id"]]), s) for s in souvenirs if s["id"] in vecteurs]
        notes.sort(key=lambda x: -x[0])
        if not notes or notes[0][0] < seuil:
            return []
        # au-dessus du seuil, et pas trop loin du meilleur : un souvenir médiocre n'accompagne pas un bon
        garde = [(n, s) for n, s in notes if n >= seuil and n >= notes[0][0] - float(REGLAGES.get("ecart_au_meilleur", 0.08))][:maximum]
        methode = "plongements"
    else:
        notes = sorted(((_score_mots(question, s["fait"]), s) for s in souvenirs), key=lambda x: -x[0])
        garde = [(n, s) for n, s in notes if n >= 0.34][:maximum]
        methode = "mots"
    resultat = [{**s, "score": round(n, 3), "methode": methode} for n, s in garde]
    if resultat:
        _noter_usage([s["id"] for s in resultat])
    return resultat


def _noter_usage(ids: list[str]):
    with _verrou:
        souvenirs = _lire_fichier()
        for s in souvenirs:
            if s["id"] in ids:
                s["utilise"] = s.get("utilise", 0) + 1
                s["dernier_usage"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _ecrire_fichier(souvenirs)


def annexe(souvenirs: list[dict], langue: str = "fr") -> str:
    """Le bloc glissé après la question (jamais dans la consigne : son début reste identique, Ollama le garde en cache)."""
    if not souvenirs:
        return ""
    lignes = "; ".join(f"{s['fait']} ({s['date']})" for s in souvenirs)
    if langue == "en":
        return f"[Things you remember about the user, use them only if they help, never recite them: {lignes}]"
    return f"[Souvenirs sur la personne, à utiliser seulement s'ils aident, sans les réciter : {lignes}]"


_VERBES = {    # troisième personne -> (vous, tu) ; les verbes réguliers en -e sont conjugués par règle
    "est": ("êtes", "es"), "a": ("avez", "as"), "fait": ("faites", "fais"), "va": ("allez", "vas"),
    "peut": ("pouvez", "peux"), "veut": ("voulez", "veux"), "doit": ("devez", "dois"), "vit": ("vivez", "vis"),
    "prend": ("prenez", "prends"), "apprend": ("apprenez", "apprends"), "comprend": ("comprenez", "comprends"),
    "sait": ("savez", "sais"), "connaît": ("connaissez", "connais"), "connait": ("connaissez", "connais"),
    "boit": ("buvez", "bois"), "lit": ("lisez", "lis"), "écrit": ("écrivez", "écris"), "dit": ("dites", "dis"),
    "part": ("partez", "pars"), "sort": ("sortez", "sors"), "dort": ("dormez", "dors"), "suit": ("suivez", "suis"),
    "tient": ("tenez", "tiens"), "vient": ("venez", "viens"), "revient": ("revenez", "reviens"),
    "choisit": ("choisissez", "choisis"), "finit": ("finissez", "finis"), "met": ("mettez", "mets"),
    "court": ("courez", "cours"), "conduit": ("conduisez", "conduis"), "construit": ("construisez", "construis"),
    "vend": ("vendez", "vends"), "attend": ("attendez", "attends"), "perd": ("perdez", "perds"),
    "répond": ("répondez", "réponds"), "entend": ("entendez", "entends"),
}
_POSSESSIFS = {"son": ("votre", "ton"), "sa": ("votre", "ta"), "ses": ("vos", "tes")}
_PAS_DES_VERBES = ("iste", "logue", "eute", "aire", "graphe", "ome", "icienne", "ienne", "euse", "trice")   # des métiers


def pour_la_personne(fait: str, tu: bool = False) -> str:
    """Un souvenir est rangé sans sujet (« Est végétarien », « Son frère s'appelle Thomas ») : à l'oral, Jarvis le
    tourne vers la personne (« vous êtes végétarien », « votre frère s'appelle Thomas »). Sans modèle ; si la
    tournure n'est pas reconnue, le souvenir est cité entre guillemets plutôt que mal conjugué."""
    fait = fait.strip().rstrip(".").strip()
    mots = fait.split()
    if not mots:
        return fait
    k = 1 if tu else 0

    def suite(reste: list[str]) -> list[str]:
        return [_POSSESSIFS[m.lower()][k] if m.lower() in _POSSESSIFS else m for m in reste]

    premier = mots[0].lower()
    if premier in _POSSESSIFS:                                  # « Son frère s'appelle Thomas »
        return " ".join([_POSSESSIFS[premier][k]] + suite(mots[1:]))
    reflechi = premier.startswith(("s'", "s’"))                 # « S'intéresse à l'astronomie »
    if reflechi:
        premier = premier[2:]
    if premier in _VERBES:
        verbe = _VERBES[premier][k]
    elif re.fullmatch(r"[a-zàâçéèêëîïôûùüÿœ]{2,}e", premier) and not premier.endswith(_PAS_DES_VERBES):
        # régulier : joue, préfère (préférez), s'appelle (appelez), habite
        if tu:
            verbe = premier + "s"
        else:
            radical = re.sub(r"è(?=[^aeiouyéèê]+e$)", "é", premier)[:-1]
            verbe = re.sub(r"(ll|tt)$", lambda m: m.group(1)[0], radical) + "ez"
    else:
        return f"« {fait} »"
    if reflechi:
        verbe = ("t'" if verbe[0] in "aeiouyéèêh" else "te ") + verbe if tu else "vous " + verbe
    return " ".join(["tu" if tu else "vous", verbe] + suite(mots[1:]))


# =============================================================================================
# Ajouter, oublier
# =============================================================================================
def _nettoyer(fait: str) -> str:
    fait = re.sub(r"\s+", " ", fait).strip().strip(".").strip()
    return fait[:1].upper() + fait[1:] if fait else fait


def ajouter(fait: str, source: str, stable: bool = True, themes: list[str] | None = None,
            attendre_themes: bool = False) -> dict | None:
    """Ajoute un souvenir. S'il existe déjà un souvenir quasi identique, il est rafraîchi au lieu d'être doublé.
    Sans `themes`, le cerveau écrit les mots-clés d'usage en tâche de fond (ou tout de suite si `attendre_themes`)."""
    fait = _nettoyer(fait)
    if len(fait) < 3:
        return None
    with _verrou:
        souvenirs = _lire_fichier()
        doublon = _plus_proche(fait, souvenirs, seuil_vecteurs=0.93, seuil_mots=0.85)
        aujourdhui = datetime.now().strftime("%Y-%m-%d")
        if doublon:
            for s in souvenirs:
                if s["id"] == doublon["id"]:
                    s.update(date=aujourdhui, source=source)
                    if len(fait) > len(s["fait"]):
                        s["fait"] = fait
                    nouveau = s
        else:
            nouveau = {"id": uuid.uuid4().hex[:10], "fait": fait, "date": aujourdhui, "source": source, "stable": stable,
                       "cree": time.time(), "utilise": 0, "dernier_usage": None, "themes": list(themes or [])}
            souvenirs.append(nouveau)
        _ecrire_fichier(souvenirs)
    _emettre("souvenir_ajoute", souvenir=nouveau, doublon=bool(doublon))
    if not nouveau.get("themes") and REGLAGES.get("themes", True):
        if attendre_themes:
            thematiser(nouveau["id"])
        else:
            threading.Thread(target=thematiser, args=(nouveau["id"],), daemon=True, name="memoire-themes").start()
    return nouveau


# =============================================================================================
# Les mots-clés d'usage : quand un souvenir doit-il servir ? (le cerveau les écrit une fois par souvenir)
# =============================================================================================
CONSIGNE_THEMES = ("Pour un fait sur une personne, liste les sujets de conversation où un assistant vocal devrait s'en souvenir "
                   "pour bien répondre : 5 à 7 sujets courts, CONCRETS, au pluriel avec leur article, en français. "
                   "Pense aux demandes où le fait change la réponse. "
                   "Interdits : les mots vagues ou de moment (habitudes, préférences, santé, personne, relation, activités, loisirs, "
                   "création, soirée, soir, matin, nuit, week-end, quotidien, vie). "
                   "Exemples : « Est allergique aux arachides » -> les repas, les restaurants, les snacks, les recettes, les desserts, "
                   "les courses ; « Son frère s'appelle Thomas » -> la famille, les frères et sœurs, les anniversaires, les cadeaux. "
                   "Réponds uniquement en JSON : {\"themes\": [\"...\"]}")
# des mots d'usage trop vagues : ils rapprocheraient n'importe quelle question de n'importe quel souvenir
MOTS_VAGUES = {"habitude", "habitudes", "preference", "preferences", "sante", "personne", "relation", "relations", "activite",
               "activites", "loisir", "loisirs", "creation", "soiree", "soir", "matin", "nuit", "week-end", "weekend", "quotidien",
               "vie", "divertissement", "pratique", "apprentissage", "projet", "proche", "proches", "nom", "information", "general"}


def _sans_accents(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"^(les|le|la|l'|des|du|de la|un|une)\s*", "", t).strip()


def nettoyer_themes(themes) -> list[str]:
    propres = []
    for t in themes or []:
        t = str(t).strip().lower()
        if t and _sans_accents(t) not in MOTS_VAGUES and t not in propres:
            propres.append(t)
    return propres[:8]
SCHEMA_THEMES = {"type": "object", "properties": {"themes": {"type": "array", "items": {"type": "string"}}}, "required": ["themes"]}
apres_appel_cerveau = lambda: None      # branché par le serveur : réchauffe le cache du cerveau après un appel annexe


def thematiser(identifiant: str) -> list[str]:
    s = next((x for x in lister() if x["id"] == identifiant), None)
    if not s or s.get("themes"):
        return (s or {}).get("themes", [])
    try:
        r = requests.post(f"{_ollama()}/api/chat", json={
            "model": CONFIG["cerveau"]["modele"], "stream": False, "think": False, "format": SCHEMA_THEMES,
            "keep_alive": CONFIG["cerveau"].get("keep_alive", "30m"),
            "messages": [{"role": "system", "content": CONSIGNE_THEMES}, {"role": "user", "content": s["fait"]}],
            "options": {"temperature": 0, "num_ctx": CONFIG["cerveau"].get("num_ctx", 8192)}}, timeout=60)
        r.raise_for_status()
        themes = nettoyer_themes(json.loads(r.json()["message"]["content"]).get("themes", []))
    except Exception:
        journal.exception("mots-clés d'un souvenir")
        return []
    finally:
        apres_appel_cerveau()
    with _verrou:
        souvenirs = _lire_fichier()
        for x in souvenirs:
            if x["id"] == identifiant:
                x["themes"] = themes
        _ecrire_fichier(souvenirs)
    return themes


def thematiser_manquants() -> int:
    """Au démarrage : les souvenirs sans mots-clés (anciens, ou écrits pendant une panne) en reçoivent."""
    n = 0
    for s in lister():
        if not s.get("themes") and thematiser(s["id"]):
            n += 1
    return n


def _vecteurs_faits(souvenirs: list[dict]) -> dict[str, list[float]]:
    """id -> vecteur du fait seul (sans ses sujets) : pour reconnaître un doublon ou le souvenir qu'on demande d'oublier."""
    cache = _charger_vecteurs()
    manquants = [s for s in souvenirs if _cle("fait|" + s["fait"]) not in cache]
    if manquants:
        vecteurs = plonger([s["fait"] for s in manquants])
        if vecteurs is None:
            return {}
        for s, v in zip(manquants, vecteurs):
            cache[_cle("fait|" + s["fait"])] = [round(x, 5) for x in v]
        DOSSIER.mkdir(exist_ok=True)
        VECTEURS.write_text(json.dumps(cache), encoding="utf-8")
    return {s["id"]: cache[_cle("fait|" + s["fait"])] for s in souvenirs if _cle("fait|" + s["fait"]) in cache}


def _plus_proche(texte: str, souvenirs: list[dict], seuil_vecteurs: float, seuil_mots: float) -> dict | None:
    if not souvenirs:
        return None
    vecteurs = _vecteurs_faits(souvenirs)
    v = plonger([texte]) if vecteurs else None
    if v:
        n, s = max(((_cosinus(v[0], vecteurs[s["id"]]), s) for s in souvenirs if s["id"] in vecteurs), key=lambda x: x[0])
        return s if n >= seuil_vecteurs else None
    n, s = max(((_score_mots(texte, s["fait"]), s) for s in souvenirs), key=lambda x: x[0])
    return s if n >= seuil_mots else None


def oublier(description: str) -> list[dict]:
    """Retire le souvenir qui correspond le mieux à la description (« que j'aime le café »). Rend les retirés."""
    with _verrou:
        souvenirs = _lire_fichier()
        if not souvenirs:
            return []
        vecteurs = _vecteurs_faits(souvenirs)
        v = plonger([description], requete="oubli") if vecteurs else None
        if v:
            notes = sorted(((_cosinus(v[0], vecteurs[s["id"]]), s) for s in souvenirs if s["id"] in vecteurs), key=lambda x: -x[0])
            seuil = float(REGLAGES.get("seuil_oubli", 0.5))
        else:
            notes = sorted(((_score_mots(description, s["fait"]), s) for s in souvenirs), key=lambda x: -x[0])
            seuil = 0.3
        if not notes or notes[0][0] < seuil:
            return []
        # le meilleur, et ceux qui en sont presque aussi proches (« oublie mon adresse » peut en toucher deux)
        retires = [s for n, s in notes if n >= seuil and n >= notes[0][0] - 0.02]
        ids = {s["id"] for s in retires}
        _ecrire_fichier([s for s in souvenirs if s["id"] not in ids])
    _emettre("souvenirs_oublies", ids=list(ids), faits=[s["fait"] for s in retires])
    return retires


def tout_oublier() -> int:
    with _verrou:
        n = len(_lire_fichier())
        _ecrire_fichier([])
    _emettre("souvenirs_oublies", ids=["*"], faits=[])
    return n


# =============================================================================================
# Fin de session : le cerveau propose, on garde les stables
# =============================================================================================
CONSIGNE_PROPOSITION = """Tu lis une conversation entre une personne et son assistant vocal Jarvis.
Relève les faits sur LA PERSONNE qui méritent d'être retenus pour les prochaines conversations : préférences, goûts,
habitudes, projets en cours, personnes de son entourage, lieux, matériel, métier, contraintes.
Pour chaque fait :
- une phrase courte (quinze mots au plus), à la troisième personne, sans « monsieur » ni « madame » (« Préfère le thé au café »),
- "stable": true seulement si le fait sera très probablement encore vrai dans un mois (goût, métier, projet de fond),
  false pour ce qui est passager (humeur du jour, demande ponctuelle, heure, météo, un calcul, une recherche).
- "themes" : 5 à 7 mots-clés courts, concrets et propres à ce fait, des sujets de questions où il doit servir
  (« Est végétarien » -> repas, recettes, restaurant, courses, cuisine) ; jamais de mots vagues (habitudes, santé, soirée…).
Ne relève rien sur Jarvis lui-même, rien sur ce que Jarvis a répondu, et rien qui figure déjà dans les souvenirs connus.
Si rien ne mérite d'être retenu, rends une liste vide.
Réponds uniquement en JSON : {"souvenirs": [{"fait": "...", "stable": true, "themes": ["..."]}]}"""

SCHEMA_PROPOSITION = {"type": "object", "properties": {"souvenirs": {"type": "array", "items": {
    "type": "object", "properties": {"fait": {"type": "string"}, "stable": {"type": "boolean"},
                                     "themes": {"type": "array", "items": {"type": "string"}}},
    "required": ["fait", "stable", "themes"]}}}, "required": ["souvenirs"]}


def proposer(historique: list[dict], url: str, modele: str, entetes: dict | None = None, delai: float = 90) -> dict:
    """Demande au cerveau les souvenirs de la session. Rend {proposes, gardes, ecartes}."""
    tours = [m for m in historique if m["role"] in ("user", "assistant") and m.get("content")]
    if not any(m["role"] == "user" for m in tours):
        return {"proposes": [], "gardes": [], "ecartes": []}
    conversation = "\n".join(f"{'Personne' if m['role'] == 'user' else 'Jarvis'} : {m['content'].split(chr(10) + chr(10) + '[')[0]}"
                             for m in tours[-60:])
    connus = "\n".join(f"- {s['fait']}" for s in lister()) or "(aucun)"
    try:
        r = requests.post(f"{url}/api/chat", json={
            "model": modele, "stream": False, "think": False, "keep_alive": CONFIG["cerveau"].get("keep_alive", "30m"),
            "format": SCHEMA_PROPOSITION,
            "messages": [{"role": "system", "content": CONSIGNE_PROPOSITION},
                         {"role": "user", "content": f"Souvenirs déjà connus :\n{connus}\n\nConversation :\n{conversation}"}],
            "options": {"num_ctx": CONFIG["cerveau"].get("num_ctx", 8192), "temperature": 0}},
            headers=entetes or {}, timeout=delai)
        r.raise_for_status()
        proposes = json.loads(r.json()["message"]["content"]).get("souvenirs", [])
    except Exception:
        journal.exception("proposition de souvenirs")
        return {"proposes": [], "gardes": [], "ecartes": [], "erreur": True}
    finally:
        apres_appel_cerveau()
    source = f"conversation du {datetime.now():%d/%m/%Y}"
    gardes, ecartes = [], []
    for p in proposes:
        fait = str(p.get("fait", "")).strip()
        if not fait:
            continue
        if p.get("stable") is True:
            s = ajouter(fait, source, themes=nettoyer_themes(p.get("themes", [])))
            if s:
                gardes.append(s)
        else:
            ecartes.append(fait)
    _emettre("souvenirs_session", gardes=[s["fait"] for s in gardes], ecartes=ecartes)
    return {"proposes": proposes, "gardes": gardes, "ecartes": ecartes}


def importer_ancien_resume(url: str | None = None, modele: str | None = None) -> int:
    """Une fois : l'ancien resume.txt passe par le cerveau comme une fin de session ; seuls les faits stables sur la
    personne deviennent des souvenirs. (Découper le résumé en phrases, essayé d'abord, donnait des souvenirs creux
    comme « Jarvis a répondu à toutes les questions avec précision ».)"""
    if not ANCIEN_RESUME.exists():
        return 0
    texte = re.sub(r"^\[[^\]]*\]\s*", "", ANCIEN_RESUME.read_text(encoding="utf-8").strip())
    n = 0
    if texte and url and modele:
        resultat = proposer([{"role": "user", "content": f"(Résumé d'une ancienne session) {texte}"}], url, modele)
        if resultat.get("erreur"):
            return 0                                        # on réessaiera au prochain démarrage
        n = len(resultat["gardes"])
    ANCIEN_RESUME.rename(ANCIEN_RESUME.with_suffix(".txt.importe"))
    return n


# =============================================================================================
# La constellation du HUD : une étoile par souvenir, placée par la forme de son sens (ACP en 3D)
# =============================================================================================
def constellation(allumes: list[str] | None = None) -> dict:
    souvenirs = lister()
    vecteurs = _vecteurs_de(souvenirs)
    positions = _positions(souvenirs, vecteurs)
    etoiles = [{"id": s["id"], "fait": s["fait"], "date": s["date"], "source": s["source"], "utilise": s.get("utilise", 0),
                "position": positions.get(s["id"], [0, 0, 0])} for s in souvenirs]
    # chaque étoile reliée à sa plus proche voisine : les souvenirs voisins par le sens dessinent des figures
    liens = []
    ids = [e["id"] for e in etoiles if e["id"] in vecteurs]
    for i in ids:
        voisins = sorted(((_cosinus(vecteurs[i], vecteurs[j]), j) for j in ids if j != i), reverse=True)
        if voisins and voisins[0][0] > 0.6:
            paire = tuple(sorted((i, voisins[0][1])))
            if paire not in liens:
                liens.append(paire)
    return {"etoiles": etoiles, "liens": [list(p) for p in liens], "allumes": allumes or []}


def _positions(souvenirs: list[dict], vecteurs: dict) -> dict[str, list[float]]:
    positions = {}
    ids = [s["id"] for s in souvenirs if s["id"] in vecteurs]
    if len(ids) >= 3:
        import numpy as np
        m = np.array([vecteurs[i] for i in ids], dtype=np.float32)
        m -= m.mean(axis=0)
        _, _, axes = np.linalg.svd(m, full_matrices=False)
        coords = m @ axes[:3].T
        coords /= (np.abs(coords).max(axis=0) + 1e-6)
        for i, c in zip(ids, coords):
            positions[i] = [round(float(x), 3) for x in c]
    for s in souvenirs:                                   # sans vecteur : une place stable tirée de l'identifiant
        if s["id"] not in positions:
            h = hashlib.sha1(s["id"].encode()).digest()
            positions[s["id"]] = [round(h[k] / 127.5 - 1, 3) for k in range(3)]
    return positions


# =============================================================================================
# Le titre : monsieur ou madame, mémorisé entre les sessions
# =============================================================================================
def lire_titre(defaut: str = "monsieur") -> str:
    try:
        return json.loads(TITRE_FICHIER.read_text(encoding="utf-8")).get("titre", defaut)
    except Exception:
        return defaut


def ecrire_titre(titre: str):
    DOSSIER.mkdir(exist_ok=True)
    TITRE_FICHIER.write_text(json.dumps({"titre": titre, "depuis": time.time()}, ensure_ascii=False), encoding="utf-8")
