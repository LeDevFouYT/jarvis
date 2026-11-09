"""Le tournoi (vidéo 5) : trois profils du même Jarvis s'affrontent, le joueur juge et élimine à la voix.

« Lance le tournoi » -> les trois premiers profils (Nova, Atlas, Pixel par défaut) entrent en lice. Puis :
« épreuve suivante », « plaidoiries », « j'élimine Nova », « fin du tournoi ». Le HUD montre trois colonnes aux
couleurs de leurs armures, prénoms énormes (événement `tournoi`).

- Même cerveau (qwen3:14b), mêmes outils, mêmes yeux : seuls le prénom, la voix et la personnalité changent. Chaque
  candidat parle à son tour ; il entend ce que les autres viennent de dire (le journal de la manche lui est donné).
- Les voix Qwen des candidats sont chargées ensemble dans un seul modèle (`MAJORDOME.regler_voix_en_plus`) : aucun
  rechargement quand l'un répond à l'autre. Une voix « Kokoro » parle sur le processeur.
- Rien n'est truqué : les critères de chaque épreuve sont dits avant, les résultats bruts (temps, réponses, images,
  sculptures) vont dans workspace/mesures/tournoi.json (clé « manches »). Le cerveau ne décide jamais du gagnant.
- Un seul gros modèle sur la carte : les dessins et les sculptures prennent la carte (le cerveau et la voix la
  rendent, puis reviennent), comme partout ailleurs dans Jarvis.
"""
import json
import shutil
import threading
import time
from pathlib import Path

from . import personnalites, profils, voix_creees
from .config import RACINE

MESURES = RACINE / "workspace" / "mesures" / "tournoi.json"
COULEURS = {"jarvis": "#5fe3ff", "mark3": "#ff4234", "friday": "#b57bff", "ultron": "#c4161c"}

EPREUVES = [
    {"cle": "dossier", "titre": "Le dossier en bordel",
     "regle": "Quarante fichiers en vrac. Chacun dit où il range les trois plus bizarres, puis range. Je juge l'explication."},
    {"cle": "miniature", "titre": "La miniature de cette vidéo",
     "regle": "Chacun invente la miniature de cette vidéo et la dessine. Je choisis la meilleure image."},
    {"cle": "devine", "titre": "Devine ce que je fais",
     "regle": "Tous regardent mon écran avec les mêmes yeux, et chacun parie sur ce que je fais. Le plus juste gagne."},
    {"cle": "finale", "titre": "Finale : sculpte-moi un dragon",
     "regle": "Les deux finalistes décrivent leur dragon, puis le sculptent en 3D. Le survivant est désigné à la fin."},
]

CONSIGNE_CANDIDAT = (
    "Tu es {prenom}, l'un des trois candidats d'un tournoi entre trois assistants vocaux construits sur le même logiciel "
    "(tes adversaires : {adversaires}). Celui qui organise le tournoi, et qui élimine, est {titre}. {ton} "
    "Tu parles à l'oral : une ou deux phrases courtes, jamais de liste, jamais d'emoji. Tu peux taquiner tes adversaires "
    "sur ce qu'ils viennent de dire, jamais méchamment. Tu ne mens jamais sur un résultat : les faits qu'on te donne sont "
    "vrais, tu ne les changes pas et tu n'inventes rien qui n'y est pas (aucun nom de dossier, aucun chiffre). "
    "Tu ne reprends JAMAIS une phrase ni une idée d'un adversaire et tu ne dis jamais « comme X l'a dit » : ton avis est "
    "le tien, différent du leur, et tu ne te répètes pas non plus. Rappel : {rappel}"
)


def _mots(texte: str) -> list[str]:
    import re
    return re.findall(r"\w+", texte.lower())


def copie_de(texte: str, deja: list[str], n: int = 6) -> str | None:
    """Le passage de `texte` qui reprend `n` mots d'affilée d'une réplique déjà dite, ou None."""
    m = _mots(texte)
    morceaux = {" ".join(m[k:k + n]) for k in range(len(m) - n + 1)}
    for d in deja:
        md = _mots(d)
        commun = morceaux & {" ".join(md[k:k + n]) for k in range(len(md) - n + 1)}
        if commun:
            return sorted(commun, key=len)[-1]
    return None


def limiter(texte: str, phrases_max: int) -> str:
    """Pas de monologue : vu le 29/10, une explication « en une ou deux phrases » en faisait seize."""
    import re
    # une fin de phrase est suivie d'un espace : « export_inconnu.xyz » ne coupe pas la phrase en deux ; et « … » ne
    # finit une phrase que devant une majuscule (vu le 07/11 : « Euh… je… » était coupé en « Euh… je… » tout court)
    phrases = re.findall(r".+?(?:[.!?]+(?=\s|$)|…+(?=\s+[A-ZÀ-Ý«\"]|\s*$)|$)", texte.strip())
    return " ".join(p.strip() for p in phrases[:phrases_max] if p.strip()).strip() or texte


def destinations_fausses(texte: str, destinations: dict[str, str]) -> str | None:
    """Les dossiers annoncés pour chaque fichier cité, comparés aux vrais. Vu en démo le 29/10 : « export_inconnu.xyz
    -> Archives » alors qu'il était allé dans Autres. Pour chaque fichier nommé, le premier dossier cité après lui (avant
    le fichier suivant) doit être le sien."""
    from .outils import ranger
    familles = list(ranger.FAMILLES) + ["Autres"]
    t = texte.lower()
    positions = sorted((t.find(n.lower()), n) for n in destinations if n.lower() in t)
    erreurs = []
    for k, (debut, nom) in enumerate(positions):
        fin = positions[k + 1][0] if k + 1 < len(positions) else len(t)
        morceau = t[debut + len(nom):fin]
        cites = sorted((morceau.find(f.lower()), f) for f in familles if f.lower() in morceau)
        vrai = destinations[nom].split("/")[0]
        if cites and cites[0][1] != vrai:
            erreurs.append(f"{nom} est allé dans {destinations[nom]}, pas dans {cites[0][1]}")
    return "; ".join(erreurs) or None


def fichiers_inventes(texte: str, destinations: dict[str, str]) -> str | None:
    """Un fichier ou un dossier cité qui n'existe pas, et les destinations fausses. Vu au test du 29/10 : en plaidoirie,
    « log_tournai.txt est dans Logs/2026-07 », « configuration_jeu.cfg est dans Jeux/2026-04 » : rien de tout ça
    n'existait."""
    import re
    from .outils import ranger
    familles = {f.lower() for f in ranger.FAMILLES} | {"autres"}
    connus = {n.lower() for n in destinations}
    erreurs = [f"le fichier {f} n'existe pas" for f in re.findall(r"\b[\w-]+\.[a-z0-9]{1,5}\b", texte, re.IGNORECASE)
               if f.lower() not in connus and not re.fullmatch(r"\d+\.\d+", f)]
    erreurs += [f"il n'y a pas de dossier {d}" for d in re.findall(r"\b([A-Za-zÀ-ÿ0-9]+)/\d{4}-\d{2}\b", texte)
                if d.lower() not in familles]
    faux = destinations_fausses(texte, destinations)
    return "; ".join(erreurs + ([faux] if faux else [])) or None


def attendre_la_voix(delai: float = 120):
    """Les répliques en file sont dites AVANT que la voix rende la carte : vu en démo le 29/10, la voix était arrêtée
    au milieu de la description d'un dragon, qui repartait en Kokoro (« voix du majordome en échec »)."""
    from . import voix
    voix.VOIX.attendre(delai)


def _ecrire_mesures(manche: dict):
    MESURES.parent.mkdir(parents=True, exist_ok=True)
    tout = json.loads(MESURES.read_text(encoding="utf-8")) if MESURES.exists() else {}
    tout.setdefault("manches", []).append(manche)
    MESURES.write_text(json.dumps(tout, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Tournoi:
    """`cerveau` : CERVEAU (generer) ; `dire(texte, moteur)` : la voix ; `emettre(evt)` : le HUD. Injectables pour le test."""

    def __init__(self, cerveau, dire, emettre, titre: str = "monsieur", noms: list[str] | None = None):
        tous = profils.lister()
        choisis = [profils.trouver(n) for n in noms] if noms else tous[:3]
        choisis = [p for p in choisis if p]
        if len(choisis) < 2:
            raise profils.Refus("il faut au moins deux profils (« enregistre ce profil sous le nom… »)")
        self.cerveau, self.dire_brut, self.emettre_brut, self.titre = cerveau, dire, emettre, titre
        self.candidats = [{**p, "en_lice": True, "derniere": "", "points": 0} for p in choisis]
        self.manche = -1
        self.journal: list[dict] = []
        self.destinations: dict[str, str] = {}      # où sont allés les fichiers de l'épreuve du dossier (les faits)
        self.derniere: dict | None = None            # la dernière manche jouée (ses résultats bruts)
        self.verrou = threading.Lock()
        self.en_cours = None
        self.debut = time.time()
        self._charger_voix()

    # --- les voix ---
    def _charger_voix(self):
        from . import majordome
        refs = []
        for c in self.candidats:
            if c["voix"] != profils.KOKORO:
                v = voix_creees.trouver(c["voix"])
                if v:
                    refs.append(voix_creees.REF_MAJORDOME if v["slug"] == voix_creees.MAJORDOME
                                else voix_creees.DOSSIER / v["slug"] / "reference.wav")
        majordome.MAJORDOME.regler_voix_en_plus(refs)

    def moteur(self, c: dict) -> str:
        if c["voix"] == profils.KOKORO:
            return "local"
        v = voix_creees.trouver(c["voix"])
        return f"majordome:{v['slug']}" if v else "local"

    # --- le HUD et la parole ---
    def etat(self) -> dict:
        e = EPREUVES[self.manche] if 0 <= self.manche < len(EPREUVES) else None
        return {"type": "tournoi", "t": time.time(), "epreuve": e["titre"] if e else ("" if self.manche < 0 else "Terminé"),
                "regle": e["regle"] if e else "", "manche": self.manche + 1, "en_cours": self.en_cours,
                "candidats": [{"prenom": c["prenom"], "couleur": COULEURS.get(c["armure"], "#5fe3ff"), "en_lice": c["en_lice"],
                               "derniere": c["derniere"], "points": c["points"], "personnalite": c["personnalite"]}
                              for c in self.candidats]}

    def emettre(self):
        self.emettre_brut(self.etat())

    def parler(self, c: dict, texte: str, quoi: str = ""):
        texte = " ".join(texte.split())
        c["derniere"] = texte
        self.journal.append({"manche": self.manche + 1, "candidat": c["prenom"], "quoi": quoi, "texte": texte, "t": time.time()})
        self.emettre()
        self.dire_brut(texte, self.moteur(c))

    def en_lice(self) -> list[dict]:
        return [c for c in self.candidats if c["en_lice"]]

    def trouver(self, nom: str) -> dict | None:
        from .prenom import _normaliser
        n = _normaliser(nom)
        return next((c for c in self.candidats if _normaliser(c["prenom"]) == n or _normaliser(c["nom"]) == n), None)

    def faire_dire(self, c: dict, consigne_moment: str, faits: str = "", phrases_max: int = 2, verifier=None) -> str:
        """Ce que le candidat dit, dans son ton, en ayant entendu les autres (les six dernières répliques).
        `verifier(texte) -> erreur ou None` : un contrôle des faits ; une réplique fausse est refaite, la correction
        donnée au candidat."""
        p = personnalites.PERSONNALITES[c["personnalite"]]
        adversaires = ", ".join(x["prenom"] for x in self.candidats if x is not c)
        consigne = CONSIGNE_CANDIDAT.format(prenom=c["prenom"], adversaires=adversaires, titre=self.titre,
                                            ton=p["ton"].format(titre=self.titre), rappel=p["rappel"])
        entendu = "\n".join(f"{j['candidat']} : {j['texte']}" for j in self.journal[-6:])
        demande = (f"Ce qui vient d'être dit :\n{entendu or '(rien encore)'}\n\n" if entendu else "") \
            + (f"Faits vrais : {faits}\n\n" if faits else "") + consigne_moment
        from .depot import nettoyer
        # Relu comme la voix : vu le 29/10, malgré la consigne, un candidat reprenait l'explication entière d'un autre,
        # ou sa propre présentation en guise de plaidoirie. Une réplique qui reprend six mots d'affilée d'une réplique
        # déjà dite est refaite, en lui montrant la copie (deux fois au plus).
        for _ in range(3):
            # 180 s : le cerveau peut devoir se recharger (après les yeux, un dessin, une sculpture)
            texte = limiter(nettoyer(self.cerveau.generer(consigne, demande, temperature=0.8, rechauffer=False, delai=180))
                            .strip('"« »'), phrases_max)
            copie = copie_de(texte, [j["texte"] for j in self.journal])
            faux = verifier(texte) if verifier else None
            if not copie and not faux:
                return texte
            if copie:
                demande += (f"\n\nTa réponse reprenait mot pour mot « {copie} », déjà dit. Recommence avec tes propres mots, "
                            f"une idée à toi.")
            if faux:
                demande += f"\n\nTa réponse était fausse : {faux}. Recommence en disant la vérité."
        return texte

    def deja_cites(self, noms: list[str]) -> list[str]:
        """Les fichiers déjà cités dans cette manche (pour que chacun choisisse les siens)."""
        dits = " ".join(j["texte"] for j in self.journal if j["manche"] == self.manche + 1)
        return [n for n in noms if n in dits]

    # --- le déroulé ---
    def presenter(self):
        for c in self.en_lice():
            self.parler(c, self.faire_dire(c, "Présente-toi en une phrase, puis dis pourquoi tu vas gagner."), "présentation")

    def epreuve_suivante(self) -> str:
        with self.verrou:
            if self.en_cours:
                return f"L'épreuve « {self.en_cours} » n'est pas finie."
            self.manche += 1
            if self.manche >= len(EPREUVES):
                return "Toutes les épreuves sont passées : désignez le survivant."
            e = EPREUVES[self.manche]
            if e["cle"] == "finale" and len(self.en_lice()) > 2:
                self.manche -= 1
                return "La finale se joue à deux : éliminez d'abord un candidat."
            self.en_cours = e["titre"]
        self.emettre()
        threading.Thread(target=self._jouer, args=(e,), daemon=True, name="tournoi").start()
        return f"Épreuve {self.manche + 1} : {e['titre']}. {e['regle']}"

    def _jouer(self, e: dict):
        manche = {"epreuve": e["cle"], "titre": e["titre"], "debut": time.strftime("%Y-%m-%d %H:%M:%S"), "candidats": {}}
        self.derniere = manche                        # ce sur quoi portent les plaidoiries qui suivent
        try:
            getattr(self, f"_epreuve_{e['cle']}")(manche)
        except Exception as ex:                       # noqa: BLE001
            manche["erreur"] = f"{type(ex).__name__} : {ex}"
            self.emettre_brut({"type": "tournoi_erreur", "t": time.time(), "message": manche["erreur"]})
        finally:
            manche["duree_s"] = round(time.time() - time.mktime(time.strptime(manche["debut"], "%Y-%m-%d %H:%M:%S")), 1)
            _ecrire_mesures(manche)
            self.en_cours = None
            self.emettre()

    def _epreuve_dossier(self, manche: dict):
        from .outils import ranger
        ranger.creer_demo()
        noms = sorted(p.name for p in ranger.DEMO.iterdir() if p.is_file())
        for c in self.en_lice():
            dossier = ranger.DEMO / f"tournoi_{c['prenom'].lower()}"
            if dossier.exists():
                shutil.rmtree(dossier)
            dossier.mkdir()
            for n in noms:
                shutil.copy2(ranger.DEMO / n, dossier / n)
            # les vraies destinations, fichier par fichier : vu le 29/10, sans elles un candidat inventait un dossier
            # « Inconnus » et les deux autres le répétaient
            destinations = {s.name: f"{d.parent.parent.name}/{d.parent.name}" for s, d in ranger.plan(dossier)}
            t = time.time()
            r = ranger.ranger(dossier)
            duree = round(time.time() - t, 2)
            faits = (f"Tu viens de ranger le dossier en {duree} s : {r.get('deplaces', 0)} fichiers classés par type et par "
                     f"mois. Où chaque fichier est allé (dossier/mois) : "
                     + "; ".join(f"{n} -> {d}" for n, d in destinations.items()) + ".")
            cites = self.deja_cites(noms)
            texte = self.faire_dire(c, "Choisis UN ou deux fichiers qui te semblent bizarres"
                                       + (f", mais pas ceux déjà cités ({', '.join(cites)})" if cites else "")
                                       + ", dis dans quel dossier ils sont VRAIMENT allés d'après les faits, et défends ton "
                                         "rangement.", faits, phrases_max=3,
                                    verifier=lambda texte: fichiers_inventes(texte, destinations))
            self.parler(c, texte, "dossier")
            manche["candidats"][c["prenom"]] = {"duree_s": duree, "deplaces": r.get("deplaces", 0), "dit": texte}
            manche["destinations"] = destinations           # pour vérifier après coup ce qui a été dit
            self.destinations = destinations

    def _epreuve_miniature(self, manche: dict):
        from . import carte, majordome
        from .outils import generer_image, panneaux
        idees = {}
        for c in self.en_lice():
            idee = self.faire_dire(c, "Décris en une phrase la miniature YouTube que tu dessinerais pour cette vidéo "
                                      "(un tournoi entre trois assistants IA). Une seule image, très lisible.")
            self.parler(c, idee, "idée")
            idees[c["prenom"]] = idee
        # en anglais pour le dessinateur, AVANT de lui rendre la carte (après, le cerveau est déchargé)
        anglais = {n: self.cerveau.generer("Transforme cette idée en une description d'image en ANGLAIS, détaillée, pour un "
                                           "générateur d'images. Aucun texte écrit dans l'image, aucune personne réelle, "
                                           "aucune marque. Réponds uniquement par la description.", idee, rechauffer=False)
                   for n, idee in idees.items()}
        images = []
        with carte.Occupation("tournoi : miniatures"):
            self.cerveau.decharger()
            attendre_la_voix()
            majordome.MAJORDOME.arreter()                 # la voix rend aussi sa place, elle revient après
            if not generer_image._lancer_comfyui():       # éteint au début du tournoi : on le démarre (jusqu'à 90 s)
                raise RuntimeError("ComfyUI ne démarre pas (comfyui.lanceur dans config.json)")
            generer_image.liberer_avant()
            for c in self.en_lice():
                t = time.time()
                chemin = generer_image.dessiner(f"YouTube thumbnail, bold and readable: {anglais[c['prenom']]}", "paysage")
                images.append({"url": f"/workspace/images/{Path(chemin).name}", "legende": c["prenom"]})
                manche["candidats"][c["prenom"]] = {"idee": idees[c["prenom"]], "image": str(chemin), "dessin_s": round(time.time() - t, 1)}
            generer_image.liberer_avant()
        self._rendre_la_voix()
        panneaux.images("Les trois miniatures", images)

    def _epreuve_devine(self, manche: dict):
        from . import carte, vision
        t = time.time()
        image, ecran = vision.capturer("principal")
        with carte.Occupation("tournoi : les yeux"):     # gemma3 à la place du cerveau, comme « regarde mon écran »
            self.cerveau.decharger()
            # la voix aussi : vu le 07/11, carte à 15,2 Go sur 16, gemma3 débordait en mémoire partagée (3 min 55, et
            # il voyait « Obsidian » sur un écran qui montrait Jarvis)
            attendre_la_voix()
            from . import majordome
            majordome.MAJORDOME.arreter()
            vu = vision.decrire_image("Décris précisément ce qu'on voit à l'écran : programmes, contenu, ce que fait la "
                                      "personne.", image)
        # la voix d'abord, le cerveau ensuite (voir _rendre_la_voix), AVANT les paris : vu le 29/10, il se rechargeait
        # pendant le premier et l'appel sautait à 60 s (la même famille de bug que le replay crypto du 20/10)
        self._rendre_la_voix()
        self.cerveau.charger()
        manche["vision"] = {"description": vu, "duree_s": round(time.time() - t, 1), "ecran": ecran}
        for c in self.en_lice():
            deja = [x["candidat"] for x in self.journal if x["quoi"] == "pari" and x["manche"] == self.manche + 1]
            pari = self.faire_dire(c, "Parie en une phrase sur ce que fait la personne en ce moment, d'après ce que tes "
                                      "yeux ont vu (les mêmes que tes adversaires)."
                                      + (" Ton pari doit être DIFFÉRENT de celui de " + ", ".join(deja)
                                         + " : un autre détail, une autre interprétation." if deja else ""),
                                   f"Ce que montre l'écran : {vu}")
            self.parler(c, pari, "pari")
            manche["candidats"][c["prenom"]] = {"pari": pari}

    def _epreuve_finale(self, manche: dict):
        from . import carte, majordome
        from .outils import hologramme
        descriptions = {}
        for c in self.en_lice():
            pris = [f"{n} : « {x} »" for n, x in descriptions.items()]
            d = self.faire_dire(c, "Décris en une phrase LE dragon que tu vas sculpter (matière, pose, décor, détail marquant)."
                                   + (" Déjà pris par ton adversaire — " + " ; ".join(pris) + ". Le tien est d'une AUTRE "
                                      "matière, dans une AUTRE pose et un AUTRE décor." if pris else ""))
            self.parler(c, d, "dragon")
            descriptions[c["prenom"]] = d
        with carte.Occupation("tournoi : sculptures"):
            self.cerveau.decharger()
            attendre_la_voix()
            majordome.MAJORDOME.arreter()
            from .outils import generer_image
            if not generer_image._lancer_comfyui():       # le dragon est d'abord dessiné, puis sculpté
                raise RuntimeError("ComfyUI ne démarre pas (comfyui.lanceur dans config.json)")
            for c in self.en_lice():
                t = time.time()
                chrono = {}
                # un nom par tournoi : vu le 07/11, « dragon de Nova » ressortait du cache la sculpture du 29/10 (0,0 s),
                # qui ne correspondait pas à la description du jour
                objet = f"dragon de {c['prenom']} {time.strftime('%Y%m%d %H%M')}"
                chemin = hologramme.sculpter(objet, descriptions[c["prenom"]], chrono)
                manche["candidats"][c["prenom"]] = {"description": descriptions[c["prenom"]], "glb": str(chemin),
                                                    "sculpture_s": round(time.time() - t, 1), "chrono": chrono}
                self.emettre_brut({"type": "hologramme", "t": time.time(), "objet": objet, "fichier": Path(chemin).name,
                                   "url": f"/workspace/hologrammes/{Path(chemin).name}", "cache": bool(chrono.get("cache")),
                                   "chrono": dict(chrono), "demande": descriptions[c["prenom"]]})
        self._rendre_la_voix()

    def _rendre_la_voix(self):
        """Après un travail lourd, la voix revient AVANT le cerveau : vu le 07/11, le cerveau reprenait la carte le
        premier, la voix ne trouvait plus que 2 023 Mo sur les 2 400 qu'il lui faut et les répliques partaient en Kokoro."""
        if all(c["voix"] == profils.KOKORO for c in self.en_lice()):
            return
        from . import majordome
        majordome.MAJORDOME.echec = (0.0, "")
        try:
            majordome.MAJORDOME.demarrer()
        except Exception as e:                        # noqa: BLE001
            self.emettre_brut({"type": "voix_repli", "t": time.time(), "raison": str(e)})

    def faits_de_la_manche(self) -> tuple[str, str]:
        """(titre, faits) de l'épreuve qui vient de se jouer. Vu à la démo du 07/11 : les plaidoiries ne recevaient que
        les faits du dossier, et après la miniature comme après la finale, les trois candidats replaidaient
        « assets_jeu.rar est dans Archives »."""
        m = self.derniere
        if not m:
            return "", ""
        cand = m.get("candidats", {})
        if m["epreuve"] == "dossier":
            faits = ("Où sont vraiment allés les fichiers du dossier : " + "; ".join(f"{n} -> {d}" for n, d in self.destinations.items())
                     + ". Ce que chacun a dit : " + " ; ".join(f"{n} : « {x.get('dit', '')} »" for n, x in cand.items())
                     + ". Ne cite aucun autre fichier ni aucun autre dossier.")
        elif m["epreuve"] == "miniature":
            faits = ("Les miniatures imaginées puis dessinées : " + " ; ".join(f"{n} : « {x.get('idee', '')} »" for n, x in cand.items())
                     + ". Tu ne sais pas encore laquelle a été choisie.")
        elif m["epreuve"] == "devine":
            faits = (f"Ce que les yeux ont vu à l'écran : {m.get('vision', {}).get('description', '')}. Les paris : "
                     + " ; ".join(f"{n} : « {x.get('pari', '')} »" for n, x in cand.items()) + ".")
        elif m["epreuve"] == "finale":
            faits = ("Les dragons décrits puis sculptés : "
                     + " ; ".join(f"{n} : « {x.get('description', '')} »" for n, x in cand.items()) + ".")
        else:
            faits = ""
        return m["titre"], faits

    def ancienne_epreuve(self, texte: str) -> str | None:
        """Une plaidoirie qui reparle d'un fichier du dossier alors que l'épreuve jouée est une autre."""
        t = texte.lower()
        cites = [n for n in self.destinations if n.lower() in t or n.lower().rsplit(".", 1)[0] in t]
        if cites:
            return (f"tu reparles de {', '.join(cites)}, un fichier de l'épreuve du dossier ; plaide sur l'épreuve qui vient "
                    f"de se jouer")
        return fichiers_inventes(texte, {})

    def plaidoiries(self):
        titre, faits = self.faits_de_la_manche()
        dossier = bool(self.derniere) and self.derniere["epreuve"] == "dossier"
        # sur le dossier : le contrôle des fichiers (sans lui, les plaidoiries en inventaient) ; ailleurs : aucun fichier
        verifier = (lambda t: fichiers_inventes(t, self.destinations)) if dossier else self.ancienne_epreuve
        sujet = (f"L'épreuve qui vient de se jouer : « {titre} ». Plaide sur CETTE épreuve (ce que tu y as fait, ce que "
                 f"les autres y ont fait), pas sur les précédentes. ") if titre else ""
        for c in self.en_lice():
            self.parler(c, self.faire_dire(c, sujet + "Tu as quinze secondes pour convaincre de ne PAS t'éliminer. Réponds à "
                                                      "ce que les autres viennent de dire.", faits, verifier=verifier),
                        "plaidoirie")

    def eliminer(self, nom: str) -> str:
        c = self.trouver(nom)
        if not c:
            return f"Il n'y a pas de candidat « {nom} »."
        if not c["en_lice"]:
            return f"{c['prenom']} est déjà éliminé."
        self.parler(c, self.faire_dire(c, "Tu viens d'être éliminé du tournoi. Dis au revoir en une phrase, dans ton style."),
                    "élimination")
        c["en_lice"] = False
        self.emettre()
        reste = self.en_lice()
        if len(reste) == 1:
            gagnant = reste[0]
            self.parler(gagnant, self.faire_dire(gagnant, "Tu as gagné le tournoi. Une phrase de victoire, dans ton style."),
                        "victoire")
            _ecrire_mesures({"epreuve": "fin", "gagnant": gagnant["prenom"], "journal": self.journal,
                             "duree_totale_s": round(time.time() - self.debut, 1)})
            return f"{c['prenom']} est éliminé. {gagnant['prenom']} gagne le tournoi."
        return f"{c['prenom']} est éliminé. Il en reste {len(reste)}."
