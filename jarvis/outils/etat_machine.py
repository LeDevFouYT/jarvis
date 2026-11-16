"""Outil etat_machine : VRAM, processeur, mémoire, disques C: et F:, température GPU. Une phrase parlable."""
import shutil
import time
from collections import deque

import psutil

NOM = "etat_machine"
DESCRIPTION = ("Donne l'état de l'ordinateur : mémoire vidéo (VRAM) utilisée et totale, charge du processeur, "
               "mémoire vive, espace libre sur les disques C et F, température de la carte graphique.")
PARAMETRES = {}
REQUIS = []

# (horodatage, charge GPU %, VRAM %) : alimenté par le HUD qui interroge /etat toutes les 2 s
HISTORIQUE = deque(maxlen=90)


def gpu() -> dict | None:
    """La plus grosse carte NVIDIA. Charge et température peuvent valoir None (« [N/A] » chez certains pilotes) :
    la mémoire vidéo suffit pour afficher la carte. Lecture commune avec l'installateur (machine.lire_nvidia)."""
    from ..machine import lire_nvidia
    cartes = [c for c in lire_nvidia(["memory.total", "memory.used", "utilization.gpu", "temperature.gpu"], timeout=5)
              if c["memory.total"]]
    if not cartes:
        return None
    c = max(cartes, key=lambda c: c["memory.total"])
    return {"utilisation": c["utilization.gpu"], "vram_utilisee_mo": c["memory.used"] or 0,
            "vram_totale_mo": c["memory.total"], "temperature": c["temperature.gpu"]}


def mesures() -> dict:
    """Tout en chiffres, pour le HUD et pour la phrase."""
    vm = psutil.virtual_memory()
    disques = {}
    for lettre in ("C", "F"):
        try:
            u = shutil.disk_usage(f"{lettre}:/")
            disques[lettre] = {"libre_go": round(u.free / 1024 ** 3, 1), "total_go": round(u.total / 1024 ** 3)}
        except OSError:
            pass
    g = gpu()
    if g:
        HISTORIQUE.append((time.time(), g["utilisation"] or 0, round(100 * g["vram_utilisee_mo"] / g["vram_totale_mo"], 1)))
    return {"gpu": g,
            "cpu": {"utilisation": psutil.cpu_percent(interval=0.3)},
            "ram": {"utilisation": vm.percent, "totale_go": round(vm.total / 1024 ** 3, 1),
                    "libre_go": round(vm.available / 1024 ** 3, 1)},
            "disques": disques}


def _panneau(m: dict):
    from . import panneaux
    jauges = []
    if m["gpu"]:
        g = m["gpu"]
        jauges.append({"nom": "Mémoire vidéo", "valeur": round(g["vram_utilisee_mo"] / 1024, 1), "max": round(g["vram_totale_mo"] / 1024),
                       "unite": "Go", "alerte": g["vram_utilisee_mo"] > 0.9 * g["vram_totale_mo"]})
        if g["utilisation"] is not None:
            jauges.append({"nom": "Charge carte graphique", "valeur": g["utilisation"], "max": 100, "unite": "%",
                           "alerte": g["utilisation"] > 95})
        if g["temperature"] is not None:
            jauges.append({"nom": "Température carte", "valeur": g["temperature"], "max": 100, "unite": "°C",
                           "alerte": g["temperature"] > 85})
    jauges += [
        {"nom": "Processeur", "valeur": round(m["cpu"]["utilisation"]), "max": 100, "unite": "%", "alerte": m["cpu"]["utilisation"] > 90},
        {"nom": "Mémoire vive", "valeur": round(m["ram"]["totale_go"] - m["ram"]["libre_go"], 1), "max": m["ram"]["totale_go"],
         "unite": "Go", "alerte": m["ram"]["utilisation"] > 90},
    ]
    for lettre, d in m["disques"].items():
        jauges.append({"nom": f"Disque {lettre}", "valeur": round(d["total_go"] - d["libre_go"]), "max": d["total_go"], "unite": "Go",
                       "alerte": d["libre_go"] < 0.1 * d["total_go"]})
    courbe = [c for _, c, _ in HISTORIQUE]
    panneaux.graphique("État de la machine", jauges, courbe=courbe if len(courbe) > 2 else [],
                       legende_courbe="charge de la carte graphique, dernières minutes")


def executer() -> str:
    m = mesures()
    _panneau(m)
    parties = []
    if m["gpu"]:
        g = m["gpu"]
        phrase = (f"mémoire vidéo {g['vram_utilisee_mo'] / 1024:.1f} gigaoctets utilisés sur "
                  f"{g['vram_totale_mo'] / 1024:.0f}, soit {(g['vram_totale_mo'] - g['vram_utilisee_mo']) / 1024:.1f} libres")
        details = ([f"{g['temperature']} degrés"] if g["temperature"] is not None else []) +                   ([f"{g['utilisation']} % de charge"] if g["utilisation"] is not None else [])
        if details:
            phrase += ", carte graphique à " + " et ".join(details)
        parties.append(phrase)
    else:
        parties.append("carte graphique injoignable")
    parties.append(f"processeur à {m['cpu']['utilisation']:.0f} %")
    parties.append(f"mémoire vive à {m['ram']['utilisation']:.0f} %, {m['ram']['libre_go']} gigaoctets libres")
    for lettre, d in m["disques"].items():
        parties.append(f"{d['libre_go']} gigaoctets libres sur le disque {lettre}")
    return ", ".join(parties) + "."
