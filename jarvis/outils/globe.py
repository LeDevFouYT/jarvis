"""Outil globe (v3, consigne 7) : la Terre en hologramme, la Station spatiale en direct, les séismes du jour.

Deux sources publiques, appelées seulement quand on le demande, et **comptées** dans les sorties Internet du HUD :
  - la Station spatiale : api.wheretheiss.at (position et altitude d'un satellite public, ici l'ISS) ;
  - les séismes : earthquake.usgs.gov, le flux « magnitude 2,5 et plus, dernières 24 h ».

Aucune position de l'utilisateur n'est envoyée ni demandée : ces deux appels ne portent que l'identifiant du
satellite ou rien du tout. Le HUD ne lit jamais navigator.geolocation (vérifié par le test).
"""
import logging
import time

import requests

from .. import compteur

NOM = "globe"
DESCRIPTION = ("Affiche la Terre en hologramme dans l'interface. « terre » : le globe seul. « station » : la position "
               "en direct de la Station spatiale internationale et sa trajectoire. « seismes » : les séismes des "
               "dernières 24 heures. Demande Internet pour la station et les séismes (compté dans les sorties).")
PARAMETRES = {"quoi": {"type": "string", "enum": ["terre", "station", "seismes"],
                       "description": "Ce qu'il faut montrer sur le globe"}}
REQUIS = ["quoi"]

ISS = 25544                       # numéro public du satellite de la Station spatiale internationale
URL_ISS = f"https://api.wheretheiss.at/v1/satellites/{ISS}/positions"
URL_SEISMES = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
DELAI = 15
sur_evenement = lambda e: None
journal = logging.getLogger("globe")


def _emettre(quoi, donnees=None, **champs):
    sur_evenement({"type": "globe", "t": time.time(), "quoi": quoi, "donnees": donnees or [], **champs})


def station() -> dict:
    """La position de la Station spatiale, et sa trajectoire d'une demi-heure avant à une heure après.
    Un seul appel : l'API rend jusqu'à dix positions d'un coup."""
    maintenant = int(time.time())
    instants = [maintenant + d * 60 for d in (-30, -20, -10, -5, 0, 10, 20, 30, 45, 60)]
    compteur.compter("station_spatiale")
    r = requests.get(URL_ISS, params={"timestamps": ",".join(str(t) for t in instants), "units": "kilometers"},
                     timeout=DELAI, headers={"User-Agent": "Jarvis (assistant local)"})
    r.raise_for_status()
    points = [{"lat": round(p["latitude"], 3), "lon": round(p["longitude"], 3),
               "altitude_km": round(p["altitude"], 1), "vitesse_kmh": round(p["velocity"], 0), "t": p["timestamp"]}
              for p in r.json()]
    passees = [p for p in points if p["t"] <= maintenant] or points[:1]
    actuelle = passees[-1]
    return {"positions": passees, "avenir": [p for p in points if p["t"] > maintenant], "actuelle": actuelle}


def seismes(minimum: float = 2.5) -> list[dict]:
    """Les séismes des dernières 24 heures (flux public de l'USGS), du plus fort au plus faible."""
    compteur.compter("seismes_usgs")
    r = requests.get(URL_SEISMES, timeout=DELAI, headers={"User-Agent": "Jarvis (assistant local)"})
    r.raise_for_status()
    liste = []
    for f in r.json().get("features", []):
        p = f.get("properties", {})
        c = (f.get("geometry") or {}).get("coordinates") or []
        if len(c) < 2 or p.get("mag") is None or p["mag"] < minimum:
            continue
        liste.append({"magnitude": round(p["mag"], 1), "lieu": p.get("place", ""), "lon": round(c[0], 2),
                      "lat": round(c[1], 2), "profondeur_km": round(c[2], 1) if len(c) > 2 else None,
                      "quand": int(p.get("time", 0) / 1000)})
    liste.sort(key=lambda s: s["magnitude"], reverse=True)
    return liste


def _heure(secondes: int) -> str:
    return time.strftime("%H h %M", time.localtime(secondes))


def executer(quoi: str = "terre") -> str:
    quoi = (quoi or "terre").strip().lower()
    if quoi.startswith("ter") or quoi in ("globe", "monde"):
        _emettre("terre")
        return "Voici la Terre, monsieur."
    try:
        if quoi.startswith("sta") or "spatiale" in quoi or "iss" in quoi:
            d = station()
            a = d["actuelle"]
            _emettre("station", d["positions"], avenir=d["avenir"], actuelle=a)
            cote = "nord" if a["lat"] >= 0 else "sud"
            sens = "est" if a["lon"] >= 0 else "ouest"
            lat = f"{abs(a['lat']):.1f}".replace(".", ",")
            lon = f"{abs(a['lon']):.1f}".replace(".", ",")
            return (f"La Station spatiale est à {lat} degrés {cote} et {lon} degrés {sens}, "
                    f"à {a['altitude_km']:.0f} kilomètres d'altitude, à {a['vitesse_kmh']:.0f} kilomètres-heure. "
                    "Sa trajectoire de la prochaine heure est tracée sur le globe.")
        if quoi.startswith("sei") or "trembl" in quoi:
            liste = seismes()
            _emettre("seismes", liste[:40], total=len(liste))
            if not liste:
                return "Aucun séisme de magnitude 2,5 ou plus dans les dernières vingt-quatre heures."
            fort = liste[0]
            magnitude = f"{fort['magnitude']:.1f}".replace(".", ",")      # dit « six virgule quatre », pas « six point quatre »
            return (f"{len(liste)} séismes de magnitude 2,5 ou plus depuis hier. Le plus fort : magnitude "
                    f"{magnitude} à {_heure(fort['quand'])}, {fort['lieu']}.")
    except requests.RequestException as e:
        journal.warning("globe %s : %s", quoi, e)
        return f"Je n'ai pas pu joindre la source publique ({type(e).__name__}). Le globe reste affiché."
    _emettre("terre")
    return "Voici la Terre, monsieur."
