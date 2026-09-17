"""Le service cloud « tout chez l'auteur » : quand son Jarvis tourne, sa carte sert les clients qui n'ont pas le
matériel, à travers une adresse Internet fixe. Démarré par le serveur si config `service_cloud.actif`.
  1. la passerelle (passerelle/serveur.py : comptes, Stripe, décompte) sur 127.0.0.1:<port>, en sous-processus ;
  2. l'agent maison (jarvis/maison.py) qui va chercher le travail sur cette passerelle et le fait tourner sur l'Ollama local ;
  3. le tunnel ngrok qui expose la passerelle sur https://<domaine> (jeton NGROK_AUTHTOKEN dans .secrets,
     domaine fixe gratuit du compte ngrok dans config `service_cloud.domaine`). Sans jeton : pas de tunnel, mais la
     passerelle et l'agent tournent quand même (tests en local).
PC éteint = tout éteint : les clients voient « cerveau hors ligne ». Rien à payer."""
import json
import secrets
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from .config import CONFIG, RACINE, SECRETS

REGLAGES = CONFIG.get("service_cloud", {})
PORT = int(REGLAGES.get("port", 8791))
DOMAINE = (REGLAGES.get("domaine") or "").strip()
JETON_NGROK = SECRETS.get("NGROK_AUTHTOKEN", "").strip()
NGROK = RACINE / "outils_externes" / "ngrok" / "ngrok.exe"
PASSERELLE_JSON = RACINE / "passerelle" / "passerelle.json"
journal = logging.getLogger("service_cloud")
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)

etat = {"actif": False, "passerelle": False, "tunnel": False, "adresse": "", "erreur": None}
_processus: list[subprocess.Popen] = []


# --- les enfants meurent avec Jarvis (objet « job » Windows), même si la fenêtre est fermée brutalement ------------
def _creer_job():
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        job = k.CreateJobObjectW(None, None)

        class LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_uint64), ("WriteOperationCount", ctypes.c_uint64),
                        ("OtherOperationCount", ctypes.c_uint64), ("ReadTransferCount", ctypes.c_uint64),
                        ("WriteTransferCount", ctypes.c_uint64), ("OtherTransferCount", ctypes.c_uint64)]

        class EXT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", LIMIT), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        info = EXT()
        info.BasicLimitInformation.LimitFlags = 0x2000     # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        return job
    except Exception:
        return None


_JOB = _creer_job()


def _adopter(p: subprocess.Popen):
    _processus.append(p)
    if _JOB:
        try:
            import ctypes
            ctypes.windll.kernel32.AssignProcessToJobObject(_JOB, int(p._handle))
        except Exception:
            pass


def _tuer_orphelins():
    """Une passerelle ou un ngrok laissés par un Jarvis précédent : on les arrête avant de repartir propre."""
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = " ".join(p.info.get("cmdline") or [])
                nom = (p.info.get("name") or "").lower()
                if ("passerelle.serveur" in cmd and f"--port {PORT}" in cmd) or nom == "ngrok.exe":
                    if p.pid != os.getpid():
                        p.kill()
                        journal.info("orphelin arrêté : %s (%s)", nom, p.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(1.0)
    except Exception:
        journal.exception("nettoyage des orphelins")


def _preparer_passerelle_json():
    """passerelle.json local : mode maison, secret partagé avec l'agent, prix généreux, plafond journalier."""
    base = {"mode": "maison", "prix_minute_eur": 0.005, "plafond_minutes_jour": 120, "maison_delai_s": 180,
            "modeles": [CONFIG["cerveau"]["modele"], CONFIG["vision"]["modele"]], "secret_admin": secrets.token_urlsafe(24)}
    if PASSERELLE_JSON.exists():
        try:
            base.update(json.loads(PASSERELLE_JSON.read_text(encoding="utf-8")))
        except Exception:
            pass
    base["mode"] = "maison"
    base["secret_maison"] = SECRETS.get("MAISON_SECRET", "")
    for cle in ("prix_minute_eur", "plafond_minutes_jour", "lien_paiement", "lien_don", "objectifs"):
        if cle in REGLAGES:
            base[cle] = REGLAGES[cle]
    PASSERELLE_JSON.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _demarrer_passerelle():
    _preparer_passerelle_json()
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "passerelle.serveur:app", "--host", "127.0.0.1",
                          "--port", str(PORT), "--log-level", "warning"], cwd=str(RACINE),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SANS_FENETRE)
    _adopter(p)
    for _ in range(30):
        time.sleep(0.5)
        try:
            requests.get(f"http://127.0.0.1:{PORT}/maison/etat", timeout=2)
            etat["passerelle"] = True
            return True
        except requests.RequestException:
            if p.poll() is not None:
                break
    etat["erreur"] = "la passerelle n'a pas démarré"
    return False


def _demarrer_tunnel():
    if not JETON_NGROK or not DOMAINE:
        etat["erreur"] = "tunnel absent : NGROK_AUTHTOKEN (.secrets) ou service_cloud.domaine manquant"
        return False
    if not NGROK.exists():
        etat["erreur"] = f"ngrok.exe introuvable ({NGROK})"
        return False
    p = subprocess.Popen([str(NGROK), "http", str(PORT), f"--domain={DOMAINE}", f"--authtoken={JETON_NGROK}",
                          "--log=stdout", "--log-format=json"], cwd=str(NGROK.parent),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SANS_FENETRE)
    _adopter(p)
    for _ in range(40):
        time.sleep(0.5)
        try:
            r = requests.get(f"https://{DOMAINE}/maison/etat", timeout=5)
            if r.status_code == 200:
                etat["tunnel"], etat["adresse"] = True, f"https://{DOMAINE}"
                return True
        except requests.RequestException:
            if p.poll() is not None:
                break
    etat["erreur"] = "le tunnel ngrok ne répond pas (jeton, domaine, ou ngrok déjà lancé ailleurs ?)"
    return False


def _demarrer_agent():
    from . import maison
    maison.PASSERELLE = f"http://127.0.0.1:{PORT}"
    maison.SECRET = SECRETS.get("MAISON_SECRET", "")
    arret = threading.Event()
    threading.Thread(target=maison.boucle, args=(arret,), daemon=True, name="maison").start()
    return arret


def demarrer(sur_evenement=lambda e: None):
    """Tout en fond, dans l'ordre : passerelle, agent, tunnel. Retourne tout de suite."""
    if not REGLAGES.get("actif"):
        return
    if not SECRETS.get("MAISON_SECRET"):
        etat["erreur"] = "MAISON_SECRET manquant dans .secrets"
        return

    def travail():
        etat["actif"] = True
        _tuer_orphelins()
        if _demarrer_passerelle():
            _demarrer_agent()
            _demarrer_tunnel()
        sur_evenement({"type": "service_cloud", "t": time.time(), **{k: v for k, v in etat.items()}})
        journal.info("service cloud : %s", etat)

    threading.Thread(target=travail, daemon=True, name="service-cloud").start()


def arreter():
    for p in _processus:
        try:
            p.terminate()
        except Exception:
            pass


# =============================================================================================
# Le service autonome : « python -m jarvis cloud ». Tourne sans le HUD, démarre avec Windows,
# relance ses morceaux s'ils tombent. L'application Jarvis, quand elle s'ouvre, le détecte et ne le double pas.
# =============================================================================================
PID_FICHIER = RACINE / "workspace" / "cloud.pid"
DEMARRAGE_DOSSIER = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
RACCOURCI = DEMARRAGE_DOSSIER / "Jarvis Cloud.vbs"


def service_externe_actif() -> bool:
    """Un service autonome tourne-t-il déjà (pid vivant et passerelle qui répond) ?"""
    try:
        pid = int(PID_FICHIER.read_text().strip())
        import psutil
        if not psutil.pid_exists(pid):
            return False
        requests.get(f"http://127.0.0.1:{PORT}/maison/etat", timeout=2)
        return True
    except Exception:
        return False


def _ollama_pret() -> bool:
    from .preparation import demarrer_ollama
    return demarrer_ollama(CONFIG["ollama"]["url"])


def boucle_autonome():
    """Passerelle + agent + tunnel, surveillés toutes les 20 s, jusqu'à Ctrl+C ou fermeture de session."""
    import signal
    if not SECRETS.get("MAISON_SECRET"):
        raise SystemExit("MAISON_SECRET manquant dans .secrets")
    PID_FICHIER.parent.mkdir(exist_ok=True)
    PID_FICHIER.write_text(str(os.getpid()))
    print(f"[Jarvis Cloud] service autonome, pid {os.getpid()} : passerelle sur 127.0.0.1:{PORT}, tunnel {DOMAINE or 'absent'}", flush=True)
    if not _ollama_pret():
        print("[Jarvis Cloud] Ollama injoignable : le cerveau ne pourra pas répondre.", flush=True)
    _tuer_orphelins()
    etat["actif"] = True
    passerelle_ok = _demarrer_passerelle()
    agent = _demarrer_agent() if passerelle_ok else None
    tunnel_ok = _demarrer_tunnel() if passerelle_ok else False
    print(f"[Jarvis Cloud] passerelle {'ok' if passerelle_ok else 'KO'}, tunnel {'ok' if tunnel_ok else 'KO : ' + str(etat['erreur'])}", flush=True)
    # Rien n'est chargé en VRAM tant qu'aucun client ne parle : l'auteur joue sur cette carte. Le modèle se charge à la
    # première question, répond, et Ollama le décharge après `service_cloud.keep_alive` (2 min) sans demande.
    arret = {"demande": False}

    def sur_signal(*_):
        arret["demande"] = True
    signal.signal(signal.SIGINT, sur_signal)
    signal.signal(signal.SIGTERM, sur_signal)
    try:
        while not arret["demande"]:
            time.sleep(20)
            # la passerelle
            try:
                requests.get(f"http://127.0.0.1:{PORT}/maison/etat", timeout=3)
            except requests.RequestException:
                print("[Jarvis Cloud] passerelle tombée : relance", flush=True)
                etat["passerelle"] = False
                _demarrer_passerelle()
            # le tunnel
            if DOMAINE and JETON_NGROK:
                try:
                    r = requests.get(f"https://{DOMAINE}/maison/etat", timeout=8)
                    etat["tunnel"] = r.status_code == 200
                except requests.RequestException:
                    etat["tunnel"] = False
                if not etat["tunnel"]:
                    print("[Jarvis Cloud] tunnel tombé : relance", flush=True)
                    for p in list(_processus):
                        if "ngrok" in " ".join(p.args if isinstance(p.args, (list, tuple)) else [str(p.args)]).lower():
                            try:
                                p.kill()
                            except Exception:
                                pass
                            _processus.remove(p)
                    _demarrer_tunnel()
            # l'agent
            from . import maison
            if not maison.etat.get("actif"):
                print("[Jarvis Cloud] agent tombé : relance", flush=True)
                agent = _demarrer_agent()
    finally:
        if agent:
            agent.set()
        arreter()
        PID_FICHIER.unlink(missing_ok=True)
        print("[Jarvis Cloud] arrêté.", flush=True)


def installer_demarrage_windows() -> str:
    """Un script VBS dans le dossier Démarrage de l'utilisateur : lance cloud.bat sans fenêtre à l'ouverture de session.
    Aucun droit administrateur."""
    DEMARRAGE_DOSSIER.mkdir(parents=True, exist_ok=True)
    cloud_bat = RACINE / "cloud.bat"
    RACCOURCI.write_text(f'CreateObject("Wscript.Shell").Run """{cloud_bat}""", 0, False\n', encoding="utf-8")
    return str(RACCOURCI)


def desinstaller_demarrage_windows() -> bool:
    if RACCOURCI.exists():
        RACCOURCI.unlink()
        return True
    return False


def solde_admin() -> dict | None:
    """Résumé pour le HUD : clients, secondes servies, euros (via /admin/clients de la passerelle locale)."""
    if not etat["passerelle"]:
        return None
    try:
        secret = json.loads(PASSERELLE_JSON.read_text(encoding="utf-8")).get("secret_admin", "")
        r = requests.get(f"http://127.0.0.1:{PORT}/admin/clients", headers={"X-Admin": secret}, timeout=3)
        if r.status_code == 200:
            j = r.json()
            return {"clients": len(j["clients"]), "requetes": j["requetes"], "secondes": j["secondes_gpu"],
                    "euros": j["facture_clients_eur"]}
    except Exception:
        pass
    return None
