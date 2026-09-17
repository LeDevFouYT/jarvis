"""La sentinelle : une surveillance en tâche de fond qui fait parler Jarvis de lui-même.
Sujets : température de la carte graphique, disque presque plein, rappel qui approche ; plus tard, les nouveaux
commentaires (une source se branche avec `ajouter_source`). Au plus une annonce toutes les 10 minutes par sujet
(`sentinelle.repos_min`). Jamais pendant que Jarvis parle ou écoute une question : l'annonce attend le calme.
Désactivable : Réglages, config `sentinelle.actif`, ou « Jarvis, désactive la sentinelle »."""
import json
import threading
import time

import psutil

from .config import CONFIG, RACINE

CONFIG.setdefault("sentinelle", {})


def reglage(nom, defaut):
    """Relu à chaque usage dans CONFIG : les Réglages et la commande vocale agissent tout de suite."""
    return type(defaut)(CONFIG.get("sentinelle", {}).get(nom, defaut))


class Sentinelle(threading.Thread):
    """`parler(texte) -> bool` dit l'annonce et rend Faux si le moment ne s'y prête pas (elle sera retentée).
    `mesures` et `horloge` sont remplaçables pour les tests."""

    def __init__(self, parler, sur_evenement=None, mesures=None, horloge=time.time):
        super().__init__(daemon=True, name="sentinelle")
        self.parler = parler
        self.sur_evenement = sur_evenement or (lambda e: None)
        self.mesures = mesures or mesures_reelles
        self.horloge = horloge
        self.dernieres: dict[str, float] = {}        # sujet -> instant de la dernière annonce
        self.sources: dict = {}                      # nom -> fonction rendant [(sujet, texte)]
        self.arret = threading.Event()
        self.reveil = threading.Event()

    def ajouter_source(self, nom: str, fonction):
        """Une source future (nouveaux commentaires YouTube…) : fonction() -> liste de (sujet, texte)."""
        self.sources[nom] = fonction

    def arreter(self):
        self.arret.set()
        self.reveil.set()

    def run(self):
        while not self.arret.is_set():
            if reglage("actif", True):
                try:
                    self.tour()
                except Exception as e:
                    self.sur_evenement({"type": "sentinelle_erreur", "t": time.time(), "message": f"{type(e).__name__} : {e}"})
            self.reveil.wait(reglage("intervalle_s", 30.0))
            self.reveil.clear()

    # --- un passage de surveillance ---
    def alertes(self) -> list[tuple[str, str]]:
        m = self.mesures()
        titre = CONFIG.get("personnage", {}).get("titre", "monsieur")
        resultat = []
        temp = m.get("temperature_gpu")
        if temp is not None and temp >= reglage("temperature_max", 85.0):
            resultat.append(("temperature", f"Attention, {titre} : la carte graphique chauffe, elle est à {temp:.0f} degrés."))
        for disque in m.get("disques", []):
            libre_go, total_go = disque["libre_go"], disque["total_go"]
            # une petite partition pleine (clé, partition de secours de 4 Go) n'est pas un souci à annoncer
            if total_go < reglage("disque_taille_min_go", 16.0):
                continue
            if libre_go < reglage("disque_min_go", 10.0) or libre_go < total_go * reglage("disque_min_pourcent", 2.0) / 100:
                resultat.append((f"disque:{disque['nom']}",
                                 f"Le disque {disque['nom']} est presque plein : il ne reste que {libre_go:.0f} gigaoctets."))
        avance = reglage("rappel_avance_min", 5.0) * 60
        for r in m.get("rappels", []):
            reste = r["quand"] - self.horloge()
            if 60 < reste <= avance:
                resultat.append((f"rappel:{r['id']}", f"Dans {round(reste / 60)} minutes : {r['texte']}."))
        for nom, fonction in list(self.sources.items()):
            try:
                resultat.extend(fonction())
            except Exception:
                pass
        return resultat

    def tour(self) -> list[str]:
        """Rend les annonces réellement faites à ce tour."""
        faites = []
        repos = reglage("repos_min", 10.0) * 60
        for sujet, texte in self.alertes():
            maintenant = self.horloge()
            if maintenant - self.dernieres.get(sujet, -1e12) < repos:
                continue
            if self.parler(texte):
                self.dernieres[sujet] = maintenant
                faites.append(texte)
                self.sur_evenement({"type": "sentinelle", "t": time.time(), "sujet": sujet, "texte": texte})
        return faites


def mesures_reelles() -> dict:
    from .outils import etat_machine, rappel
    g = etat_machine.gpu()
    disques = []
    for p in psutil.disk_partitions(all=False):
        if "cdrom" in p.opts or not p.fstype:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        disques.append({"nom": p.mountpoint.rstrip(":\\/") or p.mountpoint, "libre_go": u.free / 1024 ** 3, "total_go": u.total / 1024 ** 3})
    return {"temperature_gpu": g["temperature"] if g else None, "disques": disques, "rappels": rappel.liste()}


def definir_actif(actif: bool):
    CONFIG.setdefault("sentinelle", {})["actif"] = actif
    chemin = RACINE / "config.json"
    fichier = json.loads(chemin.read_text(encoding="utf-8"))
    fichier.setdefault("sentinelle", {})["actif"] = actif
    chemin.write_text(json.dumps(fichier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
