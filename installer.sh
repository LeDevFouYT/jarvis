#!/usr/bin/env bash
# Installation de Jarvis sous Linux (Ubuntu 22.04 / 24.04 et dérivées). L'équivalent d'installer.bat.
# Sans sudo pour Jarvis lui-même ; les paquets système (une fois) et Ollama sont indiqués s'ils manquent.
set -e
cd "$(dirname "$0")"
echo "[Jarvis] Installation dans $PWD"

# 1. Ce que le système doit fournir : Python 3.12 + venv, le son (PortAudio pour le micro), xdg-open, pactl
manque=()
command -v python3.12 >/dev/null || manque+=(python3.12 python3.12-venv)
ldconfig -p 2>/dev/null | grep -q libportaudio || manque+=(libportaudio2)
command -v xdg-open >/dev/null || manque+=(xdg-utils)
command -v pactl >/dev/null || manque+=(pulseaudio-utils)
command -v espeak-ng >/dev/null || manque+=(espeak-ng)
if [ ${#manque[@]} -gt 0 ]; then
    echo "[Jarvis] Il manque des paquets système. Lancez une fois, puis relancez ce script :"
    echo "    sudo apt install ${manque[*]}"
    exit 1
fi

# 2. Le venv et les dépendances (pycaw, propre à Windows, est ignoré tout seul)
[ -x .venv/bin/python ] || python3.12 -m venv .venv
echo "[Jarvis] Installation des dépendances (quelques minutes la première fois)..."
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt

# 3. Les fichiers de configuration
[ -f config.json ] || { cp config.example.json config.json; echo "[Jarvis] config.json créé"; }
[ -f .secrets ] || { cp .secrets.example .secrets; echo "[Jarvis] .secrets créé"; }

# 4. Ollama (le cerveau) : son installateur officiel demande sudo, on ne le lance pas à votre place
if ! command -v ollama >/dev/null; then
    echo "[Jarvis] Ollama n'est pas installé. Une fois : curl -fsSL https://ollama.com/install.sh | sh"
fi

# 5. La carte graphique et le choix des modèles
.venv/bin/python -m jarvis installer
chmod +x lancer.sh
echo "[Jarvis] Prêt. Lancez ./lancer.sh"
