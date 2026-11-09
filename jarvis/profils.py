"""Les profils (vidéo 5) : un profil = prénom + voix + personnalité + armure. « Passe sur le profil Nova » change tout
d'un coup ; c'est ce qui fait exister les trois candidats du tournoi.

- Rangés dans config.json, `profils` : {clé: {nom, prenom, voix, personnalite, armure}} ; `profil` = le profil en service.
- `voix` : le nom d'une voix Qwen3-TTS (« Majordome », une voix créée) ou « Kokoro » (la voix d'origine, sur le processeur).
- « Enregistre ce profil sous le nom Nova » photographie ce qui est en service : on règle à la voix (« appelle-toi
  Nova », « mode parano », « prends la voix Orage »), puis on enregistre.
- Changer de voix Qwen recharge le moteur (≈ 30 s, mesuré le 29/10) : la phrase de confirmation peut partir en Kokoro.
"""
import json
import re
import unicodedata

from . import armures, personnalites, prenom, voix_creees
from .config import CONFIG, RACINE

KOKORO = "Kokoro"


class Refus(ValueError):
    pass


def _cle(nom: str) -> str:
    n = unicodedata.normalize("NFD", nom.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-")[:30]


def _ecrire(profils: dict | None = None, actuel: str | None = None):
    chemin = RACINE / "config.json"
    fichier = json.loads(chemin.read_text(encoding="utf-8"))
    for cible in (CONFIG, fichier):
        if profils is not None:
            cible["profils"] = profils
        if actuel is not None:
            cible["profil"] = actuel
    chemin.write_text(json.dumps(fichier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def lister() -> list[dict]:
    return list(CONFIG.get("profils", {}).values())


def trouver(nom: str) -> dict | None:
    return CONFIG.get("profils", {}).get(_cle(nom))


def voix_en_service() -> str:
    if CONFIG.get("voix", {}).get("moteur") != "majordome":
        return KOKORO
    slug = voix_creees.actuelle()
    return next((v["nom"] for v in voix_creees.lister() if v["slug"] == slug), "Majordome")


def creer(nom: str, prenom_: str | None = None, voix: str | None = None, personnalite: str | None = None,
          armure: str | None = None) -> dict:
    """Un profil ; ce qui n'est pas donné est pris de ce qui est en service."""
    nom = (nom or "").strip()
    if not _cle(nom):
        raise Refus("donnez un nom au profil")
    ok, propre = prenom.valider(prenom_ or prenom.actuel())
    if not ok:
        raise Refus(propre)
    voix = voix or voix_en_service()
    if voix != KOKORO and not voix_creees.trouver(voix):
        raise Refus(f"je ne connais pas de voix « {voix} »")
    personnalite = personnalite or personnalites.actuelle()
    if personnalite not in personnalites.PERSONNALITES:
        raise Refus(f"je ne connais pas la personnalité « {personnalite} »")
    armure = armure or armures.actuelle()
    profil = {"nom": nom, "prenom": propre, "voix": voix if voix == KOKORO else voix_creees.trouver(voix)["nom"],
              "personnalite": personnalite, "armure": armure}
    profils = dict(CONFIG.get("profils", {}))
    profils[_cle(nom)] = profil
    _ecrire(profils)
    return profil


def appliquer(nom: str) -> dict:
    """Met le profil en service : prénom, personnalité, armure tout de suite ; la voix se charge en fond."""
    p = trouver(nom)
    if not p:
        noms = ", ".join(x["nom"] for x in lister()) or "aucun"
        raise Refus(f"je ne connais pas de profil « {nom} » (profils : {noms})")
    prenom.definir(p["prenom"])
    personnalites.definir(p["personnalite"])
    armures.definir(p["armure"])
    if p["voix"] == KOKORO:
        voix_creees._ecrire_config(moteur="local")
        from . import majordome
        majordome.suivre_moteur("local")
    else:
        voix_creees.choisir(p["voix"])
    _ecrire(actuel=_cle(nom))
    return p


def actuel() -> dict | None:
    return CONFIG.get("profils", {}).get(CONFIG.get("profil", ""))
