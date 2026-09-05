#!/usr/bin/env bash
#
# Start the demo.
#
# Deliberately hard to kill: the interface must come up even with no cluster configured,
# an unreachable cluster, or a missing truststore, because the operator configures the
# cluster *in the interface* and cannot do that if the container is crash-looping. Every
# cluster-dependent step is best-effort here and re-runnable at runtime from
# backend/clientsetup.py, which is what handles a cluster entered later.
#
# Nothing below uses `set -e`. An earlier version did, and a single failed curl during
# cluster-name discovery killed the container before it printed anything — a silent
# restart loop with no diagnostic, which is the worst way for a demo to fail.

set -uo pipefail

HQ_HOST="${HQ_HOST:-}"
HQ_USER="${HQ_USER:-mapr}"
HQ_PASSWORD="${HQ_PASSWORD:-mapr}"
EDGE_HOST="${EDGE_HOST:-}"

# The truststore can arrive as an environment variable, which works whether the Docker
# context is local or a remote host, or as a bind mount.
if [[ ! -s /opt/mapr/conf/ssl_truststore && -n "${MAPR_TRUSTSTORE_B64:-}" ]]; then
  if echo "${MAPR_TRUSTSTORE_B64}" | base64 -d > /opt/mapr/conf/ssl_truststore 2>/dev/null; then
    echo "Installed the cluster truststore from MAPR_TRUSTSTORE_B64"
  else
    echo "WARNING: MAPR_TRUSTSTORE_B64 is not valid base64; ignoring it." >&2
    rm -f /opt/mapr/conf/ssl_truststore
  fi
fi

if [[ -z "$HQ_HOST" ]]; then
  echo "No cluster configured. Starting the interface so you can set one up there."
else
  echo "Preparing the Data Fabric client for ${HQ_HOST}..."

  # Ask the cluster its own name; configure.sh otherwise writes "my.cluster.com", and
  # the name is what stream replica paths are qualified with. Best-effort: if the
  # cluster is unreachable this falls back and the interface still starts.
  CLUSTER_NAME="${HQ_CLUSTER_NAME:-}"
  if [[ -z "$CLUSTER_NAME" ]]; then
    CLUSTER_NAME=$(curl -sk -m 15 -u "${HQ_USER}:${HQ_PASSWORD}" \
      "https://${HQ_HOST}:${HQ_REST_PORT:-8443}/rest/dashboard/info" 2>/dev/null \
      | sed -n 's/.*"cluster":{"name":"\([^"]*\)".*/\1/p') || true
  fi

  if [[ -z "$CLUSTER_NAME" ]]; then
    echo "WARNING: could not reach ${HQ_HOST}:${HQ_REST_PORT:-8443} to read the cluster" >&2
    echo "         name. The interface will start; fix the connection there." >&2
  else
    # Pin the address: a slow container resolver costs seconds on every cluster call,
    # and pinning here keeps hostnames matching the cluster's TLS certificate.
    for host in "$HQ_HOST" "$EDGE_HOST"; do
      [[ -n "$host" ]] || continue
      grep -q " ${host}\$" /etc/hosts && continue
      ip=$(getent hosts "$host" | awk '{print $1; exit}') || true
      [[ -n "${ip:-}" ]] && echo "${ip} ${host}" >> /etc/hosts && echo "Pinned ${host} to ${ip}"
    done

    /opt/mapr/server/configure.sh -N "${CLUSTER_NAME}" -c \
        -C "${HQ_HOST}:${HQ_CLDB_PORT:-7222}" -Z "${HQ_HOST}:${HQ_ZK_PORT:-5181}" -secure \
        >/tmp/configure.log 2>&1 \
      && echo "Client configured for cluster ${CLUSTER_NAME}" \
      || echo "WARNING: configure.sh failed; see /tmp/configure.log" >&2

    if [[ -s /opt/mapr/conf/ssl_truststore ]]; then
      if echo "${HQ_PASSWORD}" | /opt/mapr/bin/maprlogin password -user "${HQ_USER}" \
           >/tmp/maprlogin.log 2>&1; then
        echo "Ticket obtained for ${HQ_USER}"
      else
        echo "WARNING: maprlogin failed — streams will not work until it succeeds:" >&2
        tail -2 /tmp/maprlogin.log >&2
      fi
    else
      echo "WARNING: no /opt/mapr/conf/ssl_truststore. A secure cluster cannot" >&2
      echo "         authenticate without it — set MAPR_TRUSTSTORE_B64 or bind-mount it." >&2
    fi

    # Imagery lives on Data Fabric volumes, reached over NFS. Needs CAP_SYS_ADMIN.
    mkdir -p /mapr
    if mountpoint -q /mapr; then
      echo "/mapr already mounted"
    elif mount -t nfs -o nolock,vers=3,soft,timeo=50,retrans=2 \
           "${HQ_HOST}:/mapr" /mapr 2>/tmp/mount.err; then
      echo "Mounted ${HQ_HOST}:/mapr at /mapr"
    else
      echo "WARNING: could not mount ${HQ_HOST}:/mapr — $(cat /tmp/mount.err)" >&2
      echo "         Imagery needs this. Run with --cap-add SYS_ADMIN and make sure the" >&2
      echo "         cluster's NFS service is reachable on 2049." >&2
    fi
  fi
fi

export MAPR_MOUNT_HQ="${MAPR_MOUNT_HQ:-/mapr}"
export MAPR_MOUNT_EDGE="${MAPR_MOUNT_EDGE:-/mapr}"

# Run from inside backend/ so its modules import each other by plain name, which keeps
# them equally runnable outside the container during development.
cd /app/backend
exec python -m uvicorn main:app \
    --host "${BIND_HOST:-0.0.0.0}" --port 8080 \
    --no-access-log --log-level info
