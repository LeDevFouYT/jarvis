"""Langue d'une phrase écrite (la parole, elle, est identifiée par Whisper).
Heuristique sans dépendance : mots très courants de chaque langue et lettres accentuées. Assez pour trancher
entre français et anglais sur une question de quelques mots ; en cas de doute, le français."""
import re
import unicodedata

from .config import CONFIG

_ANGLAIS = set("""the a an is are was were be been am i you he she it we they my your his her our their me him us them
what what's whats who whom where when why how which can could would should will shall do does did don't doesn't
didn't not no yes please thanks thank hello hi hey tell show open close find search play set turn give make let's
this that these those there here with without for from to of in on at by about into over under up down out time
today tomorrow weather now and or but if then than so just also too very much many some any all every one two
""".split())
_FRANCAIS = set("""le la les un une des du de d l est sont suis es êtes sommes était je tu il elle on nous vous ils elles
mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs moi toi lui eux quoi qui que qu où quand pourquoi
comment quel quelle quels quelles peux peut pouvez veux veut voulez fais fait faites dis dit dites ouvre ferme
cherche mets montre donne est-ce ce cette ces ça cela ici là avec sans pour par dans sur sous et ou mais si alors
donc aussi très beaucoup oui non merci bonjour bonsoir salut s'il plaît heure aujourd'hui demain maintenant pas ne
""".split())


def detecter_texte(texte: str) -> str:
    """« fr » ou « en » (ou la première langue autorisée si une seule est configurée)."""
    autorisees = CONFIG.get("oreilles", {}).get("langues", ["fr", "en"])
    if len(autorisees) == 1:
        return autorisees[0]
    t = texte.lower()
    if re.search(r"[éèêàùâîôûçœ]", t):
        return "fr"
    mots = re.findall(r"[a-z']+", unicodedata.normalize("NFKD", t))
    if not mots:
        return "fr"
    en = sum(1 for m in mots if m in _ANGLAIS)
    fr = sum(1 for m in mots if m in _FRANCAIS)
    return "en" if en >= 2 and en > fr * 1.5 and "en" in autorisees else "fr"
