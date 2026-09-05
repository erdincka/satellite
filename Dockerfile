# Satellite: one service, two Data Fabric site connections.
#
# The Data Fabric client is needed only for streams — the native client is the only way
# to address a stream you provisioned yourself. Provisioning goes over REST and assets
# over S3, so this image needs no FUSE mount and never calls maprcli.
#
# On the base image: maprtech/pacc is the obvious candidate and does not work here. Its
# newest tag carries client 8.0, which cannot complete the secure CLDB handshake against
# an 8.1 cluster, and installing 8.1 over the top leaves a broken native library state.
# Installing a matching client onto a clean base is the version you can actually run, so
# set MAPR_VERSION to whatever your cluster runs.

# ---------------------------------------------------------------- frontend build
FROM --platform=$BUILDPLATFORM node:22-alpine AS ui

WORKDIR /ui
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
# Vite writes to ../backend/static, which is /backend/static inside this stage.
RUN npm run build


# ---------------------------------------------------------------------- runtime
FROM rockylinux:9

# HPE's package repository is the default. It requires credentials, so if you build this
# image yourself either supply them or point these at a mirror you can reach:
#
#   docker build --build-arg MAPR_REPO=http://your-mirror/mapr/v8.1.0/rhel9 \
#                --build-arg MAPR_MEP_REPO=http://your-mirror/mapr/MEP/MEP-10.1.0/redhat .
#
# Match MAPR_REPO to your cluster's version: a client older than the cluster cannot
# authenticate to it.
ARG MAPR_REPO=https://package.ezmeral.hpe.com/releases/v8.1.0/redhat
ARG MAPR_MEP_REPO=https://package.ezmeral.hpe.com/releases/MEP/MEP-10.1.0/redhat

ENV LD_LIBRARY_PATH=/opt/mapr/lib \
    CFLAGS=-I/opt/mapr/include \
    LDFLAGS=-L/opt/mapr/lib \
    JAVA_HOME=/usr/lib/jvm/jre-11 \
    PATH=/app/.venv/bin:/root/.local/bin:/opt/mapr/bin:$PATH \
    PYTHONUNBUFFERED=1

# compat-openssl11: the Data Fabric librdkafka links against OpenSSL 1.1 while Rocky 9
# ships OpenSSL 3, so importing the streams client fails on libssl.so.1.1 without it.
RUN dnf install -y --setopt=tsflags=nodocs \
        gcc gcc-c++ make openssl nfs-utils openssh-clients sshpass \
        java-11-openjdk-headless compat-openssl11 \
        findutils procps-ng \
    && dnf clean all

# mapr-client pulls mapr-hadoop-util and mapr-librdkafka, which live in the MEP
# (ecosystem) repository rather than core, so both repos are needed.
RUN printf '[MapR_Core]\nname=MapR Core\nbaseurl=%s\nenabled=1\ngpgcheck=0\nprotect=1\n' \
        "$MAPR_REPO" > /etc/yum.repos.d/mapr_core.repo \
    && printf '[MapR_Ecosystem]\nname=MapR Ecosystem\nbaseurl=%s\nenabled=1\ngpgcheck=0\n' \
        "$MAPR_MEP_REPO" > /etc/yum.repos.d/mapr_ecosystem.repo \
    && dnf install -y --setopt=tsflags=nodocs mapr-client \
    && dnf clean all

# uv brings its own CPython, so the image is not tied to the base distribution's.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app

COPY backend/requirements.txt ./
RUN uv venv --python 3.12 /app/.venv \
    && VIRTUAL_ENV=/app/.venv uv pip install --no-cache -r requirements.txt

# Installed on its own because it compiles a C extension against /opt/mapr, so a failure
# here is unambiguous. The import name is confluent_kafka — the Data Fabric client is a
# fork of it — and the assertion proves we got the Data Fabric build rather than upstream
# confluent-kafka, which would silently break stream path addressing.
RUN VIRTUAL_ENV=/app/.venv uv pip install --no-cache mapr-streams-python \
    && /app/.venv/bin/python -c "\
from importlib.metadata import version; import confluent_kafka; \
print('native streams client:', version('mapr-streams-python'))"

COPY backend/ /app/backend/
COPY images.json downloaded_images.tar entrypoint.sh ./
COPY --from=ui /backend/static /app/backend/static

RUN chmod +x /app/entrypoint.sh && mkdir -p /app/state

EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
