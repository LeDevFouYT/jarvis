"""workspace/mesures/crypto.json : les chiffres mesurés de chaque brique, pour le montage de la vidéo.
Chaque brique écrit sa section (`ecrire("1_cours", resultat_test="12/12", ...)`) ; le reste du fichier est gardé."""
import json
import threading

from ..config import RACINE

FICHIER = RACINE / "workspace" / "mesures" / "crypto.json"
_verrou = threading.Lock()


def lire() -> dict:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return {"briques": {}}


def ecrire(section: str, **champs) -> dict:
    """Fusionne `champs` dans briques[section] (un dict y est fusionné, pas remplacé, sur un niveau)."""
    with _verrou:
        donnees = lire()
        cible = donnees.setdefault("briques", {}).setdefault(section, {})
        for cle, valeur in champs.items():
            if isinstance(valeur, dict) and isinstance(cible.get(cle), dict):
                cible[cle] = {**cible[cle], **valeur}
            else:
                cible[cle] = valeur
        FICHIER.parent.mkdir(parents=True, exist_ok=True)
        temporaire = FICHIER.with_suffix(".tmp")
        temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        temporaire.replace(FICHIER)
        return cible
