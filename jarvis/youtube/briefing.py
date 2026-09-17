"""Le briefing : ce qui a bougé depuis hier, en faits sourcés. Pas de météo, pas de lieu.

- Ma chaîne (`youtube.ma_chaine`) : abonnés et vues des vidéos récentes comparés au dernier relevé (un instantané
  par jour dans cache/youtube.sqlite ; le premier jour, Jarvis le dit et compare dès le lendemain), vidéos publiées
  depuis ce relevé, les trois vidéos qui ont gagné le plus de vues.
- Les nouveaux commentaires qui demandent quelque chose, sur les vidéos des 30 derniers jours : un commentaire
  déjà montré par un briefing précédent ne revient pas.
- Un concurrent en forme (`youtube.concurrents`) : parmi leurs vidéos des 7 derniers jours, celle qui dépasse le plus
  trois fois la médiane de sa chaîne.
- Les rappels des prochaines 24 heures, et l'état de la machine (carte graphique, mémoire, disques)."""
import statistics
import time
from datetime import datetime, timedelta

from . import acces, commentaires, donnees
from .acces import PARIS
from .analyste import Faits, nombre_fr


def _liste(valeur) -> list[str]:
    if isinstance(valeur, str):
        return [x.strip() for x in valeur.replace(";", ",").split(",") if x.strip()]
    return [str(x).strip() for x in valeur or [] if str(x).strip()]


def briefing(ma_chaine: str | None = None, concurrents: list[str] | None = None) -> dict:
    reglages = acces.REGLAGES
    ma_chaine = ma_chaine if ma_chaine is not None else reglages.get("ma_chaine", "")
    concurrents = _liste(concurrents if concurrents is not None else reglages.get("concurrents", []))
    f = Faits()
    sections, demandes_panneau, gains_panneau = [], [], []
    jour = acces.aujourdhui()

    if ma_chaine:
        try:
            ch = donnees.chaine(ma_chaine)
            videos = donnees.videos_recentes(ch, 15)
            src = "API YouTube Data v3" if ch["source"] == "api" else "pages publiques YouTube (yt-dlp)"
            instantane = {"abonnes": ch.get("abonnes"), "vues": {v["id"]: v["vues"] for v in videos},
                          "titres": {v["id"]: v["titre"] for v in videos}, "quand": time.time()}
            precedent = acces.dernier_releve_avant(f"chaine:{ch['id']}", jour)
            acces.releve(f"chaine:{ch['id']}", jour, instantane)
            if not precedent:
                f.ajouter("ma chaîne", f"Premier relevé de {ch['titre']} : {nombre_fr(ch.get('abonnes'))} abonnés, "
                                       f"{len(videos)} vidéos récentes suivies. Les écarts seront donnés au prochain briefing.",
                          src, abonnes=ch.get("abonnes"), videos=len(videos))
            else:
                jour_prec, avant = precedent
                depuis = datetime.fromisoformat(jour_prec).replace(tzinfo=PARIS)
                nouvelles = [v for v in videos if v["timestamp"] and datetime.fromtimestamp(v["timestamp"], PARIS) >= depuis + timedelta(days=1)]
                if ch.get("abonnes") is not None and avant.get("abonnes") is not None:
                    ecart = ch["abonnes"] - avant["abonnes"]
                    f.ajouter("ma chaîne", f"{ch['titre']} : {nombre_fr(ch['abonnes'])} abonnés, {'+' if ecart >= 0 else ''}{nombre_fr(ecart)} "
                                           f"depuis le relevé du {depuis:%d/%m}.", src, abonnes=ch["abonnes"], ecart_abonnes=ecart)
                gains = sorted(((v["vues"] - avant["vues"][v["id"]], v) for v in videos if v["id"] in avant.get("vues", {})),
                               key=lambda x: -x[0])
                total = sum(g for g, _ in gains)
                if gains:
                    f.ajouter("ma chaîne", f"Vidéos suivies : +{nombre_fr(total)} vues depuis le {depuis:%d/%m}. "
                              + " ; ".join(f"« {v['titre']} » +{nombre_fr(g)}" for g, v in gains[:3]) + ".",
                              src, gain_total=total, **{f"gain_{i + 1}": g for i, (g, _) in enumerate(gains[:3])})
                    gains_panneau = [{"nom": v["titre"][:40], "valeur": g} for g, v in gains[:8]]
                if nouvelles:
                    f.ajouter("ma chaîne", f"{len(nouvelles)} vidéo(s) publiée(s) depuis : "
                              + " ; ".join(f"« {v['titre']} » {nombre_fr(v['vues'])} vues" for v in nouvelles) + ".",
                              src, nouvelles=len(nouvelles), **{f"nouvelle_{i + 1}_vues": v["vues"] for i, v in enumerate(nouvelles)})
            sections.append("ma chaîne")

            # commentaires nouveaux qui demandent quelque chose
            recentes = [v for v in videos if v["timestamp"] and time.time() - v["timestamp"] < 30 * 86400][:3 if ch["source"] != "api" else 5]
            nouveaux = []
            for v in recentes:
                lus = donnees.commentaires(v["id"], 100)
                vus = acces.deja_vus(f"commentaires:{ch['id']}", [c["id"] for c in lus if c.get("id")])
                nouveaux += [{**c, "video": v["titre"]} for c in lus if c.get("id") not in vus and commentaires.est_demande(c["texte"])]
            if nouveaux:
                themes = commentaires.regrouper(nouveaux[:80]) if len(nouveaux) >= 3 else []
                texte = f"{len(nouveaux)} nouveau(x) commentaire(s) qui demandent quelque chose"
                valeurs = {"demandes_nouvelles": len(nouveaux)}
                if themes:
                    texte += " : " + " ; ".join(f"« {t['theme']} » {t['nombre']}" for t in themes[:4])
                    valeurs.update({f"theme_{i + 1}": t["nombre"] for i, t in enumerate(themes[:4])})
                else:
                    texte += " : " + " ; ".join(f"« {c['texte'][:90]} »" for c in nouveaux[:3])
                f.ajouter("commentaires", texte + ".", "commentaires publics des vidéos récentes", **valeurs)
                demandes_panneau = ([{"titre": t["theme"], "detail": t["exemples"][0], "meta": str(t["nombre"])} for t in themes]
                                    or [{"titre": c["texte"][:90], "detail": c["video"], "meta": c["auteur"]} for c in nouveaux[:10]])
            else:
                f.ajouter("commentaires", "Aucun nouveau commentaire qui demande quelque chose.", "commentaires publics des vidéos récentes",
                          demandes_nouvelles=0)
        except acces.ErreurYouTube as e:
            f.ajouter("ma chaîne", f"Chaîne indisponible : {e}.", "YouTube")
    else:
        f.ajouter("ma chaîne", "Aucune chaîne réglée : indiquez la vôtre dans les Réglages (section YouTube).", "Réglages")

    # un concurrent en forme
    meilleur = None
    for nom in concurrents[:5]:
        try:
            ch = donnees.chaine(nom)
            videos = donnees.videos_recentes(ch, 30)
            mediane = statistics.median(v["vues"] for v in videos) if videos else 0
            for v in videos:
                if v["timestamp"] and time.time() - v["timestamp"] < 7 * 86400 and mediane and v["vues"] > 3 * mediane:
                    ratio = v["vues"] / mediane
                    if not meilleur or ratio > meilleur[0]:
                        meilleur = (ratio, ch, v, mediane)
        except acces.ErreurYouTube:
            continue
    if concurrents:
        if meilleur:
            ratio, ch, v, mediane = meilleur
            f.ajouter("concurrent", f"Chez {ch['titre']}, « {v['titre']} » fait {nombre_fr(v['vues'])} vues en moins de 7 jours, "
                                    f"soit {nombre_fr(ratio, 1)} fois la médiane de la chaîne ({nombre_fr(mediane)}).",
                      "vidéos publiques des concurrents", vues=v["vues"], ratio=round(ratio, 1), mediane=mediane)
        else:
            f.ajouter("concurrent", f"Aucune vidéo des {len(concurrents[:5])} concurrent(s) au-dessus de 3 fois sa médiane cette semaine.",
                      "vidéos publiques des concurrents", concurrents=len(concurrents[:5]))
        sections.append("concurrents")

    # rappels et machine
    from ..outils import etat_machine, rappel
    prochains = [r for r in rappel.liste() if 0 <= r["quand"] - time.time() < 86400]
    if prochains:
        f.ajouter("rappels", f"{len(prochains)} rappel(s) dans les 24 heures : " + " ; ".join(
            f"{datetime.fromtimestamp(r['quand']):%H h %M} {r['texte']}" for r in prochains[:5]) + ".", "rappels programmés", rappels=len(prochains))
    else:
        f.ajouter("rappels", "Aucun rappel dans les 24 heures.", "rappels programmés", rappels=0)
    m = etat_machine.mesures()
    g = m.get("gpu") or {}
    morceaux, valeurs = [], {}
    if g:
        morceaux.append(f"carte graphique à {g['temperature']} °C, {nombre_fr(g['vram_utilisee_mo'] / 1024, 1)} Go de mémoire vidéo sur "
                        f"{nombre_fr(g['vram_totale_mo'] / 1024)}")
        valeurs.update(temperature=g["temperature"], vram_go=round(g["vram_utilisee_mo"] / 1024, 1), vram_totale_go=round(g["vram_totale_mo"] / 1024))
    for lettre, d in m.get("disques", {}).items():
        morceaux.append(f"disque {lettre} : {nombre_fr(d['libre_go'])} Go libres")
        valeurs[f"disque_{lettre}_libre_go"] = d["libre_go"]
    f.ajouter("machine", "Machine : " + ", ".join(morceaux) + ".", "mesures de cette machine", **valeurs)
    return {"faits": f.liste, "sections": sections, "demandes": demandes_panneau, "gains": gains_panneau,
            "quota": acces.quota() if acces.cle() else None}


def pour_le_cerveau(b: dict) -> str:
    lignes = "\n".join(f"{x['id']} [{x['sujet']}] {x['texte']}" for x in b["faits"])
    return (f"FAITS DU BRIEFING :\n{lignes}\nRÈGLE : fais le briefing du matin en 4 à 7 phrases parlées, dans cet ordre : chaîne, "
            "commentaires, concurrent, rappels, machine. Une phrase = un seul fait, et chaque phrase dit de quoi elle parle (ma chaîne, "
            "le concurrent…) : ce qui concerne le concurrent ne s'applique jamais à ma chaîne. Chaque affirmation cite un chiffre "
            "recopié tel quel de ces faits, en chiffres. "
            "Ne parle ni de météo, ni de lieu, ni de rien qui n'est pas dans ces faits.")
