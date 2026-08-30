#!/usr/bin/env bash
#
# Configure the Data Fabric client for whichever cluster HQ points at, obtain a ticket,
# then serve the app.
#
# Everything here is client-side: configure.sh writes this container's own
# mapr-clusters.conf and maprlogin fetches a ticket for this container. Nothing on the
# cluster is changed.
#
# Only one client configuration is possible per container, so when HQ and the edge are
# on different clusters this configures HQ's and relies on the trust relationship
# between them. With both sites on one cluster — the common case — it is simply that
# cluster.

set -euo pipefail

HQ_HOST="${HQ_HOST:-}"
HQ_USER="${HQ_USER:-mapr}"
HQ_PASSWORD="${HQ_PASSWORD:-mapr}"
CLDB_PORT="${HQ_CLDB_PORT:-7222}"
ZK_PORT="${HQ_ZK_PORT:-5181}"

if [[ -n "$HQ_HOST" ]]; then
  # Ask the cluster its own name rather than guessing: configure.sh otherwise writes
  # "my.cluster.com", and the name is what stream replica paths are qualified with.
  CLUSTER_NAME="${HQ_CLUSTER_NAME:-$(
    curl -sk -m 15 -u "${HQ_USER}:${HQ_PASSWORD}" \
      "https://${HQ_HOST}:${HQ_REST_PORT:-8443}/rest/dashboard/info" 2>/dev/null \
      | sed -n 's/.*"cluster":{"name":"\([^"]*\)".*/\1/p'
  )}"
  CLUSTER_NAME="${CLUSTER_NAME:-df.cluster}"

  echo "Configuring Data Fabric client for ${HQ_HOST} (cluster ${CLUSTER_NAME})..."
  /opt/mapr/server/configure.sh -N "${CLUSTER_NAME}" \
      -c -C "${HQ_HOST}:${CLDB_PORT}" -Z "${HQ_HOST}:${ZK_PORT}" -secure \
      >/tmp/configure.log 2>&1 || {
    echo "configure.sh failed; see /tmp/configure.log" >&2
    tail -20 /tmp/configure.log >&2
  }

  # A secure cluster requires its own truststore, and it cannot be derived from the
  # server certificate — the CLDB handshake rejects one built that way. Copy
  # /opt/mapr/conf/ssl_truststore from any cluster node and mount it here.
  # MAPR_TRUSTSTORE_B64 is the portable way in: a bind mount refers to a path on the
  # Docker *host*, which is not where the file lives when the Docker context is remote.
  if [[ ! -s /opt/mapr/conf/ssl_truststore && -n "${MAPR_TRUSTSTORE_B64:-}" ]]; then
    echo "${MAPR_TRUSTSTORE_B64}" | base64 -d > /opt/mapr/conf/ssl_truststore \
      && echo "Installed truststore from MAPR_TRUSTSTORE_B64"
  fi
  if [[ ! -s /opt/mapr/conf/ssl_truststore ]]; then
    echo "ERROR: /opt/mapr/conf/ssl_truststore is missing." >&2
    echo "       A secure cluster will not authenticate without it. Copy it from" >&2
    echo "       /opt/mapr/conf/ssl_truststore on any cluster node, then either:" >&2
    echo "         mount it   -v /path/to/ssl_truststore:/opt/mapr/conf/ssl_truststore:ro" >&2
    echo "         or pass it MAPR_TRUSTSTORE_B64=\$(base64 -w0 ssl_truststore)" >&2
  fi

  # The ticket is what the native streams client authenticates with.
  if echo "${HQ_PASSWORD}" | /opt/mapr/bin/maprlogin password -user "${HQ_USER}" \
       >/tmp/maprlogin.log 2>&1; then
    echo "Ticket: $(/opt/mapr/bin/maprlogin print 2>/dev/null | sed -n 2p)"
  else
    echo "maprlogin failed — streams will not work until it succeeds:" >&2
    tail -5 /tmp/maprlogin.log >&2
  fi
else
  # Not fatal: the interface still starts so the operator can enter a cluster there.
  echo "HQ_HOST is not set; connect a cluster from the interface." >&2
fi

# Run from inside backend/ so its modules import each other by plain name, which keeps
# them equally runnable outside the container during development.
# Mount each cluster's NFS export so imagery can live on Data Fabric volumes and cross
# between the sites by volume mirroring. This is why the container needs CAP_SYS_ADMIN:
# mounting is a privileged operation. The MapR FUSE client would avoid NFS but does not
# work in a container — it creates the mount and exits immediately, leaving every access
# failing with "Transport endpoint is not connected".
mount_cluster() {
  local host="$1" target="$2" label="$3"
  [[ -n "$host" ]] || return 0
  mkdir -p "$target"
  if mountpoint -q "$target"; then return 0; fi
  if mount -t nfs -o nolock,vers=3,hard,timeo=100,retrans=2 "${host}:/mapr" "$target" 2>/tmp/mount.err; then
    echo "Mounted ${label} (${host}:/mapr) at ${target}"
  else
    echo "WARNING: could not mount ${label} at ${target}: $(cat /tmp/mount.err)" >&2
    echo "         imagery needs this mount; run with --cap-add SYS_ADMIN and make sure" >&2
    echo "         the cluster's NFS service is reachable on port 2049." >&2
  fi
}

mount_cluster "${HQ_HOST:-}" /mapr "HQ"
export MAPR_MOUNT_HQ=/mapr
if [[ -n "${EDGE_HOST:-}" && "${EDGE_HOST}" != "${HQ_HOST:-}" ]]; then
  mount_cluster "${EDGE_HOST}" /mapr-edge "edge"
  export MAPR_MOUNT_EDGE=/mapr-edge
else
  export MAPR_MOUNT_EDGE=/mapr
fi

# Pin each cluster's address in /etc/hosts. A container's default resolver can take
# seconds to answer, and every cluster call pays it — measured at 3.07s per REST call
# against a cluster that responds in 0.30s once connected.
for host in "${HQ_HOST:-}" "${EDGE_HOST:-}"; do
  [[ -n "$host" ]] || continue
  grep -q " ${host}\$" /etc/hosts && continue
  ip=$(getent hosts "$host" | awk '{print $1; exit}')
  if [[ -n "$ip" ]]; then
    echo "${ip} ${host}" >> /etc/hosts
    echo "Pinned ${host} to ${ip}"
  fi
done

cd /app/backend
exec python -m uvicorn main:app \
    --host "${BIND_HOST:-0.0.0.0}" --port 8080 \
    --no-access-log --log-level info
