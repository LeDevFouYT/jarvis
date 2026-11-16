"""Test de la lecture de la carte graphique : python -m jarvis.tests.carte_nvidia   (Jarvis peut tourner)
Retour d'un abonné le 16/11 : RTX 5090 Astral, pilote à jour, et le HUD affichait « pas de carte NVIDIA ».

1. nvidia-smi joué : une carte ; deux cartes NVIDIA ; « [N/A] » sur la température et la charge ; sortie vide ou
   illisible ; nvidia-smi absent du PATH mais rangé dans le DriverStore ; aucun nvidia-smi du tout.
   Pour chaque cas : la jauge du HUD (etat_machine.gpu), la phrase de Jarvis, le panneau, l'examen de l'installateur.
2. La vraie carte de cette machine, par la même lecture."""
import os
import subprocess
import sys
import types

from ._commun import Verifs

from .. import machine  # noqa: E402
from ..outils import etat_machine  # noqa: E402

V = Verifs("Lecture de la carte graphique")

# réponses de nvidia-smi par requête (le début de --query-gpu suffit à les distinguer)
UNE = {"name": "NVIDIA GeForce RTX 5090, 32607, 581.57",
       "memory.total,memory.used": "32607, 1830, 4, 41",
       "memory.free": "30777", "memory.total": "32607"}
DEUX = {"name": "NVIDIA GeForce GTX 1050 Ti, 4096, 581.57\nNVIDIA GeForce RTX 5090, 32607, 581.57",
        "memory.total,memory.used": "4096, 300, 1, 35\n32607, 1830, 4, 41",
        "memory.free": "3796\n30777", "memory.total": "4096\n32607"}
NA = {"name": "NVIDIA GeForce RTX 5090, 32607, 581.57",
      "memory.total,memory.used": "32607, 1830, [N/A], [N/A]",
      "memory.free": "30777", "memory.total": "32607"}
VIDE = {"name": "", "memory.total,memory.used": "", "memory.free": "", "memory.total": ""}
ABIME = {"name": "No devices were found", "memory.total,memory.used": "Failed to initialize NVML: Driver/library version mismatch",
         "memory.free": "[N/A]", "memory.total": "erreur"}


def jouer(reponses: dict):
    """Remplace subprocess.run dans machine : rend la sortie prévue pour la requête, note l'exécutable appelé."""
    appels = []

    def faux_run(cmd, **_):
        appels.append(cmd[0])
        requete = cmd[1].split("=", 1)[1]
        cle = next((k for k in sorted(reponses, key=len, reverse=True) if requete.startswith(k)), None)
        return types.SimpleNamespace(stdout=(reponses.get(cle, "") + "\n") if cle else "", returncode=0)
    machine.subprocess.run = faux_run
    machine._EXE.clear()
    return appels


VRAI_RUN = subprocess.run
VRAI_WHICH = machine.shutil.which
VRAI_EXISTS = machine.os.path.exists


def remettre():
    machine.subprocess.run = VRAI_RUN
    machine.shutil.which = VRAI_WHICH
    machine.os.path.exists = VRAI_EXISTS
    machine._EXE.clear()


def avec_exe(chemin="nvidia-smi.exe"):
    machine.shutil.which = lambda nom: chemin if nom == "nvidia-smi" else VRAI_WHICH(nom)
    machine.os.path.exists = lambda c: c == chemin or VRAI_EXISTS(c)


def phrase_sans_crash():
    try:
        etat_machine.HISTORIQUE.clear()
        from ..outils import panneaux
        garde = panneaux.graphique
        panneaux.graphique = lambda *a, **k: None
        try:
            return etat_machine.executer()
        finally:
            panneaux.graphique = garde
    except Exception as e:
        return f"ERREUR {type(e).__name__}: {e}"


# --- 1. cas joués -------------------------------------------------------------------------------------------
try:
    avec_exe()
    jouer(UNE)
    g = etat_machine.gpu()
    V.ok(g and g["vram_totale_mo"] == 32607 and g["temperature"] == 41 and g["utilisation"] == 4,
         "une carte : la jauge lit 32 Go, 41 °C, 4 %", g)
    V.ok(machine._nvidia() == {"nom": "NVIDIA GeForce RTX 5090", "vram_mo": 32607, "pilote": "581.57"},
         "une carte : l'installateur voit la RTX 5090", machine._nvidia())
    V.ok(machine.examiner()["verdict"] == "local_complet", "une carte : version complète en local")
    V.ok(machine.vram_libre_mo() == 30777, "une carte : mémoire libre lue", machine.vram_libre_mo())

    jouer(DEUX)
    g = etat_machine.gpu()
    V.ok(g and g["vram_totale_mo"] == 32607, "deux cartes : la jauge garde la plus grosse (avant : « pas de carte NVIDIA »)", g)
    V.ok(machine._nvidia()["nom"] == "NVIDIA GeForce RTX 5090", "deux cartes : l'installateur garde la plus grosse")
    V.ok(machine.vram_libre_mo() == 30777, "deux cartes : mémoire libre de la carte la plus libre")
    from .. import preparation
    V.ok(preparation.vram_mo() == 32607, "deux cartes : la préparation lit 32 Go", preparation.vram_mo())

    jouer(NA)
    g = etat_machine.gpu()
    V.ok(g and g["vram_totale_mo"] == 32607 and g["temperature"] is None and g["utilisation"] is None,
         "[N/A] : la carte reste affichée, sans température ni charge (avant : « pas de carte NVIDIA »)", g)
    p = phrase_sans_crash()
    V.ok("mémoire vidéo" in p and "None" not in p and "ERREUR" not in p, "[N/A] : la phrase de Jarvis reste propre", p[:110])
    etat_machine.HISTORIQUE.clear()
    m = etat_machine.mesures()
    V.ok(len(etat_machine.HISTORIQUE) == 1 and etat_machine.HISTORIQUE[-1][1] == 0, "[N/A] : la courbe de charge ne plante pas")
    V.ok(m["gpu"] is not None, "[N/A] : /etat envoie la carte au HUD")

    jouer(VIDE)
    V.ok(etat_machine.gpu() is None and machine._nvidia() is None, "sortie vide : aucune carte, sans exception")
    jouer(ABIME)
    V.ok(etat_machine.gpu() is None and machine._nvidia() is None and machine.vram_libre_mo() is None,
         "sortie illisible (pilote cassé) : aucune carte, sans exception")
    p = phrase_sans_crash()
    V.ok("injoignable" in p and "ERREUR" not in p, "sortie illisible : Jarvis dit « carte graphique injoignable »", p[:60])

    # nvidia-smi pas dans le PATH, seulement dans le DriverStore
    depot = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "DriverStore", "FileRepository",
                         "nvlt.inf_amd64_essai", "nvidia-smi.exe")
    machine.shutil.which = lambda nom: None if nom == "nvidia-smi" else VRAI_WHICH(nom)
    machine.os.path.exists = lambda c: c == depot
    vrai_glob = machine.Path.glob
    machine.Path.glob = lambda self, motif: iter([machine.Path(depot)]) if motif == "nv*/nvidia-smi.exe" else vrai_glob(self, motif)
    vrai_mtime = machine.os.path.getmtime
    machine.os.path.getmtime = lambda c: 0 if c == depot else vrai_mtime(c)
    try:
        appels = jouer(UNE)
        g = etat_machine.gpu()
        V.ok(g and g["vram_totale_mo"] == 32607 and appels and appels[0] == depot,
             "nvidia-smi hors du PATH : trouvé dans le DriverStore (avant : « pas de carte NVIDIA »)", appels[:1])
    finally:
        machine.Path.glob = vrai_glob
        machine.os.path.getmtime = vrai_mtime

    machine.shutil.which = lambda nom: None if nom == "nvidia-smi" else VRAI_WHICH(nom)
    machine.os.path.exists = lambda c: False
    machine._EXE.clear()
    vrai_glob = machine.Path.glob
    machine.Path.glob = lambda self, motif: iter([]) if motif == "nv*/nvidia-smi.exe" else vrai_glob(self, motif)
    try:
        V.ok(machine.nvidia_smi() is None and etat_machine.gpu() is None and machine.examiner()["verdict"] == "cloud",
             "aucun pilote NVIDIA : pas de carte, mode cloud comme avant")
    finally:
        machine.Path.glob = vrai_glob
finally:
    remettre()

# --- 2. la vraie carte ----------------------------------------------------------------------------------------
exe = machine.nvidia_smi()
g = etat_machine.gpu()
n = machine._nvidia()
if exe:
    V.ok(g is not None and n is not None and g["vram_totale_mo"] == n["vram_mo"],
         f"cette machine : {n['nom'] if n else '?'} lue par la jauge et par l'installateur", exe)
    V.info(phrase_sans_crash()[:150])
else:
    V.info("pas de pilote NVIDIA sur cette machine : partie 2 sautée")

sys.exit(V.fin())
