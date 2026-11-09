"""Test de la version Linux : python -m jarvis.tests.linux   (aucun modèle chargé)
Demande des utilisateurs (vidéo 5). Ce PC n'a ni WSL ni Docker (WSL demande les droits administrateur et un
redémarrage) : le vrai essai sous Linux reste à faire. Ici, sur Windows :

1. Lecture du code : aucun module ne touche à une API Windows au chargement (ctypes.windll, os.startfile, winreg…
   au niveau du module ou en argument par défaut) — c'est ce qui ferait planter `import jarvis` sous Linux.
2. Jarvis croit tourner sous Linux (`systeme_os.SYSTEME = "linux"`) : chaque pouvoir porté appelle la bonne commande
   (xdg-open, xdg-user-dir, /proc/meminfo, pactl, loginctl), interceptée sans rien exécuter ; chaque pouvoir non
   porté répond une phrase claire au lieu de planter.
3. Les scripts : installer.sh et lancer.sh passent `bash -n`, en fins de ligne LF ; pycaw ne s'installe que sous
   Windows (requirements.txt)."""
import ast
import shutil
import subprocess
import sys
from pathlib import Path

from ._commun import Verifs

from .. import systeme_os  # noqa: E402
from ..config import RACINE  # noqa: E402

WINDOWS_SEUL = ("windll", "startfile", "winreg", "msvcrt", "WinDLL", "WINFUNCTYPE")


def appels_au_chargement(fichier: Path) -> list[str]:
    """Les usages d'une API Windows exécutés à l'import : hors des fonctions, ou dans un argument par défaut."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    trouves = []

    def fouiller(noeud, ou):
        for n in ast.walk(noeud):
            if isinstance(n, ast.Attribute) and n.attr in WINDOWS_SEUL:
                trouves.append(f"{fichier.relative_to(RACINE).as_posix()}:{n.lineno} {n.attr} ({ou})")

    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.args.defaults + n.args.kw_defaults:
                if d is not None:
                    fouiller(d, "argument par défaut")
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for d in m.args.defaults:
                        fouiller(d, "argument par défaut")
                elif not isinstance(m, ast.Expr):
                    fouiller(m, "corps de classe")
        elif isinstance(n, ast.If) and "platform" in ast.unparse(n.test) or isinstance(n, (ast.Import, ast.ImportFrom)):
            continue                                       # un `if sys.platform == "win32":` est voulu
        else:
            fouiller(n, "niveau du module")
    return trouves


def main() -> int:
    v = Verifs("La version Linux · couche par système")
    v.info("WSL et Docker absents de ce PC : le vrai essai sous Linux reste à faire (voir le compte rendu)")

    # ------------------------------------------------------------------ 1. lecture du code
    modules = [p for p in (RACINE / "jarvis").rglob("*.py") if "tests" not in p.parts and "voix_qwen" not in p.parts
               and p.name not in ("superposition.py",)]
    fautes = [f for p in modules for f in appels_au_chargement(p)]
    v.ok(not fautes, f"{len(modules)} modules lus : aucune API Windows touchée au chargement", fautes[:8] or "")

    # ------------------------------------------------------------------ 2. Jarvis croit tourner sous Linux
    lances, executes = [], []
    vrai_popen, vrai_run, vrai_which = subprocess.Popen, subprocess.run, shutil.which

    class FauxProcessus:
        def __init__(self, arguments, **_):
            lances.append(list(arguments))
            self.returncode, self.stdout = 0, ""

    def faux_run(arguments, **_):
        executes.append(list(arguments))
        sorties = {"xdg-user-dir": "/home/alex/Téléchargements\n"}
        return subprocess.CompletedProcess(arguments, 0, stdout=sorties.get(arguments[0], ""), stderr="")

    systeme_os.SYSTEME = "linux"
    subprocess.Popen, subprocess.run = FauxProcessus, faux_run
    shutil.which = lambda nom: f"/usr/bin/{nom}" if nom in ("xdg-open", "pactl", "firefox", "gedit") else None
    try:
        systeme_os.ouvrir("/home/alex/facture.pdf")
        v.ok(lances[-1] == ["xdg-open", "/home/alex/facture.pdf"], "ouvrir un fichier : xdg-open", lances[-1])
        v.ok(systeme_os.dossier_connu("telechargements") == Path("/home/alex/Téléchargements")
             and executes[-1] == ["xdg-user-dir", "DOWNLOAD"], "« mes téléchargements » : xdg-user-dir, même en français")
        meminfo = "MemTotal:       32698124 kB\nMemFree:         1234 kB\n"
        v.ok(systeme_os.ram_go(meminfo) == 31.2, "la mémoire vive lue dans /proc/meminfo", systeme_os.ram_go(meminfo))
        commandes_son = []
        def son(a):
            commandes_son.append(a)
            return "Volume: front-left: 32768 /  50% / -18,06 dB" if a[1] == "get-sink-volume" else ""
        v.ok(systeme_os.volume_linux("plus", son) == "Volume réglé à 60 %."
             and ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "60%"] in commandes_son, "« monte le son » : pactl, 50 -> 60 %")
        v.ok(systeme_os.verrouiller_linux(lambda a: 0) == "Session verrouillée.", "« verrouille » : loginctl lock-session")
        from ..outils import ouvrir_application, ouvrir_site, systeme as outil_systeme
        r = ouvrir_application.lancer("firefox")
        v.ok(lances[-1] == ["/usr/bin/firefox"] and "lancé" in r, "« ouvre Firefox » : le programme par son nom", (r, lances[-1]))
        ouvrir_site._ouvrir("https://www.youtube.com")
        v.ok(lances[-1] == ["xdg-open", "https://www.youtube.com"], "« ouvre YouTube » : xdg-open")
        v.ok(outil_systeme.volume("moins").startswith("Volume réglé"), "l'outil systeme passe par pactl sous Linux")
        from ..outils import ecrire, fenetres
        from .. import superposition_pilote, vision
        absents = {"fenêtres": fenetres.executer("lister"), "frappe": ecrire.executer("bonjour"),
                   "superposition": superposition_pilote.definir(True)[1]}
        v.ok(all("Windows" in t for t in absents.values()), "les pouvoirs non portés répondent une phrase claire, sans planter", absents)
        v.ok(vision.ecrans() == [{"bbox": None, "principal": True}], "voir l'écran : tout le bureau (un seul écran sous X11)")
        from ..outils import ranger
        v.ok(ranger.resoudre("téléchargements") == Path("/home/alex/Téléchargements"), "« range mes téléchargements » trouve le dossier Linux")
    finally:
        systeme_os.SYSTEME = None
        subprocess.Popen, subprocess.run, shutil.which = vrai_popen, vrai_run, vrai_which

    # ------------------------------------------------------------------ 3. sous le vrai Windows, rien n'a changé
    # en lecture seule : les tests des fenêtres et de la dictée déplacent des fenêtres et tapent au clavier, ce qui
    # dérangerait un tournage en cours
    if sys.platform == "win32":
        import ctypes
        from ..outils import ecrire, fenetres, presse_papiers
        v.ok(isinstance(ecrire.user32, ctypes.WinDLL) and isinstance(presse_papiers.kernel32, ctypes.WinDLL),
             "sous Windows, les vraies bibliothèques (user32, kernel32) sont chargées")
        liste = fenetres.lister_fenetres()
        v.ok(len(liste) > 0, f"lister les fenêtres marche toujours ({len(liste)} fenêtres ouvertes)")
        try:
            presse_papiers.lire()
            lu = True
        except Exception as e:                               # noqa: BLE001
            lu = f"{type(e).__name__} : {e}"
        v.ok(lu is True, "lire le presse-papiers marche toujours (sans le modifier)", lu)

    # ------------------------------------------------------------------ 4. les scripts
    bash = shutil.which("bash")
    for nom in ("installer.sh", "lancer.sh"):
        brut = (RACINE / nom).read_bytes()
        ok_bash = bash and subprocess.run([bash, "-n", str(RACINE / nom)], capture_output=True).returncode == 0
        v.ok(b"\r" not in brut and ok_bash, f"{nom} : fins de ligne LF, syntaxe bash juste")
    v.ok('pycaw; sys_platform == "win32"' in (RACINE / "requirements.txt").read_text(encoding="utf-8"),
         "requirements.txt : pycaw seulement sous Windows")
    v.ok("*.sh text eol=lf" in (RACINE / ".gitattributes").read_text(encoding="utf-8"), ".gitattributes garde les .sh en LF")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
