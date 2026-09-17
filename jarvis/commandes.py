"""Commandes vocales spéciales, traitées avant le cerveau (rapides, sans modèle).
  « Jarvis, éteins-toi »                   -> extinction : phrase d'au revoir puis arrêt propre
  « Jarvis, oublie tout »                  -> oublier : vide la conversation (les souvenirs de la session sont d'abord proposés)
  « Jarvis, silence »                      -> silence : la voix se tait jusqu'au prochain mot de réveil
  « appelle-moi madame / monsieur »        -> titre
  « qu'est-ce que tu sais de moi »         -> souvenirs_liste : les souvenirs, et la constellation dans le HUD
  « retiens que je préfère le thé »        -> retenir (argument : « je préfère le thé »)
  « oublie que j'aime le café »            -> oublier_souvenir (argument : « j'aime le café »)
  « passe en mode coach »                  -> personnalite (argument : coach, sarcastique ou majordome)
  « désactive la sentinelle » / « active » -> sentinelle (argument : off / on)
  « annule »                               -> annuler : défait le dernier rangement
  « oui » / « non », si une confirmation est en attente (fermer une fenêtre avec du travail) -> confirmer / refuser"""
import re
import unicodedata

COMMANDES = {
    "extinction": [r"\beteins?[- ]toi\b", r"\bextinction\b", r"\bva dormir\b", r"\barrete[- ]toi\b", r"\bferme[- ]toi\b"],
    "oublier": [r"\boublie tout\b", r"\boublie la conversation\b", r"\befface tout\b", r"\befface la conversation\b",
                r"\boublie ce qu'?on a dit\b"],
    "silence": [r"^(jarvis[,.]?\s*)?silence[.! ]*$", r"\btais[- ]toi\b", r"^(jarvis[,.]?\s*)?chut[.! ]*$"],
    "titre_madame": [r"\bappelle[- ]moi madame\b", r"\bje suis une femme\b", r"\bdis[- ]moi madame\b", r"\bc'?est madame\b"],
    "titre_monsieur": [r"\bappelle[- ]moi monsieur\b", r"\bje suis un homme\b", r"\bdis[- ]moi monsieur\b", r"\bc'?est monsieur\b"],
    "souvenirs_liste": [r"\bqu'?est[- ]ce que tu sais (de|sur) moi\b", r"\bque sais[- ]tu (de|sur) moi\b",
                        r"\bqu'?est[- ]ce que vous savez (de|sur) moi\b", r"\bce que tu sais de moi\b",
                        r"\btes souvenirs sur moi\b", r"\bwhat do you know about me\b", r"\bmontre[- ]moi tes souvenirs\b"],
    "annuler": [r"^(jarvis[,.]?\s*)?annule( le rangement| ca| ce rangement| le dernier rangement)?[.! ]*$",
                r"\bremets? (tout )?(comme avant|en place)\b", r"\bdefais le rangement\b"],
}

_RETENIR = re.compile(r"^(?:jarvis[,.]?\s*)?(?:retiens|retenez|souviens[- ]toi|souvenez[- ]vous|rappelle[- ]toi|"
                      r"n'?oublie pas|memorise|garde en memoire|note dans ta memoire)\s+(?:bien\s+)?"
                      r"(?:que\s+|qu'|le fait que\s+)(.+)$")
_OUBLIER_SOUVENIR = re.compile(r"^(?:jarvis[,.]?\s*)?(?:oublie|oubliez|efface de ta memoire)\s+"
                               r"(?:que\s+|qu'|le fait que\s+|ce que je t'?ai dit sur\s+|l'?histoire de\s+)(.+)$")
_PERSONNALITE = re.compile(r"\b(?:passe|passes|mets[- ]toi|bascule)\s+en\s+mode\s+(majordome|sarcastique|sarcasme|coach)\b"
                           r"|^(?:jarvis[,.]?\s*)?mode\s+(majordome|sarcastique|coach)[.! ]*$"
                           r"|\bsois\s+(?:mon\s+)?(coach|sarcastique|majordome)\b")
_SENTINELLE = re.compile(r"\b(desactive|coupe|arrete|eteins|active|allume|reactive|remets?)\s+(?:la\s+)?sentinelle\b")
_OUI = re.compile(r"^(?:jarvis[,.]?\s*)?(oui|ouais|yes|vas[- ]y|confirme|je confirme|c'?est bon|fais[- ]le|d'?accord|ok)\b.{0,30}$")
_NON = re.compile(r"^(?:jarvis[,.]?\s*)?(non|no|laisse tomber|annule|surtout pas|pas du tout|n'?en fais rien)\b.{0,30}$")


def _normaliser(t: str) -> str:
    t = t.replace("’", "'")
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _texte_original(texte: str, extrait_normalise: str) -> str:
    """La partie extraite, reprise dans le texte d'origine (accents compris) : on compte les caractères de base."""
    brut = re.sub(r"\s+", " ", texte.replace("’", "'")).strip()
    n = _normaliser(brut)
    debut = n.rfind(extrait_normalise)
    if debut < 0:
        return extrait_normalise
    # position équivalente dans le texte d'origine : même nombre de caractères non diacritiques avant
    compte, i = 0, 0
    for i, c in enumerate(brut):
        if compte == debut:
            break
        if unicodedata.category(unicodedata.normalize("NFD", c)[0]) != "Mn":
            compte += 1
    return brut[i:].strip(" .!?")


def reconnaitre(texte: str) -> str | None:
    return analyser(texte)[0]


def analyser(texte: str, confirmation_en_attente: bool = False) -> tuple[str | None, str]:
    """(commande, argument) ; (None, "") si la phrase est pour le cerveau."""
    n = _normaliser(texte)
    if confirmation_en_attente:
        if _OUI.match(n):
            return "confirmer", ""
        if _NON.match(n):
            return "refuser", ""
    m = _RETENIR.match(n)
    if m:
        return "retenir", _texte_original(texte, m.group(1))
    m = _OUBLIER_SOUVENIR.match(n)
    if m and not re.match(r"^(tout|la conversation|ce qu'?on a dit)\b", m.group(1)):
        return "oublier_souvenir", _texte_original(texte, m.group(1))
    m = _PERSONNALITE.search(n)
    if m and len(n) <= 80:
        nom = next(g for g in m.groups() if g)
        return "personnalite", {"sarcasme": "sarcastique"}.get(nom, nom)
    m = _SENTINELLE.search(n)
    if m and len(n) <= 60:
        return "sentinelle", "off" if m.group(1) in ("desactive", "coupe", "arrete", "eteins") else "on"
    if len(n) > 60:      # une commande est courte ; une longue phrase qui contient « silence » n'en est pas une
        return None, ""
    for nom, motifs in COMMANDES.items():
        if any(re.search(motif, n) for motif in motifs):
            return nom, ""
    return None, ""
