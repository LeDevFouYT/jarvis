# Démo réelle de Jarvis

Tout ce qui suit fonctionne pour de vrai : vrai micro, vraie voix, vrai bot Telegram, vraie webcam, vraies données
YouTube. Aucun faux serveur ni image d'essai.

## 1. La veille : préparer

```
.venv\Scripts\python.exe -m jarvis demo
```

La commande vérifie chaque brique sans lancer Jarvis et dit comment régler ce qui manque :

| Contrôle | Pour que ce soit prêt |
|---|---|
| Ollama et modèles | `ollama pull` des modèles indiqués |
| Whisper et Kokoro | un premier `lancer.bat` les télécharge |
| Micro | un casque : l'interruption et la conversation continue marchent mieux |
| ComfyUI | lancé avant de filmer, sinon Jarvis le démarre et il faut compter une minute de plus |
| Webcam | une webcam branchée, ou dans OBS « Démarrer la caméra virtuelle » |
| Telegram | Réglages › Telegram : les 4 étapes (BotFather, jeton, « bonjour » au bot, trouver mon identifiant) |
| YouTube | sans clé ça marche ; avec une clé gratuite (Réglages › YouTube) c'est plus rapide |
| Ma chaîne | Réglages › YouTube › Ma chaîne, et un ou deux concurrents |
| Machine | au moins 4 Go de mémoire vive libres : fermer navigateurs lourds et jeux |

Puis, le jour même : lancer `lancer.bat`, attendre les quatre voyants verts en bas du HUD (cerveau, whisper, micro, voix),
appuyer sur F pour le plein écran.

## 2. Le déroulé

L'ordre compte : la webcam et les miniatures libèrent la carte graphique pour la vision ou le dessin, puis le cerveau
se recharge. On les garde pour la fin. Durées mesurées sur la RTX 5080 le 17/09/2026.

| # | Ce qu'on dit (ou fait) | Ce qu'on voit | Durée |
|---|---|---|---|
| 1 | « Jarvis, quelle heure est-il ? » | réponse immédiate, sans le cerveau | < 1 s |
| 2 | « Dans quel état est la machine ? » | panneau de jauges et courbe de la carte graphique | 1 s |
| 3 | « Retiens que je suis végétarien » puis « Qu'est-ce que tu sais de moi ? » | la constellation des souvenirs | 2 s |
| 4 | « Propose-moi une idée de dîner rapide pour ce soir » | l'étoile « végétarien » s'allume, le dîner en tient compte | 3 s |
| 5 | Parler pendant qu'il répond | il se tait et écoute (casque) | immédiat |
| 6 | Après une réponse, enchaîner sans dire « Jarvis » | l'anneau de décompte autour du réacteur | 8 s d'écoute |
| 7 | « Passe en mode coach » puis « J'ai la flemme de monter ma vidéo » | il pousse à s'y mettre maintenant | 2 s |
| 8 | « Passe en mode majordome » puis « What's the tallest mountain in Europe? » | réponse et voix anglaises | 2 s |
| 9 | « Ouvre le bloc-notes », « mets-le à droite », « ferme-le » | la fenêtre bouge ; s'il y a du texte non enregistré, il demande | 1 s chacun |
| 10 | « Range mes téléchargements » puis « annule » | le graphique du rangement ; tout revient en place | 2 s |
| 11 | Copier un long texte, puis « Résume ce que j'ai copié » | le résumé à l'écran et dans le presse-papiers | 5 s |
| 12 | « Résume-moi cette vidéo » + un lien YouTube | la frise des moments clés ; un clic ouvre la vidéo au bon moment | 40 s pour 6 min de vidéo |
| 13 | « Analyse ma chaîne » | le nuage des vidéos (les exceptions brillent), les barres par jour, la vérification des chiffres | 15 à 30 s |
| 14 | « Qu'est-ce que les gens demandent dans les commentaires de » + un lien | les demandes groupées et comptées | 20 à 40 s |
| 15 | « Fais-moi le briefing » | ta chaîne, les commentaires, le concurrent, les rappels, la machine | 30 à 60 s |
| 16 | Téléphone : envoyer un vocal au bot | réponse en texte puis en vocal ; le message apparaît dans le HUD | 5 à 15 s |
| 17 | Téléphone : « Ouvre la calculatrice » | les boutons Oui / Non ; rien ne s'ouvre avant « Oui » | au clic |
| 18 | « Jarvis, regarde-moi » | la photo et sa description ; rien n'est enregistré | 30 s, plus le rechargement du cerveau |
| 19 | « Fais-moi trois miniatures pour ma vidéo sur … » | trois miniatures 1280×720 avec le titre | 1 min 30 à 2 min |
| 20 | « Jarvis, éteins-toi » | au revoir et extinction propre | 3 s |

## 3. À savoir pendant le tournage

- Le premier chiffre de la vérification apparaît tout de suite ; le jugement de chaque phrase arrive quelques secondes après la réponse.
- Un propriétaire de vidéo peut interdire le lecteur intégré : le clic ouvre alors YouTube directement, au bon moment.
- Sans clé YouTube, la première analyse d'une chaîne lit ses pages publiques (15 à 30 s) ; la suivante sort du cache.
- Si Jarvis parle trop fort dans les haut-parleurs, il peut s'entendre : avec un casque, aucun souci.
