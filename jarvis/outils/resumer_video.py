"""Outil resumer_video : le résumé d'une vidéo YouTube et ses moments clés, sans clé ni compte.

1. yt-dlp télécharge l'audio seul (quelques Mo, sans ffmpeg) dans cache/videos/ ;
2. Whisper le transcrit sur la carte graphique, avec l'instant de chaque phrase ;
3. le cerveau écrit un résumé et 5 à 8 moments clés horodatés (sortie JSON). Une longue transcription est
   résumée par morceaux qui tiennent dans le contexte habituel du cerveau (le changer rechargerait le modèle),
   puis les morceaux sont fusionnés ;
4. chaque instant est recalé sur le début de la phrase transcrite la plus proche et borné à la durée réelle ;
5. panneau frise : un clic ouvre la vidéo intégrée, au bon moment.

Le résultat est gardé par identifiant de vidéo (cache/videos/<id>.json) : redemander la même vidéo est immédiat.
L'audio téléchargé est effacé dès la transcription. Réponse directe : « je lance le résumé », le résumé est dit
quand il est prêt (événement video_resume)."""
import json
import logging
import re
import threading
import time
from pathlib import Path

from ..config import RACINE

NOM = "resumer_video"
DESCRIPTION = ("Résume une vidéo YouTube à partir de son lien : un résumé et 5 à 8 moments clés horodatés, affichés sur une "
               "frise où un clic ouvre la vidéo au bon moment. Aucune clé nécessaire. Compte une à deux minutes.")
PARAMETRES = {"lien": {"type": "string", "description": "Le lien YouTube (youtube.com/watch?v=…, youtu.be/…, shorts) ou l'identifiant"}}
REQUIS = ["lien"]
DIRECT = True

CACHE = RACINE / "cache" / "videos"
DUREE_MAX = 3 * 3600                  # au-delà, la transcription serait trop longue pour un assistant vocal
MORCEAU_CARACTERES = 15000            # ~4 500 jetons : tient dans num_ctx 8192 avec la consigne et la réponse
sur_evenement = lambda e: None
journal = logging.getLogger("resumer_video")
_verrou = threading.Lock()

_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/|/v/)([A-Za-z0-9_-]{11})")

SCHEMA = {"type": "object", "properties": {
    "resume": {"type": "string"},
    "moments": {"type": "array", "items": {"type": "object", "properties": {
        "t": {"type": "string", "description": "mm:ss ou h:mm:ss, pris dans la transcription"},
        "titre": {"type": "string"}}, "required": ["t", "titre"]}}},
    "required": ["resume", "moments"]}

CONSIGNE = ("Tu résumes une vidéo à partir de sa transcription horodatée (chaque ligne commence par [mm:ss]). "
            "Réponds en français, en JSON : \"resume\" = {longueur}, clair et fidèle, sans rien inventer ni markdown ; "
            "\"moments\" = {nombre} moments clés dans l'ordre, chacun avec \"t\" = l'horodatage EXACT d'une ligne de la "
            "transcription où ce moment commence, et \"titre\" = 3 à 8 mots qui disent ce qui s'y passe. "
            "Répartis les moments sur toute la vidéo.")


def identifiant(lien: str) -> str | None:
    lien = (lien or "").strip()
    m = _ID.search(lien)
    if m:
        return m.group(1)
    return lien if re.fullmatch(r"[A-Za-z0-9_-]{11}", lien) else None


def _secondes(horodatage: str) -> float | None:
    morceaux = re.findall(r"\d+", str(horodatage))
    if not morceaux:
        return None
    valeurs = [int(x) for x in morceaux[-3:]]
    total = 0
    for v in valeurs:
        total = total * 60 + v
    return float(total)


def _mmss(secondes: float) -> str:
    s = int(round(secondes))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def telecharger_audio(vid: str) -> tuple[Path, dict]:
    import yt_dlp
    from .. import compteur
    CACHE.mkdir(parents=True, exist_ok=True)
    compteur.compter("youtube_audio")
    from ..youtube.donnees import _Silence
    options = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True, "logger": _Silence(), "format": "bestaudio[ext=m4a]/bestaudio/best",
               "outtmpl": str(CACHE / "%(id)s.audio.%(ext)s"), "match_filter": yt_dlp.utils.match_filter_func(f"duration < {DUREE_MAX}")}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True)
    if not info or not info.get("requested_downloads"):
        raise RuntimeError("vidéo trop longue ou indisponible")
    chemin = Path(info["requested_downloads"][0]["filepath"])
    return chemin, {"titre": info.get("title", ""), "chaine": info.get("channel") or info.get("uploader", ""),
                    "duree": float(info.get("duration") or 0), "publiee": info.get("upload_date", ""),
                    "integrable": info.get("playable_in_embed") is not False}


def transcrire(chemin: Path) -> tuple[list[dict], str]:
    from .. import oreilles
    oreilles.charger_whisper()
    segments, info = oreilles._whisper.transcribe(str(chemin), beam_size=1, vad_filter=True, condition_on_previous_text=False)
    lignes = [{"debut": round(s.start, 1), "fin": round(s.end, 1), "texte": s.text.strip()} for s in segments if s.text.strip()]
    return lignes, info.language


def _transcription_horodatee(segments: list[dict], pas: float = 20.0) -> list[tuple[float, str]]:
    """Les phrases regroupées par ~20 s : « [mm:ss] texte ». Assez fin pour horodater, assez court pour le contexte."""
    blocs, debut, texte = [], None, []
    for s in segments:
        if debut is None:
            debut = s["debut"]
        texte.append(s["texte"])
        if s["fin"] - debut >= pas:
            blocs.append((debut, " ".join(texte)))
            debut, texte = None, []
    if texte:
        blocs.append((debut, " ".join(texte)))
    return blocs


def _appeler_cerveau(titre: str, lignes: str, longueur: str, nombre: str) -> dict:
    from ..cerveau import CERVEAU
    brut = CERVEAU.generer(CONSIGNE.format(longueur=longueur, nombre=nombre), f"Titre : {titre}\n\nTranscription :\n{lignes}",
                           delai=240, format=SCHEMA)
    return json.loads(brut)


def resumer(titre: str, segments: list[dict], duree: float) -> dict:
    blocs = _transcription_horodatee(segments)
    lignes = [f"[{_mmss(t)}] {texte}" for t, texte in blocs]
    morceaux, courant = [], []
    for ligne in lignes:
        if courant and sum(len(x) + 1 for x in courant) + len(ligne) > MORCEAU_CARACTERES:
            morceaux.append(courant)
            courant = []
        courant.append(ligne)
    if courant:
        morceaux.append(courant)
    if len(morceaux) == 1:
        resultat = _appeler_cerveau(titre, "\n".join(morceaux[0]), "4 à 6 phrases", "5 à 8")
    else:
        # par morceaux, puis une fusion : le résumé de chaque partie devient une ligne horodatée
        parties = [_appeler_cerveau(titre, "\n".join(m), "3 phrases", "2 à 4") for m in morceaux]
        candidats = [x for p in parties for x in p.get("moments", [])]
        synthese = "\n".join(f"{m[0].split(']')[0]}] {p.get('resume', '')}" for m, p in zip(morceaux, parties))
        moments = "\n".join(f"[{x['t']}] {x['titre']}" for x in candidats)
        resultat = _appeler_cerveau(titre, f"Résumés des parties :\n{synthese}\n\nMoments proposés (en choisir 5 à 8) :\n{moments}",
                                    "5 à 7 phrases", "5 à 8")
    return {"resume": resultat.get("resume", "").strip(), "moments": caler_moments(resultat.get("moments", []), blocs, duree)}


def caler_moments(moments: list[dict], blocs: list[tuple[float, str]], duree: float) -> list[dict]:
    """Chaque instant proposé est recalé sur le bloc transcrit le plus proche (un instant inventé ne passe pas),
    borné à la durée, dédoublonné (20 s d'écart au moins), trié, 8 au plus."""
    debuts = [t for t, _ in blocs] or [0.0]
    cales = []
    for m in moments:
        t = _secondes(m.get("t", ""))
        titre = str(m.get("titre", "")).strip()
        if t is None or not titre or (duree and t > duree + 5):
            continue                                  # un instant au-delà de la vidéo est inventé : écarté, pas recalé
        t = min(debuts, key=lambda d: abs(d - t))
        if all(abs(t - c["t"]) >= 20 for c in cales):
            cales.append({"t": t, "titre": titre[:80]})
    cales.sort(key=lambda c: c["t"])
    return cales[:8]


def analyser(lien: str, progression=lambda etape: None) -> dict:
    """Le travail complet, sans le cycle de voix ni les événements (utilisé aussi par le test)."""
    vid = identifiant(lien)
    if not vid:
        raise ValueError("ce n'est pas un lien YouTube")
    cache = CACHE / f"{vid}.json"
    if cache.exists():
        donnees = json.loads(cache.read_text(encoding="utf-8"))
        donnees["depuis_cache"] = True
        return donnees
    chrono = {}
    t = time.time()
    progression("téléchargement de l'audio")
    chemin, infos = telecharger_audio(vid)
    chrono["telechargement"] = round(time.time() - t, 1)
    try:
        t = time.time()
        progression("transcription par Whisper")
        segments, langue = transcrire(chemin)
        chrono["transcription"] = round(time.time() - t, 1)
    finally:
        chemin.unlink(missing_ok=True)
    if not segments:
        raise RuntimeError("aucune parole dans cette vidéo")
    duree = infos["duree"] or segments[-1]["fin"]
    t = time.time()
    progression("résumé par le cerveau")
    resultat = resumer(infos["titre"], segments, duree)
    chrono["resume"] = round(time.time() - t, 1)
    donnees = {"id": vid, **infos, "duree": duree, "langue": langue, "segments": segments, **resultat,
               "chrono": chrono, "cree": time.time()}
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    donnees["depuis_cache"] = False
    return donnees


def panneau(d: dict):
    from . import panneaux
    panneaux.frise(f"Vidéo · {d['titre'][:70]}", [
        {"t": m["t"], "titre": m["titre"], "detail": _mmss(m["t"]),
         "url": f"https://www.youtube.com/embed/{d['id']}?start={int(m['t'])}&autoplay=1"} for m in d["moments"]],
        video={"id": d["id"], "duree": d["duree"], "resume": d["resume"], "chaine": d.get("chaine", ""),
               "lien": f"https://www.youtube.com/watch?v={d['id']}", "integrable": d.get("integrable", True)})


def executer(lien: str) -> str:
    from .. import outils
    from ..cerveau import TITRE
    vid = identifiant(lien)
    if not vid:
        return "Je n'ai pas reconnu de lien YouTube. Donnez-moi l'adresse de la vidéo."
    if not _verrou.acquire(blocking=False):
        return "Je résume déjà une vidéo, un instant."
    source = outils.source_courante()
    deja = (CACHE / f"{vid}.json").exists()

    def travail():
        debut = time.time()
        try:
            sur_evenement({"type": "video_debut", "t": time.time(), "id": vid})
            d = analyser(vid, lambda etape: sur_evenement({"type": "video_etape", "t": time.time(), "id": vid, "etape": etape}))
            panneau(d)
            sur_evenement({"type": "video_resume", "t": time.time(), "id": vid, "titre": d["titre"], "resume": d["resume"],
                           "moments": d["moments"], "duree": round(time.time() - debut, 1), "chrono": d.get("chrono", {}),
                           "depuis_cache": d["depuis_cache"], "source": source})
        except Exception as e:
            journal.exception("résumé vidéo")
            sur_evenement({"type": "video_erreur", "t": time.time(), "id": vid, "message": f"{type(e).__name__} : {e}", "source": source})
        finally:
            _verrou.release()

    threading.Thread(target=travail, daemon=True, name="video-fond").start()
    if deja:
        return f"Cette vidéo est déjà résumée, {TITRE}. Je vous la présente."
    return f"Je lance le résumé de la vidéo, {TITRE} : téléchargement du son, transcription, puis synthèse. Comptez une à deux minutes."
