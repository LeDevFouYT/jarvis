"""Fabrique la charge utile et le paquet de mise à jour, localement (construire.bat) ou dans l'action GitHub.
  python installateur/paquet.py --version 1.0.12
Produit : installateur/charge/ (fichiers de Jarvis, code en .pyc), installateur/charge.zip (embarqué dans l'exe),
installateur/dist/mise_a_jour.zip (le même contenu, téléchargé par les Jarvis installés), installateur/dist/version.json
(manifeste : version, adresse du zip, empreinte SHA-256, notes), installateur/dist/Jarvis-Source.zip n'est PAS produit ici
(le code vendu part du dépôt privé, voir la passerelle)."""
import argparse
import compileall
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CHARGE = RACINE / "installateur" / "charge"
DIST = RACINE / "installateur" / "dist"
FICHIERS = ["config.example.json", "requirements.txt", "lancer.bat", "installer.bat", "cloud.bat", "README.md", ".secrets.example"]
DEPOT_PUBLIC = "LeDevFouYT/jarvis"


def construire(version: str, notes: str = "") -> dict:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Python 3.12 obligatoire : les .pyc doivent correspondre au Python embarqué")
    if CHARGE.exists():
        shutil.rmtree(CHARGE)
    shutil.copytree(RACINE / "jarvis", CHARGE / "jarvis", ignore=shutil.ignore_patterns("__pycache__"))
    for nom in FICHIERS:
        shutil.copy2(RACINE / nom, CHARGE / nom)
    shutil.copy2(RACINE / "installateur" / "parametres.json", CHARGE / "parametres.json")
    (CHARGE / "version.json").write_text(json.dumps({"version": version, "date": time.strftime("%Y-%m-%d"), "notes": notes},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    # le code livré en bytecode seulement
    if not compileall.compile_dir(str(CHARGE / "jarvis"), quiet=1, legacy=True, force=True):
        raise SystemExit("compilation échouée")
    for py in (CHARGE / "jarvis").rglob("*.py"):
        py.unlink()
    for cache in (CHARGE / "jarvis").rglob("__pycache__"):
        shutil.rmtree(cache)
    # charge.zip (dans l'exe) et mise_a_jour.zip (téléchargé par les clients) : même contenu
    DIST.mkdir(parents=True, exist_ok=True)
    zip_charge = shutil.make_archive(str(RACINE / "installateur" / "charge"), "zip", RACINE / "installateur", "charge")
    zip_maj = DIST / "mise_a_jour.zip"
    shutil.copy2(zip_charge, zip_maj)
    sha = hashlib.sha256(zip_maj.read_bytes()).hexdigest()
    manifeste = {"version": version, "date": time.strftime("%Y-%m-%d"), "notes": notes,
                 "zip": f"https://github.com/{DEPOT_PUBLIC}/releases/download/v{version}/mise_a_jour.zip",
                 "sha256": sha, "exe": f"https://github.com/{DEPOT_PUBLIC}/releases/download/v{version}/Jarvis-Installateur.exe"}
    (DIST / "version.json").write_text(json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifeste


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--version", required=True)
    a.add_argument("--notes", default="")
    args = a.parse_args()
    notes = args.notes
    if not notes:
        try:
            notes = subprocess.run(["git", "log", "-1", "--pretty=%s"], capture_output=True, text=True, cwd=RACINE).stdout.strip()
        except Exception:
            pass
    m = construire(args.version, notes)
    print(json.dumps({k: m[k] for k in ("version", "sha256", "zip")}, ensure_ascii=False))
