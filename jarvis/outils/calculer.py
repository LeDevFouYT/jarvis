"""Outil calculer : arithmétique exacte sans eval.

Audit du 19/09 : « 9 puissance 9 puissance 9 » calculait un entier de 370 millions de chiffres. Le calcul bloque tous
les fils de Python, donc micro, voix et HUD figés plusieurs minutes, et le délai de l'outil ne pouvait pas le couper.
Une puissance dont le résultat dépasserait MAX_CHIFFRES chiffres est estimée par les logarithmes, sans être calculée."""
import ast
import math
import operator

NOM = "calculer"
DESCRIPTION = "Calcule une expression arithmétique exacte (+ - * / puissance, parenthèses)."
PARAMETRES = {"expression": {"type": "string", "description": "ex. 17*23 ou (3+4)/2"}}
REQUIS = ["expression"]

MAX_CHIFFRES = 1000          # au-delà, un résultat entier n'a de toute façon aucun sens à l'oral

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.FloorDiv: operator.floordiv}


class TropGrand(Exception):
    def __init__(self, chiffres: float):
        super().__init__(chiffres)
        self.chiffres = chiffres          # nombre de chiffres, estimé (log10 du résultat)


def _chiffres(n) -> float:
    return math.log10(abs(n)) if n else 0.0


def _puissance(base, exposant):
    if abs(base) > 1 and exposant > 0:
        estime = exposant * _chiffres(base)
        if estime > MAX_CHIFFRES:
            raise TropGrand(estime)
    return operator.pow(base, exposant)


def _evaluer(noeud):
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
        return noeud.value
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in _OPS:
        gauche, droite = _evaluer(noeud.left), _evaluer(noeud.right)
        if isinstance(noeud.op, ast.Pow):
            resultat = _puissance(gauche, droite)
        else:
            resultat = _OPS[type(noeud.op)](gauche, droite)
        if isinstance(resultat, int) and resultat.bit_length() > MAX_CHIFFRES * 3.33:
            raise TropGrand(_chiffres(resultat))
        return resultat
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in _OPS:
        return _OPS[type(noeud.op)](_evaluer(noeud.operand))
    raise ValueError("expression non autorisée")


def _hauteur_puissance(noeud) -> float | None:
    """log10 d'une tour de puissances trop grande pour être calculée (9**9**9 : environ 3,7 × 10^8 chiffres)."""
    if isinstance(noeud, ast.BinOp) and isinstance(noeud.op, ast.Pow):
        try:
            base = _evaluer(noeud.left)
        except TropGrand:
            return None
        try:
            exposant = float(_evaluer(noeud.right))
        except TropGrand:
            return float("inf")
        return exposant * _chiffres(base)
    return None


def _milliers(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def executer(expression: str) -> str:
    expr = expression.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".")
    arbre = ast.parse(expr, mode="eval").body
    try:
        resultat = _evaluer(arbre)
    except TropGrand as e:
        exact = _hauteur_puissance(arbre)
        if exact == float("inf"):
            return f"{expression} : un nombre si grand que même son nombre de chiffres ne tient pas dans un calcul."
        if exact is None:          # une partie du calcul dépasse déjà la limite : on ne connaît qu'un minimum
            return f"{expression} : un nombre de plus de {_milliers(int(e.chiffres) + 1)} chiffres, trop long pour être écrit."
        return (f"{expression} : environ 10 puissance {_milliers(int(exact))}, "
                f"un nombre de {_milliers(int(exact) + 1)} chiffres, trop long pour être écrit.")
    except OverflowError:
        return f"{expression} : le résultat dépasse ce que je sais représenter."
    if isinstance(resultat, float) and resultat.is_integer():
        resultat = int(resultat)
    return f"{expression} = {resultat}"
