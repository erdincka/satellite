#!/usr/bin/env bash

[ -d images ] || (mkdir images && tar -xf ./downloaded_images.tar -C images/)
CLUSTER_NAME=$(cat /opt/mapr/conf/mapr-clusters.conf | head -n 1 | awk '{print $1}')
echo "Cluster Name: ${CLUSTER_NAME}"
maprcli volume create -path /apps/satellite -name satellite
maprcli volume create -path /apps/satellite/assets -name hq_assets
maprcli volume create -path /apps/satellite/edge -name edge
maprcli volume create -path /apps/satellite/edge_replicated -name edge_replicated
maprcli volume create -path /apps/satellite/edge/assets -name edge_assets -type mirror -source edge_replicated@${CLUSTER_NAME}
maprcli stream create -path /apps/satellite/hq_stream -produceperm p -consumeperm p -topicperm p
maprcli stream replica autosetup -path /apps/satellite/hq_stream -replica /apps/satellite/edge/edge_stream -multimaster true
