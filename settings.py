import logging
import socket

def get_cluster_name():
    with open("/opt/mapr/conf/mapr-clusters.conf", "r") as f:
        line = f.readline().strip('\n')
        cluster_name = line.split(" ")[0]
        return cluster_name

TITLE = "Data Fabric Core to Edge Demo"
STORAGE_SECRET = "ezmer@1r0cks"

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


# Application settings
HQ_SERVICES = ["pipeline", "download", "record", "broadcast", "request", "response"]
EDGE_SERVICES = ["receive", "request", "response"]

HQ_TILES = []
EDGE_TILES = []

BGCOLORS = {
    "pipeline": "bg-sky-300",
    "download": "bg-red-300",
    "record": "bg-emerald-300",
    "broadcast": "bg-green-300",
    "request": "bg-amber-300",
    "response": "bg-orange-300",
    "receive": "bg-lime-300",
    # "": "bg-stone-300",
}

# Configure logging

# INSECURE REQUESTS ARE OK in Lab
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# reduce logs from these
# logging.getLogger("streams_handle_rd_kafka_assign").setLevel(logging.FATAL)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

logging.getLogger("pyiceberg.io").setLevel(logging.WARNING)

logging.getLogger("mapr.ojai.storage.OJAIConnection").setLevel(logging.WARNING)
logging.getLogger("mapr.ojai.storage.OJAIDocumentStore").setLevel(logging.WARNING)
