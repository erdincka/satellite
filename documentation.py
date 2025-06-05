import inspect
from nicegui import app, ui

import services
import settings
from utils import run_command_with_dialog
import utils

DEMO = {
    "name": "core to edge",
    "description": "With this demo, we will use Data Fabric to enable our microservice-architecture app to process end to end pipeline across multiple locations.",
    "image": "core-edge.png",
    "link": "https://github.com/erdincka/missionx"
}

INTRO = """
HQ acts as the hub for information flow in this scenario. It is where the data is collected from various sources (we simulate IMAGE feed),
processed and distributed to various targets, including the field teams working at the edge, as actionable intelligence.
Microservice status for Headquarters are shown above.
You can pause/resume them on clicking their icon. The numbers indicate the processed items for each service.
We are going to start and explain each service in the following steps.
"""

FLOW = {
    'HQ': [
        {
            "title": "Data Ingestion Service",
            "description": """
We start by generating sample data mocking RSS feed from NASA Image API.
We are using pre-recorded images from 2014, but we can also get them in real-time using the relevant NASA API calls.
For each message we recieve, we will create a record in the JSON Table and
send a message to the pipeline to inform the next service, Image Download, so it can process the message content.
""",
            "code": utils.nasa_feed,
        },
        {
            "title": "Data Processing (ETL) Service",
            "description": """
With each message in the pipeline, we will get a link to download the asset. We will download this asset,
and save the image in a volume, while updating the location of the asset in the database.
""",
            "code": services.publish_to_pipeline,
        },
        {
            "title": "Broadcast Service",
            "description": "Now we are ready to know all the field teams that we have new intelligence. We send a message to Asset Broadcast topic, so any/all subscribers can see relevant metadata for that asset.",
            "code": services.pipeline_to_broadcast,
        },
        {
            "title": "Request Listener",
            "description": "We broadcast the assets we've got from the feed. Now we are ready to serve the assets for any field team if they request it. For that, we have a listener service that monitors the topic ASSET_REQUEST for any request from the field.",
            "code": services.request_listener,
        },
    ],
    'EDGE': [
        {
            "title": "Upstream Comm",
            "description": "Monitor upstream connectivity and data replication status",
            "code": utils.stream_replication_status,
        },
        {
            "title": "Broadcast Listener",
            "description": "We will subscribe to the ASSET_BROADCAST topic so we can be notified of incoming new assets.",
            "code": services.asset_listener,
        },
        {
            "title": "Asset Request",
            "description": """Any assets requested by clicking on the asset data will be put into ASSET_REQUEST topic,
            so HQ can process and send the asset through the replicated volume.""",
            "code": services.asset_request,
        },
        {
            "title": "Asset Viewer",
            "description": """We will periodically check the volume where the requested assets are copied. Once the asset is ready, it will be
            displayed in a tile on the Dashboard.""",
            "code": services.response_listener,
        },
    ]
}


def help_page():
    with ui.expansion(
        settings.TITLE,
        icon="info",
        caption="Core to Edge end to end pipeline processing using Ezmeral Data Fabric",
        group="help",
    ).classes("w-full").classes("text-bold") as help:
        ui.markdown(DEMO["description"]).classes("font-normal")
        ui.image(DEMO["image"]).classes(
            "object-scale-down g-10"
        )

    ui.separator()

    # Prepare
    with ui.expansion("Demo Preparations", icon="engineering", caption="Need to create volumes and streams before demo", group="help").classes("w-full text-bold"):

        ui.label("Create the volumes and streams.")

        ui.code(open('configure-app.sh').read(), language='bash').classes("w-full")

        # ui.button("Run", on_click=laxmbda: run_command_with_dialog('./configure-app.sh'))

        ui.space()

    ui.separator()

    # Demo Flow
    with ui.expansion("Demo Flow for HQ", icon="fa-solid fa-gears", caption="Let's start the demo at the HQ Dashboard!", group="help").classes("w-full text-bold"):
        for step in FLOW['HQ']:
            ui.label(step["title"]).classes('subtitle1')
            ui.markdown(step["description"])
            ui.code(inspect.getsource(step["code"])).classes("w-full")

    ui.separator()

    with ui.expansion("Demo Flow for Edge", icon="fa-solid fa-truck-field", caption="Continue the demo at the Edge Dashboard!", group="help").classes("w-full text-bold"):
        for step in FLOW['EDGE']:
            ui.label(step["title"]).classes('subtitle1')
            ui.markdown(step["description"])
            ui.code(inspect.getsource(step["code"])).classes("w-full")

    return help

def welcome():
    with ui.dialog().props("full-width") as help, ui.card().classes("relative grow place-items-center"):
        ui.button('Close', on_click=help.close)
        help_page()

    help.on('close', help.clear)
    return ui.button(icon='help', on_click=help.open).props('unelevated round')
    