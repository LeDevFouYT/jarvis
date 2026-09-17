"""Chargement de config.json et du fichier .secrets."""
import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def charger_config() -> dict:
    return json.loads((RACINE / "config.json").read_text(encoding="utf-8"))


def charger_secrets() -> dict:
    """Une ligne CLE=valeur par secret. Fichier absent = aucun secret."""
    fichier = RACINE / ".secrets"
    secrets = {}
    if fichier.exists():
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, valeur = ligne.split("=", 1)
                secrets[cle.strip()] = valeur.strip()
    return secrets


CONFIG = charger_config()
SECRETS = charger_secrets()
# Essais en direct : JARVIS_SECRET_<CLE>=valeur remplace un secret en mémoire seulement (jamais écrit dans .secrets).
SECRETS.update({cle[len("JARVIS_SECRET_"):]: valeur for cle, valeur in os.environ.items() if cle.startswith("JARVIS_SECRET_")})


def _resoudre_annuaire():
    """Mode cloud sans domaine : l'adresse de la passerelle (proxy RunPod) change quand le pod est recréé.
    `cerveau.cloud.annuaire` pointe sur un petit fichier JSON fixe ({"url": "https://…"}) que le client lit au
    démarrage pour connaître l'adresse du jour. Silencieux si l'annuaire ne répond pas : l'URL de config reste."""
    cloud = CONFIG.get("cerveau", {}).get("cloud", {})
    if CONFIG.get("cerveau", {}).get("mode") != "cloud" or not cloud.get("annuaire"):
        return
    try:
        import requests
        r = requests.get(cloud["annuaire"], timeout=5)
        url = r.json().get("url", "").strip()
        if url.startswith("http"):
            cloud["url"] = url
    except Exception:
        pass


_resoudre_annuaire()
