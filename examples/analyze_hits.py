import h5py
import numpy as np
import matplotlib.pyplot as plt
import sys
import os

def analyze_output(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return

    print(f"Analyzing {file_path}...")
    
    with h5py.File(file_path, 'r') as f:
        # Check for Hits ntuple
        if 'default_ntuples/Hits' not in f:
             print("Error: 'Hits' ntuple not found in the HDF5 file.")
             return
        
        hits_group = f['default_ntuples/Hits']
        
        # Determine number of valid entries
        num_entries = None
        if 'entries' in hits_group:
            ent_dset = hits_group['entries']
            num_entries = int(ent_dset[0]) if ent_dset.shape != () else int(ent_dset[()])
        
        def get_col(name):
            if name in hits_group:
                dset = hits_group[name]
                if isinstance(dset, h5py.Group) and 'pages' in dset:
                    data = dset['pages'][:]
                elif isinstance(dset, h5py.Dataset):
                    data = dset[:]
                else:
                    return np.array([])
                return data[:num_entries] if num_entries is not None else data
            return np.array([])

        # Extract data
        edep = get_col('Edep')
        pos_x = get_col('PosX')
        pos_y = get_col('PosY')
        particle_names = get_col('ParticleName')

        if len(edep) == 0:
            print("No hits found in the simulation.")
            return

        print(f"Total Hits: {len(edep)}")

        # Create plots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        # 1. Energy Spectrum
        ax1.hist(edep, bins=100, color='skyblue', edgecolor='black')
        ax1.set_title('Energy Deposition Spectrum')
        ax1.set_xlabel('Energy (MeV)')
        ax1.set_ylabel('Counts')
        ax1.grid(alpha=0.3)

        # 2. Hit Position Heatmap (XY)
        h = ax2.hist2d(pos_x, pos_y, bins=50, cmap='viridis')
        ax2.set_title('Hit Distribution (XY Plane)')
        ax2.set_xlabel('X (mm)')
        ax2.set_ylabel('Y (mm)')
        fig.colorbar(h[3], ax=ax2, label='Hits')

        plt.tight_layout()
        output_plot = "simulation_analysis.png"
        plt.savefig(output_plot)
        print(f"Analysis complete. Plot saved to {output_plot}")
        plt.show()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_hits.py <path_to_hdf5_file>")
    else:
        analyze_output(sys.argv[1])
