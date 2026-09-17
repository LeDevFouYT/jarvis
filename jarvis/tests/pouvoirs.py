"""Tous les tests des pouvoirs 02 à 13, un par pouvoir, chacun dans son propre processus :
  python -m jarvis.tests.pouvoirs              tous (la réponse éclair en dernier, la plus longue)
  python -m jarvis.tests.pouvoirs rangement    un seul
Arrêter le Jarvis lancé avant : les tests utilisent la même carte graphique et le même modèle."""
import subprocess
import sys
import time

TESTS = [
    ("02", "memoire_longue", "mémoire longue"),
    ("03", "conversation_continue", "conversation continue"),
    ("04", "interruption", "interruption"),
    ("06", "personnalites", "personnalités"),
    ("07", "langues", "langues"),
    ("09", "fenetres", "fenêtres"),
    ("10", "rangement", "rangement"),
    ("11", "dictee", "dictée et presse-papiers"),
    ("12", "sentinelle", "sentinelle"),
    ("01", "ordres", "il obéit (question entière, outil appelé)"),
    ("13", "telegram_entrant", "le téléphone"),
    ("14-16", "voir_et_creer", "il voit et il crée (webcam, vidéo, miniatures)"),
    ("17-19", "youtube", "il gère la chaîne (analyste, commentaires, briefing, vérification)"),
    ("05", "eclair", "réponse éclair"),
]


def main():
    choisis = sys.argv[1:]
    bilan = []
    for numero, module, nom in TESTS:
        if choisis and module not in choisis:
            continue
        t = time.time()
        args = [sys.executable, "-X", "utf8", "-m", f"jarvis.tests.{module}"] + (["apres", "2"] if module == "eclair" else [])
        code = subprocess.call(args)
        bilan.append((numero, nom, code, time.time() - t))
    print("\n=== Bilan des pouvoirs ===")
    for numero, nom, code, duree in bilan:
        print(f"  {'✓' if code == 0 else '✗'} pouvoir {numero} · {nom:<26} {duree:5.0f} s")
    sys.exit(0 if all(code == 0 for _, _, code, _ in bilan) else 1)


if __name__ == "__main__":
    main()
