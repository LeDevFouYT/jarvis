"""La vérification d'une réponse de Jarvis contre le JSON de faits, en trois contrôles.

1. Les chiffres (déterministe) : les nombres de la réponse sont relevés tels qu'on les écrit en français
   (« 12 345 », « 3,4 fois », « 45 % », « 1,2 million », « 12 k », « 18 h », « 7:30 ») et cherchés dans le JSON, à la
   précision où ils sont écrits. Les dates (« 15/09/2026 ») ne sont pas découpées en nombres. Absent = écart.
2. Le rattachement (déterministe) : chaque chiffre est rattaché au fait qui le contient ET qui partage le plus de mots
   avec la phrase. « moyenne » dans une phrase dont le fait dit « médiane » est signalé : le chiffre existe, le mot ment.
3. Les affirmations (cerveau, après la réponse, sans la retarder) : chaque phrase est confrontée aux faits et jugée
   exacte, inexacte ou invérifiable. Mesuré le 16/09 : tous les chiffres d'une réponse existaient, mais « la vidéo la
   plus vue (382 vues) publiée le mercredi à 20 h » assemblait trois faits différents ; seul ce contrôle le voit.

Rend les chiffres, les écarts, les alertes de rattachement et (plus tard) le jugement des phrases."""
import json
import re
import unicodedata

_DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_NOMBRE = re.compile(
    r"(?<![\w,./])(?P<nombre>\d{1,3}(?:[   ]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?P<duree>:\d{2})?"
    r"(?:\s?(?P<unite>millions?|milliards?|k\b|K\b|%|fois|h\b|heures?|min\b|minutes?|s\b|secondes?|vues|abonnés))?",
    re.IGNORECASE)
_MULTIPLICATEURS = {"million": 1e6, "millions": 1e6, "milliard": 1e9, "milliards": 1e9, "k": 1e3}
_VIDES = set("le la les un une des du de d l et ou a au aux en dans sur pour par avec que qui est sont ce cette ces "
             "vous votre vos tu ton ta tes il elle ils elles on se sa son ses plus moins pas ne".split())


def _valeur(brut: str) -> tuple[float, int]:
    """« 12 345 » -> (12345, 0) ; « 3,45 » -> (3.45, 2 décimales)."""
    brut = re.sub(r"[   ]", "", brut)
    if "," in brut or "." in brut:
        entier, _, decimales = brut.replace(",", ".").partition(".")
        return float(f"{entier}.{decimales}"), len(decimales)
    return float(brut), 0


def chiffres_cites(texte: str) -> list[dict]:
    texte = _DATE.sub(lambda m: "#" * len(m.group(0)), texte)          # une date n'est pas trois nombres
    cites = []
    for m in _NOMBRE.finditer(texte):
        valeur, decimales = _valeur(m.group("nombre"))
        unite = (m.group("unite") or "").lower()
        if m.group("duree"):
            valeur, decimales, unite = valeur * 60 + int(m.group("duree")[1:]), 0, "secondes"
        pas = 10 ** -decimales
        multiplicateur = _MULTIPLICATEURS.get(unite, 1)
        cites.append({"cite": m.group(0).strip(), "valeur": valeur * multiplicateur, "precision": pas * multiplicateur,
                      "unite": unite, "position": m.start()})
    return cites


def _mots(texte: str) -> set[str]:
    t = unicodedata.normalize("NFD", texte.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {m[:5] for m in re.findall(r"[a-z]{3,}", t) if m not in _VIDES}


def _nombres_du_json(faits: list[dict]) -> list[tuple[float, str]]:
    trouves = []

    def parcourir(x, fait_id):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            trouves.append((float(x), fait_id))
        elif isinstance(x, dict):
            for v in x.values():
                parcourir(v, fait_id)
        elif isinstance(x, (list, tuple)):
            for v in x:
                parcourir(v, fait_id)

    for f in faits:
        parcourir(f.get("valeurs", {}), f["id"])
        for c in chiffres_cites(f.get("texte", "")):
            trouves.append((c["valeur"], f["id"]))
    return trouves


def _correspond(cite: dict, valeur: float) -> bool:
    demi = cite["precision"] / 2
    if cite["precision"] >= 1 and cite["unite"] not in ("million", "millions", "milliard", "milliards", "k"):
        if abs(cite["valeur"] - valeur) < 1e-6:
            return True
        # un entier cité peut être l'arrondi d'une valeur du JSON (médiane 12,5 -> « 12 » ou « 13 ») : à 0,5 près
        return abs(cite["valeur"] - valeur) <= 0.5 + 1e-9 and valeur != int(valeur)
    return abs(cite["valeur"] - valeur) <= demi + 1e-9


def phrases(texte: str) -> list[tuple[int, int, str]]:
    """(début, fin, phrase) : on coupe après . ! ? suivis d'un espace, sans couper « 3,5 » ni « 12.4 »."""
    morceaux, debut = [], 0
    for m in re.finditer(r"[.!?]+(?=\s|$)", texte):
        morceaux.append((debut, m.end(), texte[debut:m.end()].strip()))
        debut = m.end()
    if texte[debut:].strip():
        morceaux.append((debut, len(texte), texte[debut:].strip()))
    return [p for p in morceaux if p[2]]


def verifier(reponse: str, faits: list[dict]) -> dict:
    nombres = _nombres_du_json(faits)
    par_id = {f["id"]: f for f in faits}
    decoupe = phrases(reponse)
    lignes, ecarts, alertes = [], [], []
    for c in chiffres_cites(reponse):
        candidats = list(dict.fromkeys(fid for v, fid in nombres if _correspond(c, v)))
        if not candidats and c["unite"] == "%":
            candidats = list(dict.fromkeys(fid for v, fid in nombres if 0 < v <= 1 and _correspond(c, v * 100)))
        phrase = next((p for d, fin, p in decoupe if d <= c["position"] < fin), reponse)
        mots = _mots(phrase)
        # le fait qui contient ce chiffre et parle de la même chose que la phrase
        fait = max(candidats, key=lambda fid: len(mots & _mots(par_id[fid]["texte"] + " " + par_id[fid]["sujet"])), default=None)
        ligne = {"cite": c["cite"], "valeur": c["valeur"], "fait": fait, "trouve": fait is not None, "phrase": phrase}
        lignes.append(ligne)
        if fait is None:
            ecarts.append(ligne)
        elif "moyenne" in phrase.lower() and "médiane" in par_id[fait]["texte"].lower() and "moyenne" not in par_id[fait]["texte"].lower():
            alertes.append({"cite": c["cite"], "fait": fait, "raison": "la phrase dit « moyenne », le fait dit « médiane »"})
    return {"chiffres": lignes, "ecarts": ecarts, "alertes": alertes, "total": len(lignes), "trouves": len(lignes) - len(ecarts),
            "phrases_jugees": None}


SCHEMA_JUGEMENT = {"type": "object", "properties": {"phrases": {"type": "array", "items": {"type": "object", "properties": {
    "numero": {"type": "integer"}, "verdict": {"type": "string", "enum": ["exacte", "inexacte", "invérifiable"]},
    "faits": {"type": "array", "items": {"type": "string"}}, "explication": {"type": "string"}},
    "required": ["numero", "verdict", "faits", "explication"]}}}, "required": ["phrases"]}

CONSIGNE_JUGEMENT = ("Tu es un vérificateur strict. On te donne des FAITS numérotés (F1, F2…) et des PHRASES numérotées. Pour chaque "
                     "phrase, dis si elle est « exacte » (tout ce qu'elle affirme est écrit dans les faits, avec les mêmes chiffres "
                     "rattachés aux mêmes choses), « inexacte » (un chiffre, un jour, une heure, un mot comme médiane/moyenne ou un "
                     "lien entre deux faits ne correspond pas) ou « invérifiable » (rien dans les faits ne permet de trancher). "
                     "Cite les faits utilisés et explique en une phrase courte, en français. Réponds en JSON.")


def juger_phrases(reponse: str, faits: list[dict]) -> list[dict]:
    """Le troisième contrôle, par le cerveau : chaque phrase de la réponse confrontée aux faits."""
    from ..cerveau import CERVEAU
    decoupe = [p for _, _, p in phrases(reponse)]
    if not decoupe:
        return []
    texte = ("FAITS :\n" + "\n".join(f"{f['id']} {f['texte']}" for f in faits)
             + "\n\nPHRASES :\n" + "\n".join(f"[{i}] {p}" for i, p in enumerate(decoupe, 1)))
    brut = json.loads(CERVEAU.generer(CONSIGNE_JUGEMENT, texte, delai=120, format=SCHEMA_JUGEMENT))
    connus = {f["id"] for f in faits}
    jugees = []
    for j in brut.get("phrases", []):
        i = j.get("numero")
        if isinstance(i, int) and 1 <= i <= len(decoupe) and j.get("verdict") in ("exacte", "inexacte", "invérifiable"):
            jugees.append({"phrase": decoupe[i - 1], "verdict": j["verdict"], "faits": [x for x in j.get("faits", []) if x in connus],
                           "explication": str(j.get("explication", ""))[:200]})
    return jugees


def panneau(resultat: dict, faits: list[dict]):
    """Le panneau du HUD : les écarts d'abord, puis les phrases inexactes, les alertes, et chaque chiffre retrouvé."""
    from ..outils import panneaux
    textes = {f["id"]: f["texte"] for f in faits}
    elements = [{"titre": f"✗ « {l['cite']} » absent du JSON de faits", "detail": l["phrase"][:140], "meta": "écart"}
                for l in resultat["ecarts"]]
    jugees = resultat.get("phrases_jugees") or []
    elements += [{"titre": f"✗ phrase inexacte : « {j['phrase'][:90]} »", "detail": f"{', '.join(j['faits'])} · {j['explication']}", "meta": "inexacte"}
                 for j in jugees if j["verdict"] == "inexacte"]
    elements += [{"titre": f"⚠ « {a['cite']} » : {a['raison']}", "detail": textes.get(a["fait"], "")[:140], "meta": a["fait"]}
                 for a in resultat.get("alertes", [])]
    elements += [{"titre": f"✓ « {l['cite']} »", "detail": f"{l['fait']} · {textes.get(l['fait'], '')[:140]}", "meta": l["fait"]}
                 for l in resultat["chiffres"] if l["trouve"]]
    inexactes = sum(j["verdict"] == "inexacte" for j in jugees)
    titre = f"Vérification · {resultat['trouves']}/{resultat['total']} chiffres trouvés"
    titre += f" · {len(resultat['ecarts'])} écart{'s' if len(resultat['ecarts']) > 1 else ''}" if resultat["ecarts"] else " · aucun écart"
    if resultat.get("phrases_jugees") is None:
        titre += " · phrases en cours de jugement"
    else:
        titre += f" · {inexactes} phrase{'s' if inexactes > 1 else ''} inexacte{'s' if inexactes > 1 else ''}" if inexactes else " · phrases exactes"
    panneaux.liste(titre, elements, vide="Aucun chiffre cité dans la réponse.", cle="verification")
