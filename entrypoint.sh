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
