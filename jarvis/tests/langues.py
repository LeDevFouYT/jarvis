"""Test du pouvoir 07, langues : python -m jarvis.tests.langues
1. Whisper reconnaît la langue d'une phrase dite en anglais et d'une phrase dite en français ;
2. une question en anglais : le cerveau répond en anglais, chaque phrase part avec la voix anglaise (bm_george) ;
3. la même en français reste en français avec ff_siwis ; texte tapé : langue détectée sans Whisper."""
import re
import sys

from ._commun import Collecteur, Verifs, attendre, faux_haut_parleur, phrase_wav

faux_haut_parleur()

from .. import langue, oreilles, serveur, voix  # noqa: E402
from ..cerveau import CERVEAU  # noqa: E402


def main() -> int:
    v = Verifs("Pouvoir 07 · langues")
    en_wav, _ = phrase_wav("langue_anglais", [("Jarvis, what is the tallest mountain in the world, and where is it?", "am_michael", "en-us")])
    fr_wav, _ = phrase_wav("langue_francais", [("Jarvis,", "am_michael", "en-us"), ("quelle est la plus haute montagne du monde ?", "ff_siwis", "fr-fr")])
    texte_en, langue_en = oreilles.transcrire_detail(en_wav)
    texte_fr, langue_fr = oreilles.transcrire_detail(fr_wav)
    v.ok(langue_en == "en", "phrase dite en anglais : langue reconnue « en »", texte_en)
    v.ok(langue_fr == "fr", "phrase dite en français : langue reconnue « fr »", texte_fr)
    v.ok(langue.detecter_texte("What time is it in Tokyo?") == "en" and langue.detecter_texte("Quelle heure est-il à Tokyo ?") == "fr",
         "texte tapé : langue détectée sans Whisper")

    evts = Collecteur()
    serveur._brancher_evenements()
    voix.sur_evenement = lambda e: (evts(e), serveur.EMETTEUR.emettre(e))
    CERVEAU.charger()
    CERVEAU.oublier()
    question = oreilles.detacher_reveil(texte_en) or texte_en
    r = serveur._dialoguer(question, langue="en", source="texte")
    v.info(f"réponse : {r['reponse']}")
    francais = re.search(r"[éèêàùç]|\b(le|la|les|est|du|des|dans|et)\b", r["reponse"], re.IGNORECASE)
    v.ok(langue.detecter_texte(r["reponse"]) == "en" or not francais, "question en anglais : réponse en anglais", r["reponse"][:80])
    v.ok("everest" in r["reponse"].lower(), "et juste (Everest)")
    v.ok(attendre(lambda: evts.de_type("phrase"), 20), "la réponse est dite")
    voix.VOIX.attendre(60)
    phrases = [e for e in evts.de_type("phrase") if e["prise"] == r["prise"]]
    v.ok(phrases and all(p["langue"] == "en" and p["voix"] == "bm_george" for p in phrases),
         "chaque phrase avec la voix anglaise Kokoro (bm_george)", [(p["voix"], p["texte"][:30]) for p in phrases])

    CERVEAU.oublier()
    question_fr = oreilles.detacher_reveil(texte_fr) or texte_fr
    r = serveur._dialoguer(question_fr, langue="fr", source="texte")
    voix.VOIX.attendre(60)
    phrases = [e for e in evts.de_type("phrase") if e["prise"] == r["prise"]]
    v.ok(langue.detecter_texte(r["reponse"]) == "fr", "question en français : réponse en français", r["reponse"][:80])
    v.ok(phrases and all(p["voix"] == "ff_siwis" for p in phrases), "avec la voix française (ff_siwis)")
    CERVEAU.oublier()
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
