# Nouveautés de Jarvis

## 🏆 Vos quatre demandes, et trois Jarvis qui s'affrontent

- **Le prénom de votre choix** : « Nova, quelle heure est-il ? » marche comme « Jarvis ». Mesuré sur 20 phrases et 5 minutes de conversation pleine de pièges (novembre, on va, nouveau) : 20 sur 20, zéro faux réveil.
- **Une voix décrite avec des mots** : Jarvis en dessine six, les réécoute et garde la meilleure. Imiter une personne réelle est refusé ; cloner un enregistrement demande votre accord (ou celui de la personne).
- **Un dossier glissé dans la fenêtre** : Jarvis le retrouve sur le disque, puis le résume, le range ou cherche dedans.
- **Linux** : `installer.sh` et `lancer.sh`. Je n'ai pas de Linux pour essayer en vrai : si vous êtes sous Linux, dites-moi ce qui coince.
- **Les profils** : un prénom, une voix, une personnalité et une armure, enregistrés ensemble. « Enregistre ce profil sous le nom Nova », puis « passe sur le profil Nova » change tout d'un coup.
- **Le mode tournoi** : plusieurs profils du même Jarvis s'affrontent en quatre épreuves (ranger un dossier, inventer une miniature, deviner ce que vous faites à l'écran, sculpter un dragon en 3D), et vous éliminez à la voix. Les plaidoiries parlent maintenant de l'épreuve qui vient de se jouer, plus de la première. Il faut une carte graphique de 16 Go pour le tournoi (tout tourne sur votre PC).
- **Jarvis trader** : le cours de 20 cryptos et des grandes bourses à la voix, un graphique géant dans le HUD, un portefeuille fictif de 10 000 € (aucun argent réel, jamais), « rejoue tes 10 derniers jours » et des alertes. Il donne des chiffres, jamais de conseil. Quand il lit un prix sur un graphique, il le compare aux vraies données et se corrige à voix haute s'il s'est trompé ; les petites pertes sous 0,1 % ne s'affichent plus « −0,0 % » ; « pourquoi tu as attendu le 12 ? » ne répète plus six fois la même raison.

## 📈 Jarvis trader : la crypto et la bourse, à la voix

- **Le cours de 20 cryptos en euros** : « combien vaut le Bitcoin ? », « comment va l'Ethereum sur 7 jours ? », « qu'est-ce qui monte le plus ? ». Les cours viennent des API publiques de Binance (Kraken en relais), sans clé ni compte.
- **Un graphique géant dans le HUD**, vert quand ça monte, rouge quand ça baisse, sur 24 heures, 7 jours ou 30 jours.
- **Un portefeuille fictif de 10 000 €** : « achète pour 500 € de Solana », « vends la moitié de mon Ethereum », « combien je vaux ? ». Chaque ordre demande un oui ou un non, avec 0,1 % de frais comme sur une vraie plateforme. Aucun argent réel, jamais.
- **« Rejoue tes 10 derniers jours »** : Jarvis repart de 10 000 € fictifs et décide seul toutes les 4 heures, sans jamais voir la suite. À la fin, il compare son résultat à « garder ses euros » et à « tout en Bitcoin le premier jour ». Demande-lui « pourquoi tu as vendu le 12 ? » : il te relit sa raison.
- **Des alertes** : « préviens-moi si le Bitcoin passe sous 70 000 € » ou « s'il perd 1 % dans l'heure ». Il vérifie toutes les 30 secondes, prévient à voix haute (et sur Telegram si tu l'as réglé), et l'alerte survit au redémarrage.
- **« Fais-moi le point crypto »**, avec chaque chiffre vérifié avant d'être dit, et **« regarde ce graphique »** pour qu'il décrive un graphique ouvert à l'écran.
- **Le point des marchés** : CAC 40, S&P 500, Nasdaq, DAX, Dow Jones, les plus fortes hausses et baisses, l'or et le pétrole.

Jarvis donne des chiffres, jamais de conseil : à « je devrais acheter ? », il répond qu'il n'est pas conseiller en investissement. Ce n'est pas un outil pour placer de l'argent.

## Sécurité importante

Une page web ouverte dans votre navigateur pouvait, par un détournement de nom de domaine, parler à
votre Jarvis comme si elle venait de votre machine — et donc lui faire ouvrir des programmes ou
déplacer vos fichiers. C'est corrigé : Jarvis ne répond plus qu'aux demandes venues de votre
ordinateur. **Mettez à jour** : il le fait tout seul au prochain lancement.

## 🔧 Le nettoyage continue : téléphone, micro et YouTube

- **Telegram, enfin sans surprise.** Une réponse envoyée à ton téléphone n'est plus coupée si quelqu'un dit « Hey Jarvis » à la maison. Une image, une capture ou une description demandée depuis le téléphone arrive sur le téléphone, pas dans les haut-parleurs du salon.
- **Change de casque quand tu veux.** Casque Bluetooth débranché, rebranché ou remplacé : Jarvis s'en rend compte tout seul et continue d'écouter et de parler, sans redémarrage.
- **Il dit quand il a un souci.** Si son cerveau (Ollama) ne répond pas, Jarvis te le dit au lieu de rester bloqué sur « réflexion ».
- **« Écris-moi un poème »** : il te le récite, il ne le tape plus dans la fenêtre ouverte. Et « quelle note as-tu eue ? » n'est plus pris pour une demande de prise de notes.
- **Rangement plus sûr** : un fichier ouvert dans Word ou Excel reste à sa place, sans doublon, et Jarvis te le signale. Les dossiers de projets de code ne sont jamais rangés.
- **Les calculs impossibles** (« 9 puissance 9 puissance 9 ») répondent instantanément au lieu de figer Jarvis.
- **YouTube plus fiable** : l'analyse de ta chaîne ne plante plus si les statistiques privées sont indisponibles, le briefing ne rate plus une vidéo publiée le soir, et changer de compte Google fonctionne proprement.

## 🛠️ Grand nettoyage : Jarvis plus fiable au quotidien

On a passé tout Jarvis au peigne fin. Voici ce qui change pour toi :

- **Il ne s'éteint plus sur une simple phrase.** « Parle-moi de l'extinction des dinosaures » ou « mon chat va dormir où ? » sont maintenant des questions comme les autres. Pour l'éteindre, dis « Jarvis, éteins-toi ».
- **Tes rappels sonnent à la bonne heure.** « Dix-huit heures », « 18 heures 30 », « dans une heure et demie », « 7 h du soir », « lundi à 9 h », « le 25 à 10 h » : tout est compris. Et un rappel manqué pendant que Jarvis était éteint t'est dit au démarrage au lieu de disparaître.
- **« Ouvre… » n'ouvre plus jamais un programme téléchargé.** Jarvis ouvre tes documents, photos, vidéos et raccourcis, mais ne lance plus un fichier .exe, .bat ou un script trouvé dans tes Téléchargements.
- **Il ne devient plus sourd.** Si une phrase ne passe pas (carte graphique occupée par une image, par exemple), Jarvis le signale et continue d'écouter, au lieu d'attendre un redémarrage.
- **Des mises à jour qui ne cassent rien.** La nouvelle version est préparée à côté de l'ancienne ; au moindre souci (antivirus, disque plein, coupure), l'ancienne est remise en place et la mise à jour réessaie au lancement suivant.
- **Jarvis Cloud** : paiement et partage de la machine plus sûrs.

## 📂 « Ouvre mes notes » : il ouvre tes fichiers

- **Ouvre un fichier par son nom**, comme tu le dis : « ouvre le document texte sur le bureau », « ouvre mes notes », « ouvre la facture en PDF ». Jarvis cherche sur le bureau, dans Documents, Téléchargements, Images, Vidéos et Musique, et comprend même un nom mal entendu.
- **Rien d'inventé** : si plusieurs fichiers se ressemblent, il te demande lequel ; s'il ne trouve rien, il le dit.
- **La fenêtre arrive devant toi** : le Bloc-notes ou le fichier ouvert passe au premier plan, même quand Jarvis est en plein écran.
- **Une seule réponse** quand tu parles en maintenant Espace : le micro du PC se met en pause, plus de réponse en double.
- « note.md » n'ouvre plus un site web par erreur.

## 🎯 Jarvis t'obéit du premier coup

- **« Jarvis, ouvre le bloc-notes » d'une traite** : Jarvis entend maintenant la question entière, même quand tu enchaînes juste après son nom. Avant, le début pouvait se perdre et il ne recevait que « le bloc note ».
- **Il agit au lieu de parler** : quand tu lui demandes d'ouvrir, ranger, écrire ou déplacer quelque chose, il le fait vraiment. Il ne répond plus « Oui, monsieur » sans rien faire, et il ne lit plus jamais le nom d'un outil à voix haute.
- **« Hey Jarvis »… puis une pause** : il attend ta question au lieu de dire qu'il n'a rien entendu.
- **Plus vif** : le premier son arrive en 1,1 seconde en valeur médiane.
- **J'ouvre le bloc-notes, monsieur** : une confirmation claire quand une application s'ouvre.

## 📱 Jarvis au téléphone, Jarvis qui voit, Jarvis qui gère ta chaîne

La plus grosse mise à jour depuis la sortie. Tout tourne toujours sur ton PC : rien ne part dans un cloud sans que tu le demandes.

### 📱 Telegram, pour de vrai
- **Écris ou envoie un vocal** à ton bot : Jarvis le transcrit sur ta machine et répond **en texte et en vocal**, avec sa propre voix.
- **Rien ne bouge sur ton PC sans ton accord** : ouvrir une appli, ranger un dossier, fermer une fenêtre… Jarvis te demande d'abord, avec des boutons **✅ Oui / ❌ Non**.
- **Ta discussion, et seulement elle.** Un inconnu qui écrit à ton bot est ignoré, et signalé en rouge dans le HUD.
- **Un assistant de configuration** en 4 étapes dans les Réglages : il vérifie ton jeton et trouve tout seul ton identifiant.

### 👀 Il voit et il crée
- **Webcam** : « Jarvis, regarde-moi ». La photo reste en mémoire, jamais enregistrée sauf si tu le demandes.
- **Résumé de vidéo YouTube** : colle un lien, Jarvis écoute la vidéo, la résume et place **5 à 8 moments clés** sur une frise. Un clic et la vidéo s'ouvre au bon moment.
- **Miniatures** : trois propositions en 1280×720, dessinées sur ta carte graphique, avec un titre percutant incrusté. En un peu plus d'une minute et demie.

### 📊 Il gère ta chaîne
- **Analyse d'une chaîne** par son nom ou son @ : médiane des vues, vidéos qui explosent (plus de 3 fois la médiane), meilleurs jours et heures, titres qui marchent. Avec un **nuage de points** où les exceptions brillent.
- **Les demandes de ta communauté** : Jarvis lit les commentaires, regroupe ce qu'on te demande par thème et compte.
- **Le briefing du matin** : ta chaîne depuis hier, les nouvelles demandes, un concurrent en forme, tes rappels et l'état du PC. Pas de météo, que du concret.
- **Zéro chiffre inventé** : chaque chiffre dit par Jarvis est cherché dans les données, et chaque phrase est relue. Les écarts s'affichent à l'écran.
- **Sans clé** ça marche déjà, avec les pages publiques. **Avec une clé YouTube gratuite**, c'est plus rapide ; et en connectant ton compte, tu as en plus la rétention et les sources de trafic.

### ⚡ Plus rapide, plus juste
- Les images se dessinent **2 à 3 fois plus vite**.
- Le lecteur YouTube intégré ne bloque plus, et si une vidéo refuse l'intégration, elle s'ouvre directement sur YouTube.
- Le mode **coach** ne te laisse plus remettre à demain.
- « Range le dossier démo » est compris quelle que soit la façon de le dire.
- Une commande `python -m jarvis demo` vérifie que tout est prêt avant de filmer une démo.

## 🧠 La mémoire, la conversation et les réflexes

- **Mémoire longue** : « retiens que… », « qu'est-ce que tu sais de moi ? », « oublie que… ». Jarvis ne se sert que des souvenirs utiles à ta question, et une constellation 3D les montre s'allumer.
- **Conversation continue** : après une réponse, il t'écoute encore quelques secondes, sans redire « Jarvis ».
- **Coupe-lui la parole** : parle pendant qu'il parle, il se tait et t'écoute.
- **Réponse éclair** : il commence à répondre en 1,7 seconde, contre 3,6 avant (valeurs médianes mesurées).
- **Trois personnalités** : majordome, sarcastique ou coach. Et il répond en anglais quand tu lui parles anglais.
- **Il agit sur ton PC** : fenêtres à gauche ou à droite, rangement de dossiers annulable, dictée, résumé du presse-papiers.
- **Sentinelle** : il te prévient si la carte chauffe, si un disque est presque plein ou si un rappel approche.

## 🛰️ La salle de briefing

- Un nouveau HUD : réacteur en 3D, panneaux holographiques, texte qui s'écrit au rythme de la voix, mode discret.
