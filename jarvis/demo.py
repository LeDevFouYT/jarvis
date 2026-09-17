"""La préparation d'une démo réelle : python -m jarvis demo
Jarvis ne se lance pas : chaque brique est vérifiée pour de vrai (aucun faux serveur, aucune image d'essai) et ce qui
manque est dit avec la façon de le régler. Le déroulé à filmer est dans DEMO.md.

Contrôles : Ollama et les trois modèles, Whisper et Kokoro sur le disque, le micro, ComfyUI (lancé, ou lançable),
une webcam qui diffuse vraiment, le bot Telegram (jeton accepté par Telegram, identifiant de discussion), YouTube
(clé testée si elle est saisie, sinon lecture publique d'une vraie chaîne), la chaîne réglée pour le briefing,
l'espace disque et la mémoire vive libre."""
import shutil
import sys

import requests

from .config import CONFIG, RACINE, SECRETS


def _ligne(ok: bool | None, titre: str, detail: str = "") -> bool | None:
    marque = {True: "✓", False: "✗", None: "·"}[ok]
    print(f"  {marque} {titre}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def verifier() -> int:
    print("\n=== Préparation de la démo réelle de Jarvis ===\n", flush=True)
    bloquants = []

    def controle(nom, fonction):
        try:
            ok, detail = fonction()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__} : {e}"
        _ligne(ok, nom, detail)
        if ok is False:
            bloquants.append(nom)

    def ollama():
        tags = [m["name"] for m in requests.get(f"{CONFIG['ollama']['url']}/api/tags", timeout=5).json().get("models", [])]
        voulus = [CONFIG["cerveau"]["modele"], CONFIG["vision"]["modele"], CONFIG.get("memoire", {}).get("modele_plongements", "qwen3-embedding:0.6b")]
        manquants = [m for m in voulus if not any(t == m or t.split(":")[0] == m.split(":")[0] and m.endswith(":latest") for t in tags)]
        return (not manquants, "modèles présents : " + ", ".join(voulus) if not manquants else "à télécharger : ollama pull " + " ; ollama pull ".join(manquants))

    def modeles_locaux():
        whisper = any((RACINE / "modeles" / "whisper").glob("**/model.bin"))
        kokoro = any((RACINE / "modeles").glob("**/*kokoro*.onnx"))
        return (whisper and kokoro, f"Whisper {'présent' if whisper else 'absent'}, Kokoro {'présent' if kokoro else 'absent'} (lancer.bat les télécharge)")

    def micro():
        import sounddevice as sd
        entrees = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
        choisi = CONFIG["oreilles"].get("peripherique")
        return (bool(entrees), f"{len(entrees)} entrée(s) ; réglé : {choisi if choisi is not None else 'micro par défaut'}. Casque conseillé pour l'interruption")

    def comfyui():
        from .outils import generer_image as G
        if G.comfyui_present():
            stats = requests.get(f"{G.URL}/system_stats", timeout=5).json()
            return True, f"lancé ({stats['system'].get('comfyui_version', '?')})"
        lanceur = G.REGLAGES.get("lanceur", "")
        from pathlib import Path
        return (bool(lanceur and Path(lanceur).exists()), "pas lancé : Jarvis le lancera (compter 1 minute)" if lanceur else "pas lancé et aucun lanceur réglé")

    def webcam():
        from .outils import webcam as W
        noms = W.peripheriques()
        if not noms:
            return False, "aucune webcam : branchez-en une (ou démarrez la caméra virtuelle d'OBS)"
        jpeg, libelle = W.capturer()
        return True, f"{libelle} diffuse ({len(jpeg) // 1024} Ko par image)"

    def telegram():
        from . import telegram_entrant as T
        if not SECRETS.get("TELEGRAM_TOKEN"):
            return False, "aucun bot : Réglages › Telegram, suivez les 4 étapes (BotFather, jeton, « bonjour », identifiant)"
        j = T.verifier_jeton(SECRETS["TELEGRAM_TOKEN"])
        if not j["ok"]:
            return False, j["message"]
        if not SECRETS.get("TELEGRAM_CHAT_ID"):
            return False, f"bot @{j['bot']} valide, mais l'identifiant de discussion manque : « trouver mon identifiant »"
        return True, f"bot @{j['bot']}, discussion {SECRETS['TELEGRAM_CHAT_ID'][-4:].rjust(8, '•')} ; réponse vocale {'oui' if CONFIG.get('telegram', {}).get('reponse_vocale', True) else 'non'}"

    def youtube():
        from .youtube import acces, donnees
        if acces.cle():
            t = acces.tester()
            return t["ok"], t["message"]
        ch = donnees.chaine(CONFIG.get("youtube", {}).get("ma_chaine") or "@YouTube")
        return None, f"pas de clé API : lecture publique (plus lente, sans quota), testée sur « {ch['titre']} »"

    def ma_chaine():
        yt = CONFIG.get("youtube", {})
        if not yt.get("ma_chaine"):
            return False, "Réglages › YouTube › Ma chaîne : indispensable pour le briefing"
        return True, f"{yt['ma_chaine']} ; concurrents : {', '.join(yt.get('concurrents', [])) or 'aucun'}"

    def ressources():
        import psutil
        libre_go = shutil.disk_usage(str(RACINE)).free / 1024 ** 3
        ram_go = psutil.virtual_memory().available / 1024 ** 3
        ok = libre_go > 5 and ram_go > 4
        return ok, (f"disque {libre_go:.0f} Go libres, mémoire vive {ram_go:.1f} Go libres"
                    + ("" if ram_go > 4 else " : fermez les applications gourmandes (navigateurs, jeux), ComfyUI ralentit sans mémoire vive"))

    for nom, fonction in (("Ollama et modèles", ollama), ("Whisper et Kokoro", modeles_locaux), ("Micro", micro),
                          ("ComfyUI (miniatures, images)", comfyui), ("Webcam", webcam), ("Telegram", telegram),
                          ("YouTube", youtube), ("Ma chaîne et concurrents", ma_chaine), ("Machine", ressources)):
        controle(nom, fonction)

    print()
    if bloquants:
        print(f"À régler avant de filmer : {', '.join(bloquants)}. Le reste de la démo marche sans.", flush=True)
    else:
        print("Tout est prêt. Lancez Jarvis (lancer.bat) et suivez DEMO.md.", flush=True)
    return 1 if bloquants else 0


if __name__ == "__main__":
    sys.exit(verifier())
