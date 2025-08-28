# Use a Miniconda base image to get access to the conda package manager
FROM continuumio/miniconda3:latest

# Set the working directory inside the container
WORKDIR /app

# Copy the environment configuration and requirements files first
# This helps Docker cache layers efficiently.
COPY requirements.txt .

# Create the conda environment and install pythonocc-core and pip dependencies
# This is the most important step for your complex dependency.
RUN conda create --name virtualpet python=3.10 && \
    conda install -c conda-forge --name virtualpet --yes pythonocc-core && \
    conda run -n virtualpet pip install -r requirements.txt

# Set the entrypoint to use the conda environment
SHELL ["conda", "run", "-n", "virtualpet", "/bin/bash", "-c"]

# Copy the rest of your application code into the container
COPY . .

# Expose the port your Flask app runs on
EXPOSE 5003

# This is the simplest and most common way to do it for Conda.
# We start a bash shell, and the command (-c) is a string that first
# sources the main conda activation script, then activates our specific environment,
# and finally executes gunicorn.
CMD /bin/bash -c "source /opt/conda/etc/profile.d/conda.sh && conda activate virtualpet && gunicorn --bind 0.0.0.0:5003 --workers 1 app:app"
