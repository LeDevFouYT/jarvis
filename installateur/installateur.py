"""L'installateur de Jarvis : un seul .exe (construit par construire.bat avec Nuitka, compilation native) qui
  1. examine la machine (carte NVIDIA, VRAM, mémoire, disque) et dit si Jarvis tourne en local, en version
     réduite, ou s'il faut le cerveau distant (RunPod à travers la passerelle payante) ;
  2. installe tout dans un dossier au choix, sans droits administrateur : Python embarqué, dépendances,
     voix Kokoro, Ollama (installateur officiel silencieux, seulement en local), fichiers de Jarvis ;
  3. règle config.json selon le verdict (et enregistre le jeton d'accès en mode cloud) ;
  4. crée un raccourci sur le Bureau et propose de lancer Jarvis.
Tout est journalisé dans installation.log dans le dossier choisi."""
import ctypes  # noqa: F401  (utilisé par jarvis/machine chargé à l'exécution : Nuitka doit l'embarquer)
import ctypes.wintypes  # noqa: F401
import json
import os
import platform  # noqa: F401  (idem)
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
import webbrowser
import zipfile
from pathlib import Path
from tkinter import filedialog, ttk

def _trouver_charge() -> Path:
    """La charge utile : un dossier `charge/` à côté du script (développement), ou `charge.zip` embarqué dans
    l'exe par Nuitka (qui refuse d'embarquer des .pyc comme données), dézippé dans un dossier temporaire."""
    import tempfile
    ici = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if (ici / "charge" / "jarvis").exists():
        return ici / "charge"
    zip_charge = ici / "charge.zip"
    if zip_charge.exists():
        dossier = Path(tempfile.mkdtemp(prefix="jarvis_charge_"))
        with zipfile.ZipFile(zip_charge) as z:
            z.extractall(dossier)
        return dossier / "charge"
    raise SystemExit(f"charge utile introuvable dans {ici}")


CHARGE = _trouver_charge()


def _charger_machine():
    """jarvis/machine (l'examen de la machine) chargé directement depuis la charge utile, .pyc ou .py :
    l'exe compilé par Nuitka n'a pas le paquet jarvis, et machine.py n'a que des dépendances standard."""
    import importlib.machinery
    import importlib.util
    dossier = CHARGE / "jarvis"
    for nom, chargeur in (("machine.pyc", importlib.machinery.SourcelessFileLoader), ("machine.py", importlib.machinery.SourceFileLoader)):
        chemin = dossier / nom
        if chemin.exists():
            spec = importlib.util.spec_from_file_location("jarvis_machine", str(chemin), loader=chargeur("jarvis_machine", str(chemin)))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise SystemExit(f"charge utile incomplète : {dossier}")


machine = _charger_machine()

PARAMETRES = json.loads((CHARGE / "parametres.json").read_text(encoding="utf-8"))
PYTHON_VERSION = PARAMETRES.get("python_version", "3.12.10")
URL_PYTHON = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
URL_GETPIP = "https://bootstrap.pypa.io/get-pip.py"
URL_OLLAMA = "https://ollama.com/download/OllamaSetup.exe"
KOKORO = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
FICHIERS = ["jarvis", "config.example.json", "requirements.txt", "lancer.bat", "installer.bat", "cloud.bat", "README.md", ".secrets.example", "version.json"]
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Installateur(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Installation de Jarvis")
        self.geometry("780x640")
        self.configure(bg="#050a12")
        self.resizable(False, False)
        self.messages = queue.Queue()
        self.examen = machine.examiner(os.environ.get("LOCALAPPDATA", "C:\\"))
        self._construire()
        self.after(100, self._vider_messages)

    # --- fenêtre ---
    def _construire(self):
        fg, bg, cyan = "#cfeefa", "#050a12", "#5fe3ff"
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor="#0f2233", background=cyan)
        tk.Label(self, text="J.A.R.V.I.S.", fg=cyan, bg=bg, font=("Segoe UI", 22, "bold")).pack(pady=(18, 0))
        tk.Label(self, text="assistant vocal local", fg="#4f8397", bg=bg, font=("Segoe UI", 10)).pack()

        cadre = tk.Frame(self, bg="#08131f", highlightbackground="#1a7d99", highlightthickness=1)
        cadre.pack(fill="x", padx=24, pady=14)
        e = self.examen
        couleur = {"local_complet": cyan, "local_reduit": "#ffb454", "cloud": "#ffb454"}[e["verdict"]]
        titre = {"local_complet": "Cette machine peut faire tourner Jarvis en local, version complète.",
                 "local_reduit": "Cette machine peut faire tourner Jarvis en local, version réduite.",
                 "cloud": "Cette machine ne peut pas faire tourner le cerveau en local : mode cloud (facturé)."}[e["verdict"]]
        tk.Label(cadre, text=titre, fg=couleur, bg="#08131f", font=("Segoe UI", 11, "bold"), wraplength=700, justify="left").pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(cadre, text=machine.resume(e), fg=fg, bg="#08131f", font=("Segoe UI", 9), wraplength=700, justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        ligne = tk.Frame(self, bg=bg)
        ligne.pack(fill="x", padx=24)
        tk.Label(ligne, text="Dossier d'installation", fg="#4f8397", bg=bg, font=("Segoe UI", 9)).pack(anchor="w")
        self.dossier = tk.StringVar(value=str(Path(os.environ.get("LOCALAPPDATA", "C:\\")) / "Jarvis"))
        tk.Entry(ligne, textvariable=self.dossier, bg="#0f2233", fg=fg, insertbackground=fg, relief="flat", font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=5)
        tk.Button(ligne, text="Parcourir", command=self._parcourir, bg="#0f2233", fg=cyan, relief="flat", padx=10).pack(side="left", padx=(8, 0))

        if e["verdict"] == "cloud":
            ligne2 = tk.Frame(self, bg=bg)
            ligne2.pack(fill="x", padx=24, pady=(10, 0))
            tk.Label(ligne2, text="Jeton d'accès Jarvis Cloud (reçu après achat)", fg="#4f8397", bg=bg, font=("Segoe UI", 9)).pack(anchor="w")
            self.jeton = tk.StringVar()
            tk.Entry(ligne2, textvariable=self.jeton, bg="#0f2233", fg=fg, insertbackground=fg, relief="flat", font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=5)
            tk.Button(ligne2, text="Acheter du crédit", command=lambda: webbrowser.open(PARAMETRES.get("url_boutique", "")),
                      bg="#0f2233", fg="#ffb454", relief="flat", padx=10).pack(side="left", padx=(8, 0))
        else:
            self.jeton = tk.StringVar()

        self.bouton = tk.Button(self, text="Installer", command=self._demarrer, bg="#1a7d99", fg="#ffffff", relief="flat",
                                font=("Segoe UI", 12, "bold"), padx=28, pady=6)
        self.bouton.pack(pady=14)
        self.progres = ttk.Progressbar(self, mode="indeterminate", length=730)
        self.progres.pack(padx=24)
        self.journal = tk.Text(self, height=13, bg="#020609", fg="#9fd3e6", relief="flat", font=("Consolas", 9), state="disabled")
        self.journal.pack(fill="both", expand=True, padx=24, pady=(10, 18))

    def _parcourir(self):
        d = filedialog.askdirectory(title="Dossier d'installation de Jarvis")
        if d:
            self.dossier.set(str(Path(d) / "Jarvis") if Path(d).name.lower() != "jarvis" else d)

    def dire(self, texte: str):
        self.messages.put(texte)

    def _vider_messages(self):
        try:
            while True:
                m = self.messages.get_nowait()
                self.journal.configure(state="normal")
                self.journal.insert("end", m + "\n")
                self.journal.see("end")
                self.journal.configure(state="disabled")
                if hasattr(self, "fichier_journal"):
                    self.fichier_journal.write(m + "\n")
                    self.fichier_journal.flush()
        except queue.Empty:
            pass
        self.after(100, self._vider_messages)

    # --- installation ---
    def _demarrer(self):
        self.bouton.configure(state="disabled", text="Installation en cours…")
        self.progres.start(12)
        threading.Thread(target=self._installer, daemon=True).start()

    def _telecharger(self, url: str, cible: Path, libelle: str):
        self.dire(f"Téléchargement de {libelle}…")
        cible.parent.mkdir(parents=True, exist_ok=True)
        dernier = [-1]

        def progres(blocs, taille, total):
            if total > 0:
                pct = min(100, blocs * taille * 100 // total)
                if pct // 10 != dernier[0]:
                    dernier[0] = pct // 10
                    self.dire(f"    {libelle} : {pct} %")
        urllib.request.urlretrieve(url, cible, progres)

    def _lancer(self, commande: list, cwd: Path, libelle: str):
        self.dire(f"{libelle}…")
        p = subprocess.Popen(commande, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", creationflags=SANS_FENETRE)
        for ligne in p.stdout:
            ligne = ligne.rstrip()
            if ligne and not ligne.startswith(("  ", "WARNING")):
                self.dire("    " + ligne[:140])
        p.wait()
        if p.returncode != 0:
            raise RuntimeError(f"{libelle} : code {p.returncode}")

    def _installer(self):
        try:
            racine = Path(self.dossier.get())
            racine.mkdir(parents=True, exist_ok=True)
            self.fichier_journal = (racine / "installation.log").open("a", encoding="utf-8")
            self.dire(f"Installation dans {racine}")
            self.dire(machine.resume(self.examen))

            # 1. les fichiers de Jarvis
            for nom in FICHIERS:
                src, dst = CHARGE / nom, racine / nom
                if src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))   # tests inclus : « python -m jarvis dire / ecouter » en dépendent
                elif src.exists():
                    shutil.copy2(src, dst)
            self.dire("Fichiers de Jarvis copiés.")

            # 2. Python embarqué
            py_dir = racine / "python"
            py = py_dir / "python.exe"
            if not py.exists():
                zip_py = racine / "python-embed.zip"
                self._telecharger(URL_PYTHON, zip_py, f"Python {PYTHON_VERSION}")
                with zipfile.ZipFile(zip_py) as z:
                    z.extractall(py_dir)
                zip_py.unlink()
                pth = next(py_dir.glob("python3*._pth"))
                pth.write_text(pth.read_text(encoding="utf-8").replace("#import site", "import site") + "\n..\n", encoding="utf-8")
                self.dire("Python embarqué installé.")
            getpip = racine / "get-pip.py"
            if not (py_dir / "Scripts" / "pip.exe").exists():
                self._telecharger(URL_GETPIP, getpip, "pip")
                self._lancer([str(py), str(getpip), "--no-warn-script-location", "-q"], racine, "Installation de pip")
                getpip.unlink(missing_ok=True)

            # 3. les dépendances (long la première fois : cuDNN et cuBLAS font 1 Go)
            self._lancer([str(py), "-m", "pip", "install", "-r", "requirements.txt", "--no-warn-script-location",
                          "--progress-bar", "off"], racine, "Installation des dépendances (plusieurs minutes)")

            # 4. la voix Kokoro
            for nom, url in KOKORO.items():
                cible = racine / "modeles" / "kokoro" / nom
                if not cible.exists():
                    self._telecharger(url, cible, f"voix Kokoro ({nom})")

            # 5. Ollama, seulement pour le local
            if self.examen["verdict"] != "cloud" and not shutil.which("ollama") \
                    and not (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe").exists():
                setup = racine / "OllamaSetup.exe"
                self._telecharger(URL_OLLAMA, setup, "Ollama")
                self.dire("Installation d'Ollama (fenêtre silencieuse, une minute)…")
                subprocess.run([str(setup), "/VERYSILENT", "/NORESTART"], timeout=600)
                setup.unlink(missing_ok=True)
                self.dire("Ollama installé. Les modèles se téléchargeront au premier lancement.")

            # 6. la configuration
            config = json.loads((racine / "config.example.json").read_text(encoding="utf-8"))
            if (racine / "config.json").exists():
                config = json.loads((racine / "config.json").read_text(encoding="utf-8"))
            machine.appliquer(config, self.examen, PARAMETRES.get("url_passerelle", ""), self.jeton.get().strip(),
                              PARAMETRES.get("url_annuaire", ""))
            (racine / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            if not (racine / ".secrets").exists():
                shutil.copy2(racine / ".secrets.example", racine / ".secrets")
            self.dire(f"config.json réglé : cerveau {config['cerveau']['modele']} en mode {config['cerveau']['mode']}.")

            # 7. raccourci sur le Bureau
            try:
                bureau = Path(os.environ["USERPROFILE"]) / "Desktop"
                script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{bureau / 'Jarvis.lnk'}');"
                          f"$s.TargetPath='{racine / 'lancer.bat'}';$s.WorkingDirectory='{racine}';$s.Save()")
                subprocess.run(["powershell", "-NoProfile", "-Command", script], timeout=30, creationflags=SANS_FENETRE)
                self.dire("Raccourci « Jarvis » créé sur le Bureau.")
            except Exception:
                self.dire("Raccourci non créé (lancer.bat dans le dossier fait la même chose).")

            self.dire("\nInstallation terminée. Au premier lancement, les modèles se téléchargent (plusieurs Go)."
                      if self.examen["verdict"] != "cloud" else
                      "\nInstallation terminée. Le cerveau est distant : vérifiez votre jeton dans config.json (cerveau.cloud.jeton).")
            self.after(0, self._termine, racine)
        except Exception as e:
            self.dire(f"\nERREUR : {type(e).__name__} : {e}")
            self.after(0, self._echec)

    def _termine(self, racine: Path):
        self.progres.stop()
        self.bouton.configure(state="normal", text="Lancer Jarvis", command=lambda: self._lancer_jarvis(racine))

    def _echec(self):
        self.progres.stop()
        self.bouton.configure(state="normal", text="Réessayer", command=self._demarrer)

    def _lancer_jarvis(self, racine: Path):
        subprocess.Popen(["cmd", "/c", "start", "", str(racine / "lancer.bat")], cwd=str(racine))
        self.after(800, self.destroy)


class InstallateurAuto:
    """Mode sans fenêtre : Jarvis-Installateur.exe --auto <dossier> [jeton]. Journal dans <dossier>/installation.log."""

    def __init__(self, dossier: str, jeton: str = ""):
        self.examen = machine.examiner(dossier)
        self.dossier = type("V", (), {"get": staticmethod(lambda: dossier)})()
        self.jeton = type("V", (), {"get": staticmethod(lambda: jeton)})()
        self.messages = queue.Queue()

    def dire(self, texte: str):
        if hasattr(self, "fichier_journal"):
            self.fichier_journal.write(texte + "\n")
            self.fichier_journal.flush()

    def after(self, _delai, fonction, *args):
        if fonction is not self._lancer_jarvis:
            fonction(*args)

    def _termine(self, racine):
        self.dire("TERMINE")

    def _echec(self):
        self.dire("ECHEC")

    def _lancer_jarvis(self, racine):
        pass

    _telecharger = Installateur._telecharger
    _lancer = Installateur._lancer
    _installer = Installateur._installer


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--auto":
        InstallateurAuto(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")._installer()
    else:
        Installateur().mainloop()
