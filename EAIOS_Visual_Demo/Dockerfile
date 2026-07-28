# EAIOS demonstration — container image
#
# Read top to bottom: each instruction adds a layer, and Docker caches layers
# it has seen before. That is why the order below is deliberate rather than
# convenient.

# Pin the minor version. "python:3.12" would drift under you between builds;
# "slim" drops the compilers and docs a running app does not need — roughly
# 120MB instead of 1GB, which matters every time a cold start pulls it.
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: no .pyc files. The container is discarded, so
#   writing them is wasted work and wasted layer space.
# PYTHONUNBUFFERED: send stdout straight out rather than buffering it. Without
#   this, logs appear late or vanish entirely when a container is killed —
#   which is exactly when you need them.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ---------------------------------------------------------------------------
# Dependencies BEFORE source. This is the single most important line ordering
# in the file.
#
# Docker caches each layer and reuses it while its inputs are unchanged. If
# source were copied first, every edit to a .py file would invalidate the
# install layer and reinstall pandas, plotly and streamlit — about ninety
# seconds, every rebuild. Copying only the requirements file first means the
# install layer is reused until the dependencies themselves change, and a
# code edit rebuilds in about two seconds.
# ---------------------------------------------------------------------------
COPY requirements-runtime.txt .

# --no-cache-dir: pip's download cache is useless in an image that is never
# reused for another install, and it would ship tens of megabytes.
RUN pip install --no-cache-dir -r requirements-runtime.txt

# Now the source. This layer is invalidated by every code change, which is
# fine — it is cheap.
COPY . .

# ---------------------------------------------------------------------------
# Run as a non-root user.
#
# By default a container process is root, and a container escape then starts
# from root on the host. This costs one line and removes an entire class of
# problem. Cloud Run and GKE both prefer it, and some hardened clusters refuse
# to schedule containers that ask for root at all.
# ---------------------------------------------------------------------------
RUN useradd --create-home --uid 1000 eaios && chown -R eaios:eaios /app
USER eaios

# Documentation, not enforcement. EXPOSE records intent; it does not open
# anything. Publishing a port is a decision made at "docker run -p", and in
# Cloud Run it is made by the platform.
EXPOSE 8501

# ---------------------------------------------------------------------------
# ENTRYPOINT vs CMD
#
# ENTRYPOINT is the executable; CMD supplies default arguments that can be
# overridden at run time:
#
#     docker run eaios                      -> the demo app on 8501
#     docker run eaios app.py --server.port=9000
#
# Note what this ordering FORBIDS. Because ENTRYPOINT is fixed at
# "streamlit run", every override must be a streamlit argument — you cannot
# run a different program. That is a deliberate constraint: the image does one
# thing. To get a shell for debugging you override the entrypoint explicitly:
#
#     docker run -it --entrypoint /bin/bash eaios
#
# --server.address=0.0.0.0 is required. Streamlit binds to localhost by
# default, and localhost inside a container means the container itself — the
# port would be published and nothing would answer. This is the most common
# reason a containerised web app appears to start and then refuses every
# connection.
#
# --server.headless=true stops Streamlit trying to open a browser and to
# prompt for an email address on first run, neither of which is possible here.
# ---------------------------------------------------------------------------
ENTRYPOINT ["streamlit", "run"]
CMD ["eaios_story_app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
