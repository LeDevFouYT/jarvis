"""Test manuel du serveur : lancer.bat d'abord, puis python -m jarvis.tests.serveur
Interroge /etat puis envoie une phrase à /parler : la réponse est parlée par le serveur, phrase par phrase."""
import time

import requests

from ..config import CONFIG

URL = f"http://{CONFIG['serveur']['hote']}:{CONFIG['serveur']['port']}"

if __name__ == "__main__":
    etat = requests.get(f"{URL}/etat", timeout=10).json()
    print("État :", {k: v for k, v in etat.items() if k not in ("machine", "rappels")})
    if etat["machine"].get("gpu"):
        g = etat["machine"]["gpu"]
        print(f"GPU : {g['vram_utilisee_mo']} / {g['vram_totale_mo']} Mo, {g['temperature']} °C")
    t = time.time()
    r = requests.post(f"{URL}/parler", json={"texte": "Jarvis, dans quel état est la machine ?"}, timeout=300).json()
    print(f"\nRéponse : {r['reponse']}")
    print(f"Outils  : {[a['outil'] for a in r['outils']]}")
    print(f"Chrono  : {r['chrono']}  (total {time.time() - t:.1f} s, première phrase parlée à {r['chrono']['premiere_phrase']} s)")
