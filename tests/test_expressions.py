import pytest
from src.expression_evaluator import ExpressionEvaluator

def test_basic_math():
    evaluator = ExpressionEvaluator()
    success, result = evaluator.evaluate("2 + 2")
    assert success
    assert result == 4

def test_math_functions():
    evaluator = ExpressionEvaluator()
    success, result = evaluator.evaluate("sin(pi/2)")
    assert success
    assert abs(result - 1.0) < 1e-9

def test_custom_symbols():
    evaluator = ExpressionEvaluator()
    evaluator.add_symbol("radius", 50)
    success, result = evaluator.evaluate("radius * 2")
    assert success
    assert result == 100

def test_gdml_indexing():
    evaluator = ExpressionEvaluator()
    # GDML uses 1-based indexing in strings like "matrix[1,2]"
    # Our evaluator maps this to "matrix_0_1" in the symtable
    evaluator.add_symbol("m_0_1", 42)
    evaluator.add_symbol("i", 1)
    evaluator.add_symbol("j", 2)
    
    success, result = evaluator.evaluate("m[i,j]")
    assert success
    assert result == 42

def test_error_handling():
    evaluator = ExpressionEvaluator()
    success, result = evaluator.evaluate("undefined_variable", verbose=False)
    assert not success
