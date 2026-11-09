"""Commandes vocales spéciales, traitées avant le cerveau (rapides, sans modèle).
  « Jarvis, éteins-toi »                   -> extinction : phrase d'au revoir puis arrêt propre
  « Jarvis, oublie tout »                  -> oublier : vide la conversation (les souvenirs de la session sont d'abord proposés)
  « Jarvis, silence »                      -> silence : la voix se tait jusqu'au prochain mot de réveil
  « appelle-moi madame / monsieur »        -> titre
  « qu'est-ce que tu sais de moi »         -> souvenirs_liste : les souvenirs, et la constellation dans le HUD
  « retiens que je préfère le thé »        -> retenir (argument : « je préfère le thé »)
  « oublie que j'aime le café »            -> oublier_souvenir (argument : « j'aime le café »)
  « passe en mode coach »                  -> personnalite (argument : coach, sarcastique ou majordome)
  « désactive la sentinelle » / « active » -> sentinelle (argument : off / on)
  « annule »                               -> annuler : défait le dernier rangement
  « passe en armure Mark III »             -> armure (argument : jarvis, mark3, friday ou ultron)
  « combien vaut le Bitcoin ? », « achète pour 500 € de Solana »… -> crypto_* et portefeuille (jarvis/crypto/vocal.py)
  « oui » / « non », si une confirmation est en attente (fermer une fenêtre avec du travail) -> confirmer / refuser
  « appelle-toi Nova », « redeviens Jarvis »  -> prenom (argument : le prénom, tel qu'il a été dit)
  « change ta voix : une voix grave et posée » -> creer_voix ({description, nom}) ; « prends la voix Orage » ->
  choisir_voix ; « reprends ta voix normale » -> voix_normale ; « quelles voix as-tu ? » -> liste_voix
  « range ce que je viens de te donner », « résume-le », « cherche les factures dedans » -> depot_ranger,
  depot_resumer, depot_chercher (le dernier dossier glissé sur le HUD, jarvis/depot.py)
Sous un autre prénom, « Nova, éteins-toi » marche comme « Jarvis, éteins-toi » : le prénom est retiré d'abord."""
import re
import unicodedata

from . import prenom

# Une commande qui agit (éteindre, tout oublier, changer le titre, se taire, annuler) doit être TOUTE la phrase :
# « Jarvis, éteins-toi s'il te plaît », pas « parle-moi de l'extinction des dinosaures ». Vu le 19/09 : ces mots
# étaient cherchés n'importe où dans la phrase, et une question banale éteignait Jarvis (aussi depuis Telegram).
_DEBUT = r"^(?:(?:hey |ok |bon |allez )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu|vous pouvez|pouvez[- ]vous|tu veux bien)\s+)?"
_FIN = r"(?:[\s,]*(?:maintenant|s'?il te plait|s'?il vous plait|stp|svp|merci|jarvis|pour ce soir|pour aujourd'?hui))*[\s.!?]*$"


def _entiere(*formes: str) -> str:
    return _DEBUT + "(?:" + "|".join(formes) + ")" + _FIN


COMMANDES = {
    "extinction": [_entiere(r"eteins[- ]toi", r"eteignez[- ]vous", r"t'?eteindre", r"vous eteindre", r"va dormir",
                            r"allez dormir", r"arrete[- ]toi", r"arretez[- ]vous", r"ferme[- ]toi", r"extinction")],
    "oublier": [_entiere(r"(?:oublie|oubliez|efface|effacez) (?:tout|la conversation|notre conversation|ce qu'?on (?:a|s'est) dit)")],
    "silence": [_entiere(r"silence", r"chut", r"tais[- ]toi", r"taisez[- ]vous")],
    "titre_madame": [_entiere(r"(?:appelle|appelez|dis)[- ]moi madame", r"je suis une femme")],
    "titre_monsieur": [_entiere(r"(?:appelle|appelez|dis)[- ]moi monsieur", r"je suis un homme")],
    "souvenirs_liste": [r"\bqu'?est[- ]ce que tu sais (de|sur) moi\b", r"\bque sais[- ]tu (de|sur) moi\b",
                        r"\bqu'?est[- ]ce que vous savez (de|sur) moi\b", r"\bce que tu sais de moi\b",
                        r"\btes souvenirs sur moi\b", r"\bwhat do you know about me\b",
                        # « montre-moi ta mémoire », « tu peux me montrer tes souvenirs ? », « ouvre ta mémoire » (17/09)
                        r"\b(montre|montrer|montrez|affiche|afficher|ouvre|ouvrir|voir)[- ](moi |me )?(tes|ta|vos|votre) (souvenirs|memoire)\b",
                        r"\bme (montrer|montres?|afficher) (tes|ta|vos|votre) (souvenirs|memoire)\b",
                        r"\bce que tu as retenu( (de|sur) moi)?\s*[?.!]*$", r"\bqu'?est[- ]ce que tu as retenu\b",
                        r"\bde quoi tu te souviens\b", r"\btu te souviens de quoi\b"],
    "annuler": [_entiere(r"annule(?: le rangement| ca| ce rangement| le dernier rangement)?",
                         r"remets? (?:tout )?(?:comme avant|en place)", r"defais le rangement")],
}

_RETENIR = re.compile(r"^(?:jarvis[,.]?\s*)?(?:retiens|retenez|souviens[- ]toi|souvenez[- ]vous|rappelle[- ]toi|"
                      r"n'?oublie pas|memorise|garde en memoire|note dans ta memoire)\s+(?:bien\s+)?"
                      r"(?:que\s+|qu'|le fait que\s+)(.+)$")
_OUBLIER_SOUVENIR = re.compile(r"^(?:jarvis[,.]?\s*)?(?:oublie|oubliez|efface de ta memoire)\s+"
                               r"(?:que\s+|qu'|le fait que\s+|ce que je t'?ai dit sur\s+|l'?histoire de\s+)(.+)$")
_PERSONNALITE = re.compile(r"\b(?:passe|passes|mets[- ]toi|bascule)\s+en\s+mode\s+"
                           r"(majordome|sarcastique|sarcasme|coach|parano(?:iaque)?|nul|maladroit)\b"
                           r"|^(?:jarvis[,.]?\s*)?mode\s+(majordome|sarcastique|coach|parano|nul)[.! ]*$"
                           r"|\bsois\s+(?:mon\s+)?(coach|sarcastique|majordome|parano)\b")
# « passe en armure Mark III », « mets l'armure Friday », « armure Ultron », « retire l'armure » (v3, consigne 1)
# « passe en armure Mark III », mais aussi « passe en mode Friday » et « reviens à l'armure Jarvis » : on les dit
# comme ça sans y penser, et ça ne marchait pas (démo du 20/09).
_ARMURE = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu)\s+)?"
                     r"(?:(?:passe|passes|passer|mets|mettre|bascule|basculer|active|activer|enfile|enfiler|charge|charger"
                     r"|equipe[- ]toi|equipe|reviens|revenir|retourne|remets|remettre)\s+(?:a\s+|en\s+|toi\s+en\s+|dans\s+)?"
                     r"(?:l'|la\s+|le\s+|ton\s+|une\s+|l\s+)?(?:armure|mode)|armure)\s+(.+?)[\s.!?]*$")
_SANS_ARMURE = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:retire|enleve|quitte)\s+(?:l'|l\s+|ton\s+)?armure[\s.!?]*$")
# « montre-toi », « montre-moi ton visage » / « cache-toi », « redeviens le réacteur » (v3, consigne 2)
_VISAGE = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu)\s+)?"
                     r"(?:montre[- ]?toi|montrez[- ]?vous|te montrer|(?:montre|affiche)[- ]?moi\s+(?:ton|votre)\s+visage|(?:montre|affiche)\s+(?:ton|votre)\s+visage)"
                     r"(?:\s+(?:a moi|jarvis))?[\s.!?]*$")
_SANS_VISAGE = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu)\s+)?"
                          r"(?:cache[- ]?toi|cachez[- ]?vous|redeviens\s+(?:le\s+|un\s+)?reacteur|(?:retourne|rentre|reviens)\s+dans\s+(?:le\s+|ton\s+)?reacteur"
                          r"|reprends?\s+(?:ta|la)\s+forme\s+(?:normale|de reacteur|d'origine)|(?:cache|range|enleve)\s+(?:ton|le)\s+visage)"
                          r"(?:\s+jarvis)?[\s.!?]*$")
# « montre-moi la Terre », « où est la Station spatiale ? », « les séismes du jour » (v3, consigne 7)
_GLOBE = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu)\s+)?(?:"
                    r"(?P<terre>(?:montre|affiche)[- ]?(?:moi\s+)?(?:la\s+)?(?:terre|planete|globe|mappemonde)"
                    r"|(?:montre|affiche)\s+le\s+globe)"
                    r"|(?P<station>(?:ou (?:est|se trouve|en est))\s+(?:l'|la\s+|le\s+)?(?:station spatiale|iss|station)"
                    r"|(?:montre|affiche)[- ]?(?:moi\s+)?(?:la\s+)?station(?: spatiale)?"
                    r"|(?:position de la|la) station spatiale)"
                    r"|(?P<seismes>(?:les\s+)?(?:seismes|tremblements de terre)(?: du jour| d'aujourd'hui| recents| de la journee)?"
                    r"|(?:montre|affiche)[- ]?(?:moi\s+)?les (?:seismes|tremblements de terre)[a-z' ]*)"
                    r")[\s.!?]*$")
# « pose-toi sur mon écran », « sors du HUD » / « rentre dans l'interface » (v3, consigne 9)
_SUPERPOSITION = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu)\s+)?(?:"
                            r"(?P<on>(?:pose|mets)[- ]toi (?:sur|par[- ]dessus) (?:mon )?(?:ecran|windows|le bureau)"
                            r"|sors du hud|affiche[- ]toi (?:par[- ]dessus|sur) (?:tout|windows|mon ecran)"
                            r"|active (?:la )?superposition)"
                            r"|(?P<off>(?:rentre|retourne) dans (?:le hud|l'interface)|quitte mon ecran"
                            r"|(?:desactive|coupe|enleve) (?:la )?superposition)"
                            r")[\s.!?]*$")
# « on est en live », « anime le direct », « coupe le live » (21/09). Le lien du direct peut suivre.
_LIVE = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:"
                   r"(?P<on>(?:on est|je suis|nous sommes) en (?:live|direct)|passe en mode (?:live|direct)"
                   r"|anime (?:le|mon) (?:live|direct)"
                   r"|(?:lance|demarre|active) (?:le |mon |la |le mode )?(?:live|direct))"
                   r"|(?P<off>(?:coupe|arrete|stoppe|termine|desactive|quitte) (?:le |mon )?(?:mode )?(?:live|direct)"
                   r"|on (?:arrete|coupe) le (?:live|direct)|fin du (?:live|direct))"
                   r")\s*(?P<lien>\S*)[\s.!?]*$")
# « mets-toi à gauche », « va en bas » : déplacer la superposition sans souris (v3, consigne 9)
_PLACE = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:mets|met|place|pose)[- ]toi|va|passe|deplace[- ]toi)\s+"
                    r"(?:a |au |en |sur (?:la |le )?)?(?P<coin>gauche|droite|haut|bas|milieu|centre)[\s.!?]*$")
# « scanne la pièce », « analyse la pièce » (v3, consigne 6)
_SCAN = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu)\s+)?"
                   r"(?:scanne|scanner|scan|analyse|analyser|balaie|balayer|examine|examiner|regarde|inspecte)\s+"
                   r"(?:moi\s+)?(?:la\s+|cette\s+|ma\s+|le\s+)?(?:piece|salle|chambre|bureau|environnement|decor|"
                   r"autour de (?:toi|moi)|ce qu'il y a autour)[\s.!?]*$")
# « active les gestes », « coupe la caméra » (v3, consigne 5)
_GESTES = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:(?:tu peux|peux[- ]tu)\s+)?"
                     r"(?P<verbe>active|activer|allume|allumer|demarre|demarrer|lance|lancer|desactive|desactiver|coupe|couper|"
                     r"eteins|eteindre|arrete|arreter)\s+(?:les\s+|le\s+|la\s+)?"
                     r"(?:gestes|commande[s]? par gestes|camera(?: des gestes)?|suivi des mains)[\s.!?]*$")
# « cache l'hologramme », « enlève l'hologramme » (v3, consigne 4)
_CACHER_HOLOGRAMME = re.compile(r"^(?:(?:hey |ok )?jarvis[,.!]?\s*)?(?:cache|enleve|retire|range|ferme|efface)\s+"
                                r"(?:l'|l\s+|le\s+|cet\s+|ton\s+)?hologramme[\s.!?]*$")
_SENTINELLE = re.compile(r"\b(desactive|coupe|arrete|eteins|active|allume|reactive|remets?)\s+(?:la\s+)?sentinelle\b")
# Les voix (vidéo 5) : « change ta voix : une voix grave et posée », « crée une voix nommée Orage : grave et
# rauque », « prends la voix Orage », « reprends la voix du majordome », « reprends ta voix normale », « quelles voix
# as-tu ? ». La description peut être longue : ces motifs passent avant la limite des 60 caractères.
_CREER_VOIX = re.compile(r"^(?:(?:tu peux |peux[- ]tu )?(?:change[rsz]?|modifie) (?:ta|de) voix|"
                         r"(?:cree|invente|fabrique|dessine)(?:[- ](?:moi|toi))? une (?:nouvelle )?voix|"
                         r"donne[- ]toi une (?:nouvelle |autre )?voix|prends une (?:nouvelle |autre )?voix)"
                         r"(?: (?:nommee|appelee) (?P<nom>[a-z0-9'-]{2,20}(?: [a-z0-9'-]{2,20})?))?"
                         r"[\s:,.!-]*(?P<desc>.*)$")
_VOIX_NORMALE = re.compile(r"^(?:re)?(?:prends|mets|reviens a|retrouve|remets) (?:ta|la|ta propre) voix "
                           r"(?:normale|d'?origine|habituelle|de base|kokoro)[\s.!?]*$")
_CHOISIR_VOIX = re.compile(r"^(?:re)?(?:prends|mets|passe sur|utilise|reviens a|choisis) (?:la|ta) voix "
                           r"(?:du |de la |de |d')?(?P<nom>[a-z0-9'-]{2,20}(?: [a-z0-9'-]{2,20}){0,3}?)[\s.!?]*$")
_LISTE_VOIX = re.compile(r"\b(?:quelles? (?:sont tes |)voix|liste (?:tes|les) voix|tes voix disponibles|"
                         r"quelles voix (?:as[- ]tu|tu as|connais[- ]tu))\b")
# Le dossier glissé sur le HUD (vidéo 5) : « range ce que je viens de te donner », « range-le », « résume-le »,
# « cherche les factures dedans ». Pas « range mes téléchargements » (l'outil ranger, par le cerveau) ni « résume ce
# que j'ai copié » (le presse-papiers).
_CE_DEPOT = r"(?:le|la|les|ca|tout ca|ce que je (?:viens de te (?:donner|glisser|envoyer)|t'?ai (?:donne|glisse|envoye))|ce dossier|le dossier que je t'?ai (?:donne|glisse|envoye))"
_DEPOT_RANGER = re.compile(rf"^(?:range|trie|classe)[- ]{_CE_DEPOT}[\s.!?]*$")
_DEPOT_RESUMER = re.compile(rf"^(?:resume|fais[- ]moi un resume de|de quoi parle|qu'?est[- ]ce qu'?il y a dans)[- ]{_CE_DEPOT}[\s.!?]*$")
_DEPOT_CHERCHER = re.compile(r"^(?:cherche|trouve|trouve[- ]moi|y a[- ]t[- ]il|est[- ]ce qu'?il y a)\s+(?P<q>.+?)\s+"
                            r"(?:dedans|la[- ]dedans|dans (?:ce dossier|le dossier que je t'?ai (?:donne|glisse)|ce que je t'?ai donne))[\s?.!]*$")
# Le tournoi (vidéo 5) : « lance le tournoi », « épreuve suivante », « plaidoiries », « j'élimine Nova », « fin du tournoi »
_TOURNOI = re.compile(r"^(?:lance|commence|demarre|on lance)\s+(?:le\s+)?tournoi[\s.!?]*$")
_EPREUVE = re.compile(r"^(?:(?:lance |passe a |on passe a )?l'?epreuve suivante|epreuve suivante|manche suivante)[\s.!?]*$")
_PLAIDOIRIES = re.compile(r"^(?:(?:les |place aux |a vous les )?plaidoiries|plaidez|defendez[- ]vous)[\s.!?]*$")
_ELIMINE = re.compile(r"^(?:j'?elimine|elimine|j'?elimine le candidat|on elimine)\s+(?P<nom>[a-z'-]{2,20})[\s.!?]*$")
_FIN_TOURNOI = re.compile(r"^(?:fin du tournoi|arrete le tournoi|termine le tournoi|le tournoi est fini)[\s.!?]*$")
# Les profils (vidéo 5) : « passe sur le profil Nova », « enregistre ce profil sous le nom Nova », « quels profils as-tu ? »
_PROFIL = re.compile(r"^(?:passe|bascule|change)\s+(?:sur|vers|de|en)\s+(?:le\s+)?profil\s+(?P<nom>[a-z0-9'-]{2,30}(?: [a-z0-9'-]{2,30})?)"
                     r"[\s.!?]*$|^(?:re)?prends\s+le\s+profil\s+(?P<nom2>[a-z0-9'-]{2,30}(?: [a-z0-9'-]{2,30})?)[\s.!?]*$")
_ENREGISTRER_PROFIL = re.compile(r"^(?:enregistre|garde|sauvegarde|memorise)\s+(?:ce|ton|le)\s+profil\s+(?:sous le nom|comme|:)?\s*"
                                 r"(?P<nom>[a-z0-9'-]{2,30}(?: [a-z0-9'-]{2,30})?)[\s.!?]*$")
_LISTE_PROFILS = re.compile(r"\b(?:quels? (?:sont tes |)profils|liste (?:tes|les) profils)\b")
# « appelle-toi Nova », « ton nom est Nova », « je vais t'appeler Nova », « redeviens Jarvis » (vidéo 5, demande des
# utilisateurs). Pas « appelle-moi madame » : c'est le titre de la personne, pas le prénom de l'assistant.
_PRENOM = re.compile(r"^(?:(?:tu peux |peux[- ]tu )?(?:appelle|appeler)[- ]toi|tu t'?appelles? (?:maintenant|desormais)|"
                     r"(?:desormais|maintenant),? tu t'?appelles?|ton (?:nouveau )?(?:nom|prenom) (?:est|sera|c'?est)|"
                     r"je (?:vais )?t'?appeler(?:ai)?|change de (?:nom|prenom)(?: pour| en|,)?|redeviens)"
                     r"\s+([a-z][a-z'-]{1,19}(?: [a-z][a-z'-]{1,19})?)[\s.!?]*$")
_OUI = re.compile(r"^(?:jarvis[,.]?\s*)?(oui|ouais|yes|vas[- ]y|confirme|je confirme|c'?est bon|fais[- ]le|d'?accord|ok)\b.{0,30}$")
_NON = re.compile(r"^(?:jarvis[,.]?\s*)?(non|no|laisse tomber|annule|surtout pas|pas du tout|n'?en fais rien)\b.{0,30}$")


def _normaliser(t: str) -> str:
    t = t.replace("’", "'")
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _texte_original(texte: str, extrait_normalise: str) -> str:
    """La partie extraite, reprise dans le texte d'origine (accents compris) : on compte les caractères de base."""
    brut = re.sub(r"\s+", " ", texte.replace("’", "'")).strip()
    n = _normaliser(brut)
    debut = n.rfind(extrait_normalise)
    if debut < 0:
        return extrait_normalise
    # position équivalente dans le texte d'origine : même nombre de caractères non diacritiques avant
    compte, i = 0, 0
    for i, c in enumerate(brut):
        if compte == debut:
            break
        if unicodedata.category(unicodedata.normalize("NFD", c)[0]) != "Mn":
            compte += 1
    return brut[i:].strip(" .!?")


def reconnaitre(texte: str) -> str | None:
    return analyser(texte)[0]


def analyser(texte: str, confirmation_en_attente: bool = False) -> tuple[str | None, str]:
    """(commande, argument) ; (None, "") si la phrase est pour le cerveau."""
    texte = prenom.retirer_appel(texte)       # « Nova, éteins-toi » : les motifs ne connaissent que « jarvis »
    n = _normaliser(texte)
    m = _PRENOM.match(n)
    if m and len(n) <= 60:
        return "prenom", _texte_original(texte, m.group(1))
    m = _CREER_VOIX.match(n)
    if m and len(n) <= 300:
        desc = _texte_original(texte, m.group("desc")) if m.group("desc").strip() else ""
        return "creer_voix", {"description": desc.strip(" .!"), "nom": m.group("nom") or ""}
    if _VOIX_NORMALE.match(n):
        return "voix_normale", ""
    m = _CHOISIR_VOIX.match(n)
    if m and len(n) <= 60:
        return "choisir_voix", m.group("nom")
    if _LISTE_VOIX.search(n) and len(n) <= 60:
        return "liste_voix", ""
    if _TOURNOI.match(n):
        return "tournoi", "lancer"
    if _EPREUVE.match(n):
        return "tournoi", "epreuve"
    if _PLAIDOIRIES.match(n):
        return "tournoi", "plaidoiries"
    if _FIN_TOURNOI.match(n):
        return "tournoi", "fin"
    m = _ELIMINE.match(n)
    if m:
        return "tournoi", "eliminer:" + m.group("nom")
    m = _PROFIL.match(n)
    if m:
        return "profil", m.group("nom") or m.group("nom2")
    m = _ENREGISTRER_PROFIL.match(n)
    if m:
        return "enregistrer_profil", _texte_original(texte, m.group("nom"))
    if _LISTE_PROFILS.search(n) and len(n) <= 60:
        return "liste_profils", ""
    if _DEPOT_RANGER.match(n):
        return "depot_ranger", ""
    if _DEPOT_RESUMER.match(n):
        return "depot_resumer", ""
    m = _DEPOT_CHERCHER.match(n)
    if m and len(n) <= 90:
        return "depot_chercher", m.group("q")
    if confirmation_en_attente:
        if _OUI.match(n):
            return "confirmer", ""
        if _NON.match(n):
            return "refuser", ""
    m = _RETENIR.match(n)
    if m:
        return "retenir", _texte_original(texte, m.group(1))
    m = _OUBLIER_SOUVENIR.match(n)
    if m and not re.match(r"^(tout|la conversation|ce qu'?on a dit)\b", m.group(1)):
        return "oublier_souvenir", _texte_original(texte, m.group(1))
    from .crypto import vocal as crypto_vocal       # le pouvoir crypto (vidéo 4) : cours, portefeuille fictif, replay, alertes
    crypto = crypto_vocal.analyser(n)
    if crypto:
        return crypto
    m = _PERSONNALITE.search(n)
    if m and len(n) <= 80:
        nom = next(g for g in m.groups() if g)
        return "personnalite", {"sarcasme": "sarcastique", "paranoiaque": "parano", "maladroit": "nul"}.get(nom, nom)
    m = _ARMURE.match(n)
    if m and len(n) <= 70:
        from .armures import nom_depuis
        nom = nom_depuis(m.group(1))
        if nom:
            return "armure", nom
    if _SANS_ARMURE.match(n):
        return "armure", "jarvis"
    m = _GLOBE.match(n)
    if m:
        return "globe", "terre" if m.group("terre") else "station" if m.group("station") else "seismes"
    m = _PLACE.match(n)
    if m:
        return "superposition_place", {"centre": "milieu"}.get(m.group("coin"), m.group("coin"))
    m = _LIVE.match(n)
    if m:
        return "live", ("on:" + (m.group("lien") or "")) if m.group("on") else "off"
    m = _SUPERPOSITION.match(n)
    if m:
        return "superposition", "on" if m.group("on") else "off"
    if _SCAN.match(n):
        return "scan", ""
    m = _GESTES.match(n)
    if m:
        return "gestes", "off" if m.group("verbe")[:3] in ("des", "cou", "ete", "arr") else "on"
    if _CACHER_HOLOGRAMME.match(n):
        return "hologramme_cacher", ""
    if _VISAGE.match(n):
        return "visage", "on"
    if _SANS_VISAGE.match(n):
        return "visage", "off"
    m = _SENTINELLE.search(n)
    if m and len(n) <= 60:
        return "sentinelle", "off" if m.group(1) in ("desactive", "coupe", "arrete", "eteins") else "on"
    if len(n) > 60:      # une commande est courte ; une longue phrase qui contient « silence » n'en est pas une
        return None, ""
    for nom, motifs in COMMANDES.items():
        if any(re.search(motif, n) for motif in motifs):
            return nom, ""
    return None, ""
