# Satellite image processing using Data Fabric & AI

## Installation

### Start with these steps if you are running the sandbox container

- Start the sandbox container

`docker run -d --name mapr --privileged -p 8443:8443 -p 8501:8501 -p 8502:8502 -p 9000:9000 -p 2222:22 -e clusterName=maprdemo.io -e isSecure --hostname maprdemo.io maprtech/dev-sandbox-container`

- Login to the container

`docker exec -it mapr bash`


### Clone the repository

`git clone https://github.com/erdincka/satellite.git`


### Navigate to the project directory

`cd satellite`


### Create venv

<!-- `python3 -m venv .venv` -->
`curl -LsSf https://astral.sh/uv/install.sh | sh`

`uv venv .venv`


### Activate virtual environment

`source .venv/bin/activate`


### Install dependencies

<!-- `pip install -r requirements.txt` -->
`uv pip install -r requirements.txt`

```bash
sudo dnf install -y python3.11-devel gcc || sudo apt install -y python3-dev gcc
# pip install --global-option=build_ext --global-option="--library-dirs=/opt/mapr/lib" --global-option="--include-dirs=/opt/mapr/include/" mapr-streams-python
CFLAGS=-I/opt/mapr/include LDFLAGS=-L/opt/mapr/lib uv pip install mapr-streams-python
```

### Extract images if using offline files

`mkdir -p images; tar -xf ./downloaded_images.tar -C images/`


### Login with your credentials

`echo mapr | maprlogin password -user mapr # or use your own user & password`


### Configure and mount NFSv4 (only if using NFSv4 - default is NFSv3 for sandbox container)

Edit nfs4server.conf and change krb5 to sys:

`sudo nano /opt/mapr/conf/nfs4server.conf`

Go to line `SecType = krb5;` and change it to `SecType = sys;`

Restart the NFSv4 server:

`maprcli node services -nodes `hostname -f` -nfs4 restart`

`sudo mount -t nfs4 -o proto=tcp,nolock,sec=sys localhost:/mapr /mapr`


### Mount the volume on the host

`mount -t nfs -o nolock,soft localhost:/mapr /mapr`


### Create the volumes and streams on Data Fabric


```bash
CLUSTER_NAME=$(cat /opt/mapr/conf/mapr-clusters.conf | head -n 1 | awk '{print $1}')
echo "Cluster Name: ${CLUSTER_NAME}"
maprcli volume create -path /apps/satellite -name satellite
maprcli volume create -path /apps/satellite/assets -name hq_assets
maprcli volume create -path /apps/satellite/edge -name edge
maprcli volume create -path /apps/satellite/edge_replicated -name edge_replicated
maprcli volume create -path /apps/satellite/edge/assets -name edge_assets -type mirror -source edge_replicated@${CLUSTER_NAME}
maprcli stream create -path /apps/satellite/hq_stream -produceperm p -consumeperm p -topicperm p
# maprcli stream create -path /apps/satellite/edge/edge_stream -produceperm p -consumeperm p -topicperm p
maprcli stream replica autosetup -path /apps/satellite/hq_stream -replica /apps/satellite/edge/edge_stream -multimaster true
# provide right access to everyone, unless you are using your own user for creating the volumes
# hadoop fs -chmod 777 /apps/satellite/assets
sudo chown $(id -un):$(id -gn) -R /mapr/${CLUSTER_NAME}/apps/satellite/
```


### Run the application

`LD_LIBRARY_PATH=/opt/mapr/lib streamlit run hq.py` or `LD_LIBRARY_PATH=/opt/mapr/lib streamlit run edge.py`


## TODO

A lot

- Point to remote (PCAI) LLM


## RESET

```bash
maprcli stream delete -path /apps/satellite/edge/edge_stream
maprcli stream delete -path /apps/satellite/hq_stream
maprcli volume remove -name edge_replicated -force true
maprcli volume remove -name edge_assets -force true
maprcli volume remove -name edge -force true
maprcli volume remove -name hq_assets -force true
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request with your chang
es.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
