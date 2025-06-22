#!/usr/bin/env bash

sed -i '1,/This container IP/!d' /usr/bin/init-script # remove the while loop at the end
/usr/bin/init-script
echo "System initialized, starting demo app..."

LD_LIBRARY_PATH=/opt/mapr/lib nohup /root/.local/bin/uv run hq.py &

LD_LIBRARY_PATH=/opt/mapr/lib nohup /root/.local/bin/uv run edge.py &

[ -f nohup.out ] && tail -f nohup.out # so docker logs will show logs

sleep infinity # just in case, keep container running
