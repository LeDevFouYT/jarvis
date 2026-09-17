"""Outil calculer : arithmétique exacte sans eval."""
import ast
import operator

NOM = "calculer"
DESCRIPTION = "Calcule une expression arithmétique exacte (+ - * / puissance, parenthèses)."
PARAMETRES = {"expression": {"type": "string", "description": "ex. 17*23 ou (3+4)/2"}}
REQUIS = ["expression"]

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.FloorDiv: operator.floordiv}


def _evaluer(noeud):
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
        return noeud.value
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in _OPS:
        return _OPS[type(noeud.op)](_evaluer(noeud.left), _evaluer(noeud.right))
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in _OPS:
        return _OPS[type(noeud.op)](_evaluer(noeud.operand))
    raise ValueError("expression non autorisée")


def executer(expression: str) -> str:
    expr = expression.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".")
    resultat = _evaluer(ast.parse(expr, mode="eval").body)
    if isinstance(resultat, float) and resultat.is_integer():
        resultat = int(resultat)
    return f"{expression} = {resultat}"
