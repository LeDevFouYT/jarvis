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
- **Développeur** : le code est juste au-dessus, licence AGPL v3 (licence commerciale sur demande).
- **Vérifier l'installateur** (« on ne lance pas un .exe sans voir ce qu'il contient », vidéo 5) : son code est
  dans `installateur/` de ce dépôt, et son empreinte SHA-256 est `{sha256}`. Sous Windows :
  `Get-FileHash Jarvis-Installateur.exe` doit donner la même.
"""


def premiere_section(texte: str) -> str:
    morceaux = re.split(r"(?m)^## ", texte)
    return ("## " + morceaux[1]).strip() if len(morceaux) > 1 else texte.strip()


def nettoyer(message: str) -> str:
    lignes = [l for l in message.splitlines() if not re.match(r"\s*(co-authored-by|signed-off-by|generated with)", l, re.IGNORECASE)]
    return "\n".join(lignes).strip()


def deja_publiee(titre: str) -> bool:
    """La section de NOUVEAUTES.md est-elle déjà dans la dernière release publique ? (09/11 : une section écrite
    dans un commit de doc, qui ne fabrique pas de version, était perdue : la release suivante prenait le titre
    technique de son commit.) Sans réponse de GitHub, on la considère publiée : on garde l'ancien comportement."""
    try:
        r = subprocess.run(["gh", "release", "view", "--repo", "LeDevFouYT/jarvis", "--json", "body", "-q", ".body"],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return True
    return r.returncode != 0 or titre in r.stdout


def notes(version: str) -> str:
    try:
        modifies = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=RACINE, capture_output=True, text=True).stdout
    except OSError:
        modifies = ""
    nouveautes = RACINE / "NOUVEAUTES.md"
    section = premiere_section(nouveautes.read_text(encoding="utf-8")) if nouveautes.exists() else ""
    if section and ("NOUVEAUTES.md" in modifies.split() or not deja_publiee(section.splitlines()[0])):
        corps = premiere_section(nouveautes.read_text(encoding="utf-8"))
    else:
        titre = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=RACINE, capture_output=True, text=True, encoding="utf-8").stdout
        corps = f"## Jarvis {version}\n\n🔧 {nettoyer(titre)}"
    import json
    fige = RACINE / "installateur" / "installateur_fige.json"
    sha = json.loads(fige.read_text(encoding="utf-8")).get("sha256", "?") if fige.exists() else "?"
    return corps + "\n" + PIED.format(sha256=sha)


if __name__ == "__main__":
    texte = notes(sys.argv[1] if len(sys.argv) > 1 else "")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(texte, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(texte)
