"""Les étapes longues de l'installation, lancées par l'installateur (Inno Setup) une fois les fichiers copiés, dans
une fenêtre visible : chaque étape est annoncée, rien ne se passe en silence.

  1. pip dans le Python embarqué (get-pip.py est livré dans l'installateur, pas téléchargé) ;
  2. les dépendances de requirements.txt (plusieurs minutes la première fois : cuDNN et cuBLAS font 1 Go) ;
  3. la voix Kokoro ;
  4. l'examen de la machine et config.json réglé selon le verdict (jeton demandé en mode cloud) ;
  5. Ollama, seulement pour le local, avec son propre installateur officiel.

Pourquoi plus de .exe « maison » : l'ancien installateur (un seul .exe compilé qui s'extrayait, téléchargeait Python,
lançait un installateur silencieux et PowerShell sans fenêtre) était classé Trojan:Win32/Wacatac.B!ml par Defender et
10 autres antivirus (VirusTotal, 18/09) : faux positif d'apprentissage automatique, mais il bloquait l'installation.

Uniquement la bibliothèque standard : ce script tourne avant l'installation des dépendances.
    python\\python.exe etapes_installation.py [--sans-pause]"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
PY = RACINE / "python" / "python.exe"
PARAMETRES = json.loads((RACINE / "parametres.json").read_text(encoding="utf-8")) if (RACINE / "parametres.json").exists() else {}
URL_OLLAMA = "https://ollama.com/download/OllamaSetup.exe"
KOKORO = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
JOURNAL = (RACINE / "installation.log").open("a", encoding="utf-8")
SANS_PAUSE = "--sans-pause" in sys.argv


def dire(texte: str = ""):
    print(texte, flush=True)
    JOURNAL.write(texte + "\n")
    JOURNAL.flush()


def etape(numero: int, titre: str):
    dire()
    dire(f"[{numero}/5] {titre}")
    dire("-" * (len(titre) + 6))


def telecharger(url: str, cible: Path, libelle: str):
    cible.parent.mkdir(parents=True, exist_ok=True)
    temporaire = cible.with_suffix(cible.suffix + ".part")
    dernier = [-1]

    def progres(blocs, taille, total):
        if total > 0:
            pct = min(100, blocs * taille * 100 // total)
            if pct // 10 != dernier[0]:
                dernier[0] = pct // 10
                print(f"    {libelle} : {pct} %", flush=True)
    dire(f"    téléchargement de {libelle} depuis {url.split('/')[2]}")
    urllib.request.urlretrieve(url, temporaire, progres)
    temporaire.replace(cible)


def lancer(commande: list, libelle: str):
    dire(f"    {libelle}")
    p = subprocess.Popen(commande, cwd=str(RACINE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace")
    for ligne in p.stdout:
        ligne = ligne.rstrip()
        if ligne:
            print("      " + ligne[:150], flush=True)
            JOURNAL.write(ligne + "\n")
    p.wait()
    if p.returncode != 0:
        raise RuntimeError(f"{libelle} : code de sortie {p.returncode}")


def ollama_present() -> bool:
    return bool(shutil.which("ollama")) or (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe").exists()


def installer():
    from jarvis import machine
    dire(f"Installation de Jarvis dans {RACINE}")
    dire(time.strftime("%d/%m/%Y %H:%M"))

    etape(1, "pip, le gestionnaire de paquets de Python")
    if (RACINE / "python" / "Scripts" / "pip.exe").exists():
        dire("    déjà présent")
    else:
        lancer([str(PY), str(RACINE / "python" / "get-pip.py"), "--no-warn-script-location", "-q"], "installation de pip")

    etape(2, "Les bibliothèques de Jarvis (plusieurs minutes la première fois, environ 2 Go)")
    lancer([str(PY), "-m", "pip", "install", "-r", "requirements.txt", "--no-warn-script-location", "--progress-bar", "off",
            "--disable-pip-version-check"], "pip install -r requirements.txt")

    etape(3, "La voix de Jarvis (Kokoro, 340 Mo)")
    for nom, url in KOKORO.items():
        cible = RACINE / "modeles" / "kokoro" / nom
        if cible.exists():
            dire(f"    {nom} : déjà présent")
        else:
            telecharger(url, cible, nom)

    etape(4, "Examen de la machine et réglages")
    examen = machine.examiner(str(RACINE))
    for ligne in machine.resume(examen).splitlines():
        dire("    " + ligne)
    config_fichier = RACINE / "config.json"
    config = json.loads((config_fichier if config_fichier.exists() else RACINE / "config.example.json").read_text(encoding="utf-8"))
    jeton = ""
    if examen["verdict"] == "cloud" and not config.get("cerveau", {}).get("cloud", {}).get("jeton"):
        dire()
        dire("    Cette machine ne peut pas faire tourner le cerveau de Jarvis : il tournera à distance (Jarvis Cloud, payant).")
        dire(f"    Crédit : {PARAMETRES.get('url_boutique', 'voir le site de Jarvis')}")
        if not SANS_PAUSE:
            jeton = input("    Collez votre jeton Jarvis Cloud, ou appuyez sur Entrée pour le mettre plus tard : ").strip()
    machine.appliquer(config, examen, PARAMETRES.get("url_passerelle", ""), jeton, PARAMETRES.get("url_annuaire", ""))
    config_fichier.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not (RACINE / ".secrets").exists() and (RACINE / ".secrets.example").exists():
        shutil.copy2(RACINE / ".secrets.example", RACINE / ".secrets")
    dire(f"    config.json : cerveau {config['cerveau']['modele']}, mode {config['cerveau']['mode']}")

    etape(5, "Ollama, qui fait tourner le cerveau sur votre carte graphique")
    if examen["verdict"] == "cloud":
        dire("    inutile en mode cloud")
    elif ollama_present():
        dire("    déjà installé")
    else:
        setup = RACINE / "workspace" / "OllamaSetup.exe"
        telecharger(URL_OLLAMA, setup, "l'installateur officiel d'Ollama")
        dire("    installation d'Ollama (sa propre fenêtre de progression s'affiche)")
        subprocess.run([str(setup), "/SILENT", "/NORESTART"], timeout=900)
        setup.unlink(missing_ok=True)
        dire("    Ollama installé" if ollama_present() else "    Ollama ne s'est pas installé : installez-le depuis ollama.com")

    dire()
    dire("Installation terminée.")
    if examen["verdict"] != "cloud":
        dire("Au premier lancement, Jarvis télécharge ses modèles (plusieurs Go) : laissez-le faire une fois.")
    elif not config["cerveau"].get("cloud", {}).get("jeton"):
        dire("Le jeton Jarvis Cloud se colle plus tard dans les Réglages de Jarvis.")


if __name__ == "__main__":
    try:
        installer()
        code = 0
    except Exception as e:
        dire()
        dire(f"ERREUR : {type(e).__name__} : {e}")
        dire(f"Le détail est dans {RACINE / 'installation.log'}. Relancez l'installateur pour reprendre là où il s'est arrêté.")
        code = 1
    if not SANS_PAUSE:
        input("\nAppuyez sur Entrée pour fermer cette fenêtre.")
    sys.exit(code)
