"""Vérification de la machine : peut-elle faire tourner Jarvis en local ?
Verdict : local_complet (NVIDIA >= 12 Go), local_reduit (NVIDIA 8 à 12 Go), cloud (moins, ou pas de NVIDIA :
le cerveau et la vision tournent alors à distance, Jarvis Cloud, à travers la passerelle payante ; les oreilles et la voix
restent sur la machine). Utilisé par l'installateur, par `python -m jarvis installer` et par le HUD."""
import ctypes
import os
import platform
import shutil
import subprocess
from pathlib import Path

# Une carte vendue « 12 Go » annonce 12 282 Mo, une « 8 Go » 8 188 Mo, une « 16 Go » 16 303 Mo (nvidia-smi) : un seuil
# au Mo près envoyait une RTX 4070 portable (8 Go) en mode cloud payant, avec un jeton à acheter (vu le 18/09, un
# abonné). D'où une marge d'un demi-gigaoctet sous la capacité annoncée.
SEUIL_COMPLET_MO = 12 * 1024 - 512
SEUIL_REDUIT_MO = 8 * 1024 - 512
RAM_MIN_GO = 12
DISQUE_MIN_GO = 25


# Lecture de nvidia-smi, partagée par l'installateur, la vérification au lancement, le majordome et la jauge du HUD.
# Corrigé le 16/11 (un abonné, RTX 5090 Astral, pilote à jour : le HUD affichait « pas de carte NVIDIA ») : la jauge
# appelait « nvidia-smi » par le seul PATH et lisait une seule ligne de nombres. Elle tombait donc dès que nvidia-smi
# n'était pas dans le PATH (les pilotes récents le rangent aussi dans le DriverStore), dès qu'il y avait deux cartes
# NVIDIA, ou dès qu'une valeur revenait « [N/A] ». Ici : nvidia-smi cherché partout, une carte par ligne, et une valeur
# illisible devient None au lieu de faire perdre toute la carte.
_EXE: list = []          # chemin trouvé, gardé : la jauge interroge toutes les 2 s


def nvidia_smi() -> str | None:
    """Chemin de nvidia-smi, ou None sans pilote NVIDIA."""
    if _EXE and os.path.exists(_EXE[0]):
        return _EXE[0]
    candidats = [shutil.which("nvidia-smi")]
    if os.name == "nt":
        racine = os.environ.get("SystemRoot", r"C:\Windows")
        candidats += [os.path.join(racine, "System32", "nvidia-smi.exe"),
                      os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")]
        try:
            depot = Path(racine) / "System32" / "DriverStore" / "FileRepository"
            candidats += sorted((str(c) for c in depot.glob("nv*/nvidia-smi.exe")),
                                key=lambda c: os.path.getmtime(c), reverse=True)
        except OSError:
            pass
    for c in candidats:
        if c and os.path.exists(c):
            _EXE[:] = [c]
            return c
    return None


def _nombre(texte: str) -> int | None:
    """« 32607 » -> 32607 ; « [N/A] », « [Not Supported] », vide -> None."""
    try:
        return int(float(texte.strip()))
    except (ValueError, AttributeError):
        return None


def lire_nvidia(champs: list[str], timeout: float = 10) -> list[dict]:
    """Une ligne de nvidia-smi par carte -> [{champ: valeur}]. Le premier champ peut être un texte (name) ; les autres
    sont des nombres, None quand la carte ne les donne pas. Liste vide sans pilote ou si nvidia-smi échoue."""
    exe = nvidia_smi()
    if not exe:
        return []
    try:
        sortie = subprocess.run([exe, "--query-gpu=" + ",".join(champs), "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or ""
    except Exception:
        return []
    texte = champs[0] in ("name", "driver_version")
    cartes = []
    for ligne in sortie.strip().splitlines():
        # le nom vient en premier : on coupe par la droite, une virgule dans un nom ne décale pas les nombres
        parties = ligne.rsplit(",", len(champs) - 1) if texte else ligne.split(",")
        if len(parties) != len(champs):
            continue
        carte = {}
        for champ, valeur in zip(champs, parties):
            carte[champ] = valeur.strip() if champ in ("name", "driver_version") else _nombre(valeur)
        cartes.append(carte)
    return cartes


def _nvidia() -> dict | None:
    """nvidia-smi : nom, VRAM totale, pilote de la plus grosse carte. None sans carte NVIDIA ou sans pilote."""
    cartes = [c for c in lire_nvidia(["name", "memory.total", "driver_version"]) if c["memory.total"]]
    if not cartes:
        return None
    c = max(cartes, key=lambda c: c["memory.total"])
    return {"nom": c["name"], "vram_mo": c["memory.total"], "pilote": c["driver_version"]}


def vram_libre_mo() -> int | None:
    """Mémoire vidéo libre à l'instant sur la carte la plus libre, None sans carte NVIDIA."""
    libres = [c["memory.free"] for c in lire_nvidia(["memory.free"]) if c["memory.free"] is not None]
    return max(libres) if libres else None


def _ram_go() -> float:
    from . import systeme_os
    if not systeme_os.est_windows():
        return systeme_os.ram_go()
    try:
        class M(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = M()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round(m.ullTotalPhys / 1024 ** 3, 1)
    except Exception:
        return 0.0


def examiner(dossier: str | None = None) -> dict:
    """Mesures + verdict + explication en français."""
    gpu = _nvidia()
    ram = _ram_go()
    cible = dossier or os.getcwd()
    try:
        disque_go = round(shutil.disk_usage(os.path.splitdrive(os.path.abspath(cible))[0] + "\\").free / 1024 ** 3, 1)
    except Exception:
        disque_go = 0.0
    cpu = os.cpu_count() or 0
    remarques = []
    if gpu is None:
        verdict = "cloud"
        raison = ("Aucune carte graphique NVIDIA détectée. Le cerveau et la vision ne peuvent pas tourner ici : "
                  "ils tourneront à distance, sur Jarvis Cloud (usage facturé). "
                  "L'écoute et la voix restent sur cette machine.")
        modeles = {"cerveau": "qwen3:14b", "vision": "gemma3:4b", "whisper": ("small", "cpu", "int8")}
    elif gpu["vram_mo"] >= SEUIL_COMPLET_MO:
        verdict = "local_complet"
        raison = (f"{gpu['nom']} avec {gpu['vram_mo'] / 1024:.0f} Go de mémoire vidéo : Jarvis tourne entièrement "
                  "en local, version complète (qwen3:14b, gemma3:4b, Whisper turbo).")
        modeles = {"cerveau": "qwen3:14b", "vision": "gemma3:4b", "whisper": ("large-v3-turbo", "cuda", "float16")}
    elif gpu["vram_mo"] >= SEUIL_REDUIT_MO:
        verdict = "local_reduit"
        raison = (f"{gpu['nom']} avec {gpu['vram_mo'] / 1024:.0f} Go de mémoire vidéo : Jarvis tourne en local en "
                  "version réduite (qwen3:8b, gemma3:4b, Whisper small). La génération d'images restera lente.")
        modeles = {"cerveau": "qwen3:8b", "vision": "gemma3:4b", "whisper": ("small", "cuda", "float16")}
    else:
        verdict = "cloud"
        raison = (f"{gpu['nom']} avec {gpu['vram_mo'] / 1024:.0f} Go de mémoire vidéo, c'est trop peu pour le cerveau. "
                  "Il tournera à distance, sur Jarvis Cloud (usage facturé). "
                  "L'écoute et la voix restent sur cette machine.")
        modeles = {"cerveau": "qwen3:14b", "vision": "gemma3:4b", "whisper": ("small", "cuda", "float16")}
    if ram and ram < RAM_MIN_GO:
        remarques.append(f"Seulement {ram:.0f} Go de mémoire vive : les chargements seront lents (16 Go recommandés).")
    if disque_go and disque_go < DISQUE_MIN_GO:
        remarques.append(f"Seulement {disque_go:.0f} Go libres sur le disque cible : il en faut {DISQUE_MIN_GO} pour les modèles.")
    if platform.system() == "Linux":
        remarques.append("Linux : l'essentiel marche (parler, écouter, cerveau, mémoire, fichiers, images) ; la superposition, "
                         "le placement des fenêtres et la frappe au clavier restent pour Windows (voir le README).")
    elif platform.system() != "Windows":
        remarques.append("Jarvis est prévu pour Windows 10 ou 11, et Linux.")
    return {"verdict": verdict, "raison": raison, "remarques": remarques, "gpu": gpu, "ram_go": ram,
            "disque_libre_go": disque_go, "cpu": cpu, "modeles": modeles, "systeme": platform.platform()}


def appliquer(config: dict, examen: dict, url_passerelle: str = "", jeton: str = "", annuaire: str = "") -> dict:
    """Règle config.json selon le verdict. Retourne la config modifiée.
    `annuaire` : fichier JSON fixe donnant l'adresse du jour de la passerelle (pod RunPod sans domaine)."""
    m = examen["modeles"]
    config.setdefault("cerveau", {})["modele"] = m["cerveau"]
    config.setdefault("vision", {})["modele"] = m["vision"]
    config.setdefault("oreilles", {}).update(modele=m["whisper"][0], appareil=m["whisper"][1], calcul=m["whisper"][2])
    if examen["verdict"] == "cloud":
        config["cerveau"]["mode"] = "cloud"
        config["cerveau"].setdefault("cloud", {})
        if url_passerelle:
            config["cerveau"]["cloud"]["url"] = url_passerelle
        config["cerveau"]["cloud"]["modele"] = m["cerveau"]
        if annuaire:
            config["cerveau"]["cloud"]["annuaire"] = annuaire
        if jeton:
            config["cerveau"]["cloud"]["jeton"] = jeton
    else:
        config["cerveau"]["mode"] = "local"
    return config


def resume(examen: dict) -> str:
    g = examen["gpu"]
    lignes = [f"Carte graphique : {g['nom']} ({g['vram_mo'] / 1024:.0f} Go, pilote {g['pilote']})" if g else "Carte graphique : aucune NVIDIA",
              f"Mémoire vive : {examen['ram_go']:.0f} Go   Processeur : {examen['cpu']} cœurs   Disque libre : {examen['disque_libre_go']:.0f} Go",
              f"Verdict : {examen['verdict'].replace('_', ' ')}", examen["raison"]] + examen["remarques"]
    return "\n".join(lignes)


if __name__ == "__main__":
    print(resume(examiner()))
