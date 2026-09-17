"""YouTube : les données d'une chaîne, ses commentaires et le briefing du matin.

  acces.py         l'API YouTube Data v3 (clé) et YouTube Analytics (OAuth) : cache SQLite, quota compté, sorties Internet
  oauth.py         connexion « application de bureau » par le navigateur (PKCE, boucle locale) pour les statistiques privées
  donnees.py       chaîne, vidéos récentes, commentaires : par l'API si une clé est saisie, sinon par yt-dlp (public, plus lent)
  analyste.py      les calculs sur les 30 dernières vidéos -> un JSON de faits sourcés
  commentaires.py  les demandes des commentaires, regroupées par thème et comptées
  briefing.py      la chaîne depuis hier, les demandes nouvelles, un concurrent en forme, les rappels, la machine
  verification.py  chaque chiffre cité par Jarvis existe-t-il dans le JSON de faits ?

Le cerveau ne calcule rien : il commente un JSON de faits où chaque nombre a sa source, et la vérification compare
sa réponse à ce JSON."""
