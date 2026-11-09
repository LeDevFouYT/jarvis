"""Le pouvoir « trader crypto » (vidéo 4). Argent FICTIF uniquement.

  cours.py         prix, variation, bougies en euros : API publiques Binance, Kraken en repli, sans clé
  portefeuille.py  10 000 € fictifs, frais 0,1 %, ordres confirmés par oui / non
  replay.py        les 10 derniers jours rejoués, qwen3:14b décide toutes les 4 h sans voir le futur
  alertes.py       « préviens-moi si le Bitcoin passe sous… », surveillance toutes les 30 s
  mesures.py       workspace/mesures/crypto.json, pour le montage

Garde-fous : aucune clé, aucun compte, aucun ordre envoyé à une plateforme (seules des requêtes GET publiques partent),
et hors simulation Jarvis donne des faits, jamais un conseil d'achat ou de vente."""

AVERTISSEMENT = "Je ne suis pas conseiller en investissement"
