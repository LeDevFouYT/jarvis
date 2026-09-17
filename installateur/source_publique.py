"""Prépare l'arbre du code public (dépôt LeDevFouYT/jarvis) à partir du dépôt privé.

Le code de Jarvis est gratuit et public (licence AGPL v3, licence commerciale en option) ; restent privés le serveur de paiement (`passerelle/`),
les notes de travail (`CLAUDE.md`), la configuration personnelle (`config.json`) et l'action de publication.
Appelé par l'action GitHub à chaque version, ou à la main :

    python installateur/source_publique.py <dossier de destination>

Le dossier reçoit les fichiers à publier ; ce qui s'y trouvait déjà et qui n'est pas publié (docs/, .git) est gardé."""
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
EXCLUS = ("passerelle/", "docs/", "CLAUDE.md", "config.json", ".github/", "site/")
GARDES = {".git", "docs"}          # présents dans le dépôt public, jamais touchés ici
# rien de personnel dans le code public (écrits en morceaux : ce fichier est publié, il ne doit pas se signaler lui-même)
INTERDITS = ("Dy" + "lan", "Bece" + "rra", "chang" + "ez-moi", "Bay" + "onne")
MOI = "installateur/source_publique.py"        # ce fichier contient la liste : on ne l'inspecte pas


def fichiers_publics() -> list[str]:
    suivis = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=RACINE).stdout.split()
    return [f for f in suivis if not f.startswith(EXCLUS)] + ["LICENSE"]


def preparer(cible: Path) -> int:
    noms = fichiers_publics()
    # on efface d'abord les fichiers publiés qui n'existent plus (sans toucher à docs/ ni .git)
    for element in cible.iterdir():
        if element.name in GARDES:
            continue
        if element.is_dir():
            shutil.rmtree(element)
        else:
            element.unlink()
    for nom in noms:
        src = RACINE / nom
        if not src.exists():
            continue
        dst = cible / nom
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # le site publié sur GitHub Pages suit les sources
    if (RACINE / "site").is_dir():
        (cible / "docs").mkdir(exist_ok=True)
        for page in (RACINE / "site").glob("*.html"):
            shutil.copy2(page, cible / "docs" / page.name)
    # garde-fou : rien de personnel ne doit partir
    fautes = []
    for f in cible.rglob("*"):
        if f.is_file() and ".git" not in f.parts and f.relative_to(cible).as_posix() != MOI:
            t = f.read_text(encoding="utf-8", errors="ignore")
            fautes += [f"{f.relative_to(cible)} : {mot}" for mot in INTERDITS if mot in t]
    if fautes:
        raise SystemExit("Publication refusée, contenu personnel détecté :\n  " + "\n  ".join(fautes))
    return len(noms)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cible = Path(sys.argv[1]).resolve()
    cible.mkdir(parents=True, exist_ok=True)
    print(f"{preparer(cible)} fichiers publiables préparés dans {cible}")
