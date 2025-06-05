#!/usr/bin/env bash

# This script is used to clean up the mapr-fs volumes and streams

echo -n "Deleting edge_stream..."
maprcli stream delete -path /apps/satellite/edge/edge_stream
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
echo -n "Deleting hq_stream"
maprcli stream delete -path /apps/satellite/hq_stream
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
echo -n "Removing replicated volume"
maprcli volume remove -name edge_replicated -force true
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
echo -n "Removing edge volumes"
maprcli volume remove -name edge_assets -force true
maprcli volume remove -name edge -force true
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
echo -n "Removing app volumes"
maprcli volume remove -name hq_assets -force true
maprcli volume remove -name satellite -force true
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
echo -n "Deleting catalog"
rm iceberg.db
[ $? -eq 0 ] && echo 'OK' || echo 'FAILED'
