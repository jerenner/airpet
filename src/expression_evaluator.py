import math
import asteval

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
        'mm': 1.0, 'cm': 10.0, 'm': 1000.0,
        'rad': 1.0, 'deg': math.pi / 180.0,
        'degree': math.pi / 180.0
    })
    
    return aeval

class ExpressionEvaluator:
    """A centralized, safe expression evaluator using asteval."""

    def __init__(self):
        """Initializes the evaluator using the central factory."""
        # This creates our own instance of a configured interpreter
        self.interpreter = create_configured_asteval()

    def evaluate(self, expression, project_defines=None):
        """
        Safely evaluates an expression string with optional context from project defines.

        Args:
            expression (str): The string expression to evaluate.
            project_defines (dict, optional): A dictionary of defines from the current project state.

        Returns:
            tuple: A tuple containing (bool, result).
                   - If successful: (True, evaluated_value)
                   - If failed: (False, error_message_string)
        """
        # We don't need to create a temporary symbol table from scratch.
        # We will add the project defines to our interpreter's existing symbol table.
        # To ensure thread safety and no state leakage, we'll save and restore the state.
        
        # Save original state of symbols that might be overwritten
        saved_symbols = {}
        if project_defines:
            for name, define_data in project_defines.items():
                if define_data and define_data.get('value') is not None:
                     if name in self.interpreter.symtable:
                         saved_symbols[name] = self.interpreter.symtable[name]
                     self.interpreter.symtable[name] = define_data['value']
        
        try:
            # Call the eval method on our configured interpreter instance
            result = self.interpreter.eval(expression, show_errors=False, raise_errors=True)
            return True, result
        except Exception as e:
            # asteval exceptions are descriptive and safe to show the user.
            return False, str(e)
        finally:
            # Clean up: remove the temporary project defines and restore any originals
            if project_defines:
                for name in project_defines:
                    if name in saved_symbols:
                        self.interpreter.symtable[name] = saved_symbols[name]
                    elif name in self.interpreter.symtable:
                        # Don't let defines from one call leak into the next
                        del self.interpreter.symtable[name]