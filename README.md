# Satellite image processing using Data Fabric & AI

## Installation

<!-- ### Serve LLM locally (skip if you plan to use the PCAI model)

#### Install packages -->

<!-- `brew install llama.cpp`


#### Run Server

`./llama-server -hf google/gemma-3-4b-it-qat-q4_0-gguf:Q4_0`

#### Test

`curl -X POST "http://localhost:8080/v1/completions" \
	-H "Content-Type: application/json" \
	--data '{
		"model": "google/gemma-3-4b-it-qat-q4_0-gguf:Q4_0",
		"prompt": "Once upon a time,",
		"max_tokens": 512,
		"temperature": 0.5
	}'
` -->


## Configure the sandbox container

- Start the sandbox container

`docker run -d --name mapr --privileged -p 8443:8443 -p 8501:8501 -p 8502:8502 -p 9000:9000 -p 2222:22 -e clusterName=maprdemo.io -e isSecure -e MAPR_TZ=Europe/London --hostname maprdemo.io maprtech/dev-sandbox-container`

- Login to the container

`docker exec -it mapr bash`

### Install git

`apt update && apt install -y git python3-dev gcc`

*TIP* Save git credentials: `git config --global credentials.helper store`

### Clone the repository

`git clone https://github.com/erdincka/satellite.git`


### Navigate to the project directory

`cd satellite`


### Create and Activate venv

`curl -LsSf https://astral.sh/uv/install.sh | sh; source ~/.bashrc`

`uv venv .venv && source .venv/bin/activate`


### Install dependencies

<!-- `pip install -r requirements.txt` -->
`uv pip install -r requirements.txt`

#### Build and install mapr-streams client

`CFLAGS=-I/opt/mapr/include LDFLAGS=-L/opt/mapr/lib uv pip install mapr-streams-python`

### Extract images if using offline files

`mkdir -p images; tar -xf ./downloaded_images.tar -C images/`


### Login with your credentials (or use your own user & password)

`echo mapr | maprlogin password -user mapr`


<!-- ### Enable and mount NFS

```bash
mkdir -p /mapr
mount -t nfs -o nolock,hard localhost:/mapr /mapr
``` -->


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
maprcli stream replica autosetup -path /apps/satellite/hq_stream -replica /apps/satellite/edge/edge_stream -multimaster true
sudo chown $(id -un):$(id -gn) -R /mapr/${CLUSTER_NAME}/apps/satellite/
```


### Run the application

You need two terminal sessions to run the application. One for the HQ and one for the edge.

`LD_LIBRARY_PATH=/opt/mapr/lib streamlit run hq.py`

and

`LD_LIBRARY_PATH=/opt/mapr/lib streamlit run edge.py`


## TODO

A lot

- Point to remote (PCAI) LLM

- Set up and reset of demo volumes and streams

- Containerize the whole demo app

- Allow using external DF cluster(s)


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
