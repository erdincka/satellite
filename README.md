# Satellite image processing using Data Fabric & AI

## Installation

### Login with your credentials

`echo mapr | maprlogin password -user mapr # or use your own user & password`

### Configure and mount NFSv4

Edit nfs4server.conf and change krb5 to sys:

`sudo nano /opt/mapr/conf/nfs4server.conf`

Go to line `SecType = krb5;` and change it to `SecType = sys;`

Restart the NFSv4 server:

`maprcli node services -nodes `hostname -f` -nfs4 restart`

`sudo mount -t nfs4 -o proto=tcp,nolock,sec=sys localhost:/mapr /mapr`


### Clone the repository in a volume

`cd /mapr/<cluster_name>/apps; git clone https://github.com/erdincka/satellite.git`

### Create volume and stream on Data Fabric

```bash
maprcli volume create -path /apps/satellite/edge -name edge
maprcli volume create -path /apps/satellite/assets -name hq_assets
maprcli volume create -path /apps/satellite/edge/assets -name edge_assets
maprcli stream create -path /apps/satellite/hq_stream -produceperm p -consumeperm p -topicperm p
maprcli stream create -path /apps/satellite/edge/edge_stream -produceperm p -consumeperm p -topicperm p
# provide right access to everyone, unless you are using your own user for creating the volumes
hadoop fs -chmod 777 /apps/satellite/assets
```

### Navigate to the project directory

`cd satellite`

### Create venv

`python3 -m venv .venv`

### Activate virtual environment

`source .venv/bin/activate`

### Install dependencies

`pip install -r requirements.txt`

```bash
sudo dnf install -y python3.11-devel gcc || sudo apt install -y python3-dev gcc
pip install --global-option=build_ext --global-option="--library-dirs=/opt/mapr/lib" --global-option="--include-dirs=/opt/mapr/include/" mapr-streams-python
```

### Extract images if using offline files

`mkdir -p images; tar -xf ./downloaded_images.tar -C images/`

### Run the application

`LD_LIBRARY_PATH=/opt/mapr/lib streamlit run hq.py` or `LD_LIBRARY_PATH=/opt/mapr/lib streamlit run edge.py`

## TODO

A lot
