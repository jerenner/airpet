"""
Tests for AI optimization tools integration.
Tests parameter registry, param studies, and optimizer dispatch.
"""

import tempfile
import unittest
import sys
import os

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


class TestParameterRegistry(unittest.TestCase):
    """Test parameter registry functionality."""

    def test_create_parameter_registry_entry(self):
        """Test creating a parameter registry entry."""
        pm = _make_pm()

        # Add a simple define
        obj, err = pm.add_define("silicon_thickness", "constant", "0.5", "mm", "geometry")
        self.assertIsNone(err)

        # Register the parameter
        entry = {
            'target_type': 'define',
            'target_ref': {
                'name': 'silicon_thickness'
            },
            'bounds': {
                'min': 0.1,
                'max': 2.0
            },
            'default': 0.5,
            'units': 'mm',
            'enabled': True
        }

        result, err = pm.upsert_parameter_registry_entry("silicon_thickness_param", entry)
        self.assertIsNone(err)
        self.assertEqual(result['name'], "silicon_thickness_param")
        self.assertEqual(result['target_type'], 'define')
        self.assertEqual(result['bounds']['min'], 0.1)
        self.assertEqual(result['bounds']['max'], 2.0)

    def test_delete_parameter_registry_entry(self):
        """Test deleting a parameter registry entry."""
        pm = _make_pm()

        obj, err = pm.add_define("test_param", "constant", "1.0", "mm", "geometry")
        self.assertIsNone(err)

        entry = {
            'target_type': 'define',
            'target_ref': {'name': 'test_param'},
            'bounds': {'min': 0.0, 'max': 10.0},
            'default': 1.0,
            'enabled': True
        }

        # Create entry
        pm.upsert_parameter_registry_entry("test_reg", entry)

        # Delete entry
        success, err = pm.delete_parameter_registry_entry("test_reg")
        self.assertTrue(success)
        self.assertIsNone(err)

        # Verify it's gone
        self.assertNotIn("test_reg", pm.current_geometry_state.parameter_registry)


class TestParameterStudy(unittest.TestCase):
    """Test parameter study functionality."""

    def test_setup_grid_param_study(self):
        """Test creating a grid parameter study."""
        pm = _make_pm()

        # Register a parameter first
        obj, err = pm.add_define("detector_thickness", "constant", "1.0", "mm", "geometry")
        self.assertIsNone(err)
        pm.upsert_parameter_registry_entry("thickness_param", {
            'target_type': 'define',
            'target_ref': {'name': 'detector_thickness'},
            'bounds': {'min': 0.5, 'max': 5.0},
            'default': 1.0,
            'enabled': True
        })

        # Create study
        config = {
            'mode': 'grid',
            'parameters': ['thickness_param'],
            'objectives': [
                {
                    'metric': 'success_flag',
                    'name': 'energy_deposit',
                    'direction': 'maximize'
                }
            ],
            'grid': {
                'per_parameter_steps': 5
            }
        }

        result, err = pm.upsert_param_study("thickness_study", config)
        self.assertIsNone(err)
        self.assertEqual(result['name'], "thickness_study")
        self.assertEqual(result['mode'], 'grid')
        self.assertIn('thickness_param', result['parameters'])

    def test_setup_random_param_study(self):
        """Test creating a random parameter study."""
        pm = _make_pm()

        obj, err = pm.add_define("source_energy", "constant", "300.0", "keV", "geometry")
        self.assertIsNone(err)
        pm.upsert_parameter_registry_entry("energy_param", {
            'target_type': 'define',
            'target_ref': {'name': 'source_energy'},
            'bounds': {'min': 100.0, 'max': 1000.0},
            'default': 300.0,
            'enabled': True
        })

        config = {
            'mode': 'random',
            'parameters': ['energy_param'],
            'objectives': [
                {
                    'metric': 'success_flag',
                    'name': 'efficiency',
                    'direction': 'maximize'
                }
            ],
            'random': {
                'samples': 20,
                'seed': 42
            }
        }

        result, err = pm.upsert_param_study("energy_study", config)
        self.assertIsNone(err)
        self.assertEqual(result['mode'], 'random')


class TestOptimizer(unittest.TestCase):
    """Test optimizer functionality."""

    def test_list_optimizer_runs_empty(self):
        """Test listing optimizer runs when none exist."""
        pm = _make_pm()

        runs = pm.list_optimizer_runs()
        self.assertEqual(runs, [])

    def test_random_search_optimizer(self):
        """Test random search optimizer with simple evaluator."""
        pm = _make_pm()

        # Create a simple parameter
        obj, err = pm.add_define("x_param", "constant", "0.5", "", "geometry")
        self.assertIsNone(err)
        entry, err = pm.upsert_parameter_registry_entry("x", {
            'target_type': 'define',
            'target_ref': {'name': 'x_param'},
            'bounds': {'min': 0.0, 'max': 1.0},
            'default': 0.5,
            'enabled': True
        })
        self.assertIsNone(err)

        # Create study
        config = {
            'mode': 'random',
            'parameters': ['x'],
            'objectives': [{'metric': 'success_flag', 'name': 'score', 'direction': 'maximize'}],
            'random': {'samples': 10}
        }
        study, err = pm.upsert_param_study("simple_study", config)
        self.assertIsNone(err)

        # Run optimizer with small budget
        result, err = pm.run_param_optimizer(
            study_name="simple_study",
            method="random_search",
            budget=5,
            seed=42
        )

        self.assertIsNone(err)
        self.assertIsNotNone(result)
        self.assertIn('best_run', result)
        self.assertIn('objectives', result['best_run'])
        self.assertEqual(result['best_run']['objectives']['score'], 1.0)


class TestOptimizationTools(unittest.TestCase):
    """Test the AI optimization tool schemas."""

    def test_tool_schemas_valid(self):
        """Test that optimization tool schemas are valid."""
        from src.ai_tools import AI_GEOMETRY_TOOLS

        opt_tool_names = [
            'create_parameter_registry',
            'setup_param_study',
            'run_optimization',
            'apply_best_result',
            'list_optimizer_runs',
            'verify_best_candidate'
        ]

        tool_dict = {t['name']: t for t in AI_GEOMETRY_TOOLS}

        for name in opt_tool_names:
            assert name in tool_dict, f"Tool {name} not found in AI_GEOMETRY_TOOLS"
            tool = tool_dict[name]
            assert 'description' in tool, f"Tool {name} missing description"
            assert 'parameters' in tool, f"Tool {name} missing parameters"
            assert tool['parameters'].get('type') == 'object', f"Tool {name} parameters not object type"

    def test_tool_required_fields(self):
        """Test that optimization tools have required fields defined."""
        from src.ai_tools import AI_GEOMETRY_TOOLS

        tool_dict = {t['name']: t for t in AI_GEOMETRY_TOOLS}

        # Check create_parameter_registry
        tool = tool_dict['create_parameter_registry']
        required = tool['parameters'].get('required', [])
        assert 'param_name' in required
        assert 'target_type' in required
        assert 'target_ref' in required
        assert 'bounds' in required

        # Check setup_param_study
        tool = tool_dict['setup_param_study']
        required = tool['parameters'].get('required', [])
        assert 'study_name' in required
        assert 'mode' in required
        assert 'parameters' in required
        assert 'objectives' in required

        # Check run_optimization
        tool = tool_dict['run_optimization']
        required = tool['parameters'].get('required', [])
        assert 'study_name' in required
        assert 'method' in required
        assert 'budget' in required


if __name__ == "__main__":
    unittest.main(verbosity=2)
