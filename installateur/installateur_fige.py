"""L'installateur figé : le même Jarvis-Installateur.exe, octet pour octet, à chaque release.

Pourquoi : un installateur reconstruit à chaque version change d'empreinte, et Microsoft Defender (détection par
apprentissage automatique, « Wacatac.B!ml ») comme SmartScreen repartent de zéro face à un fichier inconnu. Un fichier
qui ne change pas garde la confiance acquise (faux positif déclaré une fois, téléchargements qui s'accumulent). Il
installe une version un peu ancienne, qui se met à jour toute seule au premier lancement (mise_a_jour.py).

On ne reconstruit que si l'installation elle-même change : les fichiers d'ENTREES ci-dessous. Alors l'action construit
un nouvel installateur, et il faut 1) le déclarer à Microsoft (microsoft.com/wdsi/filesubmission), 2) le figer en
mettant sa version, son empreinte et `entrees` dans installateur_fige.json (python installateur/installateur_fige.py
--figer <version>).

    python installateur/installateur_fige.py                 code 0 : l'installateur figé est dans dist/
                                                             code 2 : l'installation a changé, il faut construire
    python installateur/installateur_fige.py --figer 1.0.25  fige la release publiée 1.0.25"""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
FICHE = ICI / "installateur_fige.json"
DIST = ICI / "dist" / "Jarvis-Installateur.exe"
DEPOT = "LeDevFouYT/jarvis"
# ce qui change l'installateur lui-même (pas le code de Jarvis, qui arrive par la mise à jour)
ENTREES = ["installateur/jarvis.iss", "installateur/etapes.py", "installateur/python_embarque.py",
           "installateur/parametres.json", "requirements.txt"]


def empreinte_entrees() -> str:
    h = hashlib.sha256()
    for nom in ENTREES:
        h.update(nom.encode())
        h.update((RACINE / nom).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def telecharger(version: str) -> bytes:
    url = f"https://github.com/{DEPOT}/releases/download/v{version}/Jarvis-Installateur.exe"
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def figer(version: str):
    exe = telecharger(version)
    fiche = {"version": version, "sha256": hashlib.sha256(exe).hexdigest(), "entrees": empreinte_entrees()}
    FICHE.write_text(json.dumps(fiche, indent=2) + "\n", encoding="utf-8")
    print(f"Installateur figé : v{version}, {len(exe) / 1e6:.1f} Mo, empreinte {fiche['sha256']}")


def recuperer() -> int:
    if not FICHE.exists():
        print("Aucun installateur figé : construction d'un nouveau.")
        return 2
    fiche = json.loads(FICHE.read_text(encoding="utf-8"))
    if fiche["entrees"] != empreinte_entrees():
        print(f"::warning::L'installation a changé depuis l'installateur figé v{fiche['version']} : nouvel installateur "
              "construit. À déclarer à Microsoft, puis à figer (installateur_fige.py --figer <version>).")
        return 2
    try:
        exe = telecharger(fiche["version"])
    except Exception as e:
        print(f"::warning::Installateur figé v{fiche['version']} introuvable ({e}) : construction d'un nouveau.")
        return 2
    if hashlib.sha256(exe).hexdigest() != fiche["sha256"]:
        print(f"::warning::L'installateur v{fiche['version']} en ligne ne correspond plus à son empreinte : construction d'un nouveau.")
        return 2
    DIST.parent.mkdir(parents=True, exist_ok=True)
    DIST.write_bytes(exe)
    print(f"Installateur figé réutilisé : v{fiche['version']}, empreinte {fiche['sha256'][:16]}… (même fichier que les versions précédentes)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--figer":
        figer(sys.argv[2])
    else:
        sys.exit(recuperer())
