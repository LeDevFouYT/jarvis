"""Les voix créées (vidéo 5, demande des utilisateurs : « on ne peut pas changer la voix »).

« Change ta voix : une voix grave et posée. » La personne décrit une voix en mots ; Qwen3-TTS VoiceDesign en dessine
six essais (voix_qwen/creer_voix.py), Whisper les réécoute, le plus juste devient la référence, puis le moteur
`majordome` (Qwen3-TTS Base en clonage de cette référence) la rejoue, stable d'une phrase à l'autre.

- Rangées dans workspace/voix/<nom>/ (reference.wav|.txt|.json, candidats/) : protégées des mises à jour.
- Le majordome d'origine reste une voix parmi les autres (« reprends la voix du majordome »).
- **Aucune imitation** : une description qui vise une personne réelle (« la voix de … », « imite … », « comme … ») est
  refusée, par des mots sûrs puis par le cerveau. La description passe en anglais par le cerveau (VoiceDesign
  comprend mieux l'anglais) et n'atteint jamais le modèle telle quelle.
- **Clonage d'un enregistrement** (Réglages) : seulement avec la case « c'est ma voix, ou j'ai l'accord écrit de la
  personne » cochée ; l'accord est écrit dans reference.json avec la date.
- Mémoire vidéo : VoiceDesign 1.7B (~5 Go) + son Whisper ne tiennent pas à côté du cerveau : la carte est prise
  (`carte.Occupation`), le cerveau et la voix en service sont rendus le temps de la création, puis reviennent.
"""
import json
import re
import shutil
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

from .config import CONFIG, RACINE

DOSSIER = RACINE / "workspace" / "voix"
MAJORDOME = "majordome"
REF_MAJORDOME = RACINE / "jarvis" / "voix_qwen" / "majordome" / "reference.wav"
CREATION_MAX_S = 900
EXTRAIT_CLONAGE = ("Bonjour. Ceci est un court enregistrement de ma propre voix, que j'autorise à servir de modèle "
                   "à mon assistant.")

CONSIGNE_ANGLAIS = (
    "Transforme la description d'une voix, écrite en français, en une description de voix en ANGLAIS pour un "
    "générateur de voix (Qwen3-TTS VoiceDesign). Décris : genre et âge approximatif, timbre, hauteur, débit, "
    "énergie, émotion, et précise qu'elle parle français couramment. Ajoute à la fin : « Clean studio recording, "
    "close microphone, no background noise, no music. » Aucun nom de personne réelle, aucun personnage existant, "
    "aucune imitation. Deux phrases au plus. Réponds uniquement par la description."
)
CONSIGNE_JUGE = (
    "Tu vérifies une demande de création de voix. Elle est INTERDITE si elle demande d'imiter ou de ressembler à une "
    "personne réelle identifiable (célébrité, politicien, proche nommé, youtubeur…) ou à un personnage existant "
    "doublé par un comédien. Elle est AUTORISÉE si elle décrit seulement des qualités (grave, douce, âgée, rapide, "
    "accent du Sud, robotique…). Réponds en JSON."
)
SCHEMA_JUGE = {"type": "object", "properties": {"interdite": {"type": "boolean"}, "raison": {"type": "string"}},
               "required": ["interdite", "raison"]}
# mots sûrs, avant le modèle : ils tiennent même si le modèle se trompe
_IMITATION = re.compile(r"\b(imite[rsz]?|imitation|parodie|deepfake|sosie)\b|\bvoix (?:de|d'|du) [A-ZÉ][a-zé]+"
                        r"|\b(?:comme|facon|façon|style|a la) [A-ZÉ][a-zé]+(?: [A-ZÉ][a-zé]+)?", re.UNICODE)
_COURANTS_MAJ = {"Le", "La", "Les", "Un", "Une", "Sud", "Nord", "Est", "Ouest", "Midi", "Paris", "Marseille", "Québec"}


class Refus(ValueError):
    pass


def _slug(nom: str) -> str:
    n = unicodedata.normalize("NFD", nom.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-")[:30] or "voix"


def nom_depuis(description: str) -> str:
    """« une voix grave et posée, un peu rauque » -> « Grave et posée »."""
    # « une voix d'homme âgé » -> « Homme âgé », pas « D'homme âgé » (vu le 07/11)
    d = re.sub(r"^\s*(?:une?\s+)?(?:voix\s+)?(?:d'|d’|de\s+)?", "", description.strip(), flags=re.IGNORECASE)
    mots = re.split(r"[,.;:!?]", d)[0].split()[:4]
    nom = " ".join(mots) or "Nouvelle voix"
    return nom[:1].upper() + nom[1:]


def lister() -> list[dict]:
    voix = [{"nom": "Majordome", "slug": MAJORDOME, "origine": "decrite", "description": "le majordome d'origine",
             "pret": REF_MAJORDOME.exists()}]
    if DOSSIER.exists():
        for d in sorted(DOSSIER.iterdir()):
            meta = d / "reference.json"
            if meta.exists() and (d / "reference.wav").exists():
                m = json.loads(meta.read_text(encoding="utf-8"))
                voix.append({"nom": m.get("nom", d.name), "slug": d.name, "origine": m.get("origine", "decrite"),
                             "description": m.get("description_fr", m.get("description", "")), "pret": True,
                             "cree_le": m.get("cree_le"), "creation_s": m.get("creation_s")})
    return voix


def trouver(nom: str) -> dict | None:
    s = _slug(nom)
    voix = lister()
    return next((v for v in voix if v["slug"] == s or _slug(v["nom"]) == s), None) \
        or next((v for v in voix if s and (s in v["slug"] or v["slug"] in s)), None)


def actuelle() -> str:
    """Le slug de la voix rejouée par le moteur majordome."""
    ref = Path(CONFIG.get("voix", {}).get("majordome", {}).get("reference") or REF_MAJORDOME)
    return MAJORDOME if ref.resolve() == REF_MAJORDOME.resolve() else ref.parent.name


def verifier_description(description: str, juge=None) -> None:
    """Lève Refus si la description vise une personne réelle. `juge(consigne, texte, format)` : le cerveau."""
    d = description.strip()
    if len(d) < 4:
        raise Refus("décrivez la voix en quelques mots (grave, douce, rapide…)")
    m = _IMITATION.search(d)
    if m and not any(w in _COURANTS_MAJ for w in m.group(0).split()[1:]):
        raise Refus("je n'imite pas la voix de quelqu'un : décrivez plutôt ses qualités (grave, posée, rauque…)")
    if juge:
        try:
            r = json.loads(juge(CONSIGNE_JUGE, d, SCHEMA_JUGE))
        except Exception:
            return                                   # cerveau indisponible : les mots sûrs ont déjà parlé
        if r.get("interdite"):
            raise Refus("je n'imite pas une personne réelle : décrivez plutôt les qualités de la voix")


def _ecrire_config(**champs):
    """voix.moteur et voix.majordome.reference, dans CONFIG et dans config.json."""
    chemin = RACINE / "config.json"
    fichier = json.loads(chemin.read_text(encoding="utf-8"))
    for cible in (CONFIG, fichier):
        v = cible.setdefault("voix", {})
        if "moteur" in champs:
            v["moteur"] = champs["moteur"]
        if "reference" in champs:
            v.setdefault("majordome", {})["reference"] = champs["reference"]
    chemin.write_text(json.dumps(fichier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def choisir(nom: str) -> dict:
    """Passe sur une voix (créée, clonée ou le majordome). Le moteur repart avec sa référence, en fond."""
    v = nom if isinstance(nom, dict) else trouver(nom)
    if not v:
        raise Refus(f"je ne connais pas de voix « {nom} »")
    ref = REF_MAJORDOME if v["slug"] == MAJORDOME else DOSSIER / v["slug"] / "reference.wav"
    _ecrire_config(moteur="majordome", reference=str(ref))
    from . import majordome
    if majordome.MAJORDOME.actif:
        majordome.MAJORDOME.arreter()
    majordome.suivre_moteur("majordome")
    return v


def _python() -> str:
    from . import majordome
    return majordome._python()


def creer(description: str, nom: str | None = None, cerveau=None, sur_etape=None, essais: int = 6) -> dict:
    """Crée une voix et la rend (sans la choisir). Long : trois à quatre minutes. `cerveau` : CERVEAU (juge,
    traduction, puis rendu de la carte) ; sans lui, la description part telle quelle (tests sans modèle)."""
    sur_etape = sur_etape or (lambda e: None)
    juge = (lambda c, t, f: cerveau.generer(c, t, format=f, temperature=0, rechauffer=False)) if cerveau else None
    verifier_description(description, juge)
    nom = (nom or nom_depuis(description)).strip()[:30]
    slug = _slug(nom)
    if slug == MAJORDOME:
        raise Refus("ce nom est déjà celui du majordome")
    if not _python():
        raise Refus("le Python de Qwen3-TTS est introuvable (voix.majordome.python)")
    anglais = description
    if cerveau:
        try:
            anglais = " ".join(cerveau.generer(CONSIGNE_ANGLAIS, description, temperature=0.2, rechauffer=False).split())[:600]
        except Exception:
            anglais = f"{description}. Speaks French fluently. Clean studio recording, close microphone, no background noise, no music."
    dossier = DOSSIER / slug
    if dossier.exists():
        shutil.rmtree(dossier)                       # recréer une voix du même nom la remplace
    dossier.mkdir(parents=True)
    (dossier / "reference.json").write_text(json.dumps(
        {"nom": nom, "description_fr": description, "origine": "decrite"}, ensure_ascii=False, indent=1), encoding="utf-8")
    from . import carte, majordome
    t0 = time.time()
    etapes = []
    with carte.Occupation("création d'une voix"):
        if cerveau:
            cerveau.decharger()
        majordome.MAJORDOME.arreter()                # la voix en service rend aussi sa place
        import os
        proc = subprocess.Popen([_python(), str(RACINE / "jarvis" / "voix_qwen" / "creer_voix.py"), "--dossier", str(dossier),
                                 "--description", anglais, "--essais", str(essais)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for ligne in proc.stdout:
                if ligne.startswith("@@"):
                    e = json.loads(ligne[2:])
                    etapes.append(e)
                    sur_etape(e)
            proc.wait(CREATION_MAX_S)
        except Exception:
            shutil.rmtree(dossier, ignore_errors=True)       # une création ratée ne laisse pas de dossier à moitié fait
            raise
        finally:
            if proc.poll() is None:
                proc.kill()
    fin = next((e for e in reversed(etapes) if e.get("etape") == "fini"), None)
    if proc.returncode != 0 or not fin:
        shutil.rmtree(dossier, ignore_errors=True)
        raise RuntimeError("la création de la voix a échoué" + (f" à l'étape « {etapes[-1]['etape']} »" if etapes else ""))
    meta = json.loads((dossier / "reference.json").read_text(encoding="utf-8"))
    meta.update(nom=nom, description_fr=description, description=anglais, origine="decrite",
                total_s=round(time.time() - t0, 1))
    (dossier / "reference.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"nom": nom, "slug": slug, "description": description, "anglais": anglais, **{k: fin[k] for k in fin if k != "etape"},
            "total_s": meta["total_s"]}


def cloner(nom: str, audio, accord: bool, transcrire=None) -> dict:
    """Une voix depuis un enregistrement (fichier WAV/MP3/OGG, ou tableau 16 kHz). Refusé sans l'accord coché.
    `transcrire(audio) -> texte` : Whisper des oreilles (le texte de la référence doit être ce qui est dit)."""
    if accord is not True:
        raise Refus("cochez « c'est ma voix, ou j'ai l'accord écrit de la personne » pour cloner un enregistrement")
    nom = (nom or "Ma voix").strip()[:30]
    slug = _slug(nom)
    if slug == MAJORDOME:
        raise Refus("ce nom est déjà celui du majordome")
    import numpy as np
    import soundfile
    from faster_whisper.audio import decode_audio
    onde = audio if isinstance(audio, np.ndarray) else decode_audio(str(audio), sampling_rate=16000)
    duree = len(onde) / 16000
    if not 4 <= duree <= 40:
        raise Refus(f"il faut un enregistrement de 5 à 30 secondes (celui-ci dure {duree:.0f} s)")
    if transcrire is None:
        from . import oreilles
        transcrire = oreilles.transcrire
    texte = transcrire(onde.astype(np.float32))
    if len(texte.split()) < 4:
        raise Refus("je n'entends pas assez de paroles dans cet enregistrement")
    dossier = DOSSIER / slug
    if dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)
    soundfile.write(dossier / "reference.wav", onde.astype(np.float32), 16000)
    (dossier / "reference.txt").write_text(texte + "\n", encoding="utf-8")
    from .voix_qwen import reecoute
    meta = {"nom": nom, "origine": "enregistrement", "texte": texte, "duree_s": round(duree, 1),
            "hauteur_hz": round(reecoute.hauteur(onde.astype(np.float32), 16000)),
            "accord": {"coche": True, "le": time.strftime("%Y-%m-%d %H:%M"),
                       "texte": "C'est ma voix, ou j'ai l'accord écrit de la personne enregistrée."},
            "cree_le": time.strftime("%Y-%m-%d %H:%M")}
    (dossier / "reference.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"nom": nom, "slug": slug, "texte": texte, "duree_s": meta["duree_s"]}


def creer_en_fond(description: str, nom: str | None, cerveau, emettre, dire) -> None:
    """La commande vocale : la création tourne en fond (trois à quatre minutes), le HUD suit les étapes, puis la
    nouvelle voix est choisie et se présente elle-même."""
    def travail():
        def etape(e):
            emettre({"type": "voix_creation", "t": time.time(), **e})
        try:
            v = creer(description, nom, cerveau, etape)
            choisir(v["nom"])
            emettre({"type": "voix_creation", "t": time.time(), "etape": "choisie", "nom": v["nom"], "total_s": v["total_s"]})
            dire(f"Voici ma nouvelle voix : {v['nom'].lower()}. Elle vous plaît ?")
        except Refus as e:
            dire(f"Je ne peux pas : {e}.")
        except Exception as e:                       # noqa: BLE001
            emettre({"type": "voix_creation", "t": time.time(), "etape": "erreur", "message": str(e)})
            dire(f"La création de la voix a échoué : {e}.")
    threading.Thread(target=travail, daemon=True, name="creation-voix").start()
