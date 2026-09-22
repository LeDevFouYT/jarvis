"""Réglages modifiables depuis l'application (panneau « Réglages » du HUD), sans ouvrir de fichier :
les clés ElevenLabs, Telegram et Jarvis Cloud vont dans `.secrets`, le moteur de voix et la voix ElevenLabs dans
`config.json`. Tout est appliqué à chaud (les dicts CONFIG et SECRETS sont partagés par tous les modules).
Les valeurs des clés ne ressortent jamais : l'API dit seulement « définie » et les 4 derniers caractères."""
import json
import re

import requests

from .config import CONFIG, RACINE, SECRETS

FICHIER_SECRETS = RACINE / ".secrets"
FICHIER_CONFIG = RACINE / "config.json"

# clé -> (libellé, aide). Vide dans le formulaire = inchangé ; "-" = effacer.
CLES = {
    "ELEVENLABS_API_KEY": ("Clé API ElevenLabs", "elevenlabs.io > Profile > API keys. Voix premium en ligne, comptée dans les sorties Internet."),
    "TELEGRAM_TOKEN": ("Jeton du bot Telegram", "Créez un bot avec @BotFather, il vous donne un jeton 123456:ABC…"),
    "TELEGRAM_CHAT_ID": ("Identifiant de discussion Telegram", "Rempli par « trouver mon identifiant » après votre premier message au bot."),
    "YOUTUBE_API_KEY": ("Clé API YouTube Data v3", "Google Cloud > votre projet > Identifiants > Clé API, limitée à YouTube Data API v3. "
                        "Gratuite : 10 000 unités par jour."),
    "CLOUD_TOKEN": ("Jeton Jarvis Cloud", "Reçu après le paiement Jarvis Cloud (jc_…). Utile seulement si le cerveau est en mode cloud."),
}


def _masque(valeur: str) -> str:
    return f"•••• {valeur[-4:]}" if len(valeur) >= 8 else "••••"


# sensibilité de l'interruption -> (niveau sonore minimal, durée de voix nette avant de couper Jarvis)
SENSIBILITES = {"faible": (0.02, 0.5), "normale": (0.012, 0.35), "forte": (0.006, 0.25)}
VOIX_ANGLAISES = [("bm_george", "George, majordome britannique"), ("bm_lewis", "Lewis, britannique"),
                  ("bf_emma", "Emma, britannique"), ("am_michael", "Michael, américain"), ("af_heart", "Heart, américaine")]


def _sensibilite_actuelle() -> str:
    inter = CONFIG.get("oreilles", {}).get("interruption", {})
    niveau = float(inter.get("seuil_niveau", 0.012))
    return min(SENSIBILITES, key=lambda k: abs(SENSIBILITES[k][0] - niveau))


def _etat_majordome() -> dict:
    from . import majordome
    ok, raison = majordome.disponible()
    return {"disponible": ok, "raison": raison, "charge": majordome.MAJORDOME.actif}


def lire() -> dict:
    """L'état des réglages pour le formulaire, sans jamais la valeur d'une clé."""
    from . import personnalites
    voix = CONFIG.get("voix", {})
    oreilles = CONFIG.get("oreilles", {})
    cc = oreilles.get("conversation_continue", {})
    inter = oreilles.get("interruption", {})
    sentinelle = CONFIG.get("sentinelle", {})
    return {
        "cles": {k: {"libelle": lib, "aide": aide, "definie": bool(SECRETS.get(k)), "apercu": _masque(SECRETS[k]) if SECRETS.get(k) else ""}
                 for k, (lib, aide) in CLES.items()},
        "voix": {"moteur": voix.get("moteur", "local"), "elevenlabs_voix": voix.get("elevenlabs_voix", ""),
                 "elevenlabs_modele": voix.get("elevenlabs_modele", "eleven_multilingual_v2"),
                 "kokoro_voix_en": voix.get("kokoro_voix_en", "bm_george"),
                 "majordome": _etat_majordome(),
                 "voix_anglaises": [{"id": i, "libelle": l} for i, l in VOIX_ANGLAISES]},
        "cerveau": {"mode": CONFIG.get("cerveau", {}).get("mode", "local")},
        "telegram": {"configure": bool(SECRETS.get("TELEGRAM_TOKEN")) and bool(SECRETS.get("TELEGRAM_CHAT_ID")),
                     "commandes": CONFIG.get("telegram", {}).get("commandes", True),
                     "reponse_vocale": CONFIG.get("telegram", {}).get("reponse_vocale", True)},
        "personnalite": {"actuelle": personnalites.actuelle(), "choix": personnalites.liste()},
        "conversation": {"continue": cc.get("actif", True), "secondes": cc.get("secondes", 8),
                         "interruption": inter.get("actif", True), "sensibilite": _sensibilite_actuelle(),
                         "anglais": "en" in oreilles.get("langues", ["fr", "en"])},
        "sentinelle": {"actif": sentinelle.get("actif", True), "temperature_max": sentinelle.get("temperature_max", 85),
                       "disque_min_go": sentinelle.get("disque_min_go", 10)},
        "memoire": {"actif": CONFIG.get("memoire", {}).get("actif", True)},
        "youtube": {"ma_chaine": CONFIG.get("youtube", {}).get("ma_chaine", ""),
                    "concurrents": ", ".join(CONFIG.get("youtube", {}).get("concurrents", [])),
                    "quota_jour": CONFIG.get("youtube", {}).get("quota_jour", 10000)},
    }


def _ecrire_reglages_avances(donnees: dict) -> tuple[bool, bool]:
    """Personnalité, conversation, langues, sentinelle, Telegram, mémoire. Rend (config changée, redémarrage requis)."""
    from . import personnalites
    change = False
    p = (donnees.get("personnalite") or {}).get("actuelle")
    if p in personnalites.PERSONNALITES and p != personnalites.actuelle():
        CONFIG.setdefault("personnage", {})["personnalite"] = p
        change = True
    conv = donnees.get("conversation") or {}
    oreilles = CONFIG.setdefault("oreilles", {})
    if "continue" in conv or "secondes" in conv:
        cc = oreilles.setdefault("conversation_continue", {})
        if "continue" in conv:
            cc["actif"] = bool(conv["continue"])
        if "secondes" in conv:
            cc["secondes"] = max(2.0, min(30.0, float(conv["secondes"])))
        change = True
    if "interruption" in conv or conv.get("sensibilite") in SENSIBILITES:
        inter = oreilles.setdefault("interruption", {})
        if "interruption" in conv:
            inter["actif"] = bool(conv["interruption"])
        if conv.get("sensibilite") in SENSIBILITES:
            inter["seuil_niveau"], inter["duree_min_s"] = SENSIBILITES[conv["sensibilite"]]
        change = True
    if "anglais" in conv:
        oreilles["langues"] = ["fr", "en"] if conv["anglais"] else ["fr"]
        change = True
    v_en = (donnees.get("voix") or {}).get("kokoro_voix_en")
    if v_en in dict(VOIX_ANGLAISES):
        CONFIG["voix"]["kokoro_voix_en"] = v_en
        change = True
    sen = donnees.get("sentinelle") or {}
    if sen:
        cible = CONFIG.setdefault("sentinelle", {})
        if "actif" in sen:
            cible["actif"] = bool(sen["actif"])
        for cle, bornes in (("temperature_max", (60, 100)), ("disque_min_go", (1, 500))):
            if cle in sen:
                cible[cle] = max(bornes[0], min(bornes[1], float(sen[cle])))
        change = True
    tg = donnees.get("telegram") or {}
    for champ in ("commandes", "reponse_vocale"):
        if champ in tg:
            CONFIG.setdefault("telegram", {})[champ] = bool(tg[champ])
            change = True
    yt = donnees.get("youtube") or {}
    if yt:
        cible = CONFIG.setdefault("youtube", {})
        if "ma_chaine" in yt:
            cible["ma_chaine"] = str(yt["ma_chaine"]).strip()
        if "concurrents" in yt:
            brut = yt["concurrents"] if isinstance(yt["concurrents"], list) else str(yt["concurrents"]).replace(";", ",").split(",")
            cible["concurrents"] = [x.strip() for x in brut if str(x).strip()][:5]
        change = True
    mem = donnees.get("memoire") or {}
    if "actif" in mem:
        CONFIG.setdefault("memoire", {})["actif"] = bool(mem["actif"])
        change = True
    return change, False


def _ecrire_secrets(nouveaux: dict[str, str | None]):
    """Met à jour les lignes CLE=valeur en gardant tout le reste du fichier (commentaires, autres clés)."""
    lignes = FICHIER_SECRETS.read_text(encoding="utf-8").splitlines() if FICHIER_SECRETS.exists() else []
    vus = set()
    sortie = []
    for ligne in lignes:
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", ligne)
        if m and m.group(1) in nouveaux:
            cle = m.group(1)
            vus.add(cle)
            if nouveaux[cle]:
                sortie.append(f"{cle}={nouveaux[cle]}")
            continue        # effacée : la ligne disparaît
        sortie.append(ligne)
    for cle, valeur in nouveaux.items():
        if cle not in vus and valeur:
            sortie.append(f"{cle}={valeur}")
    FICHIER_SECRETS.write_text("\n".join(sortie).rstrip("\n") + "\n", encoding="utf-8")
    for cle, valeur in nouveaux.items():
        if valeur:
            SECRETS[cle] = valeur
        else:
            SECRETS.pop(cle, None)


def _appliquer_cloud():
    """Le jeton cloud est figé dans les en-têtes du cerveau et de la vision au chargement : on les rafraîchit."""
    try:
        from . import cerveau, vision
        jeton = SECRETS.get("CLOUD_TOKEN") or CONFIG.get("cerveau", {}).get("cloud", {}).get("jeton", "")
        for module, actif in ((cerveau, cerveau.MODE == "cloud"), (vision, bool(vision._CLOUD))):
            module.ENTETES.clear()
            if actif and jeton:
                module.ENTETES["Authorization"] = f"Bearer {jeton}"
    except Exception:
        pass


def ecrire(donnees: dict) -> dict:
    """`donnees` : {"cles": {CLE: "valeur" | "-" | ""}, "voix": {"moteur": …, "elevenlabs_voix": …}, "cerveau": {"mode": …}}.
    Retourne l'état après écriture et `redemarrer` si un réglage ne prend effet qu'au prochain lancement."""
    redemarrer = False
    cles = {}
    for cle, valeur in (donnees.get("cles") or {}).items():
        if cle not in CLES:
            continue
        valeur = str(valeur or "").strip()
        if not valeur:
            continue                          # champ laissé vide : inchangé
        cles[cle] = None if valeur == "-" else valeur
    if cles:
        _ecrire_secrets(cles)
        if "CLOUD_TOKEN" in cles:
            _appliquer_cloud()
    config_change = False
    voix = donnees.get("voix") or {}
    if voix.get("moteur") in ("local", "elevenlabs", "majordome"):
        if voix["moteur"] != CONFIG["voix"].get("moteur"):
            from . import majordome
            majordome.suivre_moteur(voix["moteur"])       # charge Qwen3-TTS en fond, ou rend la carte graphique
        CONFIG["voix"]["moteur"] = voix["moteur"]
        config_change = True
    for champ in ("elevenlabs_voix", "elevenlabs_modele"):
        if champ in voix and isinstance(voix[champ], str):
            CONFIG["voix"][champ] = voix[champ].strip()
            config_change = True
    mode = (donnees.get("cerveau") or {}).get("mode")
    if mode in ("local", "cloud") and mode != CONFIG["cerveau"].get("mode", "local"):
        CONFIG["cerveau"]["mode"] = mode
        config_change = redemarrer = True
    avance, _ = _ecrire_reglages_avances(donnees)
    config_change = config_change or avance
    if config_change:
        FICHIER_CONFIG.write_text(json.dumps(CONFIG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    etat = lire()
    etat["redemarrer"] = redemarrer
    return etat


def voix_elevenlabs() -> list[dict]:
    """Les voix du compte ElevenLabs (nom, identifiant, langue/description), pour la liste déroulante."""
    cle = SECRETS.get("ELEVENLABS_API_KEY")
    if not cle:
        return []
    r = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": cle}, timeout=15)
    r.raise_for_status()
    voix = []
    for v in r.json().get("voices", []):
        labels = v.get("labels") or {}
        voix.append({"id": v["voice_id"], "nom": v.get("name", v["voice_id"]),
                     "detail": ", ".join(x for x in (labels.get("language"), labels.get("gender"), labels.get("accent")) if x)})
    return voix


def tester(quoi: str) -> dict:
    """Vérifie une clé auprès du service. Telegram envoie un vrai message de test au client (c'est son bot)."""
    try:
        if quoi == "elevenlabs":
            cle = SECRETS.get("ELEVENLABS_API_KEY")
            if not cle:
                return {"ok": False, "message": "Aucune clé ElevenLabs enregistrée."}
            r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": cle}, timeout=15)
            if r.status_code == 401:
                return {"ok": False, "message": "ElevenLabs refuse cette clé (401)."}
            r.raise_for_status()
            j = r.json()
            reste = j.get("character_limit", 0) - j.get("character_count", 0)
            return {"ok": True, "message": f"ElevenLabs répond : formule {j.get('tier', '?')}, {format(reste, ',').replace(',', ' ')} caractères restants ce mois."}
        if quoi == "telegram":
            from .outils import telegram
            if not telegram.configure():
                return {"ok": False, "message": "Il manque le jeton du bot ou l'identifiant de discussion."}
            r = requests.get(f"https://api.telegram.org/bot{SECRETS['TELEGRAM_TOKEN']}/getMe", timeout=15)
            if r.status_code == 401:
                return {"ok": False, "message": "Telegram refuse ce jeton (401)."}
            r.raise_for_status()
            nom = r.json().get("result", {}).get("username", "?")
            reponse = telegram.envoyer("Jarvis est connecté à ce bot. Tout fonctionne.")
            if "envoyé" in reponse.lower():
                return {"ok": True, "message": f"Message de test envoyé par @{nom}."}
            return {"ok": False, "message": reponse}
        if quoi == "youtube":
            from .youtube import acces
            return acces.tester()
        if quoi == "cloud":
            from . import cerveau
            solde = cerveau.CERVEAU.solde_cloud()
            if solde is None:
                return {"ok": False, "message": "Le cerveau est en mode local : Jarvis Cloud n'est pas utilisé."}
            if "erreur" in solde:
                return {"ok": False, "message": f"Jarvis Cloud ne répond pas ({solde['erreur']}) : jeton absent ou refusé, ou passerelle éteinte."}
            minutes = solde.get("minutes_restantes", solde.get("minutes"))
            return {"ok": True, "message": f"Jarvis Cloud répond : {minutes} minutes restantes." if minutes is not None else "Jarvis Cloud répond."}
        return {"ok": False, "message": f"Test inconnu : {quoi}"}
    except requests.RequestException as e:
        return {"ok": False, "message": f"Le service ne répond pas ({type(e).__name__})."}
