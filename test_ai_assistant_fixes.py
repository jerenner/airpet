"""
Headless tests for AI assistant fixes:
1. NIST material recognition
2. Particle source defaults (particle type, direction mode, energy format)
"""

import sys
import os

# Add the src directory to the path
src_dir = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_dir)

from geometry_types import GeometryState, Material, ParticleSource


def test_nist_material_creation():
    """Test that NIST materials are properly created with mat_type='nist'."""
    print("\n=== Test 1: NIST Material Creation ===")
    
    # Test 1a: Create a NIST material directly
    nist_mat = Material("G4_PLASTIC_SCINTILLATOR", mat_type='nist')
    
    if nist_mat.mat_type != 'nist':
        print(f"FAIL: Expected mat_type='nist', got '{nist_mat.mat_type}'")
        return False
    
    print(f"PASS: NIST material created with mat_type='{nist_mat.mat_type}'")
    
    # Test 1b: Create a standard material
    std_mat = Material("custom_material", mat_type='standard', 
                       Z_expr='6', A_expr='12', density_expr='1.5')
    
    if std_mat.mat_type != 'standard':
        print(f"FAIL: Expected mat_type='standard', got '{std_mat.mat_type}'")
        return False
    
    print(f"PASS: Standard material created with mat_type='{std_mat.mat_type}'")
    
    # Test 1c: Test from_dict with NIST material (no properties)
    nist_dict = {
        'name': 'G4_WATER',
        'mat_type': 'nist',
        'Z_expr': '',
        'A_expr': '',
        'density_expr': '',
        'components': None
    }
    
    nist_from_dict = Material.from_dict(nist_dict)
    if nist_from_dict.mat_type != 'nist':
        print(f"FAIL: Expected mat_type='nist' from dict, got '{nist_from_dict.mat_type}'")
        return False
    
    print(f"PASS: NIST material from_dict with mat_type='{nist_from_dict.mat_type}'")
    
    # Test 1d: Test from_dict with NIST name but no explicit mat_type
    # (should auto-detect as NIST based on name and lack of properties)
    nist_auto_dict = {
        'name': 'G4_AIR',
        'Z_expr': '',
        'A_expr': '',
        'density_expr': '',
        'components': None
    }
    
    nist_auto = Material.from_dict(nist_auto_dict)
    if nist_auto.mat_type != 'nist':
        print(f"FAIL: Expected auto-detection of NIST material, got '{nist_auto.mat_type}'")
        return False
    
    print(f"PASS: NIST material auto-detected from_dict with mat_type='{nist_auto.mat_type}'")
    
    return True


def test_gps_command_normalization():
    """Test GPS command normalization logic."""
    print("\n=== Test 2: GPS Command Normalization ===")
    
    # Import the normalization logic directly
    def normalize_gps_commands(gps_commands):
        """Copy of the normalization logic from project_manager.py"""
        normalized = {}
        
        if gps_commands:
            for key, value in gps_commands.items():
                if isinstance(value, dict):
                    # Convert {"value": 100, "unit": "keV"} to "100 keV"
                    if 'value' in value and 'unit' in value:
                        normalized[key] = f"{value['value']} {value['unit']}"
                    else:
                        normalized[key] = str(value)
                elif value is None:
                    normalized[key] = ""
                else:
                    normalized[key] = str(value)
        
        # Set sensible defaults for missing GPS commands
        # Particle type - default to gamma if not specified
        if 'particle' not in normalized or not normalized.get('particle'):
            normalized['particle'] = 'gamma'
        
        # Direction mode - default to Direction (not Isotropic) if not specified
        if 'ang/type' not in normalized or not normalized.get('ang/type'):
            normalized['ang/type'] = 'Direction'
        
        # Energy format - ensure proper Geant4 format with * operator
        if 'energy' in normalized and normalized['energy']:
            energy_str = normalized['energy']
            # Convert "1 GeV" to "1*GeV" format for Geant4
            if ' ' in energy_str and '*' not in energy_str:
                parts = energy_str.strip().split()
                if len(parts) == 2:
                    normalized['energy'] = f"{parts[0]}*{parts[1]}"
        
        return normalized
    
    # Test 2a: Empty commands get defaults
    result = normalize_gps_commands({})
    
    if result.get('particle') != 'gamma':
        print(f"FAIL: Expected default particle='gamma', got '{result.get('particle')}'")
        return False
    
    if result.get('ang/type') != 'Direction':
        print(f"FAIL: Expected default ang/type='Direction', got '{result.get('ang/type')}'")
        return False
    
    print(f"PASS: Defaults applied - particle='{result.get('particle')}', ang/type='{result.get('ang/type')}'")
    
    # Test 2b: Energy format conversion
    test_cases = [
        ({'energy': '1 GeV'}, '1*GeV'),
        ({'energy': '100 keV'}, '100*keV'),
        ({'energy': '511 keV'}, '511*keV'),
        ({'energy': '10 MeV'}, '10*MeV'),
    ]
    
    for input_cmds, expected_energy in test_cases:
        result = normalize_gps_commands(input_cmds)
        actual_energy = result.get('energy', '')
        if actual_energy != expected_energy:
            print(f"FAIL: Expected '{expected_energy}', got '{actual_energy}'")
            return False
        print(f"PASS: Energy '{input_cmds['energy']}' -> '{actual_energy}'")
    
    # Test 2c: Already correct format preserved
    result = normalize_gps_commands({'energy': '511*keV'})
    if result.get('energy') != '511*keV':
        print(f"FAIL: Expected '511*keV' to be preserved, got '{result.get('energy')}'")
        return False
    print(f"PASS: Correct format preserved - energy='{result.get('energy')}'")
    
    # Test 2d: Explicit values preserved
    explicit_cmds = {
        'particle': 'electron',
        'energy': '511*keV',
        'ang/type': 'Isotropic',
        'pos/type': 'Point'
    }
    result = normalize_gps_commands(explicit_cmds)
    
    checks = [
        ('particle', 'electron'),
        ('energy', '511*keV'),
        ('ang/type', 'Isotropic'),
        ('pos/type', 'Point'),
    ]
    
    for key, expected in checks:
        actual = result.get(key, '')
        if actual != expected:
            print(f"FAIL: Expected {key}='{expected}', got '{actual}'")
            return False
    
    print(f"PASS: Explicit values preserved")
    
    # Test 2e: Dict format conversion (also gets normalized to * format)
    dict_format = {
        'energy': {'value': 100, 'unit': 'keV'}
    }
    result = normalize_gps_commands(dict_format)
    if result.get('energy') != '100*keV':
        print(f"FAIL: Expected '100*keV' from dict, got '{result.get('energy')}'")
        return False
    print(f"PASS: Dict format converted and normalized - energy='{result.get('energy')}'")
    
    return True


def test_material_from_dict_nist_detection():
    """Test Material.from_dict auto-detects NIST materials."""
    print("\n=== Test 3: NIST Material Auto-Detection ===")
    
    # Test various NIST material names
    nist_names = [
        'G4_WATER',
        'G4_AIR',
        'G4_PLASTIC_SCINTILLATOR',
        'G4_GALLEX_LSC',
        'G4_Al',
        'G4_Pb',
    ]
    
    for name in nist_names:
        mat_dict = {
            'name': name,
            'Z_expr': '',
            'A_expr': '',
            'density_expr': '',
            'components': None
        }
        
        mat = Material.from_dict(mat_dict)
        if mat.mat_type != 'nist':
            print(f"FAIL: {name} should be detected as NIST, got '{mat.mat_type}'")
            return False
        
        print(f"PASS: {name} detected as NIST material")
    
    # Test that non-NIST names are not auto-detected
    std_dict = {
        'name': 'custom_material',
        'Z_expr': '6',
        'A_expr': '12',
        'density_expr': '1.5',
        'components': None
    }
    
    std_mat = Material.from_dict(std_dict)
    if std_mat.mat_type != 'standard':
        print(f"FAIL: custom_material should be 'standard', got '{std_mat.mat_type}'")
        return False
    
    print(f"PASS: custom_material correctly set as 'standard'")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("AI Assistant Fixes - Headless Tests")
    print("="*60)
    
    tests = [
        ("NIST Material Creation", test_nist_material_creation),
        ("GPS Command Normalization", test_gps_command_normalization),
        ("NIST Material Auto-Detection", test_material_from_dict_nist_detection),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\nERROR in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
