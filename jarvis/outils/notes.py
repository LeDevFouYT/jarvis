"""Outils noter et lire_notes : un fichier texte dans memoire/."""
import re
from datetime import datetime
from types import SimpleNamespace

from ..config import RACINE

_NOTES = RACINE / "memoire" / "notes.txt"


def noter(texte: str) -> str:
    _NOTES.parent.mkdir(exist_ok=True)
    with _NOTES.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%d/%m/%Y %H:%M}] {texte}\n")
    return "Note enregistrée."


def lire_notes() -> str:
    from . import panneaux
    lignes = _NOTES.read_text(encoding="utf-8").strip().splitlines() if _NOTES.exists() else []
    elements = []
    for ligne in reversed(lignes[-20:]):
        m = re.match(r"\[(.+?)\]\s*(.*)", ligne)
        elements.append({"titre": m.group(2), "meta": m.group(1)} if m else {"titre": ligne})
    panneaux.liste("Notes", elements, vide="Aucune note pour l'instant.")
    return "\n".join(lignes[-20:]) if lignes else "Aucune note."


NOTER = SimpleNamespace(NOM="noter", DESCRIPTION="Enregistre une note ou un rappel écrit pour plus tard.",
                        PARAMETRES={"texte": {"type": "string"}}, REQUIS=["texte"], executer=noter)
LIRE = SimpleNamespace(NOM="lire_notes", DESCRIPTION="Relit les dernières notes enregistrées.",
                       PARAMETRES={}, REQUIS=[], executer=lire_notes)
