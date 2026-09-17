"""Test manuel du cerveau : python -m jarvis.tests.cerveau
Trois questions dont deux qui exigent un outil. Affiche les outils appelés et les durées."""
import time

from ..cerveau import CERVEAU, MODELE

QUESTIONS = [
    "Bonsoir Jarvis, présentez-vous en une phrase.",
    "Quelle heure est-il ?",
    "Combien font 17 fois 23 ?",
]

if __name__ == "__main__":
    print(f"Cerveau : {MODELE}. Chargement...")
    print(f"  charge en {CERVEAU.charger():.1f} s\n")
    for question in QUESTIONS:
        print(f"Monsieur : {question}")
        t = time.time()
        reponse = CERVEAU.repondre(question, journal=lambda nom, res: print(f"  [outil {nom}] {res}"))
        print(f"Jarvis   : {reponse}   ({time.time() - t:.1f} s)\n")
