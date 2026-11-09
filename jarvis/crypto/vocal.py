"""Les phrases crypto reconnues sans le cerveau (commandes.analyser les essaie avant lui) : rapides, et surtout
déterministes pour les chiffres et les garde-fous. Rend (commande, argument) ou None.

  « combien vaut le Bitcoin ? », « montre-moi l'Ethereum sur 7 jours »     -> crypto {action: cours}
  « qu'est-ce qui monte le plus ? »                                        -> crypto {action: classement}
  « fais-moi le point crypto »                                             -> crypto {action: point}
  « achète pour 500 € de Bitcoin », « vends la moitié de mon Ethereum »    -> crypto_ordre
  « combien je vaux ? », « remets le portefeuille à zéro »                  -> portefeuille
  « rejoue tes 10 derniers jours », « pourquoi tu as vendu le 12 ? »        -> crypto_replay
  « préviens-moi si le Bitcoin passe sous 70 000 € », « quelles sont mes alertes ? » -> crypto_alerte
  « je devrais acheter du Bitcoin ? »                                       -> crypto_conseil (le garde-fou)
  « regarde ce graphique »                                                  -> crypto_vision

Le texte arrive normalisé par commandes._normaliser : minuscules, sans accents."""
import re

from .cours import reconnaitre

dernier_symbole = "BTC"          # « s'il prend 5 % » : la dernière crypto dont on a parlé

_DEBUT = r"^(?:(?:hey|ok|dis|bon|allez)\s+)?(?:jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu|pourrais[- ]tu|vous pouvez)\s+)?"
_NOMBRE = r"(\d{1,3}(?:[  ]\d{3})+|\d+(?:[.,]\d+)?)"

_CONSEIL = re.compile(
    r"(je devrais|est[- ]ce que je devrais|devrais[- ]je|dois[- ]je|je dois|est[- ]ce que je dois|faut[- ]il|il faut|"
    r"tu me conseilles?|tu conseilles?|vous me conseillez|tu me recommandes?|c'?est le (?:bon )?moment|"
    r"tu penses? que je|tu crois que je|vaut[- ]il mieux|ca vaut le coup|j'?ai interet a|je fais bien)"
    r".{0,40}\b(acheter|vendre|investir|miser|placer|garder|prendre|revendre)\b")
_CONSEIL_2 = re.compile(r"\b(quelle crypto|quoi) (?:je dois |dois[- ]je |faut[- ]il |acheter|j'?achete)"
                        # une prédiction ou « je mets tout dessus » : vu au test du 16/10, le cerveau répondait par le classement
                        r"|\b(?:va|vont|devrait|devraient) (?:monter|baisser|remonter|chuter|exploser|grimper|s'?effondrer)\b"
                        r"|\bje (?:mets|place|investis|mise) (?:tout|toutes mes|mes economies|mon argent|mon epargne)")

_ACHAT = re.compile(r"\b(?:achete|achetes|achetez|acheter|prends|investis|mets|place)\s+(?:moi\s+)?(?:pour\s+)?"
                    + _NOMBRE + r"\s?(k|mille)?\s?(?:euros?|€|eur)(?![a-z])\s*(?:de|d'|du|en|dans)?")
_VENTE = re.compile(r"\b(?:vends|vendez|vendre|revends|liquide|solde)\s+(?:moi\s+)?"
                    r"(?:(?P<part>la moitie|un quart|le quart|un tiers|le tiers|tout|tous|toute|la totalite)"
                    r"|(?P<pct>" + _NOMBRE[1:-1] + r")\s?(?:%|pour ?cent)"
                    r"|pour\s+(?P<eur>" + _NOMBRE[1:-1] + r")\s?(?:euros?|€|eur))")
_FRACTIONS = {"la moitie": 0.5, "un quart": 0.25, "le quart": 0.25, "un tiers": 1 / 3, "le tiers": 1 / 3,
              "tout": 1.0, "tous": 1.0, "toute": 1.0, "la totalite": 1.0}

_VALEUR = re.compile(r"(combien (?:je vaux|est[- ]ce que je vaux|vaut mon portefeuille|j'?ai gagne|j'?ai perdu|ai[- ]je)|"
                     r"(?:etat|valeur|point sur|montre[- ]moi|affiche) (?:de |du |sur )?(?:mon |le )?portefeuille|"
                     r"^(?:mon|le) portefeuille\b|qu'?est[- ]ce que j'?ai dans (?:mon|le) portefeuille|"
                     r"ou en est (?:mon|le) portefeuille)")
_ZERO = re.compile(r"(remets?|remettre|reinitialise|repars?|redemarre|vide)\s.{0,30}portefeuille.{0,25}"
                   r"(zero|depart|10 ?000|dix mille|neuf|initial)|(reinitialise|remise a zero d[eu]) (?:mon |le )?portefeuille")
_JOURNAL = re.compile(r"(mes ordres|journal des ordres|historique des ordres|qu'?est[- ]ce que j'?ai achete)")

_REPLAY = re.compile(r"(rejoue|rejouer|refais|refaire|relance|lance|montre[- ]moi|repasse)\s.{0,20}"
                     r"(10|dix) (?:derniers )?jours|(lance|relance|montre[- ]moi) (?:le |ton )?replay|rejoue ta simulation")
_POURQUOI = re.compile(r"pourquoi (?:tu as|as[- ]tu|t'?as|vous avez|avez[- ]vous)\s+(?P<verbe>vendu|achete|garde|rien fait|attendu)"
                       r"(?:.{0,30}?\b(?:le|du)\s+(?P<jour>\d{1,2})\b)?")

_ALERTE_SEUIL = re.compile(
    r"(?:previens|previens[- ]moi|avertis|alerte|dis|signale|appelle)[- ]?(?:moi)?\s+(?:si\s+|s'|quand\s+|des que\s+|lorsque\s+)"
    r"(?P<sujet>.{0,40}?)\s*(?P<sens>passe sous|passe en dessous de|descend sous|descend en dessous de|tombe sous|tombe a|"
    r"passe au[- ]dessus de|passe au[- ]dela de|depasse|monte au[- ]dessus de|franchit|atteint|passe|descend a|remonte a)\s+(?:les\s+)?"
    + _NOMBRE + r"\s?(k|mille)?\s?(?:euros?|€|eur)?")
_ALERTE_VARIATION = re.compile(
    r"(?:previens|previens[- ]moi|avertis|alerte|dis|signale)[- ]?(?:moi)?\s+(?:si\s+|s'|quand\s+|des que\s+|lorsque\s+)"
    r"(?P<sujet>.{0,40}?)\s*(?P<sens>prend|gagne|monte de|grimpe de|bondit de|perd|baisse de|chute de|recule de|descend de|bouge de|varie de)\s+"
    r"(?:plus de\s+)?" + _NOMBRE + r"\s?(?:%|pour ?cent)\s*(?P<duree>dans l'?heure|en une heure|en 1 ?h(?:eure)?|sur une heure|"
    r"dans la journee|en 24 ?h(?:eures)?|sur 24 ?h(?:eures)?|aujourd'?hui|en une journee|dans les 24 ?h(?:eures)?)?")
_ALERTES_LISTE = re.compile(r"(quelles sont mes alertes|mes alertes|liste (?:des |mes )?alertes|quelles alertes|"
                            r"j'?ai (?:des|quelles) alertes)")
_ALERTE_SUPPR = re.compile(r"(supprime|efface|retire|annule|enleve|oublie)[sz]?\s+(?P<toutes>toutes\s+)?(?:les |mes |l'|la |une )?alertes?"
                           r"(?P<reste>.{0,30})")

_POINT = re.compile(r"(point|briefing|resume|bilan|tour)\s(?:sur les |des |du |de la |crypto)?\s?(crypto|cryptos|marche crypto|cryptomonnaies?)")
_CLASSEMENT = re.compile(r"(qu'?est[- ]ce qui|quelle crypto|quelles cryptos|ce qui|qui)\s.{0,20}(monte|baisse|grimpe|chute|recule|progresse) le plus|"
                         r"(plus fortes?|meilleures?|pires?) (hausses?|baisses?|cryptos?)|top (des )?cryptos?")
_COURS = re.compile(r"\b(combien (?:vaut|coute|fait|valent|vaut actuellement)|quel est le (?:prix|cours)|le (?:prix|cours) d|"
                    r"comment va|comment se porte|ou en est|montre[- ]moi|montre|affiche|donne[- ]moi|cours d|prix d|"
                    r"et (?:le|l'|la)|^et)\b")
# plusieurs graphiques : « montre-moi le Bitcoin et l'Ethereum », « compare… », « montre-moi les cryptos »
_PLUSIEURS = re.compile(r"\b(?:montre|affiche|compare|comparer|mets|donne)[- ]?(?:moi|nous)?\b"
                        r"(?:.*\b(?P<toutes>les cryptos|toutes les cryptos|les grandes cryptos|plusieurs graphiques|les graphiques|"
                        r"plusieurs cryptos|les principales cryptos|le marche crypto)\b"
                        r"|.*\b(?P<marches>les indices|les marches|les bourses|les grands indices|les marches mondiaux)\b)?")
_POINT_BOURSE = re.compile(r"(point|briefing|resume|bilan|etat|tour)\s(?:des|sur les|de la|du)\s(marches|bourse|marche boursier)|"
                           r"comment (?:vont|va|se portent|se porte) (?:les marches|la bourse|wall street)|la bourse aujourd'?hui|"
                           r"(?:quoi de neuf|des nouvelles) (?:en|de la) bourse")
_CHANGE = re.compile(r"(?:combien vaut|cours d[ue]|taux d[ue]|prix d[ue]|a combien est|combien fait|change d[ue])\s+(?:le |la |l'|un |une )?"
                     r"(?P<devise>dollars?|livres? sterling|livre|yens?|franc suisse|yuan)\b")
_VISION = re.compile(r"(regarde|lis|analyse|decris|observe|jette un (?:oeil|coup d'?oeil) (?:a|sur))\s+(?:ce|le|mon|cet|l'?)\s?"
                     r"(graphique|graph|chart|courbe|cours|tradingview|ecran de trading)")


def _montant(brut: str, multiplicateur: str | None = None) -> float:
    valeur = float(re.sub(r"[  ]", "", brut).replace(",", "."))
    return valeur * 1000 if multiplicateur in ("k", "mille") else valeur


def _sujet(texte: str) -> str | None:
    """La crypto ou l'actif de bourse nommé, ou le dernier dont on a parlé si la phrase dit « il », « s'il »."""
    from .actifs import reconnaitre as reconnaitre_actif
    s = reconnaitre_actif(texte)
    if s:
        return s
    if re.search(r"\b(s'?il|si il|il|elle|ca|le cours)\b", texte):
        return dernier_symbole
    return None


def analyser(n: str) -> tuple[str, object] | None:
    global dernier_symbole
    from ..config import CONFIG
    if not CONFIG.get("crypto", {}).get("actif", True):          # le pouvoir s'éteint dans config.json (crypto.actif)
        return None
    n = re.sub(_DEBUT, "", n.strip()).strip()
    if len(n) > 120:
        return None
    from . import actifs, bourse as B
    symbole = reconnaitre(n)
    actif = actifs.reconnaitre(n)                  # une crypto ou un actif de bourse (CAC 40, Apple, l'or…)
    en_bourse = bool(actif) and actifs.est_bourse(actif)
    parle_crypto = bool(symbole) or bool(re.search(r"\bcryptos?\b|cryptomonnaie|crypto[- ]monnaie|\bjetons?\b|\bcoins?\b", n))
    parle_bourse = en_bourse or bool(re.search(r"\bbourse\b|\bactions?\b|\bmarches?\b|\bindices?\b|wall street", n))
    if actif:
        dernier_symbole = actif

    # 1. le garde-fou passe avant tout : une demande de conseil n'est jamais un ordre
    if (parle_crypto or parle_bourse) and (_CONSEIL.search(n) or _CONSEIL_2.search(n)):
        return "crypto_conseil", actif or "BTC"

    # 2. le portefeuille fictif
    if _ZERO.search(n):
        return "portefeuille", {"action": "zero"}
    m = _ACHAT.search(n)
    if m and actif:
        return "crypto_ordre", {"sens": "achat", "crypto": actif, "montant_eur": _montant(m.group(1), m.group(2))}
    m = _VENTE.search(n)
    if m and actif:
        if m.group("part"):
            return "crypto_ordre", {"sens": "vente", "crypto": actif, "fraction": _FRACTIONS[m.group("part")]}
        if m.group("pct"):
            return "crypto_ordre", {"sens": "vente", "crypto": actif, "fraction": min(1.0, _montant(m.group("pct")) / 100)}
        return "crypto_ordre", {"sens": "vente", "crypto": actif, "montant_eur": _montant(m.group("eur"))}
    if _VALEUR.search(n):
        return "portefeuille", {"action": "valeur"}
    if _JOURNAL.search(n) and ("portefeuille" in n or "ordre" in n or parle_crypto):
        return "portefeuille", {"action": "journal"}

    # 3. le replay des 10 jours
    if _REPLAY.search(n):
        return "crypto_replay", {"action": "lancer"}
    m = _POURQUOI.search(n)
    if m:
        return "crypto_replay", {"action": "pourquoi", "verbe": m.group("verbe"),
                                 "jour": int(m.group("jour")) if m.group("jour") else None}

    # 4. les alertes
    if _ALERTES_LISTE.search(n) and not _ALERTE_SUPPR.search(n):
        return "crypto_alerte", {"action": "lister"}
    m = _ALERTE_SUPPR.search(n)
    if m:
        return "crypto_alerte", {"action": "supprimer", "crypto": actifs.reconnaitre(m.group("reste") or ""),
                                 "toutes": bool(m.group("toutes")) or not actifs.reconnaitre(m.group("reste") or "")}
    m = _ALERTE_VARIATION.search(n)
    if m:
        cible = _sujet(m.group("sujet"))
        if cible:
            baisse = m.group("sens").split()[0] in ("perd", "baisse", "chute", "recule", "descend")
            bouge = m.group("sens").split()[0] in ("bouge", "varie")
            duree = m.group("duree") or "dans la journee"
            return "crypto_alerte", {"action": "creer", "crypto": cible, "type": "variation",
                                     "pourcent": _montant(m.group(3)) * (1 if bouge else -1 if baisse else 1),
                                     "dans_les_deux_sens": bouge,
                                     "fenetre_s": 3600 if ("heure" in duree or re.search(r"\b1 ?h", duree)) else 86400}
    m = _ALERTE_SEUIL.search(n)
    if m:
        cible = _sujet(m.group("sujet"))
        if cible:
            sens = m.group("sens")
            dessous = any(x in sens for x in ("sous", "dessous", "descend", "tombe"))
            return "crypto_alerte", {"action": "creer", "crypto": cible, "type": "seuil",
                                     "seuil_eur": _montant(m.group(3), m.group(4)), "direction": "sous" if dessous else "dessus"}

    # 5. la bourse : le point des marchés, les devises, ce qui monte, plusieurs graphiques, un cours
    if _POINT_BOURSE.search(n):
        return "bourse", {"action": "point"}
    m = _CHANGE.search(n)
    if m and B.devise_dite(m.group("devise")):
        return "bourse", {"action": "change", "devise": B.devise_dite(m.group("devise"))}
    if _CLASSEMENT.search(n) and parle_bourse and not parle_crypto:
        return "bourse", {"action": "classement"}
    m = _PLUSIEURS.search(n)
    if m:
        tous = actifs.reconnaitre_tous(n)
        if (len(tous) >= 2 and any(actifs.est_bourse(x) for x in tous)) or (m.group("marches") and not actif):
            return "bourse", {"action": "comparer", "actifs": tous[:6], "periode": B.periode_depuis(n)}
    if en_bourse and _COURS.search(n) and len(n) < 90:
        return "bourse", {"action": "cours", "actif": actif, "periode": B.periode_depuis(n)}

    # 6. le point crypto, le classement, le cours
    if _POINT.search(n):
        return "crypto", {"action": "point"}
    if _CLASSEMENT.search(n) and (parle_crypto or len(n) < 40):
        return "crypto", {"action": "classement"}
    if _VISION.search(n):
        return "crypto_vision", n
    m = _PLUSIEURS.search(n)
    if m:
        from .cours import periode_depuis, reconnaitre_tous
        tous = reconnaitre_tous(n)
        if len(tous) >= 2 or (m.group("toutes") and not symbole):
            return "crypto", {"action": "comparer", "cryptos": tous[:6], "periode": periode_depuis(n)}
    if symbole and _COURS.search(n) and len(n) < 90:
        from .cours import periode_depuis
        return "crypto", {"action": "cours", "crypto": symbole, "periode": periode_depuis(n)}
    return None
