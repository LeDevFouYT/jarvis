"""Un client cloud a droit à tout : python -m jarvis.tests.cloud_complet

Jusqu'au 22/09, un client qui payait ses minutes se voyait refuser trois choses — la vidéo, la sculpture 3D et
les miniatures — parce qu'elles demandent une carte graphique. C'était incohérent : il paie au temps de calcul,
il doit avoir accès à tout ce que la carte sait faire.

Ces trois travaux passent désormais par la passerelle, comme les images : la machine de l'auteur calcule, le
fichier revient, le temps est décompté. Ce test joue les deux bouts sans réseau, sans carte et sans ComfyUI :

1. côté client : chaque outil bascule vers la passerelle au lieu de refuser, et range le fichier reçu ;
2. côté machine de l'auteur : l'agent reconnaît les trois travaux, prend la carte, et refuse ce qui est trop lourd ;
3. les refus restent lisibles : crédit épuisé, plafond du jour, machine éteinte ;
4. **la frontière de sécurité tient** : le travail transmis ne contient qu'une description, jamais un ordre.
"""
import base64
import sys
from pathlib import Path

from ._commun import Verifs

RACINE = Path(__file__).resolve().parents[2]


class FausseReponse:
    def __init__(self, donnees, code=200):
        self._d, self.status_code = donnees, code

    def json(self):
        return self._d


def cote_client(v: Verifs):
    """Les trois outils, en mode cloud, sans carte graphique ni réseau."""
    import threading
    import time

    from .. import cerveau
    from ..outils import generer_video, hologramme, miniatures, travaux_cloud

    envois = []

    def faux_demander(genre, corps, delai):
        envois.append({"genre": genre, "corps": corps, "delai": delai})
        if genre == "video":
            return {"mp4": base64.b64encode(b"\x00\x00\x00 ftypisom" + b"x" * 200).decode(), "secondes": 280}
        if genre == "modele3d":
            return {"glb": base64.b64encode(b"glTF" + b"y" * 200).decode(), "secondes": 340}
        return {"images": [base64.b64encode(b"\x89PNG" + b"z" * 100).decode() for _ in range(3)], "secondes": 95}

    evenements = []
    vrais = (cerveau.MODE, travaux_cloud.demander)
    anciens = {m: m.sur_evenement for m in (generer_video, hologramme, miniatures)}
    try:
        cerveau.MODE = "cloud"
        travaux_cloud.demander = faux_demander
        for m in anciens:
            m.sur_evenement = evenements.append

        phrase = generer_video.executer("une armure qui décolle", 4)
        v.ok("distante" in phrase, "la vidéo est acceptée au lieu d'être refusée", phrase)
        # un objet unique : un objet déjà sculpté sortirait du cache sans passer par la passerelle
        objet = f"objet d'essai {time.strftime('%H%M%S')}"
        phrase = hologramme.executer(objet)
        v.ok("distante" in phrase, "la sculpture 3D est acceptée", phrase)
        phrase = miniatures.executer("mon test de Jarvis", "JARVIS EN LOCAL")
        v.ok("distante" in phrase, "les miniatures sont acceptées", phrase)

        # on attend la FIN des trois travaux, pas seulement leur départ : les fichiers s'écrivent dans des fils
        finis = {"video_prete", "hologramme", "miniatures", "video_ia_erreur", "hologramme_erreur",
                 "miniatures_erreur"}
        fin = time.time() + 20
        while time.time() < fin and sum(1 for e in evenements if e.get("type") in finis) < 3:
            time.sleep(0.2)
        genres = sorted(e["genre"] for e in envois)
        v.ok(genres == ["miniatures", "modele3d", "video"], "les trois travaux partent vers la passerelle", genres)

        rates = [e for e in evenements if e.get("type", "").endswith("erreur")]
        prets = [e for e in evenements if e.get("type") in ("video_prete", "hologramme", "miniatures")]
        v.ok(len(prets) == 3 and not rates, "les trois fichiers reçus sont rangés et annoncés au HUD",
             [e.get("type") for e in evenements] if rates else f"{len(prets)}/3")
        fichiers = [Path(e["chemin"]) for e in evenements
                    if e.get("type") in ("video_prete", "hologramme") and e.get("chemin")]
        v.ok(all(f.exists() and f.stat().st_size > 100 for f in fichiers) if fichiers else False,
             "la vidéo reçue est écrite sur le disque", [f.name for f in fichiers])
        for f in fichiers:                                   # le test ne laisse rien derrière lui
            f.unlink(missing_ok=True)
        for e in evenements:                                 # ni miniature ni .glb d'essai
            for chemin in (e.get("chemins") or []):
                Path(chemin).unlink(missing_ok=True)
        # l'objet d'essai ne doit pas rester dans le cache des hologrammes (l'événement ne porte pas son chemin)
        (hologramme.DOSSIER / f"{hologramme.nom_fichier(objet)}.glb").unlink(missing_ok=True)
    finally:
        cerveau.MODE, travaux_cloud.demander = vrais
        for m, ancien in anciens.items():
            m.sur_evenement = ancien

    return envois


def frontiere(v: Verifs, envois: list):
    """Ce qui traverse ne doit être qu'une description : aucun ordre, aucun chemin, aucun code."""
    interdits = ("cmd", "powershell", "subprocess", "import ", "C:\\\\", "/etc/", "rm ", "del ", "..")
    fautes = []
    for e in envois:
        for cle, valeur in (e["corps"] or {}).items():
            if isinstance(valeur, str) and any(mot in valeur for mot in interdits):
                fautes.append(f"{e['genre']}.{cle}")
        for cle in e["corps"]:
            if cle not in ("prompt", "secondes", "objet", "sujet", "titre"):
                fautes.append(f"{e['genre']} : champ inattendu « {cle} »")
    v.ok(not fautes, "le travail transmis ne contient qu'une description, jamais un ordre", fautes or "propre")

    # et l'agent, de son côté, ne sait exécuter que ces trois travaux-là
    from .. import maison
    v.ok(sorted(maison.LOURDS) == ["miniatures", "modele3d", "video"],
         "la machine de l'auteur ne sert que ces trois travaux", sorted(maison.LOURDS))
    source = (RACINE / "jarvis" / "maison.py").read_text(encoding="utf-8")
    v.ok("subprocess" not in source and "eval(" not in source and "exec(" not in source,
         "l'agent n'a aucun moyen d'exécuter autre chose (ni subprocess, ni eval, ni exec)")
    v.ok("LIMITE_OCTETS" in source and "trop lourd" in source,
         "un fichier trop lourd est refusé proprement au lieu d'étouffer la passerelle")


def passerelle(v: Verifs):
    """Les routes ouvertes côté serveur, et leurs garde-fous."""
    source = (RACINE / "passerelle" / "serveur.py").read_text(encoding="utf-8")
    v.ok('"/travail/{genre}"' in source, "la passerelle expose une route pour les travaux lourds")
    bloc = source[source.index("async def travail_lourd("):source.index("async def travail_lourd(") + 1400]
    v.ok("_client(authorization)" in bloc, "elle vérifie le jeton du client")
    v.ok("PLAFOND_JOUR_S" in bloc, "elle applique le plafond du jour")
    v.ok("genre not in TRAVAUX_LOURDS" in bloc, "elle refuse un travail qu'elle ne connaît pas")
    v.ok("_soumettre_maison" in bloc, "elle facture le temps comme pour le reste")


def refus(v: Verifs):
    """Les messages quand ça ne peut pas marcher : ils doivent rester compréhensibles."""
    from ..outils import travaux_cloud
    for code, mot in ((402, "crédit"), (429, "plafond"), (503, "hors ligne"), (504, "pas répondu")):
        v.ok(mot in travaux_cloud.RAISONS.get(code, ""), f"HTTP {code} est traduit en français",
             travaux_cloud.RAISONS.get(code))


def main() -> int:
    v = Verifs("Cloud complet · un client qui paie a droit à tout")
    envois = cote_client(v)
    frontiere(v, envois)
    passerelle(v)
    refus(v)
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
