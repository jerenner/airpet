import pytest
import h5py
import numpy as np
import os
from tempfile import NamedTemporaryFile

# We define a reusable parser function that mirrors the logic in app.py
def extract_g4_column(hits_group, name, num_entries=None):
    if name not in hits_group:
        return np.array([])
    
    node = hits_group[name]
    # Geant4's HDF5 analysis manager can store data in 'pages' under a group
    if isinstance(node, h5py.Group) and 'pages' in node:
        data = node['pages'][:]
    elif isinstance(node, h5py.Dataset):
        data = node[:]
    else:
        return np.array([])
    
    if num_entries is not None and len(data) >= num_entries:
        return data[:num_entries]
    return data

def test_hdf5_paginated_format():
    """Verifies that the parser handles Geant4's paginated HDF5 format."""
    with NamedTemporaryFile(suffix=".hdf5", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        with h5py.File(tmp_path, 'w') as f:
            hits = f.create_group("default_ntuples/Hits")
            # Create a paginated column for Energy
            edep_grp = hits.create_group("Edep")
            edep_grp.create_dataset("pages", data=np.array([0.511, 0.662, 1.173, 1.332], dtype='f4'))
            # Create a flat column for ParticleName
            hits.create_dataset("ParticleName", data=np.array([b"gamma", b"gamma", b"gamma", b"gamma"]))
            # Create the entries count
            hits.create_dataset("entries", data=np.array([4], dtype='i4'))
            
        with h5py.File(tmp_path, 'r') as f:
            hits_group = f["default_ntuples/Hits"]
            num_entries = int(hits_group["entries"][0])
            
            edep = extract_g4_column(hits_group, "Edep", num_entries)
            names = extract_g4_column(hits_group, "ParticleName", num_entries)
            
            assert len(edep) == 4
            assert np.allclose(edep, [0.511, 0.662, 1.173, 1.332])
            assert names[0] == b"gamma"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_hdf5_respects_entry_limit():
    """Verifies that the parser respects the 'entries' count even if pages are larger."""
    with NamedTemporaryFile(suffix=".hdf5", delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        with h5py.File(tmp_path, 'w') as f:
            hits = f.create_group("default_ntuples/Hits")
            # We have 10 data points in the file
            hits.create_dataset("Edep", data=np.arange(10, dtype='f4'))
            # But the simulation only finished 5 events
            hits.create_dataset("entries", data=np.array([5], dtype='i4'))
            
        with h5py.File(tmp_path, 'r') as f:
            hits_group = f["default_ntuples/Hits"]
            num_entries = int(hits_group["entries"][0])
            
            edep = extract_g4_column(hits_group, "Edep", num_entries)
            
            assert len(edep) == 5
            assert np.all(edep == [0, 1, 2, 3, 4])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_hdf5_missing_columns():
    """Verifies that the parser handles missing columns gracefully."""
    with NamedTemporaryFile(suffix=".hdf5", delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        with h5py.File(tmp_path, 'w') as f:
            f.create_group("default_ntuples/Hits")
            
        with h5py.File(tmp_path, 'r') as f:
            hits_group = f["default_ntuples/Hits"]
            data = extract_g4_column(hits_group, "NonExistent")
            assert isinstance(data, np.ndarray)
            assert len(data) == 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
