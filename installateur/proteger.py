"""Compile le paquet jarvis de la charge utile en bytecode (.pyc à côté, sans les .py) avant de construire l'exe.
Le client installé n'a plus les sources en clair : `python -m jarvis` charge les .pyc (Python 3.12, le même que le
Python embarqué). Ce n'est pas un chiffrement, un outil de décompilation le relit, mais ce n'est plus lisible
en ouvrant un fichier. Le HUD (index.html) reste en clair : c'est du HTML, il est de toute façon dans le navigateur."""
import compileall
import sys
from pathlib import Path

charge = Path(sys.argv[1] if len(sys.argv) > 1 else "installateur/charge") / "jarvis"
if not charge.exists():
    raise SystemExit(f"charge introuvable : {charge}")
if sys.version_info[:2] != (3, 12):
    raise SystemExit("la charge doit être compilée avec Python 3.12, celui du Python embarqué")
ok = compileall.compile_dir(str(charge), quiet=1, legacy=True, optimize=0, force=True)
if not ok:
    raise SystemExit("compilation échouée")
n = 0
for py in charge.rglob("*.py"):
    if py.with_suffix(".pyc").exists():
        py.unlink()
        n += 1
for cache in charge.rglob("__pycache__"):
    for f in cache.iterdir():
        f.unlink()
    cache.rmdir()
print(f"{n} fichiers .py remplacés par leur .pyc dans {charge}")
