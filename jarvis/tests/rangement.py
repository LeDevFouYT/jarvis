"""Test du pouvoir 10, rangement : python -m jarvis.tests.rangement
Sur workspace/demo_rangement : classement par type et par mois, rien de supprimé, journal écrit, « annule » remet
chaque fichier à sa place avec sa date d'origine, dossiers créés retirés ; refus des dossiers système. Le dossier de
démonstration est remis à neuf à la fin, prêt à filmer."""
import hashlib
import sys
from pathlib import Path

from ._commun import Verifs

from .. import commandes  # noqa: E402
from ..config import RACINE  # noqa: E402
from ..outils import ranger as R  # noqa: E402


def empreinte(dossier: Path) -> dict:
    return {f.name: (f.stat().st_size, int(f.stat().st_mtime), hashlib.sha1(f.read_bytes()).hexdigest())
            for f in dossier.rglob("*") if f.is_file()}


def main() -> int:
    v = Verifs("Pouvoir 10 · rangement")
    demo = R.creer_demo()
    avant = empreinte(demo)
    v.ok(len(avant) == len(R._DEMO_NOMS), "workspace/demo_rangement rempli de faux fichiers", len(avant))
    v.ok(len({m for _, m, _ in avant.values()}) > 5, "datés sur plusieurs mois")

    r = R.ranger(demo)
    v.ok(r["ok"] and r["deplaces"] == len(avant), "rangement : tous les fichiers déplacés", r["message"])
    racine = [f for f in demo.iterdir() if f.is_file()]
    v.ok(not racine, "plus aucun fichier en vrac à la racine")
    ranges = [f for f in demo.rglob("*") if f.is_file()]
    v.ok(all(len(f.relative_to(demo).parts) == 3 for f in ranges), "chaque fichier dans Type/AAAA-MM/")
    v.ok((demo / "Images").exists() and (demo / "Documents").exists() and (demo / "Autres").exists(), "familles Images, Documents, Autres…")
    v.ok(empreinte(demo) == avant, "rien de supprimé ni modifié : mêmes noms, tailles, dates et contenus")
    exemple = next(f for f in ranges if f.name == "facture_electricite_juin.pdf")
    v.ok(exemple.parent.parent.name == "Documents", "une facture PDF va dans Documents", str(exemple.relative_to(demo)))
    v.ok(Path(r["journal"]).exists(), "journal d'annulation écrit", Path(r["journal"]).name)

    v.ok(commandes.analyser("Jarvis, annule")[0] == "annuler", "« annule » est une commande")
    a = R.annuler()
    v.ok(a["ok"] and a["remis"] == len(avant), "annulation : tout est remis", a["message"])
    v.ok(sorted(f.name for f in demo.iterdir()) == sorted(avant), "les fichiers sont de retour à la racine, et les dossiers créés ont disparu")
    v.ok(empreinte(demo) == avant, "avec leurs dates et contenus d'origine")
    v.ok(not R.annuler()["ok"], "une deuxième annulation n'a plus rien à faire")

    for dossier, raison in [(Path("C:/Windows"), "système"), (Path("C:/"), "racine"), (Path.home(), "profil"),
                            (Path.home() / "AppData" / "Local", "système"), (RACINE, "Jarvis"), (Path("C:/Program Files"), "système")]:
        r = R.ranger(dossier)
        v.ok(not r["ok"] and "refuse" in r["message"], f"refus : {dossier} ({raison})", r["message"])

    v.ok(R.resoudre("téléchargements") is not None and R.resoudre("le dossier démo") == R.DEMO, "« téléchargements » et « démo » sont trouvés")
    formes = ["dossier de démonstration", "la démonstration", "demo_rangement", "Démo rangement"]
    v.ok(all(R.resoudre(f) == R.DEMO for f in formes), "le nom reformulé par le cerveau est reconnu (vu en direct : « dossier de démonstration »)",
         {f: str(R.resoudre(f)) for f in formes})
    message = R.executer("démo")
    v.ok("rangé" in message, "l'outil ranger par son nom", message)
    R.annuler()
    R.creer_demo()
    v.info("dossier de démonstration remis à neuf pour le tournage")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
