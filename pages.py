import time
import json
import logging
import os
import random
from typing import Callable
import streamlit as st
import services
import settings
import utils

logger = logging.getLogger(__name__)


@st.dialog("Asset Viewer", width='large')
def asset_viewer(asset: dict):
    logger.info("Opening asset viewer for %s", asset['title'])

    st.image(asset['preview'], caption=asset['title'])
    st.text(f"Description: {asset['description']}")
    st.text(f"Keywords: {asset.get('keywords', None)}")
    if "analysis" in asset:
        st.text(f"Category: {asset.get('analysis', None)}")
    if "object" in asset:
        st.text(f"Detected: {asset.get('object', None)}")
        st.chat_input(key="question", placeholder="Ask a question...", on_submit=questions_to_image, args=(asset["preview"].split('/')[-1], asset["description"],))
        st.session_state["ai_response"] = st.chat_message("ai")


@st.cache_data(ttl=60)
def get_item_display_time(item):
    """Returns the remaining display time for an item."""
    now = time.time()
    created_at = item.get("created_at", now) # use now if no created_at
    remaining_time = max(0, 20 - (now - created_at)) # 20 seconds
    return remaining_time

@st.fragment
def image_tiles(items: list, source: str, wait_message: str = "Loading tiles...", columns: int = 4):
    """Displays a list of items in a grid layout."""
    index = 0
    item_containers = {}  # Dictionary to store containers for each item
    logger.info("Got %s items to display", len(items))

    with st.spinner(wait_message, show_time=True):
        grid = st.columns(columns)
        for item in utils.last_five(items):
            if isinstance(item, str):
                item = json.loads(item)
            item['created_at'] = time.time()  # record creation time
            with grid[index % len(grid)].container(border=True):
                # st.subheader(source, divider=True, anchor=False)
                st.button(label=source.upper(), on_click=asset_viewer, args=(item,), key=f"{source}_{index}", type='tertiary')
                # st.image(item['preview'] if 'preview' in item else [], caption=item['title'], width=180)
                # st.text(f"Category: {item['analysis']}")
                st.text(f"Description: {item['description'][:20]}{'...' if len(item['description']) > 20 else ''}", help=item['description'])
                st.text(f"Keywords: {item.get('keywords', '')[:20]}{'...' if len(item['keywords']) > 20 else ''}", help=item.get('keywords', None))
                if "object" in item:
                    st.text(f"Detected: {item['object']}")
                item_containers[index] = st.empty()  # create an empty container
                index += 1

    # Update the display periodically
    for index, container in item_containers.items():
        item = next((item for item in items if item.get('index', -1) == index), None)
        if item is None:
            continue

        remaining_time = get_item_display_time(item)
        if remaining_time > 0:
            container.write(f"Remaining time: {int(remaining_time)} seconds")
        else:
            container.empty()  # remove the item

@st.fragment
def message_tiles(generator: Callable, source: str, wait_message: str = "Loading tiles...", limit: int = 5, columns: int = 5):
    index = 0
    with st.spinner(wait_message, show_time=True):
        grid = st.columns(columns)
        for item in generator() if limit == 0 else generator()[:-limit]:
            with grid[index%len(grid)].container(border=True):
                # st.subheader(source, divider=True, anchor=False)
                st.button(label=source.upper(), on_click=asset_viewer, args=(item,), key=f"{source}_{index}", type='tertiary')
                "---"
                st.text(item['title'][:20], help=item['title'])
                st.text(f"Category: {item['analysis']}")
                st.text(f"Description: {item['description'][:20]}{'...' if len(item['description']) > 20 else ''}", help=item['description'])
                st.text(f"Keywords: {item.get('keywords', '')[:20]}{'...' if len(item['keywords']) > 20 else ''}", help=item.get('keywords', None))
                if "object" in item:
                    st.text(f"Detected: {item['object']}")
                # st.button(label="", icon=":material/open_in_new:", on_click=asset_viewer, args=(item,), key=f"{source}_{index}")
                index += 1


@st.dialog(title="Demo flow", width="large")
def hq_diagram():
    st.image("./app_light.png") # TODO: when st delivers runtime theme detection, use that to pick the right image


@st.fragment
def hq_actionbar():
    # Connectivity status
    utils.stream_replication_status(settings.HQ_STREAM)
    cols = st.columns(3)
    cols[0].toggle("Live", key="isLive", help="Toggle live data fetching from NASA")
    cols[1].write(f"Connected: {':white_check_mark:'if st.session_state.get('stream_replication', False) else ':exclamation:'}")
    cols[2].write(f"Mounted: {':white_check_mark:' if os.path.exists(settings.MAPR_MOUNT) else ':exclamation:'}")


@st.fragment
def hq_broadcaster():
    # Publish some messages to the pipeline
    # st.button("Broadcast some messages to start the flow", on_click=services.publish_to_pipeline, type='primary', icon='📡')
    services.publish_to_pipeline(random.randint(1,10))

    # Process and broadcast messages in pipeline
    # image_tiles(generator=services.pipeline_to_broadcast, source='Broadcast', wait_message="Publishing assets...", columns=4, limit=0)
    for _ in services.pipeline_to_broadcast(): pass # no need for the returning items
    # st.write("HQ PROCESS TOPICS")
    # st.write("Pipeline")
    # st.dataframe(st.session_state["pipeline_success"][::-1])
    # st.write("Download")
    # st.dataframe(st.session_state["download_success"][::-1])
    # st.write("Broadcast")
    # st.dataframe(st.session_state["broadcast_success"][::-1])

    # image_tiles(generator=lambda: [b for b in st.session_state['broadcast_success']], source='Broadcast', wait_message="Publishing assets...", columns=4, limit=0)


@st.fragment
def hq_responder():
    for item in services.request_listener():
        st.success(f"Responded to: {item['title']}")
    # image_tiles(generator=services.request_listener, source="Asset Request", wait_message="Checking for requests...", columns=4, limit=0)


@st.fragment
def edge_actionbar():
    row = st.columns(4)
    utils.stream_replication_status(settings.EDGE_STREAM)
    row[0].toggle("Stream replication", key="stream_replication", help="Enable or disable stream replication", on_change=utils.toggle_stream_replication, args=(False,))
    # row[1].write(f"Volume Mirror: {':white_check_mark' if st.session_state.get('volume_mirror', False) else ':exclamation:'}")
    row[2].write(f"Mount Status: {':white_check_mark:' if os.path.exists(settings.MAPR_MOUNT) else ':exclamation:'}")
    row[3].button("Mirror files", on_click=utils.start_volume_mirror, icon=":material/download:")


@st.fragment(run_every=30)
def edge_listen_for_responses():
    for item in services.response_listener():
        st.success(f"Reply received: {item['title']}")
    # image_tiles(generator=services.response_listener, source="Asset Response", wait_message="Checking for responses...", columns=5, limit=0)


def edge_asset_viewer():
    view_assets = st.session_state["view_assets"]["selection"]["rows"]
    if len(view_assets) == 0: # no selection
        return
    asset = st.session_state["response_success"][view_assets[0]]
    logger.info("Object detection in: %s", asset['preview'].split('/')[-1])
    asset["object"] = utils.ai_detect_objects(filename=asset["preview"].split('/')[-1])
    logger.info("Detected: %s", asset["object"])
    asset_viewer(asset)


@st.fragment
def edge_completed():
    st.dataframe(st.session_state["response_success"],
        selection_mode="single-row",
        on_select=edge_asset_viewer,
        key="view_assets"
    )


@st.fragment(run_every=30)
def edge_listen_for_assets():
    # message_tiles(generator=services.asset_listener, source="Broadcast", wait_message="Listening for assets...", columns=5, limit=0)
    with st.spinner("Listening for assets...", show_time=True):
        for asset in services.asset_listener():
            st.toast(f"Received asset: {asset['title']}")


# @st.fragment
# def edge_asset_list():
#     root = f"{settings.MAPR_MOUNT}/{settings.EDGE_ASSETS}"
#     logger.info("Listing files in %s", root)
#     files = []
#     for file in os.listdir(root):
#         logger.info(file)
#         files.append(file)
#     st.session_state["edge_asset_files"] = files
#     st.dataframe(st.session_state["edge_asset_files"])


@st.fragment
def edge_requester():
    st.dataframe([
        {
            'Status': a['status'] if 'status' in a else 'broadcast',
            'Title': a['title'].title(),
            'Description': a['description'],
            'Category': a['analysis'] if 'analysis' in a else 'Not analyzed',
        } for a in st.session_state["asset_broadcast"] ],
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="selected_assets",
        height=200
    )

    # st.dataframe(st.session_state["selected_assets"])
    for asset in services.asset_request():
        st.toast("Asset requested: {}".format(asset['title']))


@st.fragment
def statusbar(services: list):
    cols = st.columns(len(services))
    for index, service in enumerate(services):
        cols[index].metric(service.title(), len(st.session_state.get(f"{service}_success", [])), delta=-len(st.session_state.get(f"{service}_fail", 0)))


def questions_to_image(filename: str, description: str):
    response = utils.ask_question(filename, description)
    logger.info("AI response: %s", response)
    st.session_state["ai_response"].write(response if response else "No response")
