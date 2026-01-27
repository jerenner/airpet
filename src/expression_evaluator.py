import math
import asteval
import re

def create_configured_asteval():
    """
    Factory function to create and configure a new asteval.Interpreter instance.
    This ensures all parts of the application use the same base configuration.
    """
    aeval = asteval.Interpreter(symtable={}, minimal=True, no_if=True, no_for=True, no_while=True, no_try=True)

    # Add safe math functions
    for func_name in ['sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2',
                      'sqrt', 'exp', 'log', 'log10', 'pow', 'abs']:
        if hasattr(math, func_name):
            aeval.symtable[func_name] = getattr(math, func_name)
    
    # Add constants and units
    aeval.symtable.update({
        'pi': math.pi, 'PI': math.pi,
        'nm': 1.0e-6, 'um': 1.0e-3, 'mm': 1.0, 'cm': 10.0, 'm': 1000.0, 'km': 1.0e6,
        'mm2': 1.0, 'cm2': 100.0, 'm2': 1000000.0,
        'mm3': 1.0, 'cm3': 1000.0, 'm3': 1000000000.0,
        'urad': 1.0e-6, 'mrad': 1.0e-3, 'rad': 1.0, 'radian': 1.0, 
        'deg': math.pi / 180.0, 'degree': math.pi / 180.0,
        'eV': 1.0e-3, 'keV': 1.0, 'MeV': 1000.0,
        'g': 1.0, 'kg': 1000.0,
        'ns': 1.0e-9, 'us': 1.0e-6, 'ms': 1.0e-3, 's': 1.0
    })
    
    return aeval

class ExpressionEvaluator:
    """A centralized, stateful expression evaluator using asteval."""
    def __init__(self):
        self.interpreter = create_configured_asteval()

    def clear_symbols(self):
        """Resets the symbol table to its initial state."""
        self.interpreter = create_configured_asteval()

    def add_symbol(self, name, value):
        """Adds a single variable or value to the symbol table."""
        self.interpreter.symtable[name] = value

    def get_symbol(self, name, default_val):
        """Gets a symbol from the symbol table, returning default_val if it does not exist"""
        return self.interpreter.symtable.get(name,default_val)
    
    def _preprocess_gdml_indexing(self, expression):
        """
        Converts GDML-style array indexing like 'm[i,j]' into 'm_i_j'.
        It uses the currently loaded symbol table to evaluate the indices.
        """
        pattern = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)(\[([^\]]+)\])')
        
        processed_expression = expression
        # Loop to handle potentially nested expressions in indices
        for _ in range(5):
            match = pattern.search(processed_expression)
            if not match:
                break

            var_name, _, indices_str = match.groups()
            
            # The indices can be comma-separated expressions themselves
            indices = indices_str.split(',')
            
            try:
                evaluated_indices = []
                for index_expr in indices:
                    # Evaluate the index using the current state of the interpreter
                    value = self.interpreter.eval(index_expr.strip())
                    # GDML is 1-based, our flattened names are 0-based.
                    evaluated_indices.append(str(int(value) - 1))
                
                transformed_var = f"{var_name}_{'_'.join(evaluated_indices)}"
                processed_expression = processed_expression.replace(match.group(0), transformed_var, 1)

            except Exception as e:
                # If an index can't be evaluated (e.g., uses a variable not yet defined),
                # stop processing this expression and let the main evaluation handle the error.
                return expression # Return the original string on failure

        return processed_expression

    def evaluate(self, expression, verbose=True):
        """
        Safely evaluates an expression string using the current symbol table.
        The symbol table should be prepared beforehand by ProjectManager.
        """
        if not isinstance(expression, str):
            return True, expression # It's already a number
            
        try:
            # First, process GDML-style array indexing
            processed_expression = self._preprocess_gdml_indexing(expression)
            
            # Then, evaluate the final processed string
            result = self.interpreter.eval(processed_expression, show_errors=False, raise_errors=True)
            return True, result
        except Exception as e:
            if verbose:
                print(f"ERROR: {str(e)}")
            return False, 0