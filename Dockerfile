# Use a Miniconda base image to get access to the conda package manager
FROM jerenner/geant4-airpet-base:11.3.2

# Set the working directory inside the container
WORKDIR /app

# Copy AIRPET files (Render auto-clones the repo for build context)
COPY . .

# Create the conda environment and install pythonocc-core and pip dependencies
# This is the most important step for your complex dependency.
RUN conda create --name airpet python=3.10 && \
    conda install -c conda-forge --name airpet --yes pythonocc-core && \
    conda run -n airpet pip install -r requirements.txt

# Build custom Geant4 binary from geant4 directory
RUN mkdir geant4/build && cd geant4/build && \
    cmake .. && make -j$(nproc)

# Set the entrypoint to use the conda environment
SHELL ["conda", "run", "-n", "virtualpet", "/bin/bash", "-c"]

# Expose the port your Flask app runs on
EXPOSE 5003

# This is the simplest and most common way to do it for Conda.
# We start a bash shell, and the command (-c) is a string that first
# sources the main conda activation script, then activates our specific environment,
# and finally executes gunicorn.
CMD /bin/bash -c "source /opt/conda/etc/profile.d/conda.sh && conda activate airpet && gunicorn --bind 0.0.0.0:5003 --workers 1 --timeout 120 app:app"
