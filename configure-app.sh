#!/usr/bin/env bash

[ -d images ] || (mkdir images && tar -xf ./downloaded_images.tar -C images/)
CLUSTER_NAME=$(cat /opt/mapr/conf/mapr-clusters.conf | head -n 1 | awk '{print $1}')
echo "Using cluster Name: ${CLUSTER_NAME}"
echo -n "Creating app volumes..."
maprcli volume create -path /apps/satellite -name satellite
[ $? -eq 0 ] && echo -n '1/5' || echo -n '!'
maprcli volume create -path /apps/satellite/assets -name hq_assets
[ $? -eq 0 ] && echo -n '2/5' || echo -n '!'
maprcli volume create -path /apps/satellite/edge -name edge
[ $? -eq 0 ] && echo -n '3/5' || echo -n '!'
maprcli volume create -path /apps/satellite/edge_replicated -name edge_replicated
[ $? -eq 0 ] && echo -n '4/5' || echo -n '!'
maprcli volume create -path /apps/satellite/edge/assets -name edge_assets -type mirror -source edge_replicated@${CLUSTER_NAME}
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
echo -n "Creating streams..."
maprcli stream create -path /apps/satellite/hq_stream -produceperm p -consumeperm p -topicperm p
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
echo -n "Enabling stream replication..."
maprcli stream replica autosetup -path /apps/satellite/hq_stream -replica /apps/satellite/edge/edge_stream -multimaster true
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
