"""Le replay des 10 derniers jours (consigne 4) : 10 000 € FICTIFS, une décision de qwen3:14b toutes les 4 heures.

La règle qui commande tout : **à chaque décision, le modèle ne voit que le passé**.
  - les bougies d'une heure sont téléchargées une fois (Binance, Kraken en repli), puis `Marche.vue(t)` ne rend que
    celles qui sont CLOSES à l'instant t (ouverture + 1 h <= t) ; la consigne de décision n'est construite qu'à partir
    de cette vue et du portefeuille à t ;
  - l'ordre s'exécute au prix connu à t (la clôture de la dernière bougie vue), avec les mêmes 0,1 % de frais qu'en vrai
    (portefeuille.Livre) ;
  - la preuve (tests/crypto_replay.py) : on remplace tout le futur par des prix absurdes, et chaque consigne reste
    identique au caractère près.
Qwen3 a été entraîné avant 2026 : il ne connaît pas les cours d'octobre 2026, il ne peut pas « se souvenir » de la suite.

Résultat comparé à « garder ses euros » (0 %) et à « tout en Bitcoin le premier jour » (mêmes frais).
Chaque décision et sa raison vont dans workspace/replay_crypto.json et workspace/mesures/crypto.json."""
import bisect
import json
import logging
import statistics
import threading
import time
from datetime import datetime

from ..config import RACINE
from . import cours
from .portefeuille import CAPITAL, FRAIS, Livre, OrdreImpossible

journal = logging.getLogger("crypto")
FICHIER = RACINE / "workspace" / "replay_crypto.json"
UNIVERS = ["BTC", "ETH", "SOL"]
PAS = 4 * 3600
JOURS = 10
DECISIONS = JOURS * 24 * 3600 // PAS            # 60
HEURE = 3600
RECUL_H = 9 * 24                                 # le passé visible avant le premier jour (indicateurs sur 7 jours)

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

# Première version (16/10, gardée pour la vidéo) : « Décide comme un gérant prudent et raisonné » -> à température 0,
# qwen3:14b a répondu « attendre » 60 fois sur 60 (0 ordre). La consigne dit maintenant l'objectif (battre les euros
# et le Bitcoin) sans pousser à trader : attendre reste permis.
CONSIGNE = (
    "Tu es Jarvis et tu gères un portefeuille FICTIF de démonstration (aucun argent réel), parti de 10 000 euros. "
    "On rejoue les 10 derniers jours : toutes les 4 heures tu prends UNE décision, en ne voyant QUE les données passées "
    "qu'on te donne (tu ne connais pas la suite). Cryptos possibles : BTC, ETH, SOL. Chaque ordre coûte 0,1 % de frais. "
    "Actions : « acheter » (montant_eur en euros, au plus les euros disponibles), « vendre » (fraction de la position, "
    "entre 0 et 1 : 0.5 = la moitié, 1 = tout), ou « attendre ». Ton objectif : finir les 10 jours avec plus que si "
    "tu avais gardé tes euros, et plus que si tu avais tout mis en Bitcoin le premier jour. Rester en euros est aussi un "
    "choix : tu rates les hausses. Tu peux répartir le capital entre plusieurs cryptos, renforcer ou alléger une position, "
    "et attendre quand rien n'est net. Un ordre fait au moins 100 euros. Décide à partir des chiffres fournis, sans rien "
    "inventer. La raison : une seule phrase en français, 25 mots au plus, qui cite le chiffre qui t'a décidé. "
    "Réponds uniquement en JSON.")
SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["acheter", "vendre", "attendre"]},
    "crypto": {"type": "string", "enum": ["BTC", "ETH", "SOL", "aucune"]},
    "montant_eur": {"type": "number"}, "fraction": {"type": "number"},
    "raison": {"type": "string"}}, "required": ["action", "crypto", "raison"]}


def date_fr(t: float, heure: bool = True) -> str:
    d = datetime.fromtimestamp(t)
    texte = f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]}"
    return f"{texte}, {d.hour} h" if heure else texte


def fenetre(maintenant: float | None = None) -> tuple[int, int]:
    """(début, fin) : la fin est la dernière frontière de 4 h passée (00 h, 04 h… UTC), le début 10 jours avant."""
    fin = int((maintenant or time.time()) // PAS * PAS)
    return fin - JOURS * 86400, fin


class Marche:
    """Les bougies d'une heure de l'univers, et la seule porte d'accès pendant le replay : `vue(t)`."""

    def __init__(self, series: dict[str, list[dict]]):
        self.series = {s: sorted(b, key=lambda x: x["t"]) for s, b in series.items()}
        self._clotures = {s: [b["t"] + HEURE for b in bs] for s, bs in self.series.items()}

    @classmethod
    def telecharger(cls, debut: int, fin: int) -> "Marche":
        heures = (fin - debut) // HEURE + RECUL_H + 2
        return cls({s: [b for b in cours.bougies(s, "1h", heures, fin=fin - 1) if b["t"] + HEURE <= fin] for s in UNIVERS})

    def vue(self, t: float) -> dict[str, list[dict]]:
        """Seulement les bougies closes à l'instant t. Rien d'autre ne sort du marché pendant le replay."""
        return {s: bs[:bisect.bisect_right(self._clotures[s], t)] for s, bs in self.series.items()}

    def prix(self, t: float) -> dict[str, float]:
        """Le prix connu à t : la clôture de la dernière bougie close."""
        return {s: bs[-1]["c"] for s, bs in self.vue(t).items() if bs}


# --- les indicateurs, calculés sur la vue seulement ---------------------------------------------------------------
def _rsi(clotures: list[float], n: int = 14) -> float | None:
    if len(clotures) <= n:
        return None
    gains = pertes = 0.0
    for a, b in zip(clotures[-n - 1:-1], clotures[-n:]):
        gains += max(0.0, b - a)
        pertes += max(0.0, a - b)
    return 100.0 if pertes == 0 else 100 - 100 / (1 + gains / pertes)


def indicateurs(bougies: list[dict]) -> dict:
    c = [b["c"] for b in bougies]
    quatre = c[-1::-4][::-1]                       # une clôture toutes les 4 h, la dernière comprise
    prix = c[-1]
    variation = lambda h: (prix / c[-1 - h] - 1) * 100 if len(c) > h else None
    jour = bougies[-24:]
    return {"prix": prix, "var_4h": variation(4), "var_24h": variation(24), "var_7j": variation(168),
            "moyenne_24h": statistics.fmean(c[-24:]), "moyenne_7j": statistics.fmean(c[-168:]),
            "rsi_4h": _rsi(quatre), "amplitude_24h": (max(b["h"] for b in jour) / min(b["l"] for b in jour) - 1) * 100,
            "clotures_4h": quatre[-12:]}


def _n(x, d=0):
    return "?" if x is None else cours.nombre(x, d)


def _pct(x):
    return "?" if x is None else cours.pourcent(x)


def consigne_decision(i: int, t: float, vue: dict[str, list[dict]], livre: Livre, recentes: list[dict]) -> str:
    """Le texte que voit le modèle à la décision i. N'utilise que `vue` (le passé) et le portefeuille à t."""
    prix = {s: bs[-1]["c"] for s, bs in vue.items()}
    d = livre.detail(prix)
    lignes = [f"Décision {i + 1} sur {DECISIONS} · {date_fr(t)} (heure de Paris). Tu ne vois que le passé.", "",
              f"PORTEFEUILLE FICTIF : {_n(d['euros'], 2)} € disponibles"]
    for l in d["positions"]:
        achats = [o for o in livre.journal if o["symbole"] == l["symbole"] and o["sens"] == "achat"]
        prix_moyen = sum(o["montant_eur"] - o["frais_eur"] for o in achats) / max(1e-12, sum(o["quantite"] for o in achats)) if achats else None
        lignes.append(f"  {l['symbole']} : {l['quantite']:.6f} ({_n(l['valeur'])} €"
                      + (f", {_pct((l['prix'] / prix_moyen - 1) * 100)} depuis le prix moyen d'achat" if prix_moyen else "") + ")")
    lignes.append(f"  Valeur totale : {_n(d['valeur'])} € ({_pct(d['gain_pct'])} depuis le départ), {d['ordres']} ordre(s) passés.")
    lignes += ["", "MARCHÉ (en euros, bougies closes seulement) :"]
    for s in UNIVERS:
        x = indicateurs(vue[s])
        decimales = 0 if x["prix"] >= 1000 else 2
        lignes.append(f"{s} {_n(x['prix'], decimales)} € · 4 h {_pct(x['var_4h'])} · 24 h {_pct(x['var_24h'])} · 7 j {_pct(x['var_7j'])} · "
                      f"moyenne 24 h {_n(x['moyenne_24h'], decimales)} · moyenne 7 j {_n(x['moyenne_7j'], decimales)} · "
                      f"RSI 14 (4 h) {_n(x['rsi_4h'])} · amplitude 24 h {_pct(x['amplitude_24h']).lstrip('+')}")
        lignes.append("  12 dernières clôtures 4 h : " + ", ".join(_n(v, decimales) for v in x["clotures_4h"]))
    if recentes:
        lignes += ["", "TES DERNIÈRES DÉCISIONS :"]
        lignes += [f"  {date_fr(r['t'])} : {r['action']}" + (f" {r['crypto']}" if r["action"] != "attendre" else "")
                   + f" — « {r['raison']} »" for r in recentes[-3:]]
    lignes += ["", "Ta décision, en JSON."]
    return "\n".join(lignes)


def _decider_par_cerveau(consigne: str) -> tuple[dict, dict]:
    from ..cerveau import CERVEAU
    # 240 s : de quoi recharger le cerveau si une autre brique l'a déchargé entre deux décisions (le 20/10, la première
    # décision attendait son chargement et sautait à 120 s)
    brut = CERVEAU.generer(CONSIGNE, consigne, delai=240, format=SCHEMA, temperature=0, rechauffer=False)
    g = getattr(CERVEAU, "derniere_generation", {}) or {}
    return json.loads(brut), {"jetons": g.get("eval_count"), "consigne_jetons": g.get("prompt_eval_count")}


def appliquer(livre: Livre, decision: dict, prix: dict[str, float], t: float) -> dict:
    """La décision du modèle, rendue exécutable : montants bornés, ordre impossible -> « attendre » (et la note dit pourquoi)."""
    action, crypto = decision.get("action"), decision.get("crypto")
    raison = str(decision.get("raison", "")).strip()[:240]
    resultat = {"action": "attendre", "crypto": None, "raison": raison, "demande": {k: decision.get(k) for k in ("action", "crypto", "montant_eur", "fraction")}}
    try:
        if action == "acheter" and crypto in UNIVERS:
            montant = float(decision.get("montant_eur") or 0)
            if montant <= 0:
                raise OrdreImpossible("montant absent")
            ordre = livre.acheter(crypto, min(montant, livre.euros), prix[crypto], quand=t, raison=raison)
            resultat.update(action="achat", crypto=crypto, montant_eur=ordre["montant_eur"], prix=prix[crypto], quantite=ordre["quantite"])
        elif action == "vendre" and crypto in UNIVERS:
            fraction = decision.get("fraction")
            fraction = 1.0 if fraction in (None, 0) else max(0.0, min(1.0, float(fraction)))
            ordre = livre.vendre(crypto, prix[crypto], fraction=fraction, quand=t, raison=raison)
            resultat.update(action="vente", crypto=crypto, montant_eur=ordre["montant_eur"], prix=prix[crypto], quantite=ordre["quantite"],
                            fraction=fraction)
    except (OrdreImpossible, ValueError, TypeError) as e:
        resultat["note"] = f"ordre impossible ({e}) : rien n'est fait"
    return resultat


class Replay:
    """Un replay complet. `decider(consigne) -> (decision, infos)` est le cerveau (remplaçable dans les tests) ;
    `emettre` reçoit chaque étape pour le HUD ; `pause_s` étale la lecture d'un replay déjà calculé."""

    def __init__(self, marche: Marche, debut: int, fin: int, decider=None, emettre=None):
        self.marche, self.debut, self.fin = marche, debut, fin
        self.decider = decider or _decider_par_cerveau
        self.emettre = emettre or (lambda e: None)
        self.livre = Livre()
        self.decisions: list[dict] = []
        self.consignes: list[str] = []
        p0 = marche.prix(debut)["BTC"]
        self.btc_quantite = CAPITAL * (1 - FRAIS) / p0
        self.arret = threading.Event()

    def instants(self) -> list[int]:
        return [self.debut + k * PAS for k in range(DECISIONS)]

    def valeur_btc(self, t: float) -> float:
        return self.btc_quantite * self.marche.prix(t)["BTC"]

    def jouer(self) -> dict:
        t_debut = time.time()
        self.emettre({"type": "replay_debut", "debut": self.debut, "fin": self.fin, "capital": CAPITAL, "decisions": DECISIONS,
                      "univers": UNIVERS})
        for i, t in enumerate(self.instants()):
            if self.arret.is_set():
                break
            vue = self.marche.vue(t)
            prix = {s: bs[-1]["c"] for s, bs in vue.items()}
            consigne = consigne_decision(i, t, vue, self.livre, self.decisions)
            self.consignes.append(consigne)
            chrono = time.time()
            try:
                decision, infos = self.decider(consigne)
            except Exception as e:
                journal.exception("replay : décision %d", i + 1)
                decision, infos = {"action": "attendre", "crypto": "aucune", "raison": f"(pas de réponse du cerveau : {type(e).__name__})"}, {"erreur": str(e)}
            duree = time.time() - chrono
            r = appliquer(self.livre, decision, prix, t)
            r.update(i=i + 1, t=t, date=date_fr(t), duree_s=round(duree, 2), valeur=round(self.livre.valeur(prix), 2),
                     btc=round(self.valeur_btc(t), 2), euros=round(self.livre.euros, 2), prix_marche={s: round(v, 4) for s, v in prix.items()},
                     **{k: v for k, v in infos.items() if v is not None})
            self.decisions.append(r)
            self.emettre({"type": "replay_etape", **{k: r[k] for k in ("i", "t", "date", "action", "crypto", "raison", "valeur", "btc", "euros")},
                          "montant_eur": r.get("montant_eur"), "prix": r.get("prix")})
        return self.bilan(time.time() - t_debut)

    def bilan(self, duree: float) -> dict:
        prix_fin = self.marche.prix(self.fin)
        valeur = self.livre.valeur(prix_fin)
        btc = self.valeur_btc(self.fin)
        ordres = [d for d in self.decisions if d["action"] in ("achat", "vente")]
        # l'effet de chaque ordre, mesuré à la fin des 10 jours : acheté puis monté = bon ; vendu puis remonté = mauvais
        for d in ordres:
            ecart = prix_fin[d["crypto"]] - d["prix"]
            d["effet_fin_eur"] = round(d["quantite"] * ecart * (1 if d["action"] == "achat" else -1), 2)
        meilleure = max(ordres, key=lambda d: d["effet_fin_eur"], default=None)
        pire = min(ordres, key=lambda d: d["effet_fin_eur"], default=None)
        durees = [d["duree_s"] for d in self.decisions]
        return {"debut": self.debut, "fin": self.fin, "debut_date": date_fr(self.debut), "fin_date": date_fr(self.fin),
                "decisions_faites": len(self.decisions), "ordres": len(ordres),
                "achats": sum(d["action"] == "achat" for d in ordres), "ventes": sum(d["action"] == "vente" for d in ordres),
                "valeur_finale_eur": round(valeur, 2), "positions_finales": {s: round(q, 8) for s, q in self.livre.positions.items()},
                "euros_finaux": round(self.livre.euros, 2), "frais_payes_eur": round(sum(o["frais_eur"] for o in self.livre.journal), 2),
                "comparaison": {"jarvis_pct": round((valeur / CAPITAL - 1) * 100, 2), "garder_ses_euros_pct": 0.0,
                                "tout_en_btc_pct": round((btc / CAPITAL - 1) * 100, 2), "tout_en_btc_eur": round(btc, 2)},
                "prix_debut": self.marche.prix(self.debut), "prix_fin": prix_fin,
                "meilleure_decision": _resume(meilleure), "pire_decision": _resume(pire),
                "duree_totale_s": round(duree, 1),
                "secondes_par_decision": {"mediane": round(statistics.median(durees), 2) if durees else None,
                                          "pire": round(max(durees), 2) if durees else None},
                "decisions": self.decisions}


def _resume(d: dict | None) -> dict | None:
    if not d:
        return None
    return {k: d.get(k) for k in ("i", "date", "action", "crypto", "montant_eur", "prix", "raison", "effet_fin_eur")}


def commentaire(b: dict) -> str:
    """Ce que Jarvis dit à la fin : les vrais chiffres, même s'il a perdu."""
    from ..outils.portefeuille import montant_dit
    c = b["comparaison"]
    sens = lambda x: "à zéro" if abs(x) < 0.05 else f"{'plus' if x > 0 else 'moins'} {cours.pourcent(x, signe=False)}"
    ecart = b["valeur_finale_eur"] - CAPITAL
    if 0.005 <= abs(ecart) and abs(c["jarvis_pct"]) < 0.05:          # −4 € : ni « à zéro », ni « moins 0,0 % »
        sens_jarvis = f"{montant_dit(ecart)} de {'moins' if ecart < 0 else 'plus'}"
    else:
        sens_jarvis = sens(c["jarvis_pct"])
    phrase = (f"Résultat : mes 10 000 euros fictifs sont devenus {montant_dit(b['valeur_finale_eur'])}, {sens_jarvis}, "
              f"en {b['ordres']} ordre{'s' if b['ordres'] > 1 else ''}. ")
    phrase += f"Garder ses euros : zéro. Tout en Bitcoin le premier jour : {sens(c['tout_en_btc_pct'])}. "
    if c["jarvis_pct"] > c["tout_en_btc_pct"] and c["jarvis_pct"] > 0:
        phrase += "J'ai battu les deux, sur dix jours seulement : ne me confiez pas vos économies pour autant."
    elif c["jarvis_pct"] > c["tout_en_btc_pct"]:
        phrase += "J'ai perdu de l'argent, mais moins que le Bitcoin. Maigre consolation."
    elif c["jarvis_pct"] > 0:
        phrase += "Je gagne, mais moins que le Bitcoin. J'aurais mieux fait de ne rien toucher."
    else:
        phrase += "J'ai fait moins bien que le Bitcoin et que vos euros. Je le garde, c'est la vérité."
    m = b.get("meilleure_decision")
    if m and m["effet_fin_eur"] > 0:
        verbe = "acheter" if m["action"] == "achat" else "vendre"
        phrase += f" Ma meilleure décision : {verbe} {"de l'Ethereum" if m['crypto'] == 'ETH' else 'du ' + cours.nom(m['crypto'])}, {m['date']}."
    return phrase


def sauver(b: dict):
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    temporaire = FICHIER.with_suffix(".tmp")
    temporaire.write_text(json.dumps({"_lisez_moi": "Replay FICTIF : 60 décisions de qwen3:14b, sans voir le futur.", **b},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    temporaire.replace(FICHIER)


def dernier() -> dict | None:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return None
