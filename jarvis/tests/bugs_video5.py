"""Les bugs de la consigne 7 (vidéo 5) : python -m jarvis.tests.bugs_video5   (Jarvis arrêté ; le cerveau est chargé)

1. Le replay crypto qui expirait à la première décision (journal du 20/10 : « Read timed out », le cerveau se
   chargeait pendant l'appel). On décharge le cerveau, puis on demande UNE vraie décision : elle doit aboutir.
   Et le replay lui-même charge le cerveau avant la première décision (lecture du code).
2. La réécoute qui refaisait trois fois toute phrase en pour cent (« deux pour cent » entendu « 2 % »).
3. Whisper qui invente une phrase sur un souffle : le filtre attrape les classiques, et un vrai souffle ne réveille pas.
Les autres bugs de la consigne ont leur test : le prénom (tests/prenom), les clones qui s'entendent (tests/tournoi)."""
import inspect
import sys
import time

import numpy as np

from ._commun import Verifs

from .. import oreilles  # noqa: E402
from ..cerveau import CERVEAU  # noqa: E402
from ..crypto import replay as R  # noqa: E402
from ..crypto.portefeuille import Livre  # noqa: E402
from ..outils import replay_crypto  # noqa: E402
from ..voix_qwen import reecoute  # noqa: E402


def main() -> int:
    v = Verifs("Les bugs de la vidéo 5 · consigne 7")

    # ------------------------------------------------------------------ 1. le replay crypto
    v.ok("CERVEAU.charger()" in inspect.getsource(replay_crypto._travail).split("jeu.jouer()")[0],
         "le replay charge le cerveau avant la première décision")
    debut, fin = R.fenetre()
    marche = R.Marche.telecharger(debut, fin)
    t0 = debut + 7 * 86400                                    # une décision au milieu de la fenêtre
    vue = marche.vue(t0) if hasattr(marche, "vue") else None
    if vue is None:
        v.info("Marche.vue absente : consigne construite sur les bougies telles quelles")
    consigne = R.consigne_decision(1, t0, vue or {}, Livre(), [])
    CERVEAU.decharger()
    time.sleep(3)
    t = time.time()
    try:
        decision, infos = R._decider_par_cerveau(consigne)
        ok = decision.get("action") in ("acheter", "vendre", "attendre")
    except Exception as e:                                     # noqa: BLE001
        decision, ok = {"erreur": f"{type(e).__name__} : {e}"}, False
    v.ok(ok, f"cerveau déchargé, première décision quand même : « {decision.get('action')} » en {time.time() - t:.0f} s "
             f"(chargement compris)", decision)

    # ------------------------------------------------------------------ 2. la réécoute en pour cent
    v.ok(reecoute.ecarts("Le Bitcoin a perdu deux pour cent depuis ce matin.", "Le Bitcoin a perdu 2 % depuis ce matin.") == []
         and reecoute.ecarts("Il a pris trois pour cent.", "Il a pris 4 %.") != [],
         "réécoute : « deux pour cent » = « 2 % », « trois » entendu « 4 % » reste une faute")

    # ------------------------------------------------------------------ 3. Whisper et le souffle
    v.ok(all(oreilles.est_hallucination(p) for p in ("Sous-titres réalisés par la communauté d'Amara.org", "Merci d'avoir regardé !", "")),
         "les phrases fantômes classiques de Whisper sont filtrées")
    oreilles.prechauffer_whisper()
    hasard = np.random.default_rng(29)
    souffle = (hasard.normal(0, 0.02, 16000 * 2) * np.hanning(16000 * 2)).astype(np.float32)   # deux secondes de souffle
    texte, _ = oreilles.transcrire_detail(souffle)
    v.ok(texte == "", f"deux secondes de souffle : rien n'est livré au cerveau (« {texte} »)")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
