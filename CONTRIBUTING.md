# Contribuer à Jarvis

## Un bug, une idée, une question

Ouvrez une [issue](https://github.com/LeDevFouYT/jarvis/issues). Rien à signer. Pour un bug, dites votre version de
Windows, votre carte graphique, et ce que Jarvis a répondu.

Les idées de nouveaux pouvoirs sont les bienvenues : plusieurs fonctions de Jarvis viennent de commentaires YouTube.

## Une proposition de code

1. Lisez [CLA.md](CLA.md) et ajoutez la ligne d'acceptation dans votre pull request. Sans elle, rien ne peut être
   fusionné (voir le fichier pour comprendre pourquoi).
2. Gardez le style du projet : tout en français, noms de variables compris, des commentaires qui expliquent le
   *pourquoi* et non le *quoi*, pas de dépendance nouvelle sans raison sérieuse.
3. Ajoutez ou complétez un test dans `jarvis/tests/`, et lancez la batterie : `python -m jarvis tests`. Un test se
   regarde tourner en direct avec `python -m jarvis.tests.ecran 8767`.
4. Un pouvoir nouveau = un fichier dans `jarvis/outils/`, ajouté à `MODULES` dans `jarvis/outils/__init__.py`.

## Licence

Le code est sous AGPL v3, avec une licence commerciale en option : voir
[LICENCE-COMMERCIALE.md](LICENCE-COMMERCIALE.md).
