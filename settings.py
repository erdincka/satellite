import socket

def get_cluster_name():
    with open("/opt/mapr/conf/mapr-clusters.conf", "r") as f:
        line = f.readline().strip('\n')
        cluster_name = line.split(" ")[0]
        return cluster_name

# MY_IP = whatismyip()
MY_HOSTNAME = socket.gethostname()
REST_URL = f"https://{MY_HOSTNAME}:8443/rest"
MAPR_USER = "mapr"
MAPR_PASSWORD = "mapr"
MAPR_CLUSTER = get_cluster_name()

HQ_VOLUME = "/apps/satellite"
HQ_STREAM = f"{HQ_VOLUME}/hq_stream"
HQ_ASSETS = f"{HQ_VOLUME}/assets"
EDGE_VOLUME = "/apps/satellite/edge"
EDGE_STREAM = f"{EDGE_VOLUME}/edge_stream"
EDGE_ASSETS = f"{EDGE_VOLUME}/assets"
EDGE_MIRROR_NAME = "edge_assets"
EDGE_REPLICATED_VOLUME = f"{HQ_VOLUME}/edge_replicated"

PIPELINE = "pipeline"
ASSET_TOPIC = "assets"
REQUEST_TOPIC = "requests"

MAPR_MOUNT = f"/mapr/{MAPR_CLUSTER}"
