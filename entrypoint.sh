#!/usr/bin/env bash
#
# Start the demo. That is all this does.
#
# Nothing here talks to a cluster. Client preparation — fetching the truststore,
# configure.sh, the ticket, the NFS mount — belongs to the application, which runs it
# when a cluster is actually configured: at startup if one is set in the environment,
# and again whenever an operator sets or changes one in the interface. A cluster that is
# unreachable, or not configured at all, must never stop the interface from coming up,
# because the interface is where the operator fixes it.
#
# An earlier version did this work here under `set -e`, and a single failed curl killed
# the container before printing anything — a silent restart loop with no diagnostic.

set -uo pipefail

export MAPR_MOUNT_HQ="${MAPR_MOUNT_HQ:-/mapr}"
export MAPR_MOUNT_EDGE="${MAPR_MOUNT_EDGE:-/mapr}"

mkdir -p /mapr /app/state

# Run from inside backend/ so its modules import each other by plain name, which keeps
# them equally runnable outside the container during development.
cd /app/backend
exec python -m uvicorn main:app \
    --host "${BIND_HOST:-0.0.0.0}" --port 8080 \
    --no-access-log --log-level info
