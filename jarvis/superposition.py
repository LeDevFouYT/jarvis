"""La superposition (v3, consigne 9) : Jarvis sort du HUD et se pose par-dessus Windows.

Une fenêtre sans bord, transparente, toujours au premier plan, qui LAISSE PASSER LES CLICS : on travaille dessous
sans jamais la sentir. Elle montre trois choses, dans le coin haut-droit de l'écran principal :
  - les notifications holographiques (rappels, images prêtes, sentinelle, erreurs…) ;
  - la réponse de Jarvis qui flotte pendant qu'il parle ;
  - les jauges de la machine (mémoire vidéo, processeur, température de la carte).

Comment c'est fait : Tk, fond d'une couleur unique déclarée transparente (`-transparentcolor`), plus WS_EX_LAYERED |
WS_EX_TOOLWINDOW (pas dans la barre des tâches) | WS_EX_NOACTIVATE (ne prend jamais le focus). Avec la transparence
par couleur clé, **les clics passent tout seuls là où rien n'est dessiné** : on travaille au travers. Là où il y a
quelque chose (la poignée, les cartes), la fenêtre reçoit la souris — c'est ce qui permet de LA DÉPLACER en la
glissant, sans raccourci. Elle tourne dans son propre processus : si elle tombe, Jarvis continue.

    python -m jarvis.superposition [--serveur http://127.0.0.1:8765] [--etat]   (--etat : journal JSON sur la sortie)
"""
import argparse
import ctypes
import os
import json
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path

ETAT = Path(__file__).resolve().parents[1] / "workspace" / "mesures" / "superposition.json"
COULEUR_CLE = "#010203"          # la couleur déclarée transparente : on ne la dessine jamais ailleurs
COULEUR_PRISE = "#050a0f"        # presque noir, mais pas la couleur clé : cette bande reçoit la souris
LARGEUR = 430
HAUTEUR = 540                    # un panneau compact, pas une colonne : on le déplace facilement
MARGE = 18
DUREE_NOTE = 9                   # secondes d'affichage d'une notification
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x00080000, 0x00000020, 0x00000080, 0x08000000

# ce qui mérite une notification, et comment la dire
NOTES = {
    "rappel": ("rappel", lambda e: e.get("texte", "")),
    "sentinelle": ("sentinelle", lambda e: e.get("texte", "")),
    "erreur": ("erreur", lambda e: e.get("message", "")),
    "image": ("image prête", lambda e: e.get("prompt", "")[:80]),
    "video_prete": ("vidéo prête", lambda e: e.get("prompt", "")[:80]),
    "hologramme": ("hologramme", lambda e: e.get("objet", "")),
    "scan_resultat": ("scan", lambda e: "je vois " + e.get("phrase", "") if e.get("phrase") else "rien de reconnu"),
    "souvenir_ajoute": ("mémoire", lambda e: (e.get("souvenir") or {}).get("fait", "")),
    "theme": ("armure", lambda e: e.get("theme", "")),
    "mot_detecte": ("réveil", lambda e: "je vous écoute"),
    "commande": ("commande", lambda e: e.get("commande", "")),
}


def _flux(url: str, sortie: queue.Queue, arret: threading.Event):
    """Les événements du serveur (SSE), relus sans arrêt tant que la fenêtre vit."""
    while not arret.is_set():
        try:
            with urllib.request.urlopen(url + "/events", timeout=70) as r:
                for ligne in r:
                    if arret.is_set():
                        return
                    ligne = ligne.decode("utf-8", "replace").strip()
                    if ligne.startswith("data:"):
                        try:
                            sortie.put(json.loads(ligne[5:].strip()))
                        except ValueError:
                            pass
        except Exception:
            time.sleep(2)


def _etat(url: str, sortie: queue.Queue, arret: threading.Event):
    """Les jauges : /etat toutes les deux secondes."""
    while not arret.is_set():
        try:
            with urllib.request.urlopen(url + "/etat", timeout=10) as r:
                sortie.put({"type": "_jauges", "etat": json.loads(r.read())})
        except Exception:
            pass
        arret.wait(2)


class Superposition:
    def __init__(self, serveur: str, journal: bool = False):
        import tkinter as tk
        self.tk = tk
        self.serveur = serveur.rstrip("/")
        self.journal = journal
        self.racine = tk.Tk()
        self.racine.title("Jarvis · superposition")
        self.racine.overrideredirect(True)
        self.racine.attributes("-topmost", True)
        self.racine.configure(bg=COULEUR_CLE)
        self.racine.attributes("-transparentcolor", COULEUR_CLE)
        ecran_l, ecran_h = self.racine.winfo_screenwidth(), self.racine.winfo_screenheight()
        self.hauteur = HAUTEUR
        place = _position_gardee()                       # là où on l'a laissée la dernière fois
        self.x = place.get("x", ecran_l - LARGEUR - MARGE)
        self.y = place.get("y", MARGE)
        self.hauteur = place.get("hauteur", self.hauteur)
        self.racine.geometry(f"{LARGEUR}x{self.hauteur}+{self.x}+{self.y}")
        self.prise = None                                # on la glisse par ses parties visibles
        self.toile = tk.Canvas(self.racine, width=LARGEUR, height=self.hauteur, bg=COULEUR_CLE,
                               highlightthickness=0, bd=0)
        self.toile.pack()
        self.toile.bind("<Button-1>", self._prendre)
        self.toile.bind("<B1-Motion>", self._glisser)
        self.toile.bind("<ButtonRelease-1>", self._poser)
        self.toile.bind("<Enter>", lambda e: self.toile.config(cursor="fleur"))
        self.notes = []                      # [{titre, texte, t}]
        self.reponse = {"texte": "", "t": 0}
        self.jauges = {}
        self.couleur = "#5fe3ff"
        self.file = queue.Queue()
        self.arret = threading.Event()
        self.compte = {"notes": 0, "images": 0}
        self.masquee = False                  # vrai quand le HUD est au premier plan
        self.masquee_depuis = 0.0             # sans nouvelle du HUD pendant 30 s, on se remontre
        self._styles_windows()
        threading.Thread(target=_flux, args=(self.serveur, self.file, self.arret), daemon=True).start()
        threading.Thread(target=_etat, args=(self.serveur, self.file, self.arret), daemon=True).start()
        self.racine.after(40, self._boucle)

    # --- Windows : au premier plan, transparente aux clics, absente de la barre des tâches ---
    def _styles_windows(self):
        self.racine.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.racine.winfo_id()) or self.racine.winfo_id()
            self.hwnd = hwnd
            styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, (styles | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT)
        except Exception as e:                                  # pas Windows : la fenêtre marche quand même
            self.hwnd = 0
            self._dire({"type": "avertissement", "message": str(e)})

    ARMURES = {"jarvis": "#5fe3ff", "mark3": "#ff8a5c", "friday": "#d2a8ff", "ultron": "#ff6a6a"}

    def _armure(self, nom: str | None):
        """Les couleurs de l'armure, éclaircies : sur un fond clair de Windows, le rouge sombre ne se voit pas."""
        couleur = self.ARMURES.get(nom or "")
        if couleur and couleur != self.couleur:
            self.couleur = couleur
            self._dire({"quoi": "armure", "nom": nom, "couleur": couleur})

    def _placer(self, coin: str):
        """« mets-toi à gauche » : les quatre coins et le milieu, sans souris."""
        e_l, e_h = self.racine.winfo_screenwidth(), self.racine.winfo_screenheight()
        x = {"gauche": MARGE, "droite": e_l - LARGEUR - MARGE, "milieu": (e_l - LARGEUR) // 2}.get(coin, self.x)
        y = {"haut": MARGE, "bas": max(MARGE, e_h - self.hauteur - MARGE)}.get(coin, self.y)
        self.x, self.y = x, y
        self.racine.geometry(f"{LARGEUR}x{self.hauteur}+{x}+{y}")
        _garder_position(x, y, self.hauteur)
        self._dire({"quoi": "placee", "coin": coin, "x": x, "y": y})

    def _dire(self, quoi: dict):
        if self.journal:
            print(json.dumps(quoi, ensure_ascii=False), flush=True)

    def _ecrire_etat(self):
        """Ce que la fenêtre est en train de faire, sur le disque : les Réglages et les tests le lisent."""
        try:
            ETAT.parent.mkdir(parents=True, exist_ok=True)
            ETAT.write_text(json.dumps({"pid": os.getpid(), "hwnd": self.hwnd, "masquee": self.masquee, "t": round(time.time(), 1),
                                        "notes": self.compte["notes"], "images": self.compte["images"],
                                        "reponse": self.reponse["texte"][:90], "jauges": bool(self.jauges),
                                        "couleur": self.couleur, "x": self.racine.winfo_x(),
                                        "y": self.racine.winfo_y()},
                                       ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # --- les événements ---
    def _traiter(self, e: dict):
        genre = e.get("type")
        if genre == "hud_present":                              # le HUD est devant : on ne le recouvre pas
            self.masquee = bool(e.get("actif"))
            self.masquee_depuis = time.time()
            self._dire({"quoi": "masquee" if self.masquee else "visible"})
            return
        if genre == "_jauges":
            self.jauges = e["etat"]
            self._armure(e["etat"].get("theme"))         # l'armure en cours, dès la première lecture de /etat
            return
        if genre == "theme":                                    # la superposition suit l'armure du HUD
            self._armure(e.get("theme"))
        if genre in ("phrase", "reponse_complete"):
            texte = (e.get("texte") or "").strip()
            if texte:
                self.reponse = {"texte": texte, "t": time.time()}
                self._dire({"quoi": "reponse", "texte": texte[:120]})
            return
        if genre == "parole_fin":
            self.reponse = {"texte": "", "t": 0}
            return
        if genre == "superposition_place":
            self._placer(e.get("coin", ""))
            return
        if genre in NOTES:
            titre, prendre = NOTES[genre]
            texte = (prendre(e) or "").strip()
            if not texte:
                return
            self.notes.append({"titre": titre, "texte": texte, "t": time.time()})
            self.notes = self.notes[-5:]
            self.compte["notes"] += 1
            self._dire({"quoi": "note", "titre": titre, "texte": texte[:120]})

    # --- le dessin ---
    def _cadre(self, x, y, l, h, couleur, epaisseur=1, coin=14):
        """Un cadre holographique : quatre coins, pas un rectangle plein."""
        t = self.toile
        for (cx, cy, dx, dy) in ((x, y, 1, 1), (x + l, y, -1, 1), (x, y + h, 1, -1), (x + l, y + h, -1, -1)):
            t.create_line(cx, cy, cx + coin * dx, cy, fill=couleur, width=epaisseur)
            t.create_line(cx, cy, cx, cy + coin * dy, fill=couleur, width=epaisseur)

    def _dessiner(self):
        t = self.toile
        t.delete("all")
        maintenant = time.time()
        y = 10
        # la poignée : discrète, toujours là, et c'est par elle qu'on attrape la fenêtre à la souris.
        # Le fond d'abord (c'est lui qui reçoit le clic ; la couleur clé, elle, laisse passer), le reste par-dessus.
        t.create_rectangle(8, 4, LARGEUR - 8, 28, outline="", fill=COULEUR_PRISE)
        t.create_line(16, 12, 30, 12, fill=self.couleur, width=2)
        t.create_line(16, 18, 26, 18, fill=self.couleur, width=1)
        t.create_text(40, 15, anchor="w", text="J.A.R.V.I.S.", fill=self.couleur, font=("Consolas", 8, "bold"))
        t.create_text(LARGEUR - 16, 15, anchor="e", text="glissez-moi", fill="#7fb7c9", font=("Consolas", 7))
        t.create_line(8, 28, LARGEUR - 8, 28, fill=self.couleur, width=1)
        y = 38
        # la réponse de Jarvis, qui flotte tant qu'il parle
        if self.reponse["texte"] and maintenant - self.reponse["t"] < 25:
            lignes = _couper(self.reponse["texte"], 42)[:4]
            h = 26 + 20 * len(lignes)
            self._cadre(8, y, LARGEUR - 16, h, self.couleur, 2, 18)
            t.create_text(20, y + 12, anchor="nw", text="JARVIS", fill=self.couleur,
                          font=("Consolas", 8, "bold"))
            for i, ligne in enumerate(lignes):
                t.create_text(20, y + 30 + i * 20, anchor="nw", text=ligne, fill="#eaffff", font=("Consolas", 11))
            y += h + 14
        # les notifications
        for note in list(self.notes):
            age = maintenant - note["t"]
            if age > DUREE_NOTE:
                self.notes.remove(note)
                continue
            lignes = _couper(note["texte"], 40)[:2]
            h = 24 + 18 * len(lignes)
            glisse = int(max(0, (0.25 - min(age, 0.25)) * 4 * 40))      # elle arrive par la droite
            x = 12 + glisse
            self._cadre(x, y, LARGEUR - 24, h, self.couleur, 1, 10)
            t.create_text(x + 10, y + 8, anchor="nw", text=note["titre"].upper(), fill=self.couleur,
                          font=("Consolas", 8, "bold"))
            for i, ligne in enumerate(lignes):
                t.create_text(x + 10, y + 24 + i * 18, anchor="nw", text=ligne, fill="#cfefff", font=("Consolas", 10))
            y += h + 10
        # les jauges de la machine, en bas
        self._jauges(self.hauteur - 110)
        self.compte["images"] += 1

    def _jauges(self, y):
        t, e = self.toile, self.jauges
        if not e:
            return
        machine = e.get("machine") or {}
        gpu, cpu, ram = machine.get("gpu") or {}, machine.get("cpu") or {}, machine.get("ram") or {}
        lignes = []
        if gpu.get("vram_totale_mo"):
            lignes.append(("mémoire vidéo", gpu.get("vram_utilisee_mo", 0) / max(1, gpu["vram_totale_mo"]),
                           f"{gpu.get('vram_utilisee_mo', 0) / 1024:.1f} / {gpu['vram_totale_mo'] / 1024:.0f} Go"))
        if gpu.get("temperature"):
            lignes.append(("carte", min(1, gpu["temperature"] / 95), f"{gpu['temperature']:.0f} °C"))
        if cpu.get("utilisation") is not None:
            lignes.append(("processeur", min(1, cpu["utilisation"] / 100), f"{cpu['utilisation']:.0f} %"))
        if ram.get("totale_go"):
            lignes.append(("mémoire", min(1, ram.get("utilisation", 0) / 100),
                           f"{ram['totale_go'] - ram.get('libre_go', 0):.1f} / {ram['totale_go']:.0f} Go"))
        if not lignes:
            return
        self._cadre(12, y - 14, LARGEUR - 24, 24 + 22 * len(lignes), self.couleur, 1, 10)
        for i, (nom, part, texte) in enumerate(lignes):
            yy = y + 6 + i * 22
            t.create_text(24, yy, anchor="w", text=nom.upper(), fill=self.couleur, font=("Consolas", 8))
            t.create_rectangle(150, yy - 5, 150 + 180, yy + 5, outline=self.couleur)
            t.create_rectangle(150, yy - 5, 150 + int(180 * max(0.02, min(1, part))), yy + 5,
                               outline="", fill=self.couleur)
            t.create_text(LARGEUR - 24, yy, anchor="e", text=texte, fill="#cfefff", font=("Consolas", 9))

    def _prendre(self, e):
        self.prise = (e.x_root - self.racine.winfo_x(), e.y_root - self.racine.winfo_y())

    def _glisser(self, e):
        if not self.prise:
            return
        self.x, self.y = e.x_root - self.prise[0], e.y_root - self.prise[1]
        self.racine.geometry(f"{LARGEUR}x{self.hauteur}+{self.x}+{self.y}")

    def _poser(self, _):
        self.prise = None
        _garder_position(self.racine.winfo_x(), self.racine.winfo_y(), self.hauteur)

    def _boucle(self):
        try:
            while True:
                self._traiter(self.file.get_nowait())
        except queue.Empty:
            pass
        if self.masquee and time.time() - self.masquee_depuis > 30:
            self.masquee = False              # le HUD ne donne plus signe de vie : on revient
            self._dire({"quoi": "visible", "raison": "plus de nouvelles du HUD"})
        if self.masquee:
            if self.racine.state() != "withdrawn":
                self.racine.withdraw()
        else:
            if self.racine.state() == "withdrawn":
                self.racine.deiconify()
                self._styles_windows()                          # Tk remet ses attributs : on repose les nôtres
            self._dessiner()
        if self.compte["images"] % 12 == 0:
            self._ecrire_etat()
        if not self.arret.is_set():
            self.racine.after(40, self._boucle)               # 25 images par seconde : c'est du texte

    def tourner(self):
        self._dire({"quoi": "prete", "hwnd": self.hwnd, "largeur": LARGEUR, "hauteur": self.hauteur})
        self.compte["images"] = 1
        self._ecrire_etat()
        try:
            self.racine.mainloop()
        finally:
            self.arret.set()


def _position_gardee() -> dict:
    """La dernière place choisie (config.json → superposition.place)."""
    try:
        c = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
        return c.get("superposition", {}).get("place", {}) or {}
    except (OSError, ValueError):
        return {}


def _faire_place() -> str:
    """Une seule superposition à la fois. Un lancement précédent oublié est prié de partir (poliment, WM_CLOSE).

    Sans ça, deux panneaux se superposaient l'un sur l'autre et se disputaient le fichier d'état — c'est ce que
    l'on voyait le 20/09. On ne ferme que ce qu'on est sûr d'avoir ouvert : une fenêtre Tk dont le processus est
    bien celui que la superposition précédente avait noté.
    """
    try:
        vieux = json.loads(ETAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    hwnd, pid = int(vieux.get("hwnd") or 0), int(vieux.get("pid") or 0)
    if not hwnd or not pid or pid == os.getpid():
        return ""
    try:
        u = ctypes.windll.user32
        if not u.IsWindow(hwnd):
            return ""
        classe = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, classe, 64)
        proprietaire = ctypes.c_ulong()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(proprietaire))
        if not classe.value.lower().startswith("tk") or proprietaire.value != pid:
            return ""
        u.PostMessageW(hwnd, 0x0010, 0, 0)                     # WM_CLOSE
        for _ in range(20):
            if not u.IsWindow(hwnd):
                break
            time.sleep(0.1)
        return f"ancienne fenêtre fermée (pid {pid})"
    except Exception:
        return ""


def _garder_position(x: int, y: int, hauteur: int):
    try:
        chemin = Path(__file__).resolve().parents[1] / "config.json"
        c = json.loads(chemin.read_text(encoding="utf-8"))
        c.setdefault("superposition", {})["place"] = {"x": int(x), "y": int(y), "hauteur": int(hauteur)}
        chemin.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError):
        pass


def _couper(texte: str, largeur: int) -> list[str]:
    mots, lignes, ligne = texte.split(), [], ""
    for mot in mots:
        if len(ligne) + len(mot) + 1 > largeur:
            lignes.append(ligne)
            ligne = mot
        else:
            ligne = (ligne + " " + mot).strip()
    if ligne:
        lignes.append(ligne)
    return lignes


def main() -> int:
    a = argparse.ArgumentParser(description="La superposition de Jarvis, par-dessus Windows")
    a.add_argument("--serveur", default="http://127.0.0.1:8765")
    a.add_argument("--etat", action="store_true", help="écrit ce qu'elle affiche, en JSON, sur la sortie")
    o = a.parse_args()
    place = _faire_place()                     # jamais deux panneaux l'un sur l'autre
    if place and o.etat:
        print(json.dumps({"quoi": "place", "detail": place}, ensure_ascii=False), flush=True)
    Superposition(o.serveur, o.etat).tourner()
    return 0


if __name__ == "__main__":
    sys.exit(main())
