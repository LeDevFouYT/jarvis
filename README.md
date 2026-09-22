# Jarvis

Un assistant vocal local façon Iron Man. Il écoute le micro en permanence, se réveille à « Hey Jarvis », comprend le français, répond à voix haute en vous appelant « monsieur », et agit sur le PC : état de la machine, fichiers, applications, sites web, volume, captures, description de l'écran, génération d'images, Telegram, rappels. Tout tourne sur la machine. La seule chose qui peut sortir sur Internet est la voix ElevenLabs, optionnelle, et le compteur en bas du HUD le montre.

## Licence et prix

Jarvis est gratuit, et son code aussi : **licence AGPL v3**. Vous pouvez l'utiliser chez vous autant que vous voulez, le
modifier, le partager, le forker. La seule condition : si vous le distribuez ou le proposez en ligne à d'autres personnes,
votre version doit être publiée sous la même licence. Le code est ici même (https://github.com/LeDevFouYT/jarvis).

Pour l'intégrer à un produit **sans publier votre code**, ou pour le revendre, il existe une licence commerciale :
voir [LICENCE-COMMERCIALE.md](LICENCE-COMMERCIALE.md). Les versions jusqu'à v1.0.18 comprises étaient sous MIT et le restent.

Tout est gratuit. Un service en ligne payant a existé pour les machines sans carte graphique suffisante (le cerveau tournait alors sur une autre machine) : il est **suspendu pour le moment**, le temps de le rendre disponible en permanence. Le code de la passerelle reste dans le dépôt pour qui veut monter la sienne.

## Ce qu'il faut

- Windows 10 ou 11, Python 3.12, une carte NVIDIA. Version complète à partir de 12 Go de VRAM (qwen3:14b, gemma3:12b, Whisper turbo), version réduite en dessous (qwen3:8b, gemma3:4b, Whisper small). Sans carte NVIDIA, ça démarre mais le cerveau tourne sur processeur, très lentement, sans vision ni images.
- Ollama installé (ollama.com). Les modèles se téléchargent tout seuls au premier lancement.
- Un micro. Un casque évite que Jarvis s'entende parler.
- Facultatif : ComfyUI pour les images, une clé ElevenLabs pour une plus belle voix, un bot Telegram pour les messages et les rappels.
- Rien n'exige de droits administrateur.

## Installation en cinq lignes

Le plus simple : double-cliquer `Jarvis-Installateur.exe`. Il examine la machine et le dit clairement : local version complète, local version réduite, ou processeur seul (lent, sans vision ni images). Il installe tout dans un dossier au choix, sans droits administrateur, et crée un raccourci sur le Bureau. Sinon, à la main :

1. Récupérer le dossier (git clone ou archive) et double-cliquer `installer.bat` : venv, dépendances, `config.json`, `.secrets`, détection de la carte et choix des modèles.
2. Ouvrir `.secrets` et y mettre les clés que vous utilisez (ElevenLabs, Telegram, cerveau distant). Laisser vide sinon.
3. Ouvrir `config.json` : le micro dans `oreilles.peripherique` (liste avec `.venv\Scripts\python.exe -m jarvis peripheriques`), la table `applications`, le chemin de ComfyUI si vous l'avez.
4. Double-cliquer `lancer.bat` : Ollama démarre s'il ne tourne pas, les modèles manquants se téléchargent, le HUD s'ouvre dans le navigateur. Appuyer sur F pour le plein écran.
5. Dire « Hey Jarvis », attendre l'anneau qui s'ouvre, poser la question.

## Commandes vocales

- « Hey Jarvis » puis n'importe quelle demande, ou directement « Jarvis, quelle heure est-il ? » d'une traite. L'enregistrement s'arrête après 0,7 s de silence. Après chaque réponse, Jarvis écoute encore 8 secondes sans mot de réveil (anneau de décompte autour du réacteur).
- « Jarvis, appelle-moi madame » (ou monsieur) : il s'en souvient d'une session à l'autre.
- « Jarvis, éteins-toi » : il dit au revoir et s'arrête proprement.
- « Jarvis, oublie tout » : il vide la conversation.
- « Jarvis, silence » : il se tait jusqu'au prochain « Hey Jarvis ».
- Parler pendant qu'il parle le coupe, et il écoute la nouvelle phrase (casque recommandé : avec des haut-parleurs, il peut s'entendre lui-même, et il coupe l'interruption s'il le détecte).
- « Retiens que je suis végétarien », « qu'est-ce que tu sais de moi ? », « oublie que je suis végétarien » : la mémoire longue. En fin de session, il garde aussi seul ce qui reste vrai dans un mois. Seuls les souvenirs utiles à une question lui sont donnés, et la constellation du HUD allume ceux qu'il a utilisés.
- « Passe en mode sarcastique » (ou majordome, ou coach) : change sa personnalité.
- Une question en anglais reçoit une réponse en anglais, avec une voix anglaise.
- « Mets Chrome à gauche », « le bloc-notes en plein écran », « sur l'autre écran », « réduis tout sauf Word », « ferme le bloc-notes » (il demande d'abord si du travail n'est pas enregistré).
- « Range le dossier Téléchargements » : classement par type et par mois, déplacements seulement, jamais de suppression ; « annule » remet tout en place. Les dossiers système sont refusés. Essai sans risque : `python -m jarvis demo_rangement` puis « range le dossier démo ».
- « Écris : bonjour à tous » tape le texte dans la fenêtre active ; « résume ce que j'ai copié » ou « reformule-le plus poliment » remet le résultat dans le presse-papiers.
- « Désactive la sentinelle » / « réactive la sentinelle » : la surveillance de fond (carte trop chaude, disque presque plein, rappel proche), au plus un message par sujet toutes les 10 minutes.
- « Jarvis, regarde-moi » : une photo par la webcam, décrite par le modèle de vision ; elle n'est jamais enregistrée, sauf « garde la photo » (workspace/webcam).
- « Résume-moi cette vidéo » + un lien YouTube : résumé et 5 à 8 moments clés sur une frise ; un clic ouvre la vidéo au bon moment. Sans clé ; une vidéo déjà résumée ressort du cache.
- « Fais-moi trois miniatures pour ma vidéo sur… » : trois images 1280×720 dessinées par ComfyUI avec un titre incrusté (workspace/miniatures).
- « Analyse la chaîne @… » (ou « ma chaîne ») : médiane des vues, vidéos au-dessus de trois fois la médiane, jours et heures, titres ; nuage des vidéos et barres par jour. « Qu'est-ce que les gens demandent dans les commentaires de… » : demandes groupées par thème et comptées. « Fais-moi le briefing » : ma chaîne depuis hier, nouvelles demandes, un concurrent en forme, rappels, machine. Chaque chiffre de la réponse est cherché dans les données et chaque phrase relue : les écarts s'affichent.
- Dans le HUD : maintenir Espace (ou le réacteur) pour parler sans mot de réveil, Échap pour le faire taire et fermer les panneaux, M pour le mode discret (le réacteur se range dans un coin), P pour rouvrir ou fermer les panneaux, F pour le plein écran, un champ texte en bas pour écrire. Les outils ouvrent des panneaux holographiques : jauges de la machine, notes, rappels, fichiers, images, recherches.

Exemples : « cherche des phares bretons sur Internet » (les résultats s'affichent dans l'onglet intégré du HUD), « mets une vidéo de chats » (lecteur YouTube intégré), « dans quel état est la machine », « quels fichiers vidéo j'ai modifiés aujourd'hui », « ouvre YouTube et cherche des vidéos de chats », « regarde mon écran et dis-moi ce que je fais », « dessine un robot majordome en laiton », « envoie-moi ça sur Telegram », « rappelle-moi dans vingt minutes de sortir le pain », « mets le volume à 30 », « verrouille la session ».

## Le mode live : Jarvis anime votre direct

Il lit le tchat de votre direct YouTube, répond quand on l'appelle, accueille les arrivées, et relance la
conversation de temps en temps — à voix haute, comme un co-animateur.

**Ce qu'il faut, une fois pour toutes :**

1. **Une clé YouTube** (gratuite). Ouvrez Réglages › YouTube : les trois boutons vous emmènent au bon endroit
   dans la console Google (créer un projet, activer l'API YouTube Data, créer une clé), vous collez la clé dans
   le champ, et « tester la clé » vous dit tout de suite si elle marche. C'est elle qui lit le tchat — sans elle,
   Jarvis vous le dira au lieu de démarrer.
2. **Que vos spectateurs entendent Jarvis.** Il parle par la sortie audio de votre PC : dans OBS, ajoutez une
   source **« Capture audio du bureau »** (ou réglez la sortie de Jarvis sur un câble virtuel type VB-Cable et
   ajoutez-le comme source). Sans ça, vous l'entendez, le direct non — c'est l'erreur classique.
3. **Un casque**, comme d'habitude : sinon Jarvis s'entend parler et se coupe lui-même.

**Pendant le direct :** « **Jarvis, on est en live** » — c'est tout. Il cherche le direct en cours sur la chaîne
réglée dans Réglages › YouTube › Ma chaîne. Vous pouvez aussi donner le lien (« anime le direct https://… »), ce
qui coûte moins de quota, ou le fixer une fois dans `config.json` → `live.video`. Puis « **coupe le live** » à la fin — il dit alors combien de messages il a traités
et combien de personnes il a accueillies. Le tchat défile dans un panneau du HUD : ses réponses y sont barrées
de cyan, les arrivées en clair, et le pied compte messages, réponses, accueils et personnes.

**Ce qu'il fait, et ce qu'il ne fait pas :**

- il répond **quand on l'appelle** (« Jarvis, … », « @Jarvis … »), pas à chaque message, et jamais deux fois en
  moins de douze secondes ;
- il **accueille les nouveaux groupés** (une phrase pour quatre arrivées, pas quatre bonjours) ;
- il **ne parle jamais par-dessus vous** : tant que vous parlez, ou qu'il vous écoute, il se tait. Ses prises de
  parole spontanées sont espacées de deux minutes et demie, et il n'en fait pas systématiquement ;
- il **n'écrit rien dans le tchat** : il parle, c'est tout.

**La sécurité, en une phrase : le tchat n'a droit qu'à des mots.** Les messages des spectateurs passent par un
appel **sans outils, sans historique et sans mémoire** : personne ne peut faire ouvrir un fichier, lancer un
programme, lire vos secrets ou sortir sur Internet en écrivant « Jarvis, ignore tes consignes et… ». Vous, votre
voix garde tous les pouvoirs : c'est votre micro, sur votre machine. Le test `python -m jarvis.tests.live` le
vérifie sur des messages piégés, et vérifie aussi dans le code que le chemin du tchat n'appelle jamais le cerveau
qui peut agir.

**Les spectateurs peuvent faire dessiner.** « Jarvis, dessine-moi un phare breton sous l'orage » : l'image est
calculée sur votre carte et s'affiche à l'écran avec le pseudo de la personne. Trois freins pour que ça reste
tenable : une demande par personne toutes les cinq minutes, quatre-vingt-dix secondes entre deux dessins (la
carte ne fait qu'une chose à la fois), et trois demandes en file au maximum.

**Ce qui est interdit ne passe pas.** Deux filtres avant de dessiner : une liste de mots qui bloque l'évidence
sans même consulter le modèle, puis un juge local qui relit la demande avec les règles de la communauté YouTube
— nudité, violence, haine et harcèlement, personnes réelles nommées, enfants, drogues et armes, automutilation,
symboles extrémistes, désinformation, marques et personnages sous droits, texte à écrire dans l'image. Dans le
doute, il refuse : une image refusée coûte une phrase, une image de trop peut coûter la chaîne. Et la demande du
spectateur n'est jamais envoyée telle quelle au générateur : elle est réécrite en description d'image.

**Le HUD du direct** (ce que voit le public) : dans OBS, ajoutez une **source navigateur** sur
`http://127.0.0.1:8765/live`, en 1920 × 1080. On y voit le réacteur qui suit la voix, le tchat avec les réponses
de Jarvis mises en avant, le dernier dessin demandé (avec le pseudo de son auteur), et un bandeau qui compte
messages, réponses, bienvenues, dessins — et les sorties Internet, la preuve à l'image que tout le reste tourne
sur votre machine. Options d'URL : `?fond=transparent` pour poser le HUD par-dessus un jeu, `?cote=gauche` pour
inverser la mise en page, `?reacteur=0` si vous êtes déjà à l'image.

Twitch n'est pas encore géré : YouTube seulement pour l'instant.

## Depuis le téléphone (Telegram)

Réglages › Telegram guide en quatre étapes : créer le bot avec @BotFather, coller et vérifier le jeton, envoyer « bonjour » au bot, « trouver mon identifiant ». Jarvis lit ensuite les messages de **cette discussion seulement** ; tout autre expéditeur est ignoré et signalé en rouge dans le HUD.

- **Texte ou vocal** : un vocal est transcrit par Whisper sur le PC. La réponse revient en texte puis en message vocal, avec la voix de Jarvis (désactivable : « réponse aussi en vocal »).
- **Une action sur le PC demande un bouton** « ✅ Oui / ❌ Non » dans Telegram : ouvrir une application ou un site, fenêtres, rangement, frappe, presse-papiers, volume, webcam. Sans réponse en 55 secondes, rien n'est fait.
- **Commandes** : `/aide`, `/etat`, `/capture`, `/image <description>`, `/notes`, `/rappel <quand> | <texte>`, `/dire <texte>`, `/silence`. Toute autre phrase est une question ; un résumé de vidéo ou des miniatures demandés depuis le téléphone y reviennent quand ils sont prêts.

## Ce qui ne marche pas encore

- La fenêtre de conversation continue et l'interruption s'entendent mal avec des haut-parleurs forts : un casque reste le bon réglage.
- L'alternance de VRAM reste visible : regarder l'écran ou la webcam prend une trentaine de secondes avec gemma3:4b, puis le cerveau se recharge pendant que la question suivante attend ; trois miniatures prennent 1 min 30 à 2 min (ComfyUI ralentit nettement sous 4 Go de mémoire vive libre). Jarvis répond tout de suite « je regarde » ou « je lance le dessin », puis parle quand c'est prêt.
- La vérification des chiffres YouTube dit si un chiffre ou une phrase est faux ; elle ne corrige pas la réponse déjà dite.
- Le mot de réveil est fragile avec de la musique ou une télévision en fond. Le modèle attend « Hey Jarvis » en anglais ; « Jarvis » seul n'est pas garanti. Seuil réglable dans `oreilles.seuil`.
- Whisper invente parfois une phrase sur un souffle ; les classiques sont filtrés par une liste, pas tous.
- Le mode cloud demande la passerelle (dossier `passerelle/`) déployée sur un serveur : le client paie des minutes de calcul, et tout ce qui a besoin d'une carte graphique passe par là — le cerveau, la vision, les images, mais aussi les vidéos, les sculptures 3D et les miniatures. L'écoute et la voix restent sur sa machine. Ce qui traverse n'est qu'une description : la machine qui calcule n'exécute jamais d'ordre venu d'un client.

## Être à 100 % local

Dans `config.json`, mettre `voix.moteur` à `local` (c'est la valeur par défaut). Kokoro parle alors sur le processeur et rien ne sort de la machine : le compteur « requêtes sorties sur internet » du HUD reste à 0. Avec `elevenlabs`, chaque phrase non encore en cache compte une requête. Telegram, le cerveau distant et les recherches sur Internet (« cherche … sur Internet », vidéos YouTube) comptent aussi : Jarvis ne sort que si vous le lui demandez. Ollama, Whisper, Kokoro, ComfyUI et l'index des fichiers ne sortent jamais.

## Réglages depuis l'application

Le bouton **Réglages** du HUD (en bas, à côté de Soutenir) ouvre un panneau où l'on colle ses clés sans ouvrir de fichier :
clé ElevenLabs (et le choix de la voix parmi celles du compte, bouton « lister mes voix »), jeton et identifiant Telegram
(bouton « envoyer un message de test »), jeton Jarvis Cloud, et le moteur de voix (Kokoro local ou ElevenLabs). Les clés
vont dans `.secrets`, le reste dans `config.json`, appliqués immédiatement ; l'application ne les réaffiche jamais
(seulement « définie » et les 4 derniers caractères). Laisser un champ vide garde la clé, écrire `-` l'efface.

## Mises à jour automatiques

À chaque lancement, Jarvis lit `version.json` de la dernière release GitHub, télécharge `mise_a_jour.zip` si elle est plus
récente, vérifie son empreinte SHA-256 et remplace ses fichiers de programme. Jamais touchés : `config.json`, `.secrets`,
`modeles/`, `memoire/`, `workspace/`, `cache/`. Pour désactiver : `mise_a_jour.auto = false` dans `config.json`.

## Réglages utiles

| Clé de `config.json` | Rôle |
|---|---|
| `cerveau.modele`, `cerveau.mode` | modèle Ollama ; `local` ou `cloud` (URL et jeton dans `cerveau.cloud` et `.secrets`) |
| `vision.modele` | modèle de vision Ollama, chargé à la place du cerveau |
| `oreilles.peripherique`, `oreilles.seuil`, `oreilles.silence_s` | micro, sensibilité du mot de réveil, silence qui clôt la phrase |
| `oreilles.conversation_continue`, `oreilles.interruption` | fenêtre d'écoute après une réponse (secondes), interruption et sa sensibilité |
| `personnage.personnalite` | `majordome`, `sarcastique` ou `coach` |
| `voix.kokoro_voix_en` | voix anglaise de Kokoro |
| `memoire.actif`, `memoire.seuil_similarite` | mémoire longue, et exigence pour qu'un souvenir accompagne une question |
| `sentinelle.actif`, `sentinelle.temperature_max` | surveillance de fond et ses seuils |
| `telegram.commandes`, `telegram.reponse_vocale` | commandes Telegram entrantes, réponse aussi en vocal |
| `youtube.ma_chaine`, `youtube.concurrents`, `youtube.quota_jour` | pour « ma chaîne » et le briefing ; limite de quota que Jarvis s'impose |
| `webcam.peripherique` | nom DirectShow de la webcam (sinon la première vraie webcam, les caméras virtuelles en dernier) |
| `comfyui.miniatures` | `largeur`, `hauteur`, `pas` du rendu des miniatures (1024, 576, 8 : agrandies ensuite en 1280×720) |
| `voix.moteur`, `voix.elevenlabs_voix`, `voix.peripherique_sortie` | Kokoro ou ElevenLabs, voix, sortie audio |
| `applications` | nom courant -> .bat, .exe, dossier ou adresse |
| `comfyui.url`, `comfyui.workflow` | API ComfyUI et workflow dans `jarvis/outils/workflows/` |
| `fichiers.racines` | dossiers indexés pour la recherche de fichiers |

## Tests, un par brique

```
.venv\Scripts\python.exe -m jarvis.tests.cerveau     trois questions, deux outils
.venv\Scripts\python.exe -m jarvis ecouter            oreilles en direct : dire « Hey Jarvis » puis une phrase
.venv\Scripts\python.exe -m jarvis ecouter fixture    pareil sans parler, sur une fixture synthétique
.venv\Scripts\python.exe -m jarvis dire "Bonjour monsieur, tout est en ordre."   voix : local puis ElevenLabs
.venv\Scripts\python.exe -m jarvis.tests.vision       décharge, regarde l'écran, recharge, chronomètre
.venv\Scripts\python.exe -m jarvis.tests.serveur      interroge le serveur lancé par lancer.bat
.venv\Scripts\python.exe -m jarvis tests             les pouvoirs 02 à 19, un test chacun, Jarvis arrêté (ou : -m jarvis tests memoire_longue)
.venv\Scripts\python.exe -m jarvis.tests.telegram_entrant   13 : sur un faux Telegram local (vocal réel, boutons, inconnu)
.venv\Scripts\python.exe -m jarvis.tests.voir_et_creer      14 à 16 : webcam, résumé d'une vraie vidéo, miniatures
.venv\Scripts\python.exe -m jarvis.tests.youtube            17 à 19 : sur un faux YouTube aux chiffres connus, cerveau réel
.venv\Scripts\python.exe -m jarvis.tests.ecran 8767         l'écran des tests : chaque vérification en direct dans le navigateur
.venv\Scripts\python.exe -m jarvis demo                     prépare une démo réelle : chaque brique vérifiée, sans lancer Jarvis
```

Les nouveautés de chaque version sont dans `NOUVEAUTES.md`, le déroulé d'une démo filmée dans `DEMO.md`.

## Structure

```
jarvis/            paquet Python : cerveau, oreilles, voix, vision, serveur, commandes, compteur, preparation
jarvis/outils/     un fichier par outil, workflows ComfyUI
jarvis/hud/        la salle de briefing : réacteur three.js (copié dans vendor/), panneaux holographiques
config.json        réglages ; config.example.json pour une nouvelle installation
.secrets           clés, jamais versionné ; .secrets.example comme modèle
lancer.bat         un double-clic pour tout démarrer
installer.bat      pour installer sur une autre machine
modeles/ cache/ workspace/ memoire/   poids, cache voix et index, images et captures, notes ; ignorés par git
```
