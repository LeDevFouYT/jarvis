"""Test manuel de la vision : python -m jarvis.tests.vision [question]
Décharge le cerveau, capture l'écran, le décrit avec gemma3, recharge le cerveau. Affiche les durées."""
import sys

from .. import vision
from ..cerveau import CERVEAU

if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Que voit-on à l'écran ?"
    print(f"Cerveau chargé en {CERVEAU.charger():.1f} s. Modèles en VRAM : {CERVEAU.modeles_charges()}")
    chrono = {}
    description = vision.decrire_ecran(question, chrono)
    print(f"\nQuestion : {question}\nVision   : {description}\n")
    for etape, duree in chrono.items():
        print(f"  {etape:24s} {duree:6.2f} s")
    print(f"\nModèles en VRAM après le cycle : {CERVEAU.modeles_charges()}")
