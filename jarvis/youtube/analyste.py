"""L'analyste : des calculs Python sur les dernières vidéos d'une chaîne, rendus en JSON de faits sourcés.

Chaque fait a un identifiant (F1, F2…), une phrase, ses valeurs chiffrées et sa source. Le cerveau ne calcule
rien : il reçoit ce JSON et commente en citant un chiffre par affirmation ; verification.py contrôle ensuite que
chaque nombre de sa réponse existe dans le JSON.

Calculs : médiane des vues, vidéos au-dessus de trois fois la médiane, durées (et formats courts ≤ 3 min),
jours et heures de publication (heure de Paris), rythme de publication, motifs de titres (longueur, chiffre,
question, exclamation, mot en capitales, parenthèses, emoji). Avec le compte connecté par OAuth et si la chaîne
est la sienne : rétention des dernières vidéos avec leurs plus fortes chutes horodatées, sources de trafic."""
import re
import statistics
from datetime import datetime, timedelta

from . import acces, donnees
from .acces import PARIS

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
TRANCHES = [("la nuit (0 h-6 h)", 0, 6), ("le matin (6 h-12 h)", 6, 12), ("l'après-midi (12 h-18 h)", 12, 18), ("le soir (18 h-24 h)", 18, 24)]
COURTE_S = 180
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def nombre_fr(x, decimales: int = 0) -> str:
    """12345 -> « 12 345 » ; 3.456 -> « 3,5 » : la forme que Jarvis cite, et que la vérification sait relire."""
    if x is None:
        return "?"
    if decimales == 0:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def _mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600} h {s % 3600 // 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _motifs(titre: str) -> dict:
    mots = titre.split()
    return {"chiffre": bool(re.search(r"\d", titre)), "question": "?" in titre, "exclamation": "!" in titre,
            "capitales": any(len(re.sub(r"\W", "", m)) >= 3 and re.sub(r"\W", "", m).isupper() for m in mots),
            "parentheses": bool(re.search(r"[()\[\]]", titre)), "emoji": bool(_EMOJI.search(titre)), "mots": len(mots)}


LIBELLES_MOTIFS = {"chiffre": "un chiffre", "question": "un point d'interrogation", "exclamation": "un point d'exclamation",
                   "capitales": "un mot en capitales", "parentheses": "des parenthèses ou crochets", "emoji": "un emoji"}


class Faits:
    def __init__(self):
        self.liste: list[dict] = []

    def ajouter(self, sujet: str, texte: str, source: str, **valeurs) -> dict:
        f = {"id": f"F{len(self.liste) + 1}", "sujet": sujet, "texte": texte, "valeurs": valeurs, "source": source}
        self.liste.append(f)
        return f


def analyser(nom: str, n: int = 30) -> dict:
    ch = donnees.chaine(nom)
    videos = [v for v in donnees.videos_recentes(ch, n) if v.get("timestamp")]
    if not videos:
        raise acces.ErreurYouTube(f"aucune vidéo publique trouvée sur « {ch['titre'] or nom} »")
    src = "API YouTube Data v3 (videos.list)" if ch["source"] == "api" else "pages publiques YouTube lues par yt-dlp"
    periode = f"{len(videos)} dernières vidéos"
    f = Faits()
    vues = [v["vues"] for v in videos]
    mediane = statistics.median(vues)
    debut = datetime.fromtimestamp(min(v["timestamp"] for v in videos), PARIS)
    fin = datetime.fromtimestamp(max(v["timestamp"] for v in videos), PARIS)

    if ch.get("abonnes") is not None:
        f.ajouter("chaîne", f"{ch['titre']} compte {nombre_fr(ch['abonnes'])} abonnés.", "statistiques publiques de la chaîne",
                  abonnes=ch["abonnes"])
    f.ajouter("période", f"Analyse des {len(videos)} dernières vidéos, publiées du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}.", src,
              videos=len(videos), jours=(fin - debut).days)
    f.ajouter("vues", f"Médiane des vues : {nombre_fr(mediane)} ; total {nombre_fr(sum(vues))} ; "
                      f"de {nombre_fr(min(vues))} à {nombre_fr(max(vues))}.", src,
              mediane=mediane, total=sum(vues), minimum=min(vues), maximum=max(vues))

    # la vidéo la plus vue en UN fait complet : sinon le cerveau assemble son jour et son heure à partir d'autres faits
    top = max(videos, key=lambda v: v["vues"])
    quand = datetime.fromtimestamp(top["timestamp"], PARIS)
    f.ajouter("vidéo la plus vue", f"Vidéo la plus vue : « {top['titre']} », {nombre_fr(top['vues'])} vues, publiée le "
                                   f"{JOURS[quand.weekday()]} {quand:%d/%m/%Y} à {quand.hour} h (heure de Paris), durée {_mmss(top['duree_s'])}.",
              src, vues=top["vues"], heure=quand.hour, duree_s=top["duree_s"])
    exceptions = sorted([v for v in videos if mediane and v["vues"] > 3 * mediane], key=lambda v: -v["vues"])
    if exceptions:
        details = " ; ".join(f"« {v['titre']} » {nombre_fr(v['vues'])} vues ({nombre_fr(v['vues'] / mediane, 1)} fois la médiane)"
                             for v in exceptions[:5])
        f.ajouter("exceptions", f"{len(exceptions)} vidéo(s) au-dessus de 3 fois la médiane : {details}.", src,
                  nombre=len(exceptions), **{f"vues_{i + 1}": v["vues"] for i, v in enumerate(exceptions[:5])},
                  **{f"ratio_{i + 1}": round(v["vues"] / mediane, 1) for i, v in enumerate(exceptions[:5])})
    elif not mediane:
        # la moitié des vidéos n'ont encore aucune vue : « aucune au-dessus de 3 fois 0 » serait faux (audit du 19/09)
        vues = sum(1 for v in videos if v["vues"] > 0)
        f.ajouter("exceptions", f"La médiane est de 0 vue : {vues} vidéo(s) sur {len(videos)} ont des vues, la comparaison "
                                f"à la médiane n'a pas encore de sens.", src, nombre=0, avec_vues=vues)
    else:
        f.ajouter("exceptions", f"Aucune vidéo au-dessus de 3 fois la médiane ({nombre_fr(3 * mediane)} vues).", src,
                  nombre=0, seuil=3 * mediane)

    # durées et formats courts
    durees = [v["duree_s"] for v in videos]
    courtes = [v for v in videos if v["duree_s"] <= COURTE_S]
    longues = [v for v in videos if v["duree_s"] > COURTE_S]
    texte = f"Durée médiane : {_mmss(statistics.median(durees))}. {len(courtes)} vidéo(s) courte(s) (3 min ou moins)"
    valeurs = {"duree_mediane_s": statistics.median(durees), "courtes": len(courtes), "longues": len(longues)}
    if courtes and longues:
        mc, ml = statistics.median(v["vues"] for v in courtes), statistics.median(v["vues"] for v in longues)
        texte += f" : médiane {nombre_fr(mc)} vues, contre {nombre_fr(ml)} pour les {len(longues)} plus longues"
        valeurs.update(mediane_courtes=mc, mediane_longues=ml)
    f.ajouter("durées", texte + ".", src, **valeurs)
    if exceptions and len(exceptions) < len(videos):
        autres = [v for v in videos if v not in exceptions]
        de, da = statistics.median(v["duree_s"] for v in exceptions), statistics.median(v["duree_s"] for v in autres)
        f.ajouter("durées", f"Durée médiane des vidéos au-dessus de 3 fois la médiane : {_mmss(de)}, contre {_mmss(da)} pour les autres.",
                  src, duree_exceptions_s=de, duree_autres_s=da)

    # jours de publication
    par_jour: dict[int, list[int]] = {}
    for v in videos:
        par_jour.setdefault(datetime.fromtimestamp(v["timestamp"], PARIS).weekday(), []).append(v["vues"])
    jours = [{"jour": JOURS[j], "videos": len(l), "mediane": statistics.median(l)} for j, l in sorted(par_jour.items())]
    texte = "Publications par jour (heure de Paris) : " + ", ".join(f"{x['jour']} {x['videos']}" for x in jours) + "."
    valeurs = {f"{x['jour']}_videos": x["videos"] for x in jours}
    comparables = [x for x in jours if x["videos"] >= 2]
    if len(comparables) >= 2:
        meilleur = max(comparables, key=lambda x: x["mediane"])
        texte += f" Meilleur jour parmi ceux d'au moins 2 vidéos : le {meilleur['jour']}, médiane {nombre_fr(meilleur['mediane'])} vues."
        valeurs["meilleur_jour_mediane"] = meilleur["mediane"]
    f.ajouter("jours", texte, src, **valeurs)

    # heures de publication
    tranches = []
    for libelle, a, b in TRANCHES:
        l = [v["vues"] for v in videos if a <= datetime.fromtimestamp(v["timestamp"], PARIS).hour < b]
        if l:
            tranches.append({"tranche": libelle, "videos": len(l), "mediane": statistics.median(l)})
    heures = [datetime.fromtimestamp(v["timestamp"], PARIS).hour for v in videos]
    heure_type = statistics.mode(heures)
    texte = (f"Heure de publication la plus fréquente : {heure_type} h ({heures.count(heure_type)} vidéos). "
             + " ; ".join(f"{t['tranche']} {t['videos']} vidéo(s), médiane {nombre_fr(t['mediane'])} vues" for t in tranches) + ".")
    f.ajouter("heures", texte, src, heure_frequente=heure_type, videos_a_cette_heure=heures.count(heure_type),
              **{f"tranche_{i + 1}_videos": t["videos"] for i, t in enumerate(tranches)},
              **{f"tranche_{i + 1}_mediane": t["mediane"] for i, t in enumerate(tranches)})

    # rythme
    if len(videos) >= 4 and (fin - debut).days >= 14:
        par_semaine = len(videos) / ((fin - debut).days / 7)
        f.ajouter("rythme", f"Rythme : {nombre_fr(par_semaine, 1)} vidéo(s) par semaine sur {(fin - debut).days} jours.", src,
                  par_semaine=round(par_semaine, 1), jours=(fin - debut).days)

    # motifs de titres
    motifs = [(_motifs(v["titre"]), v["vues"]) for v in videos]
    mots = statistics.median(m["mots"] for m, _ in motifs)
    texte = f"Titres : {nombre_fr(mots)} mots en médiane"
    valeurs = {"mots_mediane": mots}
    if exceptions:
        me = statistics.median(_motifs(v["titre"])["mots"] for v in exceptions)
        texte += f" ({nombre_fr(me)} pour les vidéos au-dessus de 3 fois la médiane)"
        valeurs["mots_exceptions"] = me
    f.ajouter("titres", texte + ".", "titres des vidéos", **valeurs)
    for motif, libelle in LIBELLES_MOTIFS.items():
        avec = [vu for m, vu in motifs if m[motif]]
        sans = [vu for m, vu in motifs if not m[motif]]
        if len(avec) >= 3 and len(sans) >= 3:
            ma, ms = statistics.median(avec), statistics.median(sans)
            f.ajouter("titres", f"{len(avec)} titres contiennent {libelle} : médiane {nombre_fr(ma)} vues, contre {nombre_fr(ms)} sans.",
                      "titres et vues des vidéos", **{f"{motif}_titres": len(avec), f"{motif}_mediane_avec": ma, f"{motif}_mediane_sans": ms})

    try:
        prive = _statistiques_privees(ch, videos, f)
    except acces.ErreurYouTube as e:
        # YouTube Analytics non activée, jeton révoqué… : les faits publics déjà calculés restent (audit du 19/09)
        prive = f"indisponibles ({e}) : statistiques publiques seulement"
    return {"chaine": {k: ch.get(k) for k in ("id", "titre", "handle", "abonnes", "source")}, "periode": periode,
            "source": src, "faits": f.liste, "prive": prive, "mediane": mediane,
            "videos": [{**v, "exception": v in exceptions, "ratio": round(v["vues"] / mediane, 2) if mediane else None} for v in videos],
            "jours": jours, "quota": acces.quota() if ch["source"] == "api" else None}


def _statistiques_privees(ch: dict, videos: list[dict], f: Faits) -> str:
    """Rétention et sources de trafic, seulement pour la chaîne du compte connecté par OAuth."""
    from . import oauth
    try:
        if not oauth.jeton_acces():
            return "non connecté (OAuth absent) : statistiques publiques seulement"
        if oauth.mon_id_de_chaine() != ch["id"]:
            return "chaîne d'un autre compte : statistiques publiques seulement"
    except Exception as e:
        return f"OAuth indisponible ({type(e).__name__})"
    source = "YouTube Analytics (compte connecté)"
    aujourdhui = datetime.now(PARIS).date()
    for v in [v for v in videos if v["duree_s"] > 60][:3]:
        debut = datetime.fromtimestamp(v["timestamp"], PARIS).date()
        r = acces.appeler("reports", {"ids": "channel==MINE", "startDate": debut.isoformat(), "endDate": aujourdhui.isoformat(),
                                      "metrics": "audienceWatchRatio", "dimensions": "elapsedVideoTimeRatio",
                                      "filters": f"video=={v['id']}"}, ttl=6 * 3600, analytics=True)
        points = [(float(x), float(y)) for x, y in r.get("rows") or []]
        if len(points) < 5:
            continue
        chutes = sorted(((points[i][1] - points[i + 1][1], points[i][0]) for i in range(len(points) - 1)), reverse=True)[:2]
        a_moitie = min(points, key=lambda p: abs(p[0] - 0.5))[1]
        texte = (f"« {v['titre']} » : {nombre_fr(a_moitie * 100)} % des spectateurs encore là à mi-vidéo ; plus fortes chutes à "
                 + " et ".join(f"{_mmss(x * v['duree_s'])} (-{nombre_fr(c * 100)} points)" for c, x in chutes) + ".")
        f.ajouter("rétention", texte, source, retention_moitie=round(a_moitie * 100),
                  **{f"chute_{i + 1}_points": round(c * 100) for i, (c, _) in enumerate(chutes)})
    r = acces.appeler("reports", {"ids": "channel==MINE", "startDate": (aujourdhui - timedelta(days=28)).isoformat(),
                                  "endDate": aujourdhui.isoformat(), "metrics": "views", "dimensions": "insightTrafficSourceType",
                                  "sort": "-views"}, ttl=6 * 3600, analytics=True)
    lignes = [(s, int(x)) for s, x in r.get("rows") or []]
    total = sum(x for _, x in lignes)
    if total:
        top = lignes[:4]
        f.ajouter("trafic", "Sources de trafic sur 28 jours : " + ", ".join(f"{s} {nombre_fr(100 * x / total)} %" for s, x in top) + ".",
                  source, **{f"source_{i + 1}_pourcent": round(100 * x / total) for i, (_, x) in enumerate(top)})
    return "rétention et sources de trafic incluses"


def pour_le_cerveau(analyse: dict) -> str:
    """Ce que le cerveau reçoit : les faits, et la règle de citation."""
    lignes = "\n".join(f"{x['id']} [{x['sujet']}] {x['texte']} (source : {x['source']})" for x in analyse["faits"])
    return (f"FAITS SUR LA CHAÎNE {analyse['chaine']['titre']} ({analyse['periode']}, {analyse['source']}). "
            f"Statistiques privées : {analyse['prive']}.\n{lignes}\n"
            "RÈGLE : commente en 3 à 5 phrases parlées. Une phrase = un seul fait : ne relie jamais dans une même phrase des "
            "chiffres venant de faits différents. Chaque affirmation cite UN chiffre recopié tel quel, en chiffres, avec le mot du "
            "fait (médiane reste médiane, jamais moyenne). N'invente, n'arrondis et ne calcule aucun autre nombre.")
