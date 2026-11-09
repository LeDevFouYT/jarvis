"""Outil replay_crypto (vidéo 4, consigne 4) : « Jarvis, rejoue tes 10 derniers jours. »

Jarvis repart de 10 000 € FICTIFS il y a 10 jours et décide seul toutes les 4 heures (60 décisions de qwen3:14b,
température 0), sans jamais voir le futur (jarvis/crypto/replay.py). Le travail se fait en fond : l'outil répond tout
de suite, le HUD montre la courbe qui avance, et Jarvis commente le vrai résultat à voix haute à la fin.

Les décisions d'une même fenêtre (elle change toutes les 4 h) sont gardées : redemander le replay les rejoue en
une minute, sans recalculer — ce sont les mêmes décisions du modèle, à température 0.
« Pourquoi tu as vendu le 12 ? » : Jarvis relit la raison qu'il avait donnée à ce moment-là."""
import logging
import threading
import time
from datetime import datetime

from ..crypto import cours, mesures, replay as R

NOM = "replay_crypto"
DESCRIPTION = ("Rejoue les 10 derniers jours de trading avec 10 000 € FICTIFS : une décision toutes les 4 heures, sans voir "
               "le futur, comparée à « garder ses euros » et « tout en Bitcoin ». « lancer » : démarre le replay (la courbe "
               "s'affiche). « pourquoi » : relit la raison d'une décision passée (verbe : vendu, acheté ; jour : le numéro du jour).")
PARAMETRES = {
    "action": {"type": "string", "enum": ["lancer", "pourquoi"]},
    "verbe": {"type": "string", "description": "vendu, acheté ou attendu, pour « pourquoi »"},
    "jour": {"type": "integer", "description": "Le jour du mois de la décision, pour « pourquoi »"},
}
REQUIS = ["action"]
DIRECT = True
LECTURE_S = 60                     # un replay déjà calculé se rejoue en une minute
sur_evenement = lambda e: None     # branché par le serveur
journal = logging.getLogger("crypto")
_en_cours: dict = {}


def _emettre(e: dict):
    sur_evenement({"t_emis": time.time(), **e, "t": e.get("t", time.time())})


def _vers_hud(e: dict):
    if e["type"] == "replay_debut":
        _emettre({"type": "panneau", "genre": "replay", "titre": "Replay · 10 jours · argent fictif", "debut": e["debut"],
                  "fin": e["fin"], "capital": e["capital"], "decisions": e["decisions"]})
    else:
        _emettre(e)


def _rejouer_lecture(b: dict):
    """Un replay déjà calculé, rejoué au rythme d'une décision par seconde."""
    _vers_hud({"type": "replay_debut", "debut": b["debut"], "fin": b["fin"], "capital": R.CAPITAL, "decisions": len(b["decisions"])})
    pause = LECTURE_S / max(1, len(b["decisions"]))
    time.sleep(1.0)
    for d in b["decisions"]:
        if _en_cours.get("arret"):
            return
        _emettre({"type": "replay_etape", **{k: d.get(k) for k in ("i", "t", "date", "action", "crypto", "raison", "valeur", "btc",
                                                                     "euros", "montant_eur", "prix")}})
        time.sleep(pause)


def _travail(t_demande: float):
    try:
        debut, fin = R.fenetre()
        precedent = R.dernier()
        if precedent and precedent.get("fin") == fin and len(precedent.get("decisions", [])) == R.DECISIONS:
            b, calcule = precedent, False
            _rejouer_lecture(b)
        else:
            calcule = True
            marche = R.Marche.telecharger(debut, fin)
            jeu = R.Replay(marche, debut, fin, emettre=_vers_hud)
            _en_cours["jeu"] = jeu
            # le cerveau chargé AVANT la première décision : vu le 20/10, il se chargeait pendant le premier appel et
            # les 120 s du délai sautaient (« décision 1 : Read timed out »)
            from ..cerveau import CERVEAU
            CERVEAU.charger()
            b = jeu.jouer()
            R.sauver(b)
            from ..cerveau import CERVEAU
            threading.Thread(target=CERVEAU.rechauffer, daemon=True).start()     # un seul réchauffage après les 60 appels
            mesures.ecrire("4_replay", **{k: v for k, v in b.items() if k not in ("prix_debut",)}, quand=time.strftime("%Y-%m-%d %H:%M"),
                           mode="calculé en direct")
        texte = R.commentaire(b)
        _emettre({"type": "replay_fin", **{k: b[k] for k in ("comparaison", "valeur_finale_eur", "ordres", "decisions_faites")},
                  "meilleure_decision": b.get("meilleure_decision"), "pire_decision": b.get("pire_decision"), "calcule": calcule,
                  "duree_s": round(time.time() - t_demande, 1)})
        _emettre({"type": "crypto_parle", "texte": texte,
                  "historique": f"(Replay des 10 jours, argent fictif) {texte}"})
    except cours.Indisponible:
        _emettre({"type": "crypto_parle", "texte": "Je n'ai pas pu télécharger les cours des 10 derniers jours : ni Binance ni Kraken ne répondent."})
    except Exception as e:
        journal.exception("replay")
        _emettre({"type": "crypto_parle", "texte": f"Le replay a échoué : {type(e).__name__}."})
    finally:
        _en_cours.clear()


def lancer() -> str:
    from .. import carte
    if _en_cours:
        return "Je suis déjà en train de rejouer mes 10 jours. Regardez la courbe."
    if carte.occupee():
        return "La carte graphique est occupée par un autre travail : je rejouerai mes 10 jours quand elle sera libre."
    debut, fin = R.fenetre()
    precedent = R.dernier()
    deja = precedent and precedent.get("fin") == fin and len(precedent.get("decisions", [])) == R.DECISIONS
    _en_cours["depuis"] = time.time()
    threading.Thread(target=_travail, args=(time.time(),), daemon=True, name="replay-crypto").start()
    phrase = (f"Je repars de 10 000 euros fictifs le {R.date_fr(debut, heure=False)}, et je décide seul toutes les quatre heures, "
              f"sans voir la suite. ")
    return phrase + ("Je rejoue mes soixante décisions. Regardez." if deja else "Soixante décisions, environ deux minutes. Regardez.")


def pourquoi(verbe: str = "", jour: int | None = None, bilan: dict | None = None) -> str:
    b = bilan or R.dernier()
    if not b:
        return "Je n'ai encore rejoué aucun jour. Dites : rejoue tes 10 derniers jours."
    sens = {"vendu": "vente", "achete": "achat", "acheté": "achat", "attendu": "attendre", "garde": "attendre", "rien fait": "attendre"}.get(
        (verbe or "").strip().lower(), None)
    candidats = [d for d in b["decisions"] if (sens is None or d["action"] == sens)
                 and (jour is None or datetime.fromtimestamp(d["t"]).day == int(jour))]
    if not candidats:
        jours = sorted({datetime.fromtimestamp(d["t"]).day for d in b["decisions"] if sens is None or d["action"] == sens})
        quoi = {"vente": "vendu", "achat": "acheté", "attendre": "attendu"}.get(sens, "décidé")
        if not jours:
            return f"Je n'ai rien {quoi} pendant ces 10 jours."
        return f"Je n'ai rien {quoi} le {jour}. J'ai {quoi} le " + ", le ".join(str(j) for j in jours[:6]) + "."
    morceaux = []
    if all(d["action"] == "attendre" for d in candidats):
        # vu le 17/10 : six « attendre » le même jour, souvent avec la même raison, relus un par un
        groupes: dict = {}
        for d in candidats:
            groupes.setdefault(d["raison"].rstrip(" ."), []).append(d)
        jour_dit = candidats[0]["date"].split(",")[0]
        tete = f"{jour_dit[0].upper() + jour_dit[1:]}, j'ai attendu {len(candidats)} fois" if len(candidats) > 1 else \
            f"{candidats[0]['date'][0].upper() + candidats[0]['date'][1:]}, j'ai attendu"
        raisons = sorted(groupes.items(), key=lambda x: -len(x[1]))[:2]
        texte = tete + ". " + " ".join(
            (f"Ma raison{' la plus fréquente' if len(raisons) > 1 and i == 0 else (' ensuite' if i else '')}, "
             f"{'à chaque fois' if len(ds) == len(candidats) and len(ds) > 1 else f'{len(ds)} fois sur {len(candidats)}' if len(candidats) > 1 else 'à ce moment-là'} : « {r} ».")
            for i, (r, ds) in enumerate(raisons))
        return texte
    for d in candidats[:2]:
        if d["action"] == "attendre":
            quoi = "j'ai attendu"
        else:
            nom = cours.nom(d["crypto"])
            quoi = f"j'ai {'acheté' if d['action'] == 'achat' else 'vendu'} pour {cours.nombre(d['montant_eur'])} euros {('d’' if nom[0] in 'AEIOU' else 'de ') + nom}".replace("d’", "d'")
            quoi += f" à {cours.euros(d['prix']).replace(' €', ' euros')}"
        raison = d["raison"].rstrip(" .")
        morceaux.append(f"{d['date'][0].upper() + d['date'][1:]}, {quoi}. Ma raison, à ce moment-là : « {raison} ».")
    return " ".join(morceaux) + (f" Et {len(candidats) - 2} autre(s) ce jour-là." if len(candidats) > 2 else "")


def executer(action: str = "lancer", verbe: str = "", jour=None) -> str:
    if action == "pourquoi":
        return pourquoi(verbe, int(jour) if str(jour or "").isdigit() else None)
    return lancer()
