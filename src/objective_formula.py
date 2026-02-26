from __future__ import annotations

import ast
import math
from typing import Any, Dict

import numpy as np


_ALLOWED_FUNCS = {
    "abs": abs,
    "min": min,
    "max": max,
    "pow": pow,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "tanh": math.tanh,
    "clip": lambda x, lo, hi: float(np.clip(float(x), float(lo), float(hi))),
}


def get_allowed_formula_functions() -> list[str]:
    return sorted(_ALLOWED_FUNCS.keys())


class _FormulaEvaluator(ast.NodeVisitor):
    def __init__(self, variables: Dict[str, Any]):
        self.variables = variables

    def visit_Expression(self, node: ast.Expression) -> float:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, (int, float, bool)):
            return float(node.value)
        raise ValueError("Unsupported constant type in objective formula.")

    def visit_Name(self, node: ast.Name) -> float:
        if node.id in self.variables:
            v = self.variables[node.id]
            if isinstance(v, (int, float, bool)):
                return float(v)
            raise ValueError(f"Variable '{node.id}' is not numeric.")
        raise ValueError(f"Unknown variable '{node.id}' in objective formula.")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        val = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        raise ValueError("Unsupported unary operator in objective formula.")

    def visit_BinOp(self, node: ast.BinOp) -> float:
        left = self.visit(node.left)
        right = self.visit(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left ** right
        if isinstance(node.op, ast.Mod):
            return left % right

        raise ValueError("Unsupported binary operator in objective formula.")

    def visit_Call(self, node: ast.Call) -> float:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function names are allowed in objective formulas.")
        fname = node.func.id
        if fname not in _ALLOWED_FUNCS:
            raise ValueError(f"Function '{fname}' is not allowed in objective formulas.")
        func = _ALLOWED_FUNCS[fname]

        args = [self.visit(a) for a in node.args]
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed in objective formulas.")

        try:
            return float(func(*args))
        except Exception as e:
            raise ValueError(f"Failed evaluating function '{fname}': {e}") from e

    def generic_visit(self, node):
        raise ValueError(f"Unsupported expression element '{type(node).__name__}' in objective formula.")


def evaluate_objective_formula(expression: str, variables: Dict[str, Any]) -> float:
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Objective formula expression is empty.")

    tree = ast.parse(expression, mode="eval")
    evaluator = _FormulaEvaluator(variables=variables)
    value = evaluator.visit(tree)
    return float(value)
