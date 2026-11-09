#!/usr/bin/env bash
# Lance Jarvis sous Linux : l'équivalent de lancer.bat.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "[Jarvis] Pas de .venv : lancez ./installer.sh une fois."
    exit 1
fi
# faster-whisper sur la carte : les bibliothèques CUDA des paquets pip nvidia-* doivent être trouvables AVANT le
# démarrage du processus (sous Windows, oreilles.py les précharge lui-même ; sous Linux, c'est LD_LIBRARY_PATH)
NV=$(.venv/bin/python -c "import os, nvidia.cublas.lib, nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ':' + os.path.dirname(nvidia.cudnn.lib.__file__))" 2>/dev/null)
[ -n "$NV" ] && export LD_LIBRARY_PATH="$NV${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Ollama qui tourne, modèles présents (téléchargés sinon), voix Kokoro présente
.venv/bin/python -m jarvis verifier || { echo "[Jarvis] La vérification a échoué, voir ci-dessus."; exit 1; }
echo "[Jarvis] Démarrage du serveur..."
exec .venv/bin/python -m jarvis
