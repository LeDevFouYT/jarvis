"""Le portefeuille FICTIF (consigne 3) : 10 000 € de départ, gardés dans workspace/portefeuille.json.

Aucun compte, aucune plateforme : un ordre ne fait que modifier ce fichier, au prix réel du moment (cours.prix) et
avec 0,1 % de frais. Le même calcul sert au replay (`Livre`, sans fichier) : mêmes frais en simulation qu'en vrai.
Chaque ordre est gardé dans le journal du fichier, avec son prix, ses frais et l'heure."""
import json
import threading
import time

from ..config import RACINE

FICHIER = RACINE / "workspace" / "portefeuille.json"
CAPITAL = 10_000.0
FRAIS = 0.001                       # 0,1 % par ordre
MINIMUM_EUR = 1.0
_verrou = threading.Lock()


class OrdreImpossible(ValueError):
    pass


class Livre:
    """Des euros, des quantités de crypto, un journal. Aucun accès au réseau ni au disque : le replay s'en sert tel quel."""

    def __init__(self, euros: float = CAPITAL, positions: dict | None = None, journal: list | None = None, depart: float = CAPITAL):
        self.euros, self.positions, self.journal, self.depart = float(euros), dict(positions or {}), list(journal or []), depart

    def acheter(self, symbole: str, montant_eur: float, prix: float, quand: float | None = None, raison: str = "") -> dict:
        montant_eur = min(float(montant_eur), self.euros)
        if montant_eur < MINIMUM_EUR:
            raise OrdreImpossible(f"il ne reste que {self.euros:.2f} € disponibles" if self.euros < MINIMUM_EUR else "montant trop petit")
        if prix <= 0:
            raise OrdreImpossible("prix invalide")
        frais = montant_eur * FRAIS
        quantite = (montant_eur - frais) / prix
        self.euros -= montant_eur
        self.positions[symbole] = self.positions.get(symbole, 0.0) + quantite
        return self._noter("achat", symbole, quantite, prix, montant_eur, frais, quand, raison)

    def vendre(self, symbole: str, prix: float, fraction: float | None = None, montant_eur: float | None = None,
               quand: float | None = None, raison: str = "") -> dict:
        detenu = self.positions.get(symbole, 0.0)
        if detenu <= 0:
            raise OrdreImpossible("aucune position")
        if montant_eur is not None:
            quantite = min(detenu, float(montant_eur) / prix)
        else:
            quantite = detenu * max(0.0, min(1.0, float(fraction if fraction is not None else 1.0)))
        brut = quantite * prix
        if brut < MINIMUM_EUR:
            raise OrdreImpossible("montant trop petit")
        frais = brut * FRAIS
        self.positions[symbole] = detenu - quantite
        if self.positions[symbole] * prix < 0.01:          # poussière : la position est soldée
            del self.positions[symbole]
        self.euros += brut - frais
        return self._noter("vente", symbole, quantite, prix, brut, frais, quand, raison)

    def _noter(self, sens, symbole, quantite, prix, montant, frais, quand, raison) -> dict:
        ordre = {"n": len(self.journal) + 1, "quand": quand or time.time(), "sens": sens, "symbole": symbole,
                 "quantite": quantite, "prix": prix, "montant_eur": round(montant, 2), "frais_eur": round(frais, 4),
                 "euros_apres": round(self.euros, 2)}
        if raison:
            ordre["raison"] = raison
        self.journal.append(ordre)
        return ordre

    def valeur(self, prix: dict[str, float]) -> float:
        return self.euros + sum(q * prix.get(s, 0.0) for s, q in self.positions.items())

    def detail(self, prix: dict[str, float]) -> dict:
        lignes = sorted(({"symbole": s, "quantite": q, "prix": prix.get(s, 0.0), "valeur": q * prix.get(s, 0.0)}
                         for s, q in self.positions.items()), key=lambda x: -x["valeur"])
        total = self.valeur(prix)
        return {"euros": self.euros, "positions": lignes, "valeur": total, "depart": self.depart,
                "gain": total - self.depart, "gain_pct": (total / self.depart - 1) * 100,
                "frais_payes": sum(o["frais_eur"] for o in self.journal), "ordres": len(self.journal)}


def charger() -> Livre:
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        return Livre(d["euros"], d.get("positions"), d.get("journal"), d.get("depart", CAPITAL))
    except Exception:
        return Livre()


def sauver(livre: Livre, cree: float | None = None):
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    try:
        ancien = json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        ancien = {}
    donnees = {"_lisez_moi": "Portefeuille FICTIF de Jarvis : aucun argent réel, aucun compte, aucune plateforme.",
               "depart": livre.depart, "euros": livre.euros, "positions": livre.positions, "journal": livre.journal,
               "cree": cree or ancien.get("cree") or time.time(), "frais": FRAIS}
    temporaire = FICHIER.with_suffix(".tmp")
    temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    temporaire.replace(FICHIER)


def remettre_a_zero() -> Livre:
    with _verrou:
        livre = Livre()
        sauver(livre, cree=time.time())
        return livre


def executer_ordre(sens: str, symbole: str, prix: float, montant_eur: float | None = None, fraction: float | None = None) -> tuple[dict, Livre]:
    """Lit le fichier, passe l'ordre, réécrit : sous verrou, pour qu'aucun ordre ne se perde."""
    with _verrou:
        livre = charger()
        if sens == "achat":
            ordre = livre.acheter(symbole, montant_eur, prix)
        else:
            ordre = livre.vendre(symbole, prix, fraction=fraction, montant_eur=montant_eur)
        sauver(livre)
        return ordre, livre
