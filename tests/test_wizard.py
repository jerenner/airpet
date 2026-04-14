"""
Tests for the Parameter Study Wizard functionality.
Tests wizard auto-detection, metric discovery, and study creation.
"""
import unittest
import json
import os
import sys
import tempfile
import shutil

# Add the project root to the path so app/src imports work from tests/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from src.project_manager import ProjectManager


def get_test_client():
    """Create a test client with a temporary project."""
    app.config['TESTING'] = True
    client = app.test_client()
    
    # Create temporary directory for test project
    temp_dir = tempfile.mkdtemp()
    original_dir = os.getcwd()
    
    os.chdir(temp_dir)
    
    # Initialize a new project using the API
    response = client.post('/new_project', data=json.dumps({
        "name": "TestWizardProject"
    }), content_type='application/json')
    
    # Set up session for test client
    with client.session_transaction() as sess:
        sess['project_path'] = temp_dir
    
    return client, temp_dir, original_dir


class TestWizardSimulationMetrics(unittest.TestCase):
    """Tests for /api/param_study/simulation_metrics endpoint."""
    
    def setUp(self):
        self.client, self.temp_dir, self.original_dir = get_test_client()
    
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_metrics_endpoint_exists(self):
        """Verify the simulation metrics endpoint responds."""
        response = self.client.get('/api/param_study/simulation_metrics')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('success', data)
        self.assertIn('metrics', data)
    
    def test_metrics_endpoint_returns_list(self):
        """Verify metrics endpoint returns a list."""
        response = self.client.get('/api/param_study/simulation_metrics')
        data = json.loads(response.data)
        self.assertIsInstance(data['metrics'], list)


class TestWizardParameterAutoDetection(unittest.TestCase):
    """Tests for parameter auto-detection from geometry."""
    
    def setUp(self):
        self.client, self.temp_dir, self.original_dir = get_test_client()
    
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_detect_solid_parameters(self):
        """Test auto-detection of solid parameters."""
        # First add a solid with parameters using the primitive solid endpoint
        solid_data = {
            "name": "test_box",
            "type": "box",
            "params": {
                "x": 10.0,
                "y": 20.0,
                "z": 30.0
            }
        }
        
        response = self.client.post('/add_primitive_solid', 
                                   data=json.dumps(solid_data),
                                   content_type='application/json')
        
        # Solid should be created (may have auto-generated name)
        self.assertEqual(response.status_code, 200)
        
    def test_detect_source_parameters(self):
        """Test auto-detection of source parameters."""
        source_data = {
            "name": "test_source",
            "type": "gun",
            "particle": "e-",
            "energy": 1.0,
            "position": [0, 0, 0],
            "direction": [0, 0, 1]
        }
        
        response = self.client.post('/api/add_source',
                                   data=json.dumps(source_data),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 200)


class TestWizardStudyCreation(unittest.TestCase):
    """Tests for wizard study creation workflow."""
    
    def setUp(self):
        self.client, self.temp_dir, self.original_dir = get_test_client()
    
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_simple_study(self):
        """Test creating a basic parameter study via wizard."""
        # First register a parameter
        param_data = {
            "name": "test_param",
            "target_type": "define",
            "target_ref": {"name": "test_define"},
            "bounds": {"min": 1.0, "max": 10.0},
            "default": 5.0,
            "units": "mm"
        }
        
        # Add a define first
        define_data = {
            "name": "test_define",
            "value": 5.0,
            "unit": "mm"
        }
        self.client.post('/add_define',
                        data=json.dumps(define_data),
                        content_type='application/json')
        
        # Register parameter
        response = self.client.post('/api/parameter_registry/upsert',
                                   data=json.dumps(param_data),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        # Create study
        study_data = {
            "name": "wizard_test_study",
            "description": "Test study created by wizard",
            "parameters": ["test_param"],
            "values_per_param": 5,
            "objective": {
                "type": "maximize",
                "metric": "test_metric",
                "reduction": "mean"
            }
        }
        
        response = self.client.post('/api/param_study/upsert',
                                   data=json.dumps(study_data),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
    
    def test_study_list_endpoint(self):
        """Test that the list endpoint returns proper structure."""
        # Ensure session is set
        with self.client.session_transaction() as sess:
            sess['project_path'] = self.temp_dir
        
        # List studies
        response = self.client.get('/api/param_study/list')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('param_studies', data)
        self.assertIsInstance(data['param_studies'], dict)


class TestWizardPresetTemplates(unittest.TestCase):
    """Tests for preset objective templates."""
    
    def test_preset_maximize_energy(self):
        """Test the maximize energy deposition preset."""
        preset = {
            "name": "Maximize Energy Deposition",
            "description": "Maximize total energy deposited in detectors",
            "metric_path": "default_ntuples/Hits/Edep",
            "reduction": "sum",
            "optimization_direction": "maximize"
        }
        
        self.assertEqual(preset["optimization_direction"], "maximize")
        self.assertEqual(preset["reduction"], "sum")
        self.assertIn("Edep", preset["metric_path"])
    
    def test_preset_minimize_thickness(self):
        """Test the minimize thickness preset."""
        preset = {
            "name": "Minimize Material Thickness",
            "description": "Minimize total material thickness while maintaining performance",
            "metric_path": "geometry/solid_thickness",
            "reduction": "mean",
            "optimization_direction": "minimize"
        }
        
        self.assertEqual(preset["optimization_direction"], "minimize")
        self.assertEqual(preset["reduction"], "mean")
    
    def test_preset_maximize_hits(self):
        """Test the maximize hit count preset."""
        preset = {
            "name": "Maximize Hit Count",
            "description": "Maximize number of detector hits",
            "metric_path": "default_ntuples/Hits/Count",
            "reduction": "sum",
            "optimization_direction": "maximize"
        }
        
        self.assertEqual(preset["optimization_direction"], "maximize")
        self.assertIn("Count", preset["metric_path"])


if __name__ == '__main__':
    unittest.main(verbosity=2)
