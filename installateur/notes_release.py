"""Les notes d'une release publique : python installateur/notes_release.py VERSION [fichier_commit_modifies]

Si NOUVEAUTES.md a changé dans ce push, la release reprend sa première section (le texte écrit pour le public).
Sinon, une note courte : le titre du commit, sans aucune ligne technique ni mention d'outil (Co-Authored-By…).
Toujours suivi de la façon d'installer ou de mettre à jour."""
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

PIED = """
---

### ⬇️ Installer ou mettre à jour

- **Nouveau** : téléchargez `Jarvis-Installateur.exe` ci-dessous et lancez-le. Il examine votre PC et installe tout, sans droits administrateur.
- **Déjà installé** : rien à faire, Jarvis se met à jour tout seul au prochain lancement. Vos réglages, souvenirs et fichiers ne sont jamais touchés.
- **Développeur** : le code est juste au-dessus, licence MIT.
"""


def premiere_section(texte: str) -> str:
    morceaux = re.split(r"(?m)^## ", texte)
    return ("## " + morceaux[1]).strip() if len(morceaux) > 1 else texte.strip()


def nettoyer(message: str) -> str:
    lignes = [l for l in message.splitlines() if not re.match(r"\s*(co-authored-by|signed-off-by|generated with)", l, re.IGNORECASE)]
    return "\n".join(lignes).strip()


def notes(version: str) -> str:
    try:
        modifies = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=RACINE, capture_output=True, text=True).stdout
    except OSError:
        modifies = ""
    nouveautes = RACINE / "NOUVEAUTES.md"
    if "NOUVEAUTES.md" in modifies.split() and nouveautes.exists():
        corps = premiere_section(nouveautes.read_text(encoding="utf-8"))
    else:
        titre = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=RACINE, capture_output=True, text=True, encoding="utf-8").stdout
        corps = f"## Jarvis {version}\n\n🔧 {nettoyer(titre)}"
    return corps + "\n" + PIED


if __name__ == "__main__":
    texte = notes(sys.argv[1] if len(sys.argv) > 1 else "")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(texte, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(texte)
