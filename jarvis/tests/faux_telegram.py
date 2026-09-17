"""Un faux Telegram local, pour les tests et les essais en direct, sans compte ni Internet.

Même API que le vrai (getMe, getUpdates, sendMessage, editMessageText, answerCallbackQuery, sendPhoto, sendVoice,
getFile et téléchargement) et une page « téléphone » sur / : la discussion avec le bot, les boutons cliquables, les
vocaux de Jarvis jouables, un champ pour écrire, un micro pour envoyer un vocal, et un bouton « inconnu » qui écrit
au bot depuis une autre discussion.

    python -m jarvis.tests.faux_telegram 8766      puis Jarvis lancé avec JARVIS_TELEGRAM_API=http://127.0.0.1:8766
                                                   JARVIS_SECRET_TELEGRAM_TOKEN=123456:ESSAI JARVIS_SECRET_TELEGRAM_CHAT_ID=777001
"""
import base64
import itertools
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PROPRIETAIRE, INCONNU, JETON = "777001", "999999", "123456:ESSAI"


def _multipart(corps: bytes, type_contenu: str) -> dict:
    """Les champs d'un formulaire multipart : {nom: bytes}."""
    frontiere = type_contenu.split("boundary=")[-1].strip().strip('"').encode()
    champs = {}
    for partie in corps.split(b"--" + frontiere):
        if b"\r\n\r\n" not in partie:
            continue
        entete, _, valeur = partie.partition(b"\r\n\r\n")
        nom = entete.split(b'name="')[1].split(b'"')[0].decode() if b'name="' in entete else ""
        champs[nom] = valeur[:-2] if valeur.endswith(b"\r\n") else valeur
    return champs


class FauxTelegram:
    def __init__(self, port: int = 0):
        self.a_livrer: list[dict] = []
        self.discussion: list[dict] = []   # ce que montre le téléphone (moi, jarvis, inconnu)
        self.envoyes, self.photos, self.vocaux, self.modifications, self.demandes = [], [], [], [], 0
        self.fichiers: dict[str, bytes] = {}
        self._ids = itertools.count(101)
        self._messages = itertools.count(1)
        self.verrou = threading.Lock()
        faux = self

        class Gestion(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _repondre(self, donnees, type_contenu="application/json", code=200):
                corps = donnees if isinstance(donnees, bytes) else json.dumps(donnees).encode()
                self.send_response(code)
                self.send_header("Content-Type", type_contenu)
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def do_GET(self):
                url = urlparse(self.path)
                q = parse_qs(url.query)
                if url.path in ("/", "/telephone"):
                    return self._repondre(PAGE.encode("utf-8"), "text/html; charset=utf-8")
                if url.path == "/discussion":
                    return self._repondre({"messages": faux.discussion})
                if url.path.startswith("/fichier/"):
                    return self._repondre(faux.fichiers.get(url.path.split("/")[-1], b""), "audio/ogg")
                if "/file/bot" in url.path:
                    return self._repondre(faux.fichiers.get(url.path.split("/")[-1], b""), "application/octet-stream")
                if url.path.endswith("/getMe"):
                    if JETON not in url.path:
                        return self._repondre({"ok": False, "description": "Unauthorized"}, code=401)
                    return self._repondre({"ok": True, "result": {"id": 1, "is_bot": True, "username": "jarvis_essai_bot"}})
                if url.path.endswith("/getFile"):
                    fid = q.get("file_id", [""])[0]
                    return self._repondre({"ok": True, "result": {"file_id": fid, "file_path": fid}})
                if url.path.endswith("/getUpdates"):
                    faux.demandes += 1
                    offset = int(q.get("offset", ["0"])[0])
                    attente = min(float(q.get("timeout", ["0"])[0]), 2.0)
                    fin = time.time() + attente
                    while time.time() < fin and not [m for m in faux.a_livrer if m["update_id"] >= offset]:
                        time.sleep(0.05)
                    return self._repondre({"ok": True, "result": [m for m in faux.a_livrer if m["update_id"] >= offset]})
                self._repondre({"ok": False}, code=404)

            def do_POST(self):
                url = urlparse(self.path)
                longueur = int(self.headers.get("Content-Length", 0))
                corps = self.rfile.read(longueur)
                type_contenu = self.headers.get("Content-Type", "")
                # --- la page téléphone ---
                if url.path == "/ecrire":
                    d = json.loads(corps)
                    faux.recevoir(d["texte"], INCONNU if d.get("inconnu") else PROPRIETAIRE)
                    return self._repondre({"ok": True})
                if url.path == "/vocal":
                    faux.vocal(corps)
                    return self._repondre({"ok": True})
                if url.path == "/cliquer":
                    d = json.loads(corps)
                    faux.cliquer(d["message_id"], d["data"])
                    return self._repondre({"ok": True})
                # --- l'API du bot ---
                d = json.loads(corps) if "json" in type_contenu else {}
                with faux.verrou:
                    if url.path.endswith("/sendMessage"):
                        n = next(faux._messages)
                        faux.envoyes.append(d["text"])
                        boutons = (d.get("reply_markup") or {}).get("inline_keyboard") or []
                        faux.discussion.append({"id": n, "de": "jarvis", "texte": d["text"], "boutons": boutons, "t": time.time()})
                        return self._repondre({"ok": True, "result": {"message_id": n}})
                    if url.path.endswith("/editMessageText"):
                        faux.modifications.append(d["text"])
                        for m in faux.discussion:
                            if m["id"] == d.get("message_id"):
                                m["texte"], m["boutons"] = d["text"], []
                        return self._repondre({"ok": True, "result": {}})
                    if url.path.endswith("/answerCallbackQuery"):
                        return self._repondre({"ok": True, "result": True})
                    if url.path.endswith("/sendPhoto"):
                        champs = _multipart(corps, type_contenu)
                        faux.photos.append(len(corps))
                        nom = f"photo{len(faux.photos)}"
                        faux.fichiers[nom] = champs.get("photo", b"")
                        faux.discussion.append({"id": next(faux._messages), "de": "jarvis", "photo": nom,
                                                "texte": champs.get("caption", b"").decode("utf-8", "replace"), "t": time.time()})
                        return self._repondre({"ok": True, "result": {}})
                    if url.path.endswith("/sendVoice"):
                        champs = _multipart(corps, type_contenu)
                        ogg = champs.get("voice", b"")
                        faux.vocaux.append(ogg)
                        nom = f"vocal{len(faux.vocaux)}"
                        faux.fichiers[nom] = ogg
                        faux.discussion.append({"id": next(faux._messages), "de": "jarvis", "vocal": nom, "t": time.time()})
                        return self._repondre({"ok": True, "result": {}})
                self._repondre({"ok": True, "result": {}})

        self.serveur = ThreadingHTTPServer(("127.0.0.1", port), Gestion)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.serveur.server_address[1]}"

    # --- ce que fait la personne au téléphone ---
    def recevoir(self, texte: str, chat: str = PROPRIETAIRE):
        with self.verrou:
            n = next(self._ids)
            prive = {"id": int(chat), "type": "private", "first_name": "Inconnu" if chat == INCONNU else "Vous"}
            self.a_livrer.append({"update_id": n, "message": {"message_id": n, "chat": prive,
                                                             "from": {"username": "inconnu" if chat == INCONNU else "moi"}, "text": texte}})
            self.discussion.append({"id": -n, "de": "inconnu" if chat == INCONNU else "moi", "texte": texte, "t": time.time()})

    def vocal(self, donnees: bytes, chat: str = PROPRIETAIRE):
        with self.verrou:
            n = next(self._ids)
            nom = f"entrant{n}"
            self.fichiers[nom] = donnees
            self.a_livrer.append({"update_id": n, "message": {"message_id": n, "chat": {"id": int(chat), "type": "private"},
                                                             "voice": {"file_id": nom, "duration": 3}}})
            self.discussion.append({"id": -n, "de": "moi", "vocal": nom, "t": time.time()})

    def cliquer(self, message_id: int, data: str, chat: str = PROPRIETAIRE):
        with self.verrou:
            n = next(self._ids)
            self.a_livrer.append({"update_id": n, "callback_query": {"id": f"cb{n}", "data": data, "from": {"username": "moi"},
                                                                    "message": {"message_id": message_id, "chat": {"id": int(chat)}}}})

    def dernier_avec_boutons(self) -> dict | None:
        return next((m for m in reversed(self.discussion) if m.get("boutons")), None)

    def arreter(self):
        self.serveur.shutdown()


PAGE = r"""<!doctype html><html lang="fr"><meta charset="utf-8"><title>Téléphone d'essai</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;background:#0d1418;font:15px system-ui,sans-serif;color:#e8eef1;display:flex;justify-content:center}
.tel{width:min(430px,100vw);height:100vh;display:flex;flex-direction:column;background:#0e1621;border-left:1px solid #1f2c38;border-right:1px solid #1f2c38}
header{padding:12px 16px;background:#17212b;display:flex;gap:10px;align-items:center}
header b{display:block}header small{color:#7f91a4}.av{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#1fa3e0,#5fe3ff);display:grid;place-items:center;font-weight:700;color:#07202c}
#fil{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:6px}
.m{max-width:82%;padding:7px 11px;border-radius:12px;white-space:pre-wrap;line-height:1.35;word-wrap:break-word}
.moi{align-self:flex-end;background:#2b5278}.jarvis{align-self:flex-start;background:#182533}
.inconnu{align-self:flex-end;background:#5a2a2a}.inconnu::before{content:"autre compte · ";color:#f3b0b0;font-size:12px}
.m audio{width:230px;height:34px;display:block}.m img{max-width:100%;border-radius:8px;display:block}
.boutons{display:flex;gap:6px;margin-top:6px}.boutons button{flex:1;background:#2b5278;border:0;color:#fff;padding:8px;border-radius:8px;font-size:14px;cursor:pointer}
footer{padding:8px;background:#17212b;display:flex;gap:6px;flex-wrap:wrap}
footer input{flex:1 1 200px;background:#242f3d;border:0;color:#fff;padding:10px;border-radius:18px;font-size:15px}
footer button{background:#2b5278;border:0;color:#fff;padding:8px 12px;border-radius:18px;cursor:pointer}
footer button.rouge{background:#6b2f2f}footer button.enreg{background:#c0392b}
</style>
<div class=tel><header><div class=av>J</div><div><b>Jarvis</b><small>bot d'essai · local</small></div></header>
<div id=fil></div>
<footer><input id=texte placeholder="Message" autocomplete=off><button id=envoyer>Envoyer</button>
<button id=micro>🎙 vocal</button><button id=inconnu class=rouge>message d'un inconnu</button></footer></div>
<script>
const fil=document.getElementById("fil");let vus="";
async function maj(){const d=await (await fetch("/discussion")).json();const s=JSON.stringify(d.messages);if(s===vus)return;vus=s;
const bas=fil.scrollTop+fil.clientHeight>=fil.scrollHeight-40;fil.innerHTML="";
for(const m of d.messages){const e=document.createElement("div");e.className="m "+m.de;
if(m.photo){const i=document.createElement("img");i.src="/fichier/"+m.photo;e.appendChild(i);}
if(m.vocal){const a=document.createElement("audio");a.controls=true;a.src="/fichier/"+m.vocal;e.appendChild(a);}
if(m.texte){const t=document.createElement("div");t.textContent=m.texte;e.appendChild(t);}
if(m.boutons&&m.boutons.length){const b=document.createElement("div");b.className="boutons";
for(const ligne of m.boutons)for(const x of ligne){const k=document.createElement("button");k.textContent=x.text;
k.onclick=()=>fetch("/cliquer",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message_id:m.id,data:x.callback_data})});b.appendChild(k);}
e.appendChild(b);}
fil.appendChild(e);}
if(bas)fil.scrollTop=fil.scrollHeight;}
setInterval(maj,400);maj();
async function ecrire(inconnu){const i=document.getElementById("texte");const t=i.value.trim()||(inconnu?"/etat":"");if(!t)return;i.value="";
await fetch("/ecrire",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({texte:t,inconnu})});maj();}
document.getElementById("envoyer").onclick=()=>ecrire(false);
document.getElementById("texte").onkeydown=e=>{if(e.key==="Enter")ecrire(false);};
document.getElementById("inconnu").onclick=()=>ecrire(true);
let rec=null;document.getElementById("micro").onclick=async function(){
if(rec){rec.stop();return;}
const flux=await navigator.mediaDevices.getUserMedia({audio:true});rec=new MediaRecorder(flux);const morceaux=[];
rec.ondataavailable=e=>morceaux.push(e.data);rec.onstop=async()=>{flux.getTracks().forEach(t=>t.stop());
await fetch("/vocal",{method:"POST",body:new Blob(morceaux)});rec=null;this.textContent="🎙 vocal";this.classList.remove("enreg");maj();};
rec.start();this.textContent="■ envoyer";this.classList.add("enreg");};
window.__telephone={ecrire};
</script></html>"""


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    faux = FauxTelegram(port)
    print(f"faux Telegram sur {faux.url} (téléphone : {faux.url}/)", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        faux.arreter()
