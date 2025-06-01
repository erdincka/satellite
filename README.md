# Satellite image processing using Data Fabric & AI

## Installation

## Configure the sandbox container

- Download the docker-compose.yaml file

`curl -o docker-compose.yaml https://raw.githubusercontent.com/erdincka/satellite/main/docker-compose.yaml`


- Start the sandbox container

`docker compose up -d`


### Wait for container to be ready

Run `docker logs -f satellite`

Watch for output like `This container IP : 172.x.0.2`

This may take around ~30 minutes.

#### Fix init script

Wait for CLDB to be ready. Wait for "after cldb (DATE)" to appear in the logs.

Create the ticket for authtication.

`docker exec -it satellite bash -c "echo mapr | maprlogin password -user mapr"`

## Start the application

For the HQ: `docker exec -it satellite bash -c "LD_LIBRARY_PATH=/opt/mapr/lib ~/.local/bin/uv run hq.py"`
For the Edge: `docker exec -it satellite bash -c "LD_LIBRARY_PATH=/opt/mapr/lib ~/.local/bin/uv run edge.py"`


```bash
CLUSTER_NAME=$(cat /opt/mapr/conf/mapr-clusters.conf | head -n 1 | awk '{print $1}')
echo "Cluster Name: ${CLUSTER_NAME}"
maprcli volume create -path /apps/satellite -name satellite
maprcli volume create -path /apps/satellite/assets -name hq_assets
maprcli volume create -path /apps/satellite/edge -name edge
maprcli volume create -path /apps/satellite/edge_replicated -name edge_replicated
maprcli volume create -path /apps/satellite/edge/assets -name edge_assets -type mirror -source edge_replicated@${CLUSTER_NAME}
maprcli stream create -path /apps/satellite/hq_stream -produceperm p -consumeperm p -topicperm p
maprcli stream replica autosetup -path /apps/satellite/hq_stream -replica /apps/satellite/edge/edge_stream -multimaster true
mount -t nfs -o nolock,hard localhost:/mapr /mapr
# sudo chown $(id -un):$(id -gn) -R /mapr/${CLUSTER_NAME}/apps/satellite/
```


### Run the application

You need two terminal sessions to run the application. One for the HQ and one for the edge.

`LD_LIBRARY_PATH=/opt/mapr/lib uv run hq.py`

and

`LD_LIBRARY_PATH=/opt/mapr/lib uv run edge.py`


## TODO

A lot

[ ] Point to remote (PCAI) LLM

[ ] UI to set up and reset of demo volumes and streams

[X] Containerize the whole demo app

[ ] Allow using external DF cluster(s)


## NOTES

### Configure and mount NFSv4 (only if using NFSv4)

Edit nfs4server.conf and change krb5 to sys:

`sudo nano /opt/mapr/conf/nfs4server.conf`

Go to line `SecType = krb5;` and change it to `SecType = sys;`

Restart the NFSv4 server:

`maprcli node services -nodes `hostname -f` -nfs4 restart`

`sudo mount -t nfs4 -o proto=tcp,nolock,sec=sys localhost:/mapr /mapr`



## RESET

```bash
maprcli stream delete -path /apps/satellite/edge/edge_stream
maprcli stream delete -path /apps/satellite/hq_stream
maprcli volume remove -name edge_replicated -force true
maprcli volume remove -name edge_assets -force true
maprcli volume remove -name edge -force true
maprcli volume remove -name hq_assets -force true
maprcli volume remove -name satellite -force true
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request with your changes.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
