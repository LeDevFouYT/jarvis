"""L'écran des tests : lance un test et montre chaque vérification au moment où elle tombe, dans le navigateur.

    python -m jarvis.tests.ecran 8767          puis http://127.0.0.1:8767/?lancer=telegram_entrant

Chaque test est lancé dans son propre processus (python -u -X utf8 -m jarvis.tests.<nom> [arguments]) ; sa sortie
arrive ligne par ligne (flux SSE) : ✓ en vert, ✗ en rouge, les détails en gris, le chronomètre qui tourne, le bilan à
la fin. L'historique des lancements reste affiché tant que l'écran est ouvert."""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RACINE = Path(__file__).resolve().parents[2]
TESTS = [("ordres", "il obéit · question entière, outil appelé"), ("telegram_entrant", "13 · téléphone Telegram"), ("voir_et_creer", "14-16 · webcam, vidéo, miniatures"),
         ("youtube", "17-19 · chaîne YouTube"), ("memoire_longue", "02 · mémoire"), ("conversation_continue", "03 · conversation"),
         ("interruption", "04 · interruption"), ("eclair", "05 · réponse éclair"), ("personnalites", "06 · personnalités"),
         ("langues", "07 · langues"), ("fenetres", "09 · fenêtres"), ("rangement", "10 · rangement"), ("dictee", "11 · dictée"),
         ("sentinelle", "12 · sentinelle"), ("armures", "v3-1 · armures et mode vidéo"), ("visage", "v3-2 · le visage de particules"), ("majordome", "v3-3 · la voix du majordome"), ("hologramme", "v3-4 · les hologrammes"), ("gestes", "v3-5 · les gestes"), ("scan", "v3-6 · le scan de la pièce"), ("globe", "v3-7 · le globe"), ("video_ia", "v3-8 · la vidéo"), ("superposition", "v3-9 · hors du HUD"), ("repetition", "RÉPÉTITION GÉNÉRALE"),
         ("live", "mode live · le tchat du direct"), ("intrusion", "intrusion · cette machine seulement"), ("cloud_complet", "cloud · un client a droit à tout"), ("passerelle_rattrapage", "passerelle · rattrapage"), ("mise_en_page", "mise en page · rien ne dépasse"), ("cadence", "cadence du HUD")]


class Lancement:
    def __init__(self, nom: str, arguments: list[str]):
        self.nom, self.arguments, self.lignes, self.debut, self.fin, self.code = nom, arguments, [], time.time(), None, None
        self.abonnes: list[queue.Queue] = []
        threading.Thread(target=self._lire, daemon=True).start()

    def _lire(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        proc = subprocess.Popen([str(RACINE / ".venv" / "Scripts" / "python.exe"), "-u", "-X", "utf8", "-m", f"jarvis.tests.{self.nom}", *self.arguments],
                                cwd=str(RACINE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True, encoding="utf-8",
                                errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for ligne in proc.stdout:
            ligne = ligne.rstrip("\n")
            if "Warning" in ligne and "warn(" in ligne:
                continue
            self._publier({"ligne": ligne, "t": round(time.time() - self.debut, 1)})
        self.code = proc.wait()
        self.fin = time.time()
        self._publier({"fin": True, "code": self.code, "duree": round(self.fin - self.debut, 1)})

    def _publier(self, message: dict):
        self.lignes.append(message)
        for q in list(self.abonnes):
            q.put(message)


LANCEMENTS: list[Lancement] = []


class Gestion(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _envoyer(self, corps: bytes, type_contenu: str):
        self.send_response(200)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            return self._envoyer(PAGE.replace("__TESTS__", json.dumps(TESTS, ensure_ascii=False)).encode("utf-8"), "text/html; charset=utf-8")
        if url.path == "/lancer":
            nom = q.get("nom", "")
            if nom not in dict(TESTS):
                return self._envoyer(b'{"erreur": "test inconnu"}', "application/json")
            en_cours = next((l for l in LANCEMENTS if l.fin is None), None)
            if en_cours:
                return self._envoyer(json.dumps({"erreur": f"{en_cours.nom} tourne encore"}).encode(), "application/json")
            LANCEMENTS.append(Lancement(nom, [a for a in q.get("arguments", "").split() if a]))
            return self._envoyer(json.dumps({"numero": len(LANCEMENTS) - 1}).encode(), "application/json")
        if url.path == "/flux":
            l = LANCEMENTS[int(q.get("numero", -1))]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            file = queue.Queue()
            deja = list(l.lignes)
            l.abonnes.append(file)
            try:
                for m in deja:
                    self.wfile.write(f"data: {json.dumps(m, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                while not (deja and deja[-1].get("fin")):
                    try:
                        m = file.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    self.wfile.write(f"data: {json.dumps(m, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                    if m.get("fin"):
                        break
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            finally:
                l.abonnes.remove(file)
            return
        self._envoyer(b"introuvable", "text/plain")


PAGE = r"""<!doctype html><html lang="fr"><meta charset="utf-8"><title>Tests en direct · Jarvis</title>
<style>
:root{--fond:#03101a;--cyan:#5fe3ff;--dim:#6f93a3;--vert:#5ff2a0;--rouge:#ff6b6b}
body{margin:0;background:var(--fond);color:#dff6ff;font:14px/1.45 "Segoe UI",system-ui,sans-serif;padding:0 20px 40px}
header{position:sticky;top:0;background:var(--fond);padding:14px 0 10px;border-bottom:1px solid #12394a;z-index:2}
h1{margin:0 0 8px;font-size:12px;letter-spacing:.35em;text-transform:uppercase;color:var(--cyan)}
.boutons{display:flex;flex-wrap:wrap;gap:6px}.boutons button{background:#07202e;border:1px solid #1b4658;color:#dff6ff;padding:6px 10px;border-radius:3px;cursor:pointer;font-size:12px}
.boutons button:hover{border-color:var(--cyan)}
.lancement{margin:16px 0;border:1px solid #12394a;border-radius:4px;background:rgba(8,38,58,.4)}
.tete{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid #12394a}
.tete b{font-size:15px}.chrono{font-variant-numeric:tabular-nums;color:var(--cyan)}
.bilan{padding:10px 14px;font-weight:600}.bilan.ok{color:var(--vert)}.bilan.ko{color:var(--rouge)}
.lignes{padding:8px 14px;font-family:Consolas,monospace;font-size:13px}
.l{white-space:pre-wrap;animation:apparait .35s ease-out}.l.ok{color:var(--vert)}.l.ko{color:var(--rouge);font-weight:600}.l.info{color:var(--dim)}.l.titre{color:var(--cyan);font-weight:600;margin-top:4px}
.compteurs{font-size:13px;color:var(--dim)}.compteurs b.v{color:var(--vert)}.compteurs b.r{color:var(--rouge)}
@keyframes apparait{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}
.encours::after{content:" ●";color:var(--cyan);animation:clignote 1s infinite}@keyframes clignote{50%{opacity:.2}}
</style>
<header><h1>Jarvis · tests en direct</h1><div class=boutons id=boutons></div></header>
<div id=lancements></div>
<script>
const TESTS=__TESTS__;
const boutons=document.getElementById("boutons");
for(const [nom,libelle] of TESTS){const b=document.createElement("button");b.textContent=libelle;b.onclick=()=>lancer(nom,"");boutons.appendChild(b);}
async function lancer(nom,args){const r=await (await fetch(`/lancer?nom=${nom}&arguments=${encodeURIComponent(args)}`)).json();
if(r.erreur){alert(r.erreur);return;}suivre(r.numero,nom,args);}
function suivre(numero,nom,args){
const bloc=document.createElement("section");bloc.className="lancement";
bloc.innerHTML=`<div class=tete><b class=encours>${(TESTS.find(t=>t[0]===nom)||[nom,nom])[1]} ${args}</b><span class=compteurs><b class=v>0</b> ✓ · <b class=r>0</b> ✗ · <span class=chrono>0,0 s</span></span></div><div class=lignes></div>`;
document.getElementById("lancements").prepend(bloc);
const lignes=bloc.querySelector(".lignes"),v=bloc.querySelector(".v"),r=bloc.querySelector(".r"),chrono=bloc.querySelector(".chrono"),titre=bloc.querySelector(".tete b");
const debut=performance.now();const minuteur=setInterval(()=>chrono.textContent=((performance.now()-debut)/1000).toFixed(1).replace(".",",")+" s",100);
let nv=0,nr=0;const es=new EventSource(`/flux?numero=${numero}`);
es.onmessage=ev=>{const m=JSON.parse(ev.data);
if(m.fin){es.close();clearInterval(minuteur);titre.classList.remove("encours");chrono.textContent=String(m.duree).replace(".",",")+" s";
const b=document.createElement("div");b.className="bilan "+(nr===0&&m.code===0?"ok":"ko");b.textContent=nr===0&&m.code===0?`Tout est vert : ${nv} vérifications réussies en ${String(m.duree).replace(".",",")} s`:`${nr} échec(s) sur ${nv+nr} vérifications (code ${m.code})`;bloc.appendChild(b);return;}
const t=m.ligne;if(!t.trim())return;const d=document.createElement("div");
const ok=/^\s*✓/.test(t),ko=/^\s*✗/.test(t);
d.className="l "+(ok?"ok":ko?"ko":t.startsWith("===")||t.startsWith("---")?"titre":"info");
if(ok)v.textContent=++nv;if(ko)r.textContent=++nr;
d.textContent=t;lignes.appendChild(d);d.scrollIntoView({block:"nearest"});};}
const p=new URLSearchParams(location.search);if(p.get("lancer"))lancer(p.get("lancer"),p.get("arguments")||"");
</script></html>"""


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    serveur = ThreadingHTTPServer(("127.0.0.1", port), Gestion)
    print(f"écran des tests sur http://127.0.0.1:{port}/", flush=True)
    serveur.serve_forever()
