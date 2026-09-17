"""Test des pouvoirs 17 à 19, il gère la chaîne : python -m jarvis.tests.youtube
Sur un faux YouTube local aux chiffres connus d'avance (tests/faux_youtube.py) : aucune vraie clé, aucun quota réel.
La base (cache, quota, relevés) et le fichier OAuth sont dans un dossier temporaire.

17 accès : la clé testée, le coût de chaque appel dans le quota du jour, le cache qui évite de redemander, la limite
   qui refuse avant Google, une sortie Internet comptée par appel réel ; OAuth « application de bureau » importé,
   connexion par la boucle locale (le navigateur est simulé), jeton renouvelé.
18 analyste : médiane, exceptions, durées, heures, motifs de titres, rétention et trafic avec OAuth — comparés aux
   valeurs attendues ; commentaires regroupés par thème et comptés ; briefing (premier relevé, puis écarts).
19 vérification : le vrai cerveau commente l'analyse ; chaque chiffre de sa réponse est cherché dans le JSON de faits,
   et les écarts sont affichés. Une réponse fabriquée avec un chiffre inventé doit être prise en défaut."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from ._commun import Verifs, faux_haut_parleur

faux_haut_parleur()

from .. import compteur  # noqa: E402
from ..config import CONFIG, SECRETS  # noqa: E402
from ..youtube import acces, analyste, briefing, commentaires, oauth, verification  # noqa: E402
from .faux_youtube import CHAINE, FauxYouTube  # noqa: E402


def main() -> int:
    v = Verifs("Pouvoirs 17 à 19 · il gère la chaîne (YouTube)")
    faux = FauxYouTube()
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_youtube_"))
    os.environ.update(JARVIS_YOUTUBE_API=faux.url, JARVIS_YOUTUBE_ANALYTICS=f"{faux.url}/analytics", JARVIS_GOOGLE_TOKEN_URI=f"{faux.url}/token")
    ancienne_cle, ancienne_config = SECRETS.get("YOUTUBE_API_KEY"), dict(CONFIG.get("youtube", {}))
    acces.CACHE, oauth.FICHIER = dossier / "youtube.sqlite", dossier / "oauth.json"
    try:
        # ------------------------------------------------------------------ 17 · accès, quota, cache
        SECRETS.pop("YOUTUBE_API_KEY", None)
        v.ok(not acces.tester()["ok"], "sans clé : le test le dit")
        SECRETS["YOUTUBE_API_KEY"] = "MAUVAISE"
        v.ok("refuse" in acces.tester()["message"], "clé refusée par Google : message clair", acces.tester()["message"])
        SECRETS["YOUTUBE_API_KEY"] = "CLE-ESSAI"
        t = acces.tester()
        v.ok(t["ok"] and "sur 10000" in t["message"], "bonne clé : le test répond, avec le quota du jour", t["message"])
        sorties = compteur.etat()["total"]
        appels = len(faux.appels)
        a = analyste.analyser("@ateliertest")
        n_appels = len(faux.appels) - appels
        v.ok(n_appels == 3, "analyse par @handle : 3 appels (chaîne, liste des vidéos, vidéos)", faux.appels[appels:])
        v.ok(compteur.etat()["total"] - sorties == n_appels, "chaque appel réel compte une sortie Internet", compteur.etat()["total"] - sorties)
        q1 = acces.quota()["utilise"]
        analyste.analyser("@ateliertest")
        v.ok(len(faux.appels) - appels == 3 and acces.quota()["utilise"] == q1, "la même analyse repart du cache : ni appel ni quota")
        acces.appeler("search", {"part": "snippet", "type": "channel", "q": "atelier"}, ttl=0)
        v.ok(acces.quota()["utilise"] == q1 + 100, "une recherche coûte 100 unités", acces.quota()["utilise"] - q1)
        CONFIG["youtube"]["quota_jour"] = acces.quota()["utilise"] + 50
        try:
            acces.appeler("search", {"part": "snippet", "q": "encore"}, ttl=0)
            v.ok(False, "au-delà de la limite réglée, Jarvis refuse avant d'appeler Google")
        except acces.ErreurYouTube as e:
            v.ok("quota" in str(e), "au-delà de la limite réglée, Jarvis refuse avant d'appeler Google", str(e))
        CONFIG["youtube"].pop("quota_jour", None)

        # ------------------------------------------------------------------ 18 · l'analyste, chiffres attendus
        valeurs = {k: val for f in a["faits"] for k, val in f["valeurs"].items()}
        v.ok(a["mediane"] == 2750, "médiane des vues : 2 750", a["mediane"])
        exc = [x for x in a["faits"] if x["sujet"] == "exceptions"][0]
        v.ok(exc["valeurs"]["nombre"] == 3 and exc["valeurs"]["vues_1"] == 15000 and exc["valeurs"]["ratio_1"] == 5.5,
             "3 vidéos au-dessus de 3 fois la médiane, la première à 15 000 vues (5,5 fois)", exc["texte"])
        v.ok(valeurs.get("courtes") == 10 and valeurs.get("longues") == 20, "10 vidéos courtes, 20 longues", (valeurs.get("courtes"), valeurs.get("longues")))
        v.ok(valeurs.get("heure_frequente") == 18 and valeurs.get("videos_a_cette_heure") == 27, "heure la plus fréquente : 18 h (27 vidéos), à l'heure de Paris")
        v.ok(valeurs.get("question_titres") == 3 and valeurs.get("question_mediane_avec") == 12000 and valeurs.get("question_mediane_sans") == 2600,
             "titres avec « ? » : 3, médiane 12 000 contre 2 600", {k: valeurs.get(k) for k in ("question_titres", "question_mediane_avec", "question_mediane_sans")})
        from datetime import datetime
        from .faux_youtube import videos as videos_du_faux
        samedis = sum(datetime.fromisoformat(x["publiee"].replace("Z", "+00:00")).astimezone(acces.PARIS).weekday() == 5 for x in videos_du_faux())
        v.ok(valeurs.get("samedi_videos") == samedis, f"{samedis} vidéos publiées le samedi, jour compté à l'heure de Paris", valeurs.get("samedi_videos"))
        v.ok(all(f["source"] and f["id"].startswith("F") for f in a["faits"]) and len(a["faits"]) >= 8, "chaque fait a un identifiant et une source", len(a["faits"]))
        v.ok(a["prive"].startswith("non connecté"), "sans OAuth : statistiques publiques seulement", a["prive"])
        v.info("faits : " + " | ".join(f"{x['id']} {x['texte']}" for x in a["faits"]))

        # ------------------------------------------------------------------ 17 · OAuth application de bureau
        v.ok(not oauth.importer_client(json.dumps({"web": {"client_id": "x"}}))["ok"], "un identifiant « web » est refusé : il faut « application de bureau »")
        v.ok(oauth.importer_client(json.dumps({"installed": {"client_id": "id-essai", "client_secret": "secret-essai",
                                                               "auth_uri": f"{faux.url}/auth", "token_uri": f"{faux.url}/token"}}))["ok"],
             "fichier OAuth « application de bureau » importé")

        def navigateur(url):                         # la personne accepte : Google renvoie le code à la boucle locale
            q = {k: val[0] for k, val in parse_qs(urlparse(url).query).items()}
            assert q["code_challenge_method"] == "S256" and "yt-analytics.readonly" in q["scope"]
            requests.get(q["redirect_uri"], params={"code": "code-essai", "state": q["state"]}, timeout=5)

        oauth.connecter(ouvrir=navigateur, delai=10)
        fin = time.time() + 10
        while oauth.etat()["en_cours"] and time.time() < fin:
            time.sleep(0.1)
        v.ok(oauth.etat()["connecte"] and oauth.etat()["compte"] == "Atelier Test", "connexion par le navigateur : compte connecté", oauth.etat()["message"])
        d = json.loads(oauth.FICHIER.read_text())
        d["jetons"]["expire"] = 0
        oauth.FICHIER.write_text(json.dumps(d))
        v.ok(oauth.jeton_acces() == "acces-essai", "jeton expiré : renouvelé automatiquement")
        acces.CACHE.unlink()
        a2 = analyste.analyser("@ateliertest")
        retention = [x for x in a2["faits"] if x["sujet"] == "rétention"]
        trafic = [x for x in a2["faits"] if x["sujet"] == "trafic"]
        v.ok(retention and retention[0]["valeurs"]["chute_1_points"] == 14, "rétention : la plus forte chute (14 points) horodatée", retention[0]["texte"] if retention else "")
        v.ok(trafic and trafic[0]["valeurs"]["source_1_pourcent"] == 60, "sources de trafic : 60 % par la recherche", trafic[0]["texte"] if trafic else "")

        # ------------------------------------------------------------------ commentaires
        c = commentaires.analyser("vid00000001")
        themes = {t["theme"]: t["nombre"] for t in c["themes"]}
        v.info(f"thèmes : {themes}")
        v.ok(c["lus"] == 12 and c["demandes"] == 8, "12 commentaires lus, 8 qui demandent quelque chose", (c["lus"], c["demandes"]))
        installation = max((n for th, n in themes.items() if "install" in th.lower() or "tuto" in th.lower()), default=0)
        linux = max((n for th, n in themes.items() if "linux" in th.lower()), default=0)
        v.ok(4 <= installation <= 5 and 2 <= linux <= 3 and sum(themes.values()) <= 8,
             "regroupés et comptés : tutoriel d'installation 5, Linux 3 (à un près, le cerveau range)", themes)

        # ------------------------------------------------------------------ briefing
        CONFIG["youtube"].update(ma_chaine="@ateliertest", concurrents=["@ateliertest"])
        b1 = briefing.briefing()
        textes = " | ".join(x["texte"] for x in b1["faits"])
        v.info(f"briefing 1 : {textes}")
        v.ok(any("Premier relevé" in x["texte"] for x in b1["faits"]), "premier briefing : premier relevé, écarts au prochain")
        v.ok(any(x["sujet"] == "commentaires" and x["valeurs"].get("demandes_nouvelles") == 8 for x in b1["faits"]), "8 nouveaux commentaires qui demandent quelque chose")
        v.ok(any(x["sujet"] == "rappels" for x in b1["faits"]) and any(x["sujet"] == "machine" for x in b1["faits"]), "rappels et état de la machine")
        v.ok(not any(m in textes.lower() for m in ("météo", "température extérieure", "pluie", "soleil")), "ni météo ni lieu")
        # un relevé d'hier, 500 vues plus bas sur chaque vidéo suivie
        hier = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
        aujourd = acces.releve(f"chaine:{CHAINE}", acces.aujourdhui())
        acces.releve(f"chaine:{CHAINE}", hier, {**aujourd, "abonnes": 4150, "vues": {k: val - 500 for k, val in aujourd["vues"].items()}})
        with acces.connexion() as base:
            base.execute("DELETE FROM releves WHERE jour = ?", (acces.aujourdhui(),))
        b2 = briefing.briefing()
        v.info("briefing 2 : " + " | ".join(x["texte"] for x in b2["faits"]))
        v.ok(any(x["valeurs"].get("ecart_abonnes") == 50 for x in b2["faits"]), "le lendemain : +50 abonnés depuis le relevé")
        v.ok(any(x["valeurs"].get("gain_total") == 7500 for x in b2["faits"]), "+7 500 vues sur les 15 vidéos suivies")
        v.ok(any(x["sujet"] == "commentaires" and x["valeurs"].get("demandes_nouvelles") == 0 for x in b2["faits"]),
             "les commentaires déjà montrés ne reviennent pas")

        # ------------------------------------------------------------------ 19 · vérification des chiffres
        fabrique = "La médiane est de 2 750 vues, la meilleure vidéo fait 15 000 vues, soit 5,5 fois la médiane, et 18 400 vues en moyenne."
        r = verification.verifier(fabrique, a["faits"])
        v.ok(r["total"] == 4 and [e["cite"] for e in r["ecarts"]] == ["18 400 vues"], "réponse fabriquée : le chiffre inventé est pris en défaut",
             [(l["cite"], l["fait"]) for l in r["chiffres"]])
        r = verification.verifier("La médiane est de 2 750 vues en moyenne.", a["faits"])
        v.ok(r["alertes"] and "moyenne" in r["alertes"][0]["raison"], "« 2 750 vues en moyenne » : le chiffre existe, le mot « moyenne » est signalé",
             r["alertes"])
        v.ok([c["cite"] for c in verification.chiffres_cites("publiée le 15/09/2026, 9 mots")] == ["9"], "une date n'est pas découpée en nombres")
        # le jugement des phrases par le cerveau : chaque chiffre existe, mais la phrase les assemble mal
        heure_top = next(x for x in a["faits"] if x["sujet"] == "vidéo la plus vue")["valeurs"]["heure"]
        fausse = f"La vidéo la plus vue fait 15 000 vues et a été publiée à 18 h. La médiane des vues est de 2 750."
        jugees = verification.juger_phrases(fausse, a["faits"])
        v.info(f"jugement : {jugees}")
        v.ok(heure_top == 10 and len(jugees) == 2 and jugees[0]["verdict"] == "inexacte" and jugees[1]["verdict"] == "exacte",
             "jugement des phrases : « 15 000 vues publiée à 18 h » inexacte (publiée à 10 h), la médiane exacte",
             [(j["verdict"], j["explication"]) for j in jugees])
        from .. import outils
        from ..cerveau import CERVEAU
        reponse = CERVEAU.repondre("Analyse la chaîne @ateliertest : qu'est-ce qui marche le mieux ?", journal=lambda n, res: None)
        faits = outils.youtube_chaine.faits()
        r = verification.verifier(reponse, faits)
        v.info(f"réponse du cerveau : {reponse}")
        for l in r["chiffres"]:
            v.info(f"  {'✓' if l['trouve'] else '✗'} « {l['cite']} » -> {l['fait'] or 'absent du JSON de faits'}")
        v.ok(r["total"] >= 3, "le cerveau cite des chiffres", r["total"])
        v.ok(not r["ecarts"], "chaque chiffre cité par le cerveau existe dans le JSON de faits", [e["cite"] for e in r["ecarts"]])
        jugees = verification.juger_phrases(reponse, faits)
        for j in jugees:
            v.info(f"  {j['verdict']} : « {j['phrase']} » ({', '.join(j['faits'])}) {j['explication']}")
        v.ok(jugees and not any(j["verdict"] == "inexacte" for j in jugees), "et aucune phrase du cerveau n'est jugée inexacte",
             [j["phrase"] for j in jugees if j["verdict"] == "inexacte"])
    finally:
        for cle in ("JARVIS_YOUTUBE_API", "JARVIS_YOUTUBE_ANALYTICS", "JARVIS_GOOGLE_TOKEN_URI"):
            os.environ.pop(cle, None)
        if ancienne_cle is None:
            SECRETS.pop("YOUTUBE_API_KEY", None)
        else:
            SECRETS["YOUTUBE_API_KEY"] = ancienne_cle
        CONFIG["youtube"].clear()
        CONFIG["youtube"].update(ancienne_config)
        faux.arreter()
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
