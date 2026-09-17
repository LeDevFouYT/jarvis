"""Point d'entrée.
  python -m jarvis                 démarre le serveur (HUD + API + oreilles + voix) et ouvre le navigateur
  python -m jarvis verifier        Ollama, modèles et voix présents (téléchargés sinon) ; utilisé par lancer.bat
  python -m jarvis installer       détecte la VRAM et choisit les modèles ; utilisé par installer.bat
  python -m jarvis ecouter         test des oreilles en direct : détections et transcriptions
  python -m jarvis ecouter FICHIER rejoue un fichier audio à la place du micro
  python -m jarvis ecouter fixture fabrique (au besoin) puis rejoue « Hey Jarvis » + une question
  python -m jarvis dire "texte"    test de la voix : local puis elevenlabs, lus dans les haut-parleurs
  python -m jarvis cloud           le service cloud tout seul (passerelle + agent + tunnel), sans l'interface
  python -m jarvis cloud installer / desinstaller   le lance avec Windows (dossier Démarrage, sans droits admin)
  python -m jarvis maison          l'agent seul : cette carte graphique sert les clients cloud via la passerelle
  python -m jarvis peripheriques   liste les micros et les sorties audio
  python -m jarvis demo            prépare la démo réelle : vérifie chaque brique pour de vrai, sans lancer Jarvis (DEMO.md)
  python -m jarvis demo_rangement  remet à neuf workspace/demo_rangement (un dossier de fichiers pour essayer le rangement)
  python -m jarvis tests [nom]     les tests des pouvoirs 02 à 19 (arrêter Jarvis avant)"""
import sys

if __name__ == "__main__":
    commande = sys.argv[1] if len(sys.argv) > 1 else "serveur"
    if commande == "demo":
        from .demo import verifier as verifier_demo
        sys.exit(verifier_demo())
    elif commande == "demo_rangement":
        from .outils.ranger import creer_demo
        print("Dossier de démonstration prêt :", creer_demo())
    elif commande == "tests":
        import runpy
        sys.argv = ["pouvoirs"] + sys.argv[2:]
        runpy.run_module("jarvis.tests.pouvoirs", run_name="__main__")
    elif commande == "verifier":
        from .preparation import verifier
        sys.exit(verifier())
    elif commande == "installer":
        from .preparation import installer
        sys.exit(installer())
    elif commande == "ecouter":
        from .tests.oreilles import en_direct
        en_direct(sys.argv[2:])
    elif commande == "dire":
        from .tests.voix import dire
        dire(sys.argv[2:])
    elif commande == "cloud":
        from . import service_cloud
        sous = sys.argv[2] if len(sys.argv) > 2 else ""
        if sous == "installer":
            print("Jarvis Cloud démarrera avec Windows :", service_cloud.installer_demarrage_windows())
        elif sous == "desinstaller":
            print("retiré du démarrage de Windows" if service_cloud.desinstaller_demarrage_windows() else "n'y était pas")
        else:
            service_cloud.boucle_autonome()
    elif commande == "maison":
        import runpy
        runpy.run_module("jarvis.maison", run_name="__main__")
    elif commande == "peripheriques":
        from .tests.oreilles import afficher_peripheriques
        afficher_peripheriques()
        from .voix import lister_sorties
        print("\nSorties audio (index à mettre dans config.json, voix.peripherique_sortie) :")
        for p in lister_sorties():
            print(f"  {'>' if p['defaut'] else ' '} {p['index']:3d}  {p['nom']}  [{p['api']}]")
    else:
        from .serveur import lancer
        lancer()
