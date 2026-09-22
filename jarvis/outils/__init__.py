"""Le registre des outils : un fichier par outil dans ce dossier, chacun avec
  NOM, DESCRIPTION (en français, lue par le cerveau), PARAMETRES (propriétés JSON Schema), REQUIS,
  et executer(**arguments) -> str (une phrase que Jarvis peut dire).
Règles communes appliquées ici : un outil qui échoue renvoie un message court, jamais une trace ;
chaque appel et son résultat sont diffusés sur /events ; un outil ne dépasse jamais DELAI_MAX secondes."""
import logging
import threading
import time
from pathlib import Path

from ..config import RACINE

JOURNAL = RACINE / "workspace" / "journal.log"
JOURNAL.parent.mkdir(exist_ok=True)
logging.basicConfig(filename=str(JOURNAL), level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s : %(message)s")
journal = logging.getLogger("outils")

from . import (briefing, calculer, chercher_fichiers, chercher_web, ecrire, etat_machine, fenetres, generer_image, generer_video, globe, heure, hologramme, notes,
               miniatures, ouvrir_application, ouvrir_fichier, ouvrir_site, presse_papiers, ranger, rappel, resumer_video, retenir, systeme,
               telegram, voir_ecran, webcam, youtube_chaine, youtube_commentaires)

DELAI_MAX = 60
sur_evenement = lambda e: None   # branché par le serveur

# Le canal de la demande en cours (fil du dialogue) : « telegram » quand la question vient du téléphone.
# `garde(nom, arguments, description) -> None | str` : une action sur le PC demandée de loin doit être autorisée
# (bouton Telegram) ; None = autorisée, sinon le texte du refus. Recopié dans le fil de l'outil.
CONTEXTE = threading.local()
refus_compte = 0


def contexte(source: str = "", garde=None):
    CONTEXTE.source, CONTEXTE.garde = source, garde


def source_courante() -> str:
    return getattr(CONTEXTE, "source", "") or ""


# Les actions qui changent quelque chose sur le PC. Rend la phrase à confirmer, ou None pour une simple lecture.
def _action_pc(nom: str, a: dict) -> str | None:
    if nom == "fenetres":
        app = a.get("application") or "la fenêtre active"
        return {"gauche": f"mettre {app} à gauche", "droite": f"mettre {app} à droite", "plein_ecran": f"mettre {app} en plein écran",
                "autre_ecran": f"passer {app} sur l'autre écran", "restaurer": f"restaurer {app}",
                "minimiser_autres": f"réduire toutes les fenêtres sauf {app}", "fermer": f"fermer {app}",
                "lister": None}.get(a.get("action"), f"agir sur {app}")
    if nom == "ranger":
        return f"ranger le dossier « {a.get('dossier', '?')} »"
    if nom == "ecrire":
        texte = str(a.get("texte", ""))
        return f"taper « {texte[:80]}{'…' if len(texte) > 80 else ''} » dans la fenêtre active" + (" puis Entrée" if a.get("entree") else "")
    if nom == "presse_papiers":
        return None if a.get("action", "lire") == "lire" else f"remplacer le presse-papiers par un texte {a.get('action')}"
    if nom == "ouvrir_application":
        return f"ouvrir « {a.get('nom', '?')} »"
    if nom == "ouvrir_fichier":
        return f"ouvrir le fichier « {a.get('nom', '?')} »" + (f" ({a['dossier']})" if a.get("dossier") else "")
    if nom == "ouvrir_site":
        return f"ouvrir le site « {a.get('site', '?')} »" + (f", recherche « {a['recherche']} »" if a.get("recherche") else "")
    if nom == "systeme":
        return {"volume": f"régler le volume à {a.get('valeur') or '?'}", "muet": "couper le son", "son": "remettre le son",
                "verrouiller": "verrouiller la session", "capture": None}.get(a.get("action"), f"système : {a.get('action')}")
    if nom == "webcam":
        return "allumer la webcam et regarder"
    return None


def action_pc(nom: str, arguments: dict | None) -> str | None:
    try:
        return _action_pc(nom, arguments or {})
    except Exception:
        return f"{nom}"

MODULES = [heure, calculer, notes.NOTER, notes.LIRE, etat_machine, chercher_fichiers, chercher_web,
           ouvrir_application, ouvrir_fichier, ouvrir_site, systeme, voir_ecran, generer_image, telegram, rappel,
           fenetres, ranger, ecrire, presse_papiers, retenir, webcam, resumer_video, miniatures,
           youtube_chaine, youtube_commentaires, briefing, hologramme, globe, generer_video]
# les outils dont la réponse est vérifiée chiffre par chiffre contre leur JSON de faits
OUTILS_A_FAITS = {"youtube_chaine": youtube_chaine, "youtube_commentaires": youtube_commentaires, "briefing": briefing}
OUTILS = {m.NOM: m for m in MODULES}


def _schema(m):
    return {"type": "function", "function": {
        "name": m.NOM, "description": m.DESCRIPTION,
        "parameters": {"type": "object", "properties": getattr(m, "PARAMETRES", {}),
                       "required": getattr(m, "REQUIS", [])}}}


SCHEMAS = [_schema(m) for m in MODULES]


def est_direct(nom: str) -> bool:
    """Un outil « direct » fournit lui-même la phrase finale : le cerveau n'est pas rappelé après lui."""
    module = OUTILS.get(nom)
    # DIRECT : toujours ; direct_dernier : selon le dernier appel (presse_papiers : un résumé oui, une simple lecture non)
    return bool(getattr(module, "DIRECT", False) or getattr(module, "direct_dernier", False))


def executer(nom: str, arguments: dict | None) -> str:
    arguments = arguments or {}
    if nom not in OUTILS:
        return f"Je ne connais pas d'outil nommé {nom}, monsieur."
    module = OUTILS[nom]
    garde, source = getattr(CONTEXTE, "garde", None), source_courante()
    description = action_pc(nom, arguments)
    if garde and description:
        refus = garde(nom, arguments, description)
        if refus:
            global refus_compte
            refus_compte += 1                       # le cerveau dit ce refus tel quel, sans le reformuler
            sur_evenement({"type": "outil_refuse", "t": time.time(), "outil": nom, "arguments": arguments, "raison": refus})
            return refus
    sur_evenement({"type": "outil_appel", "t": time.time(), "outil": nom, "arguments": arguments, "source": source})
    debut = time.time()
    resultat = {"texte": None, "erreur": None}

    def travail():
        contexte(source, garde)                   # le fil de l'outil connaît le canal (confirmations par bouton)
        try:
            resultat["texte"] = str(module.executer(**arguments))
        except TypeError as e:
            # argument inattendu ou manquant : on réessaie avec les seuls paramètres connus
            try:
                connus = {k: v for k, v in arguments.items() if k in getattr(module, "PARAMETRES", {})}
                resultat["texte"] = str(module.executer(**connus))
            except Exception as e2:
                resultat["erreur"] = e2
                journal.exception("outil %s (%s)", nom, arguments)
        except Exception as e:
            resultat["erreur"] = e
            journal.exception("outil %s (%s)", nom, arguments)

    fil = threading.Thread(target=travail, daemon=True, name=f"outil-{nom}")
    fil.start()
    delai = getattr(module, "DELAI", DELAI_MAX)          # les outils YouTube lisent des pages : jusqu'à trois minutes
    fil.join(delai)
    if fil.is_alive():
        texte = f"L'outil {nom} n'a pas répondu en {int(delai)} secondes. Je rends la main."
        journal.warning("outil %s : délai dépassé (%s)", nom, arguments)
    elif resultat["erreur"] is not None:
        e = resultat["erreur"]
        texte = f"L'outil {nom} a échoué : {type(e).__name__}, {str(e)[:120]}."
    else:
        texte = resultat["texte"] or "Aucun résultat."
    sur_evenement({"type": "outil_resultat", "t": time.time(), "outil": nom, "resultat": texte[:500],
                   "duree": round(time.time() - debut, 2)})
    journal.info("outil %s %s -> %s (%.1f s)", nom, arguments, texte[:200].replace("\n", " "), time.time() - debut)
    return texte


def demarrer_taches_de_fond():
    """Index des fichiers et rappels programmés : lancés par le serveur au démarrage."""
    chercher_fichiers.demarrer_index()
    rappel.recharger()
