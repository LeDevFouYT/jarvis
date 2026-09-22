"""Test du rattrapage des paiements (22/09) : personne ne paie dans le vide.

    python -m jarvis.tests.passerelle_rattrapage

Le webhook Stripe frappe à la seconde du paiement, et il frappe sur la machine qui héberge le service. Si elle est éteinte —
c'est arrivé le 22/09 à 20 h 02 — le client paie 5 €, aucun compte n'est créé, aucun jeton n'est montré, et sa
page de merci est injoignable. Le rattrapage relit les paiements récents chez Stripe au démarrage et crédite
ceux qui manquent.

Ce test joue un faux Stripe (aucun appel réseau) et une base neuve, puis vérifie :
1. un paiement raté pendant l'extinction est bien rattrapé, avec le bon crédit ;
2. le rattrapage repassé deux fois ne crédite pas deux fois (idempotence par référence) ;
3. un paiement déjà encaissé par le webhook n'est pas recrédité ;
4. une session non payée, un don, ou un produit étranger au cloud ne créditent rien ;
5. Stripe injoignable ne fait pas tomber le démarrage.
"""
import json
import sys
import tempfile
from pathlib import Path

from ._commun import Verifs

RACINE = Path(__file__).resolve().parents[2]


class FausseReponse:
    def __init__(self, donnees, code=200):
        self._d, self.status_code = donnees, code

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._d


def session(identifiant, euros, produit="cloud", email="client@exemple.fr", paye=True, devise="eur"):
    return {"id": identifiant, "payment_status": "paid" if paye else "unpaid", "status": "complete",
            "amount_total": int(euros * 100), "currency": devise, "metadata": {"jarvis": produit},
            "customer_details": {"email": email}}


def charger_passerelle(base: Path):
    """Charge la passerelle sur une base NEUVE.

    `db()` ouvre `BASE`, une variable du module, relue à chaque appel : on la remplace juste après l'import et
    tout le test travaille sur le fichier temporaire. Sans cette ligne, le test écrit dans la base de production —
    c'est arrivé le 22/09, deux faux clients se sont retrouvés à côté du vrai.
    """
    import importlib
    sys.path.insert(0, str(RACINE))
    module = importlib.import_module("passerelle.serveur")
    module.BASE = base
    with module.db() as c:                      # le schéma est créé à la première connexion
        c.execute("SELECT 1")
    return module


def main() -> int:
    v = Verifs("Passerelle · le rattrapage des paiements")
    dossier = Path(tempfile.mkdtemp(prefix="jarvis_rattrapage_"))
    base = dossier / "passerelle.sqlite"
    vraie = RACINE / "passerelle" / "passerelle.sqlite"
    avant = vraie.stat().st_mtime if vraie.exists() else 0
    try:
        P = charger_passerelle(base)
    except Exception as e:
        v.ok(False, "la passerelle se charge", f"{type(e).__name__} : {e}")
        return v.fin()

    v.ok(hasattr(P, "rattraper"), "le rattrapage existe")
    if not hasattr(P, "rattraper"):
        return v.fin()
    P.STRIPE_CLE = P.STRIPE_CLE or "sk_test_faux"

    sessions = [session("cs_nuit", 5.0), session("cs_don", 3.0, produit="don"),
                session("cs_impaye", 5.0, paye=False), session("cs_autre", 9.0, produit="kutavo"),
                session("cs_devise", 5.0, devise="usd")]
    appels = []

    class FauxHttpx:
        @staticmethod
        def get(url, **k):
            appels.append(url)
            return FausseReponse({"data": sessions})

    vrai_httpx = P.httpx
    P.httpx = FauxHttpx
    try:
        r = P.rattraper(72)
        v.ok(r["rattrapes"] == 1, "le paiement raté pendant l'extinction est rattrapé, lui seul", r)
        with P.db() as c:
            client = c.execute("SELECT * FROM clients WHERE email = 'client@exemple.fr'").fetchone()
        v.ok(client is not None, "le compte du client est créé")
        minutes = round(client["credit_secondes"] / 60) if client else 0
        attendu = round(P.euros_vers_secondes(5.0) / 60)
        v.ok(minutes == attendu, f"il est crédité de ce qu'il a payé ({attendu} min)", f"{minutes} min")
        v.ok(bool(client and str(client["jeton"]).startswith("jc_")), "il a un jeton utilisable",
             (client["jeton"][:6] + "…") if client else "—")

        r2 = P.rattraper(72)
        v.ok(r2["rattrapes"] == 0, "repassé une deuxième fois, il ne crédite rien de plus", r2)
        with P.db() as c:
            encore = c.execute("SELECT credit_secondes FROM clients WHERE email = 'client@exemple.fr'").fetchone()[0]
        v.ok(round(encore / 60) == attendu, "le crédit n'a pas doublé", f"{round(encore / 60)} min")

        # ce que le webhook a déjà encaissé ne repasse pas non plus
        P._crediter_session_stripe(session("cs_webhook", 10.0, email="autre@exemple.fr"))
        sessions.append(session("cs_webhook", 10.0, email="autre@exemple.fr"))
        r3 = P.rattraper(72)
        v.ok(r3["rattrapes"] == 0, "un paiement déjà encaissé par le webhook n'est pas recrédité", r3)

        with P.db() as c:
            autres = c.execute("SELECT COUNT(*) FROM clients WHERE email NOT IN "
                               "('client@exemple.fr', 'autre@exemple.fr')").fetchone()[0]
        v.ok(autres == 0, "ni le don, ni l'impayé, ni un produit étranger ne créent de compte", f"{autres} en trop")

        class HttpxCasse:
            @staticmethod
            def get(*a, **k):
                raise ConnectionError("Stripe injoignable")

        P.httpx = HttpxCasse
        r4 = P.rattraper(72)
        v.ok(r4["rattrapes"] == 0 and "raison" in r4, "Stripe injoignable : il le dit et ne tombe pas", r4)
    finally:
        P.httpx = vrai_httpx

    # le rattrapage est bien branché au démarrage
    code = (RACINE / "passerelle" / "serveur.py").read_text(encoding="utf-8")
    bloc = code[code.index("def _au_demarrage("):code.index("def _au_demarrage(") + 420]
    v.ok("rattraper" in bloc, "il est lancé au démarrage de la passerelle")
    v.ok("/rattrapage" in code and "SECRET_ADMIN" in code, "et disponible à la demande, réservé à l'administrateur")
    # le test doit rester dans son bac à sable : la base de production ne doit pas avoir bougé d'un octet
    apres = vraie.stat().st_mtime if vraie.exists() else 0
    v.ok(apres == avant, "la base de production n'a pas été touchée par le test",
         "intacte" if apres == avant else "MODIFIÉE — à nettoyer")
    return v.fin()


if __name__ == "__main__":
    sys.exit(main())
